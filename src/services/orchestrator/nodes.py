"""Node implementations for interview orchestrator."""

import logging
import json
import uuid
import time
from typing import TYPE_CHECKING, Optional
from datetime import datetime
from openai import AsyncOpenAI

from src.services.sandbox_service import SandboxService, Language as SandboxLanguage
from src.services.code_metrics import get_code_metrics
from src.services.orchestrator.types import InterviewState, QuestionRecord, QuestionGeneration
from src.services.orchestrator.context_builders import (
    build_resume_context, build_conversation_context, build_job_context
)
from src.services.orchestrator.resume_exploration import (
    initialize_resume_exploration, find_unexplored_anchor, extract_topics_from_exploration
)

logger = logging.getLogger(__name__)

# Common base system prompt for all interview nodes
# All responses will be spoken aloud, so formatting is critical
COMMON_SYSTEM_PROMPT = """You are an authentic interviewer having a natural conversation. Your responses will be spoken aloud.

Core principles:
- Be authentic and genuine - not formulaic or robotic
- Be natural and conversational - not sycophantic or overly enthusiastic
- You have full context of the conversation, resume, and job requirements
- Trust your judgment and adapt to the conversation flow

Format for speech:
- Avoid colons (use periods or commas instead)
- Use commas instead of em dashes
- Write percentages as '5 percent' not '5%'
- Ensure sentences end with proper punctuation"""

if TYPE_CHECKING:
    from src.services.response_analyzer import ResponseAnalyzer
    from src.services.code_analyzer import CodeAnalyzer
    from src.services.feedback_generator import FeedbackGenerator
    from src.services.interview_logger import InterviewLogger


class NodeHandler:
    """Handler for all interview orchestrator nodes with shared dependencies."""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        response_analyzer: "ResponseAnalyzer",
        code_analyzer: "CodeAnalyzer",
        feedback_generator: "FeedbackGenerator",
        sandbox_service: SandboxService,
        interview_logger: Optional["InterviewLogger"] = None,
        is_duplicate_question=None,  # Function to check duplicate questions
    ):
        self.openai_client = openai_client
        self.response_analyzer = response_analyzer
        self.code_analyzer = code_analyzer
        self.feedback_generator = feedback_generator
        self.sandbox_service = sandbox_service
        self.interview_logger = interview_logger
        self.is_duplicate_question = is_duplicate_question

    async def initialize_node(self, state: InterviewState) -> InterviewState:
        """Initialize interview state."""
        if "conversation_history" not in state:
            state["conversation_history"] = []
        if "questions_asked" not in state:
            state["questions_asked"] = []
        if "detected_intents" not in state:
            state["detected_intents"] = []
        if "checkpoints" not in state:
            state["checkpoints"] = []
        if "sandbox" not in state:
            state["sandbox"] = {
                "is_active": False,
                "last_activity_ts": 0.0,
                "submissions": [],
                "signals": [],
                "hints_provided": [],
            }
        if "turn_count" not in state:
            state["turn_count"] = 0
        if "phase" not in state:
            state["phase"] = "intro"
        if "code_submissions" not in state:
            state["code_submissions"] = []

        state = initialize_resume_exploration(state)
        state["last_node"] = "initialize"
        state["current_question"] = None
        state["active_user_request"] = None
        state["answer_quality"] = 0.0
        return state

    async def greeting_node(self, state: InterviewState) -> InterviewState:
        """Generate personalized greeting."""
        conversation_history = state.get("conversation_history", [])
        turn_count = state.get("turn_count", 0)

        has_greeting = False
        for msg in conversation_history:
            if msg.get("role") == "assistant":
                has_greeting = True
                break

        # Allow greeting node to be called - let it decide if greeting is appropriate
        # LLM routing should handle this, but if called, generate greeting anyway
        # (It will be natural if LLM made the decision)

        state["last_node"] = "greeting"
        state["phase"] = "intro"
        resume_context = build_resume_context(state)

        prompt = f"""Generate a personalized greeting for the interview.

Resume Context:
{resume_context}

Your greeting will be spoken aloud. Welcome them warmly and personally. Reference something from their resume if relevant. You can mention they have access to a code sandbox if they want to use it. Be authentic and conversational."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": COMMON_SYSTEM_PROMPT + " Welcome the candidate genuinely and personally. Be warm.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
            )

            greeting = response.choices[0].message.content.strip()
            state["next_message"] = greeting
            state["conversation_history"].append({
                "role": "assistant",
                "content": greeting,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            default_greeting = "Hello! Welcome to your interview. I'm looking forward to learning more about your background."
            state["next_message"] = default_greeting
            state["conversation_history"].append({
                "role": "assistant",
                "content": default_greeting,
                "timestamp": datetime.utcnow().isoformat(),
            })

        return state

    async def question_node(self, state: InterviewState) -> InterviewState:
        """Generate adaptive question based on resume exploration."""
        state["last_node"] = "question"
        state["phase"] = "exploration"

        conversation_context = build_conversation_context(
            state, self.interview_logger)
        resume_context = build_resume_context(state)
        job_context = build_job_context(state)

        if self.interview_logger:
            self.interview_logger.log_context_injection("question_generation", {
                "conversation_length": len(conversation_context),
                "resume_context_length": len(resume_context),
                "turn": state.get("turn_count", 0),
                "last_node": state.get("last_node"),
            })

        anchor_id = find_unexplored_anchor(state)
        anchor_info = ""
        if anchor_id:
            anchor_data = state["resume_exploration"][anchor_id]
            anchor_info = f"""
Target Resume Anchor: {anchor_id} ({anchor_data['anchor_type']})
Already Explored Aspects: {list(anchor_data.get('aspects_covered', set()))}
Depth Score: {anchor_data.get('depth_score', 0)}
"""

        all_aspects = {"challenges", "impact", "design", "tools",
                       "team", "results", "tradeoffs", "implementation", "learning", "mistakes", "success", "collaboration"}
        if anchor_id:
            covered = state["resume_exploration"][anchor_id].get(
                "aspects_covered", set())
            available_aspects = list(all_aspects - covered)
        else:
            available_aspects = list(all_aspects)

        questions_asked = [q["text"]
                           for q in state.get("questions_asked", [])[-10:]]

        # Get user's last response for context
        last_user_response = ""
        if state.get("conversation_history"):
            for msg in reversed(state.get("conversation_history", [])):
                if msg.get("role") == "user":
                    last_user_response = msg.get("content", "")
                    break

        prompt = f"""You are conducting an interview. Generate the next question based on the full context below.

{job_context}Resume Context:
{resume_context}

{anchor_info}

Full Conversation History:
{conversation_context}

Questions Already Asked:
{chr(10).join(f"- {q}" for q in questions_asked) if questions_asked else "None yet"}

Suggested Aspects to Explore: {', '.join(available_aspects) if available_aspects else 'all'}

Your response will be spoken aloud. Generate a natural, authentic question that flows from the conversation. Be genuine and conversational - acknowledge what they've shared when it makes sense, but don't force it. Ask about something relevant to their background or what they've mentioned. Avoid repeating questions you've already asked."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=QuestionGeneration,
                messages=[
                    {
                        "role": "system",
                        "content": COMMON_SYSTEM_PROMPT + " Generate questions that are genuine, relevant, and flow naturally from the conversation. Acknowledge when it makes sense, but don't force it. Show you're listening through natural conversation.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.85,
            )

            question_text = response.question.strip()
            resume_anchor = response.resume_anchor or anchor_id
            aspect = response.aspect

            if self.is_duplicate_question and self.is_duplicate_question(question_text, resume_anchor, aspect, state):
                logger.warning(f"Duplicate question detected, regenerating...")
                question_text = "Can you tell me more about a challenging project you've worked on?"
                resume_anchor = anchor_id
                aspect = "challenges"

            question_record: QuestionRecord = {
                "id": str(uuid.uuid4()),
                "text": question_text,
                "source": "resume",
                "resume_anchor": resume_anchor,
                "aspect": aspect,
                "asked_at_turn": state["turn_count"],
            }

            state["questions_asked"] = state.get("questions_asked", [])
            state["questions_asked"].append(question_record)

            if resume_anchor and resume_anchor in state.get("resume_exploration", {}):
                state["resume_exploration"][resume_anchor]["aspects_covered"].add(
                    aspect)
                state["resume_exploration"][resume_anchor]["depth_score"] += 1
                state["resume_exploration"][resume_anchor]["last_explored_turn"] = state["turn_count"]

            state["current_question"] = question_text
            state["next_message"] = question_text
            state["conversation_history"].append({
                "role": "assistant",
                "content": question_text,
                "timestamp": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.error(f"Error generating question: {e}")
            fallback = "Can you tell me about a challenging project you've worked on?"
            state["current_question"] = fallback
            state["next_message"] = fallback
            state["conversation_history"].append({
                "role": "assistant",
                "content": fallback,
                "timestamp": datetime.utcnow().isoformat(),
            })

        return state

    async def followup_node(self, state: InterviewState) -> InterviewState:
        """Generate follow-up question or clarification."""
        state["last_node"] = "followup"
        last_question = state.get("current_question", "")
        last_answer = state.get("last_response", "")
        needs_clarification = state.pop("_needs_clarification", False)

        if needs_clarification:
            prompt = f"""The user asked for clarification on this question: "{last_question}"

Your response will be spoken aloud. Rephrase the question in a clearer, simpler way. Be natural and conversational."""
        else:
            prompt = f"""Generate a follow-up question based on the conversation context.

Previous Question: {last_question}
Candidate's Answer: {last_answer}

Full Conversation History:
{build_conversation_context(state, self.interview_logger)}

Your response will be spoken aloud. Generate a natural follow-up that builds on what they just shared. Be authentic and genuine - ask what you're genuinely curious about based on their answer. Don't force acknowledgments, but respond naturally to what they've said."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": COMMON_SYSTEM_PROMPT + " Generate follow-up questions that build naturally on what the candidate just shared. Respond naturally to their answers without forcing acknowledgments.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
            )

            followup = response.choices[0].message.content.strip()
            question_record: QuestionRecord = {
                "id": str(uuid.uuid4()),
                "text": followup,
                "source": "followup",
                "resume_anchor": None,
                "aspect": "deep_dive",
                "asked_at_turn": state["turn_count"],
            }
            state["questions_asked"] = state.get("questions_asked", [])
            state["questions_asked"].append(question_record)
            state["current_question"] = followup
            state["next_message"] = followup
            state["conversation_history"].append({
                "role": "assistant",
                "content": followup,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            fallback = "Can you provide more details about that?"
            state["current_question"] = fallback
            state["next_message"] = fallback
            state["conversation_history"].append({
                "role": "assistant",
                "content": fallback,
                "timestamp": datetime.utcnow().isoformat(),
            })

        return state

    async def transition_node(self, state: InterviewState) -> InterviewState:
        """Transition to next topic."""
        state["last_node"] = "transition"
        conversation_context = build_conversation_context(
            state, self.interview_logger)
        resume_context = build_resume_context(state)

        # Get user's last response for context
        last_user_response = ""
        if state.get("conversation_history"):
            for msg in reversed(state.get("conversation_history", [])):
                if msg.get("role") == "user":
                    last_user_response = msg.get("content", "")
                    break

        prompt = f"""Generate a transition to a new topic.

Resume Context:
{resume_context}

Conversation so far:
{conversation_context[:300]}

Your response will be spoken aloud. Smoothly transition to a new topic from their background. Be natural and conversational. Acknowledge what they've shared when it makes sense, but don't force it."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": COMMON_SYSTEM_PROMPT + " Generate transitions that feel natural and smooth.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
            )

            transition = response.choices[0].message.content.strip()
            state["next_message"] = transition
            state["conversation_history"].append({
                "role": "assistant",
                "content": transition,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            state["next_message"] = "Great! Let's move on to another topic."

        return state

    async def evaluation_node(self, state: InterviewState) -> InterviewState:
        """Comprehensive interview evaluation and feedback generation."""
        state["last_node"] = "evaluation"
        state["phase"] = "closing"

        try:
            topics_covered = extract_topics_from_exploration(state)
            comprehensive_feedback = await self.feedback_generator.generate_feedback(
                conversation_history=state.get("conversation_history", []),
                resume_context=state.get("resume_structured", {}),
                code_submissions=state.get("code_submissions", []),
                topics_covered=topics_covered,
                job_description=state.get("job_description"),
            )

            state["feedback"] = comprehensive_feedback.model_dump()
            logger.info(
                f"Generated evaluation feedback with overall_score: {state['feedback'].get('overall_score', 0)}")
        except Exception as e:
            logger.error(
                f"Failed to generate comprehensive feedback: {e}", exc_info=True)
            topics_covered = extract_topics_from_exploration(state)
            state["feedback"] = {
                "summary": "Interview completed successfully.",
                "topics_covered": topics_covered,
                "turn_count": state.get("turn_count", 0),
                "overall_score": 0.5,
            }

        return state

    async def closing_node(self, state: InterviewState) -> InterviewState:
        """Generate closing message."""
        state["last_node"] = "closing"
        state["phase"] = "closing"
        conversation_summary = build_conversation_context(
            state, self.interview_logger)

        prompt = f"""Generate a closing message for the interview.

Conversation Summary:
{conversation_summary[:500]}

Your closing will be spoken aloud. Thank them genuinely. Reference something specific from the conversation if relevant. Be warm and authentic."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": COMMON_SYSTEM_PROMPT + " You are closing an interview. Be warm and appreciative. Reference the conversation naturally.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
            )

            closing = response.choices[0].message.content.strip()
            state["next_message"] = closing
            state["conversation_history"].append({
                "role": "assistant",
                "content": closing,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            state["next_message"] = "Thank you for your time today. It was great learning more about your background!"

        return state

    async def sandbox_guidance_node(self, state: InterviewState) -> InterviewState:
        """Guide user to use sandbox for writing code, optionally providing an exercise."""
        state["last_node"] = "sandbox_guidance"
        logger.info("Sandbox guidance node - guiding user to write code")

        if self.interview_logger:
            self.interview_logger.log_state("sandbox_guidance", state)

        should_provide_exercise = await self._should_provide_exercise(state)

        if should_provide_exercise:
            exercise = await self._generate_coding_exercise(state)
            state["sandbox"]["initial_code"] = exercise.get("starter_code", "")
            state["sandbox"]["exercise_description"] = exercise.get(
                "description", "")
            state["sandbox"]["exercise_difficulty"] = exercise.get(
                "difficulty", "medium")
            state["sandbox"]["exercise_hints"] = exercise.get("hints", [])
            if "hints_provided" not in state["sandbox"]:
                state["sandbox"]["hints_provided"] = []
            state["sandbox"]["is_active"] = True
            state["current_code"] = exercise.get("starter_code", "")
            logger.info(
                f"Generated coding exercise: {exercise.get('description', '')[:50]}")

        resume_context = build_resume_context(state)
        job_context = build_job_context(state)
        conversation_context = build_conversation_context(
            state, self.interview_logger)

        if should_provide_exercise:
            prompt = f"""Generate a message introducing a coding exercise to the candidate.

{job_context}

Resume Context:
{resume_context[:200]}

Exercise Description:
{exercise.get('description', '')}

Your message will be spoken aloud. Introduce the coding exercise naturally. Guide them to the code sandbox where it's set up. Be clear and supportive."""
        else:
            prompt = f"""Generate a message guiding the candidate to use the code sandbox.

Conversation Context:
{conversation_context[:300]}

Resume Context:
{resume_context[:200]}

Your message will be spoken aloud. Acknowledge their request to write code. Guide them to the code sandbox. Let them know you'll review it when they submit. Be natural and helpful."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": COMMON_SYSTEM_PROMPT + " You are guiding a candidate to use the code sandbox. Be clear and helpful.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
            )

            guidance_message = response.choices[0].message.content.strip()
            state["next_message"] = guidance_message

            if self.interview_logger:
                self.interview_logger.log_llm_call(
                    "sandbox_guidance", prompt, guidance_message, "gpt-4o-mini"
                )

            state["conversation_history"].append({
                "role": "assistant",
                "content": guidance_message,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.error(
                f"Error generating sandbox guidance: {e}", exc_info=True)
            if self.interview_logger:
                self.interview_logger.log_error("sandbox_guidance", e)
            fallback = "Great! I'd love to see your code. Please use the code sandbox on the right side of your screen. Write your code there and submit it when you're ready, and I'll review it for you."
            state["next_message"] = fallback
            state["conversation_history"].append({
                "role": "assistant",
                "content": fallback,
                "timestamp": datetime.utcnow().isoformat(),
            })

        return state

    async def _should_provide_exercise(self, state: InterviewState) -> bool:
        """Determine if agent should provide a coding exercise."""
        active_request = state.get("active_user_request")
        if active_request and active_request.get("type") == "write_code":
            return True

        job_desc = state.get("job_description", "").lower(
        ) if state.get("job_description") else ""
        coding_keywords = ["python", "javascript", "code",
                           "programming", "developer", "engineer", "software"]
        if job_desc and any(keyword in job_desc for keyword in coding_keywords):
            return True

        conversation = build_conversation_context(state, self.interview_logger)
        if "technical" in conversation.lower() or "coding" in conversation.lower():
            return True

        return False

    async def _generate_coding_exercise(self, state: InterviewState) -> dict:
        """Generate a coding exercise based on job description and resume."""
        job_context = build_job_context(state)
        resume_context = build_resume_context(state)
        conversation_context = build_conversation_context(
            state, self.interview_logger)[:500]

        prompt = f"""Generate a coding exercise for an interview candidate.

{job_context}

Resume Context:
{resume_context[:300]}

Recent Conversation:
{conversation_context}

Create a coding exercise that:
1. Is relevant to the job requirements
2. Matches the candidate's experience level
3. Can be completed in 15-30 minutes
4. Tests practical programming skills

Return a JSON object with:
- "description": Clear problem description (2-3 sentences)
- "starter_code": Python code with function signatures and docstrings, comments explaining the problem
- "language": "python" or "javascript"
- "difficulty": "easy", "medium", or "hard"
- "hints": List of 2-3 hints if candidate gets stuck

Example starter_code format:
```python
def solve_problem(input_data):
    \"\"\"
    Problem: [description]
    
    Args:
        input_data: [description]
    
    Returns:
        [description]
    \"\"\"
    # TODO: Implement your solution here
    pass
```

Return ONLY valid JSON, no markdown formatting."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": COMMON_SYSTEM_PROMPT + " You are creating coding interview exercises. Generate practical, relevant problems.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                response_format={"type": "json_object"},
            )

            exercise = json.loads(response.choices[0].message.content)
            return exercise
        except Exception as e:
            logger.error(f"Error generating exercise: {e}", exc_info=True)
            return {
                "description": "Implement a function that finds the maximum value in a list.",
                "starter_code": """def find_max(numbers):
    \"\"\"
    Find the maximum value in a list of numbers.
    
    Args:
        numbers: List of integers
    
    Returns:
        Maximum integer in the list
    \"\"\"
    # TODO: Implement your solution here
    pass""",
                "language": "python",
                "difficulty": "easy",
                "hints": ["Think about iterating through the list", "Keep track of the maximum value seen so far"]
            }

    async def check_sandbox_code_changes(self, state: InterviewState) -> InterviewState:
        """Poll sandbox for code changes and provide real-time guidance if needed."""
        if not state.get("sandbox", {}).get("is_active"):
            return state

        sandbox = state.get("sandbox", {})
        last_poll = sandbox.get("last_poll_time", 0.0)
        current_time = time.time()

        if current_time - last_poll < 10.0:
            return state

        current_code = state.get("current_code", "")
        last_snapshot = sandbox.get("last_code_snapshot", "")
        initial_code = sandbox.get("initial_code", "")
        last_activity_ts = sandbox.get("last_activity_ts", 0.0)

        help_keywords = ["# help", "# stuck", "# hint",
                         "# todo", "# ???", "// help", "// stuck"]
        asking_for_help = any(keyword in current_code.lower()
                              for keyword in help_keywords)

        time_since_activity = current_time - \
            last_activity_ts if last_activity_ts > 0 else 0
        is_stuck = time_since_activity > 30.0 and current_code != initial_code

        if current_code and current_code != last_snapshot:
            if current_code != initial_code:
                state["sandbox"]["last_code_snapshot"] = current_code
                state["sandbox"]["last_poll_time"] = current_time
                state["sandbox"]["last_activity_ts"] = current_time

                code_length_change = len(
                    current_code) - len(last_snapshot) if last_snapshot else len(current_code)
                if code_length_change > 50:
                    last_encouragement = sandbox.get(
                        "last_encouragement_time", 0.0)
                    if current_time - last_encouragement > 60.0:
                        if not any(keyword in current_code.lower() for keyword in ["todo", "pass", "raise", "notimplemented"]):
                            state["sandbox"]["last_encouragement_time"] = current_time
                            signals = sandbox.get("signals", [])
                            if "making_progress" not in signals:
                                signals.append("making_progress")
                                state["sandbox"]["signals"] = signals

        if asking_for_help or is_stuck:
            exercise_hints = sandbox.get("exercise_hints", [])
            hints_provided = sandbox.get("hints_provided", [])

            if exercise_hints and len(hints_provided) < len(exercise_hints):
                next_hint_index = len(hints_provided)
                next_hint = exercise_hints[next_hint_index]

                hint_message = f"Here's a hint to help you: {next_hint}"
                if asking_for_help:
                    hint_message = f"I see you're looking for help. {hint_message}"
                elif is_stuck:
                    hint_message = f"You seem to be stuck. {hint_message}"

                state["next_message"] = hint_message
                hints_provided.append(next_hint)
                state["sandbox"]["hints_provided"] = hints_provided

                signals = sandbox.get("signals", [])
                if "needs_help" not in signals:
                    signals.append("needs_help")
                    state["sandbox"]["signals"] = signals

                logger.info(
                    f"Provided hint {next_hint_index + 1}/{len(exercise_hints)} to user")
            elif asking_for_help:
                state["next_message"] = "You're making progress! Try breaking the problem down into smaller steps. If you need to, you can always ask me specific questions about your approach."

        state["sandbox"]["last_poll_time"] = current_time
        return state

    async def code_review_node(self, state: InterviewState) -> InterviewState:
        """Execute code, analyze it, and generate feedback."""
        state["last_node"] = "code_review"
        logger.info("Code review node - reviewing submitted code")

        if self.interview_logger:
            self.interview_logger.log_state("code_review_start", state)

        code = state.get("current_code")
        if not code:
            state["next_message"] = "I don't see any code to review. Please submit your code."
            return state

        sandbox = state.get("sandbox", {})
        exercise_description = sandbox.get("exercise_description", "")
        initial_code = sandbox.get("initial_code", "")

        exercise_mismatch_note = ""
        if exercise_description and initial_code:
            try:
                check_prompt = f"""You are reviewing code submitted by a candidate. 

EXERCISE PROVIDED:
{exercise_description}

STARTER CODE PROVIDED:
```python
{initial_code[:500]}
```

CODE SUBMITTED BY CANDIDATE:
```python
{code[:1000]}
```

Determine if the submitted code is an attempt to solve the exercise provided, or if it's completely different code.

IMPORTANT: The candidate must solve the EXACT exercise provided. If the exercise asks for "task management API" but code implements "book management API", that's a MISMATCH. Only consider it a match if the code addresses the specific domain and requirements of the exercise.

Return a JSON object with:
- "matches_exercise": true/false
- "reason": Brief explanation (1 sentence)

If the code doesn't match, the candidate may have submitted unrelated code instead of working on the exercise."""

                response = await self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": COMMON_SYSTEM_PROMPT +
                            " You are a code reviewer. Analyze if submitted code matches the exercise."},
                        {"role": "user", "content": check_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )

                check_result = json.loads(response.choices[0].message.content)

                if not check_result.get("matches_exercise", True):
                    reason = check_result.get(
                        "reason", "The code doesn't appear to match the exercise.")
                    exercise_mismatch_note = f"\n\nNote: I notice you submitted code that doesn't match the exercise I provided ({exercise_description[:100]}...). I'll review what you submitted, but I'd also like to see your solution to the original exercise when you're ready."
                    logger.warning(f"Code mismatch detected: {reason}")
            except Exception as e:
                logger.warning(f"Failed to check exercise match: {e}")

        state["sandbox"]["is_active"] = True
        state["sandbox"]["last_activity_ts"] = datetime.utcnow().timestamp()
        state["sandbox"]["signals"].append("code_submitted")

        language_str = state.get("current_language", "python").lower()
        try:
            sandbox_language = SandboxLanguage(language_str)
        except ValueError:
            sandbox_language = SandboxLanguage.PYTHON

        try:
            execution_result = await self.sandbox_service.execute_code(
                code=code,
                language=sandbox_language,
            )

            exec_result_dict = execution_result.to_dict()
            state["code_execution_result"] = exec_result_dict

            conversation_summary = build_conversation_context(
                state, self.interview_logger)
            job_context = build_job_context(state)
            code_quality = await self.code_analyzer.analyze_code(
                code=code,
                language=language_str,
                execution_result=exec_result_dict,
                context={
                    "question": state.get("current_question", ""),
                    "conversation_summary": conversation_summary,
                    "job_description": job_context,
                },
            )

            state["code_quality"] = {
                "quality_score": code_quality.quality_score,
                "correctness_score": code_quality.correctness_score,
                "efficiency_score": code_quality.efficiency_score,
                "readability_score": code_quality.readability_score,
                "best_practices_score": code_quality.best_practices_score,
                "strengths": code_quality.strengths,
                "weaknesses": code_quality.weaknesses,
                "feedback": code_quality.feedback,
                "suggestions": code_quality.suggestions,
            }

            feedback_message = await self.code_analyzer.generate_code_feedback_message(
                code_quality=code_quality,
                execution_result=exec_result_dict,
            )

            followup_question = await self.code_analyzer.generate_adaptive_question(
                code_quality=code_quality,
                execution_result=exec_result_dict,
                conversation_context=conversation_summary,
            )

            combined_message = f"{feedback_message}{exercise_mismatch_note}\n\n{followup_question}"
            state["next_message"] = combined_message
            state["current_question"] = followup_question

            state["conversation_history"].append({
                "role": "assistant",
                "content": combined_message,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {
                    "type": "code_review",
                    "execution_result": exec_result_dict,
                    "code_quality": state["code_quality"],
                },
            })

            submission = {
                "code": code,
                "language": language_str,
                "execution_result": exec_result_dict,
                "code_quality": state["code_quality"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            state["code_submissions"].append(submission)
            state["sandbox"]["submissions"].append(submission)

            try:
                metrics = get_code_metrics()
                metrics.record_execution(
                    user_id=state["user_id"],
                    interview_id=state["interview_id"],
                    code=code,
                    language=language_str,
                    execution_result=exec_result_dict,
                    code_quality=state["code_quality"],
                )
            except Exception as e:
                logger.warning(f"Failed to record code metrics: {e}")

        except Exception as e:
            logger.error(f"Error in code review: {e}", exc_info=True)
            state["sandbox"]["signals"].append("execution_error")
            state["next_message"] = "I encountered an issue reviewing your code. Please try submitting it again."
            state["code_execution_result"] = {"error": str(e)}

        return state

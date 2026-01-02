"""LangGraph-based interview orchestrator with robust state management."""

import logging
import json
import uuid
from typing import TypedDict, Literal, Optional
from datetime import datetime
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field

from src.core.config import settings
from src.services.response_analyzer import ResponseAnalyzer
from src.services.code_analyzer import CodeAnalyzer
from src.services.sandbox_service import SandboxService, Language as SandboxLanguage
from src.services.code_metrics import get_code_metrics
from src.services.feedback_generator import FeedbackGenerator
from src.services.interview_logger import InterviewLogger

logger = logging.getLogger(__name__)


# ============================================================================
# ROBUST STATE STRUCTURE
# ============================================================================

class QuestionRecord(TypedDict):
    """Record of a question asked during the interview."""
    id: str
    text: str
    source: str  # resume | followup | user_request | transition
    # project_1, skill_python, internship_itg, etc.
    resume_anchor: Optional[str]
    aspect: str  # challenges, impact, design, tradeoffs, implementation, etc.
    asked_at_turn: int


class UserIntent(TypedDict):
    """Detected user intent from their response."""
    type: str  # technical_assessment | change_topic | clarify | stop | continue | write_code | review_code | show_code | no_intent
    confidence: float  # 0.0-1.0
    extracted_from: str  # raw text that triggered this intent
    turn: int
    # Additional context (e.g., requested_topic, etc.)
    metadata: Optional[dict]


class ResumeExploration(TypedDict):
    """Tracking of how deeply we've explored a resume anchor."""
    anchor_id: str  # project_1, skill_python, internship_itg
    anchor_type: str  # project | skill | experience | education
    # design, challenges, tools, impact, team, results, etc.
    aspects_covered: set[str]
    depth_score: int  # 0-10, how deeply explored
    last_explored_turn: int


class SandboxState(TypedDict):
    """State of code sandbox activity."""
    is_active: bool
    last_activity_ts: float  # Unix timestamp
    submissions: list[dict]  # Code submissions with results
    # struggling, confident, refactoring, idle, syntax_errors, rapid_iterations
    signals: list[str]
    # Exercise fields
    initial_code: str  # Code provided by agent (exercise starter)
    exercise_description: str  # Problem description
    exercise_difficulty: str  # easy, medium, hard
    exercise_hints: list[str]  # Hints for the exercise
    last_code_snapshot: str  # Last code seen during polling
    last_poll_time: float  # Timestamp of last poll


class InterviewState(TypedDict):
    """Robust state schema for LangGraph interview workflow."""

    # Core identifiers
    interview_id: int
    user_id: int
    resume_id: int | None

    # Conversation
    turn_count: int
    conversation_history: list[dict]

    # Questions tracking (EXPLICIT)
    questions_asked: list[QuestionRecord]
    current_question: str | None

    # Resume understanding (STRUCTURED)
    resume_structured: dict  # parsed resume data
    # anchor_id -> exploration
    resume_exploration: dict[str, ResumeExploration]

    # Job context
    job_description: str | None  # Job description/requirements

    # User intent (FIRST-CLASS)
    detected_intents: list[UserIntent]
    active_user_request: UserIntent | None

    # Sandbox / code
    sandbox: SandboxState

    # Flow control
    phase: str  # intro | exploration | technical | closing
    last_node: str
    next_node: str | None

    # Legacy fields (for backward compatibility during migration)
    resume_context: dict  # Keep for now, will migrate
    answer_quality: float
    topics_covered: list[str]  # Deprecated, use resume_exploration
    next_message: str | None  # AI's next message to send
    last_response: str | None  # User's last response
    current_code: str | None
    code_execution_result: dict | None
    code_quality: dict | None
    code_submissions: list[dict]
    feedback: dict | None

    # System
    checkpoints: list[str]  # Checkpoint IDs for recovery


# ============================================================================
# PYDANTIC MODELS FOR LLM INTEGRATION
# ============================================================================

class UserIntentDetection(BaseModel):
    """LLM-driven user intent detection."""
    intent_type: Literal[
        "write_code", "review_code", "technical_assessment", "change_topic",
        "clarify", "stop", "continue", "no_intent"
    ] = Field(..., description="Type of user intent")
    confidence: float = Field(..., ge=0.0, le=1.0,
                              description="Confidence score")
    reasoning: str = Field(..., description="Why this intent was detected")
    metadata: dict = Field(default_factory=dict,
                           description="Additional context")


class NextActionDecision(BaseModel):
    """LLM-driven decision on what to do next."""
    action: Literal["greeting", "question", "followup", "transition", "closing", "evaluation", "sandbox_guidance", "code_review"] = Field(
        ..., description="What action to take next"
    )
    reasoning: str = Field(...,
                           description="Brief reasoning for this decision")
    should_evaluate: bool = Field(
        default=False, description="Whether to run evaluation before closing")


class ResumeAnchor(BaseModel):
    """Identified resume anchor for exploration."""
    anchor_id: str = Field(...,
                           description="Unique identifier (e.g., project_1, skill_python)")
    anchor_type: Literal["project", "skill", "experience",
                         "education"] = Field(..., description="Type of anchor")
    description: str = Field(..., description="Brief description")


class QuestionGeneration(BaseModel):
    """Generated question with metadata."""
    question: str = Field(..., description="The question text")
    resume_anchor: Optional[str] = Field(
        None, description="Which resume anchor this relates to")
    aspect: str = Field(...,
                        description="What aspect we're exploring (challenges, impact, etc.)")
    reasoning: str = Field(..., description="Why this question was chosen")


# ============================================================================
# INTERVIEW ORCHESTRATOR
# ============================================================================

class InterviewOrchestrator:
    """LangGraph orchestrator with robust state management."""

    def __init__(self):
        self._openai_client = None
        self._response_analyzer = ResponseAnalyzer()
        self._code_analyzer = CodeAnalyzer()
        self._feedback_generator = FeedbackGenerator()
        self._sandbox_service = None
        self._interview_logger: Optional[InterviewLogger] = None

    def set_interview_logger(self, logger: InterviewLogger):
        """Set the interview logger for debugging."""
        self._interview_logger = logger

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    def _get_sandbox_service(self):
        if self._sandbox_service is None:
            self._sandbox_service = SandboxService()
        return self._sandbox_service

    # ========================================================================
    # CONTEXT BUILDERS (Read-only context injection)
    # ========================================================================

    def _build_decision_context(self, state: InterviewState) -> dict:
        """Build context for decision node."""
        ctx = {
            "turn": state["turn_count"],
            "phase": state.get("phase", "exploration"),
            "last_question": state.get("current_question"),
            "questions_asked": [q["text"] for q in state.get("questions_asked", [])],
            "questions_count": len(state.get("questions_asked", [])),
            "active_user_request": state.get("active_user_request"),
            "resume_coverage": {
                k: {
                    "aspects_covered": list(v.get("aspects_covered", set())),
                    "depth_score": v.get("depth_score", 0),
                }
                for k, v in state.get("resume_exploration", {}).items()
            },
            "sandbox_signals": state.get("sandbox", {}).get("signals", []),
            "conversation_length": len(state.get("conversation_history", [])),
        }

        # Log context injection
        if self._interview_logger:
            self._interview_logger.log_context_injection("decision", ctx)

        return ctx

    def _build_job_context(self, state: InterviewState) -> str:
        """Build job description context string."""
        job_desc = state.get("job_description")
        if not job_desc:
            return ""
        return f"Job Requirements:\n{job_desc}\n\n"

    def _build_resume_context(self, state: InterviewState) -> str:
        """Build resume context string (legacy, for prompts)."""
        resume_ctx = state.get("resume_context") or state.get(
            "resume_structured", {})
        if not resume_ctx:
            return "No resume context available."

        parts = []
        if resume_ctx.get("profile"):
            parts.append(f"Profile: {resume_ctx['profile'][:200]}")
        if resume_ctx.get("experience"):
            parts.append(f"Experience: {resume_ctx['experience'][:300]}")
        if resume_ctx.get("education"):
            parts.append(f"Education: {resume_ctx['education'][:200]}")
        if resume_ctx.get("projects"):
            parts.append(f"Projects: {resume_ctx['projects'][:200]}")
        if resume_ctx.get("skills"):
            parts.append(
                f"Skills: {', '.join(resume_ctx['skills'][:10]) if isinstance(resume_ctx['skills'], list) else 'N/A'}")

        return "\n".join(parts) if parts else "No resume details available."

    def _build_conversation_context(self, state: InterviewState) -> str:
        """Build conversation context string."""
        history = state.get("conversation_history", [])
        if not history:
            ctx_str = "No conversation yet."
            if self._interview_logger:
                self._interview_logger.log_context_injection(
                    "conversation", {"messages_count": 0})
            return ctx_str

        context_parts = []
        recent_messages = history[-8:]  # Last 8 messages
        for msg in recent_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Skip checkpoint system messages
            if role == "system" and "CHECKPOINT" in content:
                continue
            context_parts.append(f"{role.upper()}: {content[:200]}")

        ctx_str = "\n".join(context_parts)

        # Log context injection
        if self._interview_logger:
            self._interview_logger.log_context_injection("conversation", {
                "total_messages": len(history),
                "recent_messages_count": len(recent_messages),
                "context_length": len(ctx_str),
                "last_message_role": history[-1].get("role") if history else None,
            })

        return ctx_str

    # ========================================================================
    # RESUME EXPLORATION HELPERS
    # ========================================================================

    def _initialize_resume_exploration(self, state: InterviewState) -> InterviewState:
        """Initialize resume exploration anchors from resume context."""
        if "resume_exploration" in state and state["resume_exploration"]:
            return state  # Already initialized

        resume_ctx = state.get("resume_context") or state.get(
            "resume_structured", {})
        exploration: dict[str, ResumeExploration] = {}

        # Extract projects
        if resume_ctx.get("projects"):
            projects = resume_ctx["projects"] if isinstance(
                resume_ctx["projects"], list) else []
            for i, project in enumerate(projects[:10], 1):  # Max 10 projects
                anchor_id = f"project_{i}"
                exploration[anchor_id] = {
                    "anchor_id": anchor_id,
                    "anchor_type": "project",
                    "aspects_covered": set(),
                    "depth_score": 0,
                    "last_explored_turn": -1,
                }

        # Extract skills
        if resume_ctx.get("skills"):
            skills = resume_ctx["skills"] if isinstance(
                resume_ctx["skills"], list) else []
            for i, skill in enumerate(skills[:15], 1):  # Max 15 skills
                anchor_id = f"skill_{skill.lower().replace(' ', '_')}"
                exploration[anchor_id] = {
                    "anchor_id": anchor_id,
                    "anchor_type": "skill",
                    "aspects_covered": set(),
                    "depth_score": 0,
                    "last_explored_turn": -1,
                }

        # Extract experiences (jobs/internships)
        if resume_ctx.get("experience"):
            experience_text = resume_ctx["experience"] if isinstance(
                resume_ctx["experience"], str) else str(resume_ctx.get("experience", ""))
            # Simple heuristic: extract company names or roles
            # In production, you'd want more sophisticated extraction
            experiences = experience_text.split("\n")[:5]  # Rough split
            for i, exp in enumerate(experiences[:5], 1):
                anchor_id = f"experience_{i}"
                exploration[anchor_id] = {
                    "anchor_id": anchor_id,
                    "anchor_type": "experience",
                    "aspects_covered": set(),
                    "depth_score": 0,
                    "last_explored_turn": -1,
                }

        state["resume_exploration"] = exploration
        return state

    def _find_unexplored_anchor(self, state: InterviewState) -> Optional[str]:
        """Find an anchor with unexplored aspects."""
        exploration = state.get("resume_exploration", {})
        if not exploration:
            return None

        # Prefer anchors with low depth_score and many unexplored aspects
        candidates = []
        all_aspects = {"challenges", "impact", "design", "tools",
                       "team", "results", "tradeoffs", "implementation"}

        for anchor_id, anchor_data in exploration.items():
            covered = anchor_data.get("aspects_covered", set())
            uncovered = all_aspects - covered
            depth = anchor_data.get("depth_score", 0)

            if uncovered:
                candidates.append((anchor_id, len(uncovered), depth))

        if not candidates:
            return None

        # Sort by: most uncovered aspects, then lowest depth
        candidates.sort(key=lambda x: (-x[1], x[2]))
        return candidates[0][0]

    # ========================================================================
    # QUESTION DEDUPLICATION
    # ========================================================================

    def _is_duplicate_question(self, question_text: str, resume_anchor: Optional[str],
                               aspect: str, state: InterviewState) -> bool:
        """Check if question is duplicate (layered strategy)."""
        questions_asked = state.get("questions_asked", [])

        # Normalize question text
        normalized = question_text.lower().strip()

        # Layer 1: Exact match
        for q in questions_asked:
            if q["text"].lower().strip() == normalized:
                return True

        # Layer 2: Aspect gating - same anchor + same aspect = block
        if resume_anchor:
            for q in questions_asked:
                if (q.get("resume_anchor") == resume_anchor and
                        q.get("aspect") == aspect):
                    return True

        # Layer 3: Semantic similarity (simple word overlap for now)
        # In production, use embeddings (e.g., OpenAI embeddings, similarity > 0.85)
        question_words = set(normalized.split())
        for q in questions_asked:
            existing_words = set(q["text"].lower().split())
            overlap = len(question_words & existing_words) / \
                max(len(question_words), len(existing_words))
            if overlap > 0.8:  # 80% word overlap
                return True

        return False

    # ========================================================================
    # NODES
    # ========================================================================

    async def _initialize_node(self, state: InterviewState) -> InterviewState:
        """Initialize interview state."""
        # Initialize defaults
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
                "hints_provided": [],  # Track which hints have been given
            }
        if "turn_count" not in state:
            state["turn_count"] = 0
        if "phase" not in state:
            state["phase"] = "intro"
        if "code_submissions" not in state:
            state["code_submissions"] = []

        # Initialize resume exploration
        state = self._initialize_resume_exploration(state)

        state["last_node"] = "initialize"
        state["current_question"] = None
        state["active_user_request"] = None
        state["answer_quality"] = 0.0

        return state

    async def _detect_user_intent_node(self, state: InterviewState) -> InterviewState:
        """Detect user intent from their last response - FIRST-CLASS NODE."""
        state["last_node"] = "detect_user_intent"

        last_response = state.get("last_response")
        if not last_response:
            state["active_user_request"] = None
            return state

        client = self._get_openai_client()

        # Build conversation context for better understanding
        conversation_context = self._build_conversation_context(state)
        recent_context = conversation_context[-500:] if len(
            conversation_context) > 500 else conversation_context

        # Get the last question asked to understand what user might be responding to
        last_question = ""
        if state.get("conversation_history"):
            for msg in reversed(state["conversation_history"]):
                if msg.get("role") == "assistant":
                    last_question = msg.get("content", "")
                    break

        prompt = f"""You are analyzing a user's response in an interview conversation to understand their TRUE INTENT.

CONVERSATION CONTEXT:
{recent_context}

LAST QUESTION ASKED: {last_question if last_question else "None (initial greeting)"}

USER'S CURRENT RESPONSE: "{last_response}"

YOUR TASK:
Understand what the user is TRYING TO ACCOMPLISH with this response. Think about:
1. What ACTION do they want the interviewer to take?
2. What is their GOAL or PURPOSE in saying this?
3. Are they making a REQUEST or just ANSWERING a question?
4. What would happen if we IGNORED their intent? Would the conversation flow naturally?

CRITICAL: Don't match keywords. Understand the user's GOAL. People express the same intent in many different ways.

INTENT TYPES - Understand the GOAL, not the words:

1. **write_code**: User wants to CREATE/WRITE code in the sandbox
   - GOAL: Demonstrate coding ability by writing code
   - SIGNALS: Proactive request to code, wants to show technical skills
   - VARIATIONS: "I'd like to write code", "Can I code something?", "Let me show you my approach", "I want to demonstrate", "Can I use the editor?"
   - NOT: Just mentioning code in an answer

2. **review_code**: User wants to SHARE/DISCUSS existing code
   - GOAL: Get feedback on code they have or want to walk through
   - SIGNALS: Has code ready, wants to show/share code
   - VARIATIONS: "Here's my code", "Can you review this?", "Let me show you the implementation", "I have some code to share"
   - NOT: Asking to write new code

3. **change_topic**: User wants to REDIRECT the conversation
   - GOAL: Move discussion to a different subject/topic
   - SIGNALS: Explicit redirection, wants to discuss something else, correcting direction
   - VARIATIONS: "Actually, let's talk about X", "Can we discuss Y instead?", "I'd rather talk about Z", "Let's change topics", "What about X?", "Instead, I want to discuss Y"
   - KEY: User is REDIRECTING, not just answering differently. Look for correction/redirection intent.
   - NOT: Just providing a different answer or example

4. **clarify**: User is CONFUSED and needs help understanding
   - GOAL: Get clarification on what was asked
   - SIGNALS: Doesn't understand, needs explanation, asking for help
   - VARIATIONS: "What do you mean?", "I don't understand", "Can you clarify?", "Could you explain?", "I'm not sure what you're asking"
   - NOT: Just asking a follow-up question

5. **technical_assessment**: User wants DIFFERENT TYPE of interview
   - GOAL: Switch to technical/coding questions format
   - SIGNALS: Requesting different interview style
   - VARIATIONS: "Give me coding questions", "I want technical assessment", "Ask me technical questions"

6. **stop**: User wants to END the interview
   - GOAL: Terminate or pause the conversation
   - SIGNALS: Clear request to stop
   - VARIATIONS: "Let's stop", "That's enough", "I want to end", "Can we finish?"

7. **continue**: User is AFFIRMING willingness to continue
   - GOAL: Express agreement/willingness
   - SIGNALS: Brief affirmative response
   - VARIATIONS: "Yes", "Sure", "Okay", "Continue", "Go ahead"

8. **no_intent**: User is just ANSWERING normally
   - GOAL: Provide information, answer the question
   - SIGNALS: Normal conversational response, providing information
   - DEFAULT: When user is just answering or having normal conversation

ANALYSIS FRAMEWORK - Think through this:

Step 1: What is the user's GOAL?
- Are they trying to DO something (request an action)?
- Are they trying to SAY something (provide information)?
- Are they trying to CHANGE something (redirect/clarify)?

Step 2: What would happen if we IGNORED this?
- If ignoring it would break the conversation flow → It's a request (write_code, change_topic, clarify, etc.)
- If ignoring it is fine → It's just an answer (no_intent)

Step 3: Look at the CONTEXT
- What was just discussed?
- What question was just asked?
- How does this response relate to the conversation flow?

EXAMPLES OF GOOD INTENT DETECTION:

Example 1:
Context: Interviewer asked "What challenges did you face?"
User: "Actually, let's talk about my team leadership instead"
Analysis: User is REDIRECTING (goal: change topic). They're not answering the question, they're changing direction.
Intent: change_topic (confidence: 0.95)

Example 2:
Context: Interviewer asked "Tell me about your project"
User: "I'd like to write some code to show you my approach"
Analysis: User wants to DEMONSTRATE (goal: write code). Proactive request to code.
Intent: write_code (confidence: 0.9)

Example 3:
Context: Interviewer asked "How did you solve that?"
User: "What do you mean by 'solve'?"
Analysis: User is CONFUSED (goal: get clarification). They need help understanding.
Intent: clarify (confidence: 0.9)

Example 4:
Context: Interviewer asked "What tools did you use?"
User: "I've worked with Python, Docker, and Kubernetes"
Analysis: User is ANSWERING (goal: provide information). Normal response.
Intent: no_intent (confidence: 0.9)

Example 5:
Context: Interviewer asked "Tell me about microservices"
User: "I've built microservices using Go. Can I show you the code?"
Analysis: User is ANSWERING but also making a REQUEST (goal: share code). The request is clear.
Intent: review_code (confidence: 0.85)

CONFIDENCE SCORING:
- 0.9+: Very clear intent, user is explicitly requesting something
- 0.7-0.89: Clear intent, but some ambiguity
- <0.7: Ambiguous, likely no_intent

Return your analysis with:
- intent_type: The best matching intent (one of: write_code, review_code, change_topic, clarify, technical_assessment, stop, continue, no_intent)
- confidence: How certain you are (0.0-1.0, float)
- reasoning: Brief explanation of WHY you chose this intent (what goal did you identify?)
- metadata: A JSON object/dict with any additional context (e.g. {{"topic": "leadership", "reason": "user redirected"}}), NOT a string"""

        try:
            detection = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=UserIntentDetection,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at understanding human intent through conversation analysis. Your job is to identify what the user is TRYING TO ACCOMPLISH, not match keywords. Think about their GOAL, their PURPOSE, and what ACTION they want. Consider the conversation context, the flow, and what would happen if their intent was ignored. Be thoughtful and holistic in your analysis.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )

            # Store intent
            intent: UserIntent = {
                "type": detection.intent_type,
                "confidence": detection.confidence,
                "extracted_from": last_response,
                "turn": state["turn_count"],
                "metadata": detection.metadata,
            }

            state["detected_intents"] = state.get("detected_intents", [])
            state["detected_intents"].append(intent)

            # Set active request if confidence is high
            if detection.confidence > 0.7:
                state["active_user_request"] = intent
                logger.info(
                    f"Detected user intent: {detection.intent_type} (confidence: {detection.confidence})")
            else:
                state["active_user_request"] = None

        except Exception as e:
            logger.warning(f"Failed to detect user intent: {e}")
            state["active_user_request"] = None

        return state

    async def _greeting_node(self, state: InterviewState) -> InterviewState:
        """Generate personalized greeting."""
        # CRITICAL: Guard against sending greeting multiple times
        conversation_history = state.get("conversation_history", [])
        turn_count = state.get("turn_count", 0)

        # Check if greeting was already sent
        has_greeting = False
        for msg in conversation_history:
            if msg.get("role") == "assistant":
                # If there's any assistant message, greeting was likely sent
                has_greeting = True
                break

        # If greeting was already sent OR turn_count > 0, skip greeting and go to question
        if has_greeting or turn_count > 0:
            logger.warning(
                f"Greeting node called but greeting already sent (turn_count={turn_count}, has_greeting={has_greeting}). "
                "Routing to question instead."
            )
            # Route to question instead
            # Mark that we were supposed to greet
            state["last_node"] = "greeting"
            return await self._question_node(state)

        state["last_node"] = "greeting"
        state["phase"] = "intro"

        client = self._get_openai_client()
        resume_context = self._build_resume_context(state)

        prompt = f"""Generate a warm, personalized greeting for the interview. Make it feel natural and human.

Resume Context:
{resume_context}

IMPORTANT: This greeting will be SPOKEN ALOUD. Write it like you're speaking, not writing.

Create a brief (2-3 sentences MAX) greeting that:
- Welcomes the candidate warmly and personally
- References something specific from their resume if relevant
- Sets a friendly, conversational tone
- Briefly mentions they can write code in the sandbox if they want (but don't force it)
- Uses SHORT sentences - easy to speak and understand
- Sounds natural when read aloud

IMPORTANT: The candidate has access to a code sandbox where they can write and submit code. You can mention this briefly in the greeting, but don't overemphasize it.

Start directly with the greeting (no prefix)."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a friendly, professional interviewer. CRITICAL: Write text that will be SPOKEN ALOUD. Use shorter sentences (2-3 sentences max). Write like you're speaking, not writing. Be conversational and warm.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
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

    async def _question_node(self, state: InterviewState) -> InterviewState:
        """Generate adaptive question based on resume exploration."""
        state["last_node"] = "question"
        state["phase"] = "exploration"

        client = self._get_openai_client()

        # Build context
        conversation_context = self._build_conversation_context(state)
        resume_context = self._build_resume_context(state)
        job_context = self._build_job_context(state)
        decision_ctx = self._build_decision_context(state)

        # Log context injection for question generation
        if self._interview_logger:
            self._interview_logger.log_context_injection("question_generation", {
                "conversation_length": len(conversation_context),
                "resume_context_length": len(resume_context),
                "turn": state.get("turn_count", 0),
                "last_node": state.get("last_node"),
            })

        # Find unexplored anchor
        anchor_id = self._find_unexplored_anchor(state)
        anchor_info = ""
        if anchor_id:
            anchor_data = state["resume_exploration"][anchor_id]
            anchor_info = f"""
Target Resume Anchor: {anchor_id} ({anchor_data['anchor_type']})
Already Explored Aspects: {list(anchor_data.get('aspects_covered', set()))}
Depth Score: {anchor_data.get('depth_score', 0)}
"""

        # Get available aspects
        all_aspects = {"challenges", "impact", "design", "tools",
                       "team", "results", "tradeoffs", "implementation"}
        if anchor_id:
            covered = state["resume_exploration"][anchor_id].get(
                "aspects_covered", set())
            available_aspects = list(all_aspects - covered)
        else:
            available_aspects = list(all_aspects)

        # Get questions already asked
        questions_asked = [q["text"] for q in state.get(
            "questions_asked", [])[-10:]]  # Last 10

        prompt = f"""Generate the next interview question based on the resume, job requirements, and conversation.

{job_context}Resume Context:
{resume_context}

{anchor_info}

Conversation History:
{conversation_context}

Questions Already Asked (DO NOT REPEAT):
{chr(10).join(f"- {q}" for q in questions_asked) if questions_asked else "None yet"}

Available Aspects to Explore: {', '.join(available_aspects) if available_aspects else 'all'}

IMPORTANT: This question will be SPOKEN ALOUD. Write it like you're speaking naturally.

Generate ONE natural, conversational question that:
- Is relevant to the resume anchor (if provided) and explores an available aspect
- Is SIMPLE and FOCUSED - ONE clear question only (ONE sentence)
- Uses SHORT, clear language - easy to understand when spoken
- Encourages storytelling with open-ended prompts
- Does NOT repeat any question from "Questions Already Asked"
- Explores a DIFFERENT aspect than previously asked about this anchor

CRITICAL: NEVER use "and" to connect two questions. ONE question = ONE thing to answer.

Return the question text only, no prefix."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=QuestionGeneration,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer. Generate relevant, engaging interview questions. CRITICAL: Your questions will be SPOKEN ALOUD. Write for speech: use short, clear sentences. One question = one sentence. Avoid complex structures. Be conversational. NEVER repeat questions. NEVER combine multiple questions with 'and'.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
            )

            question_text = response.question.strip()
            resume_anchor = response.resume_anchor or anchor_id
            aspect = response.aspect

            # Deduplication check
            if self._is_duplicate_question(question_text, resume_anchor, aspect, state):
                logger.warning(f"Duplicate question detected, regenerating...")
                # Fallback to simple question
                question_text = "Can you tell me more about a challenging project you've worked on?"
                resume_anchor = anchor_id
                aspect = "challenges"

            # Record question
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

            # Update resume exploration
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

    async def _decide_next_action(self, state: InterviewState) -> InterviewState:
        """Data-driven decision node with structured signals."""
        state["last_node"] = "decide"

        # Check for hint requests when sandbox is active (before other intent checks)
        sandbox = state.get("sandbox", {})
        if sandbox.get("is_active") and state.get("last_response"):
            last_response_lower = state.get("last_response", "").lower()
            hint_keywords = ["hint", "stuck", "help", "clue",
                             "guide", "what should i", "how do i", "i don't know"]
            is_hint_request = any(
                keyword in last_response_lower for keyword in hint_keywords)

            if is_hint_request:
                exercise_hints = sandbox.get("exercise_hints", [])
                hints_provided = sandbox.get("hints_provided", [])

                if exercise_hints and len(hints_provided) < len(exercise_hints):
                    next_hint_index = len(hints_provided)
                    next_hint = exercise_hints[next_hint_index]

                    state["next_message"] = f"Here's a hint to help you: {next_hint}"
                    hints_provided.append(next_hint)
                    state["sandbox"]["hints_provided"] = hints_provided
                    state["_next_action"] = "followup"  # Just provide the hint
                    logger.info(
                        f"Provided hint {next_hint_index + 1}/{len(exercise_hints)} upon user request")
                    return state
                elif exercise_hints:
                    state["next_message"] = "I've provided all available hints. Try breaking the problem into smaller steps, or feel free to ask me specific questions about your approach."
                    state["_next_action"] = "followup"
                    return state

        # Check active user request FIRST (highest priority)
        active_request = state.get("active_user_request")
        if active_request and active_request.get("confidence", 0) > 0.7:
            intent_type = active_request.get("type")

            # Log intent detection
            if self._interview_logger:
                self._interview_logger.log_intent_detection(
                    state.get("last_response", ""),
                    active_request
                )

            # CRITICAL: Handle code/sandbox requests
            if intent_type in ["write_code", "use_sandbox"]:
                state["_next_action"] = "sandbox_guidance"
                logger.info(
                    f"Routing to sandbox_guidance for intent: {intent_type}")
                if self._interview_logger:
                    self._interview_logger.log_decision(
                        {"intent": intent_type,
                            "confidence": active_request.get("confidence")},
                        "sandbox_guidance",
                        "User requested to write code in sandbox"
                    )
                state["active_user_request"] = None
                return state

            elif intent_type in ["review_code", "code_walkthrough", "show_code"]:
                # Check if code exists in sandbox state
                if state.get("current_code"):
                    state["_next_action"] = "code_review"
                    logger.info(
                        "Routing to code_review - code exists in state")
                else:
                    # Guide user to write code first
                    state["_next_action"] = "sandbox_guidance"
                    logger.info(
                        "Routing to sandbox_guidance - no code yet, requesting user to write code")

                if self._interview_logger:
                    self._interview_logger.log_decision(
                        {"intent": intent_type, "has_code": bool(
                            state.get("current_code"))},
                        state["_next_action"],
                        "User requested code review"
                    )
                state["active_user_request"] = None
                return state

            elif intent_type == "technical_assessment":
                state["_next_action"] = "question"
                state["phase"] = "technical"
                state["active_user_request"] = None
                return state
            elif intent_type == "change_topic":
                state["_next_action"] = "transition"
                state["active_user_request"] = None
                return state
            elif intent_type == "clarify":
                # Route to followup but mark that we need to clarify/rephrase
                state["_next_action"] = "followup"
                state["_needs_clarification"] = True
                state["active_user_request"] = None
                # Don't return - let it fall through to generate clarification
                # But we'll handle it in the followup node
            elif intent_type == "stop":
                state["_next_action"] = "closing"
                state["active_user_request"] = None
                return state

        # Build decision context
        decision_ctx = self._build_decision_context(state)
        conversation_context = self._build_conversation_context(state)
        resume_context = self._build_resume_context(state)

        client = self._get_openai_client()

        # Get answer quality
        answer_quality = 0.0
        if state.get("last_response") and state.get("current_question"):
            try:
                analysis = await self._response_analyzer.analyze_answer(
                    state.get("current_question", ""),
                    state.get("last_response", ""),
                    {"resume_context": state.get("resume_context", {})},
                )
                answer_quality = analysis.quality_score
                state["answer_quality"] = answer_quality
            except Exception:
                pass

        prompt = f"""Decide the next action for this interview based on structured signals.

Decision Context:
- Turn: {decision_ctx['turn']}
- Phase: {decision_ctx['phase']}
- Questions Asked: {decision_ctx['questions_count']}
- Conversation Length: {decision_ctx['conversation_length']}
- Answer Quality (last): {answer_quality:.2f}
- Sandbox Signals: {decision_ctx['sandbox_signals']}

Last Question: {decision_ctx.get('last_question', 'None')}

Resume Coverage:
{json.dumps(decision_ctx['resume_coverage'], indent=2, default=str)}

Conversation:
{conversation_context[:500]}

DECISION RULES (apply in order - STRICT ORDER, NO EXCEPTIONS):

1. **CRITICAL**: If conversation_history has ANY assistant messages OR turn_count > 0 → NEVER choose "greeting". Greeting is ONLY for the very first interaction with zero messages.

2. If conversation_length == 0 AND no assistant messages → "greeting" (first time only)

3. If turn >= 8 AND resume coverage is sufficient (3+ anchors with depth >= 2) → "evaluation" then "closing"

4. If last node was "question" → "transition" (MUST NOT choose "question" again)

5. If last node was "transition" → "question"

6. If answer_quality < 0.5 AND no recent followup → "followup"

7. If last node was "greeting" → "question" (MUST choose question after greeting)

8. Otherwise → "transition" (explore new area)

**ABSOLUTE RULE**: If conversation_history has assistant messages, "greeting" is FORBIDDEN. Choose "question" or "transition" instead.

Choose: greeting, question, followup, transition, closing, evaluation, sandbox_guidance, code_review

Note: sandbox_guidance and code_review are typically handled by intent detection, but you can choose them if the context clearly indicates the user wants to work with code."""

        try:
            decision = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=NextActionDecision,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an interviewer deciding the next action. CRITICAL RULES: (1) NEVER choose 'greeting' if conversation_history has any assistant messages or turn_count > 0. Greeting is ONLY for the very first interaction. (2) After 'question' choose 'transition', after 'transition' choose 'question'. (3) After 'greeting' ALWAYS choose 'question'. (4) After sufficient coverage, evaluate then close.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )

            state["_next_action"] = decision.action
            state["_should_evaluate"] = decision.should_evaluate

        except Exception:
            # Fallback logic with strict greeting guard
            conversation_history = state.get("conversation_history", [])
            has_assistant_messages = any(
                msg.get("role") == "assistant" for msg in conversation_history)
            turn_count = state.get("turn_count", 0)

            # NEVER route to greeting if conversation has started
            if (not conversation_context or conversation_context == "No conversation yet.") and not has_assistant_messages and turn_count == 0:
                state["_next_action"] = "greeting"
            elif decision_ctx["turn"] >= 8:
                state["_next_action"] = "evaluation"
            elif state.get("last_node") == "question":
                state["_next_action"] = "transition"
            elif state.get("last_node") == "greeting":
                # After greeting, always go to question
                state["_next_action"] = "question"
            else:
                state["_next_action"] = "question"
            state["_should_evaluate"] = False

        return state

    async def _followup_node(self, state: InterviewState) -> InterviewState:
        """Generate follow-up question or clarification."""
        state["last_node"] = "followup"

        client = self._get_openai_client()
        last_question = state.get("current_question", "")
        last_answer = state.get("last_response", "")

        # Check if this is a clarification request
        needs_clarification = state.pop("_needs_clarification", False)

        if needs_clarification:
            # User asked for clarification - rephrase the last question
            prompt = f"""The user asked for clarification on this question: "{last_question}"

IMPORTANT: This will be SPOKEN ALOUD. Write it like you're speaking naturally.

Rephrase the question to make it clearer and easier to understand:
- Use simpler language
- Break it into smaller parts if needed
- Be more specific about what you're asking
- Keep it conversational and warm
- Is SHORT and CLEAR - one question, one sentence if possible
- NEVER uses "and" to connect two questions

Return ONLY the rephrased question, no prefix or explanation."""
        else:
            # Normal follow-up question
            prompt = f"""Generate a natural follow-up question to dive deeper.

Previous Question: {last_question}
Candidate's Answer: {last_answer}

IMPORTANT: This question will be SPOKEN ALOUD. Write it like you're speaking naturally.

Generate a SIMPLE, FOCUSED follow-up question that:
- Shows genuine interest
- Asks for ONE specific thing
- Builds on what they just said
- Is conversational and warm
- Is SHORT and CLEAR - one question, one sentence
- NEVER uses "and" to connect two questions

Return ONLY the follow-up question, no prefix."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer asking follow-up questions. CRITICAL: Write for speech. One question = one sentence. Be curious and conversational. NEVER combine questions with 'and'.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
            )

            followup = response.choices[0].message.content.strip()

            # Record followup question
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

    async def _transition_node(self, state: InterviewState) -> InterviewState:
        """Transition to next topic."""
        state["last_node"] = "transition"

        client = self._get_openai_client()
        conversation_context = self._build_conversation_context(state)
        resume_context = self._build_resume_context(state)

        prompt = f"""Generate a smooth, natural transition to a new topic.

Resume Context:
{resume_context}

Conversation so far:
{conversation_context[:300]}

IMPORTANT: This transition will be SPOKEN ALOUD. Write it like you're speaking naturally.

Generate a brief (1-2 sentences MAX) transition that:
- Acknowledges what they've shared positively
- Smoothly introduces a new topic from their background
- Is natural and conversational
- Uses SHORT, clear sentences

Return ONLY the transition text, no prefix."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer transitioning between topics. CRITICAL: Write for speech. Use short sentences (2-3 max). Be smooth and natural.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
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

    async def _evaluation_node(self, state: InterviewState) -> InterviewState:
        """Comprehensive interview evaluation and feedback generation."""
        state["last_node"] = "evaluation"
        state["phase"] = "closing"

        client = self._get_openai_client()

        # Generate comprehensive feedback
        try:
            comprehensive_feedback = await self._feedback_generator.generate_feedback(
                conversation_history=state.get("conversation_history", []),
                resume_context=state.get("resume_context") or state.get(
                    "resume_structured", {}),
                code_submissions=state.get("code_submissions", []),
                topics_covered=list(
                    state.get("topics_covered", [])),  # Legacy field
                # Include job description
                job_description=state.get("job_description"),
            )

            state["feedback"] = comprehensive_feedback.model_dump()
            logger.info(
                f"Generated evaluation feedback with overall_score: {state['feedback'].get('overall_score', 0)}")

        except Exception as e:
            logger.error(
                f"Failed to generate comprehensive feedback: {e}", exc_info=True)
            # Fallback to simple feedback
            state["feedback"] = {
                "summary": "Interview completed successfully.",
                "topics_covered": state.get("topics_covered", []),
                "turn_count": state.get("turn_count", 0),
                "overall_score": 0.5,
            }

        return state

    async def _closing_node(self, state: InterviewState) -> InterviewState:
        """Generate closing message."""
        state["last_node"] = "closing"
        state["phase"] = "closing"

        client = self._get_openai_client()
        conversation_summary = self._build_conversation_context(state)

        prompt = f"""Generate a personalized closing message for the interview. Make it warm, specific, and memorable.

Conversation Summary:
{conversation_summary[:500]}

IMPORTANT: This closing will be SPOKEN ALOUD. Write it like you're speaking naturally.

Generate a brief closing (2-3 sentences MAX) that:
- Thanks the candidate genuinely and personally
- References something specific from the conversation
- Is warm, appreciative, and professional
- Sets positive expectations for next steps
- Uses SHORT, clear sentences

Return ONLY the closing message, no prefix."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional interviewer closing an interview. CRITICAL: Write for speech. Use short sentences (2-4 max). Be warm and appreciative.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
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

    async def _should_provide_exercise(self, state: InterviewState) -> bool:
        """Determine if agent should provide a coding exercise."""
        # Provide exercise if:
        # 1. User explicitly requested to code (write_code intent)
        # 2. Job description requires coding skills
        # 3. Agent decides to test technical skills (based on conversation)

        active_request = state.get("active_user_request")
        if active_request and active_request.get("type") == "write_code":
            return True

        job_desc = state.get("job_description", "").lower(
        ) if state.get("job_description") else ""
        coding_keywords = ["python", "javascript", "code",
                           "programming", "developer", "engineer", "software"]
        if job_desc and any(keyword in job_desc for keyword in coding_keywords):
            return True

        # Check if conversation suggests technical assessment needed
        conversation = self._build_conversation_context(state)
        if "technical" in conversation.lower() or "coding" in conversation.lower():
            return True

        return False

    async def _generate_coding_exercise(self, state: InterviewState) -> dict:
        """Generate a coding exercise based on job description and resume."""
        client = self._get_openai_client()
        job_context = self._build_job_context(state)
        resume_context = self._build_resume_context(state)
        conversation_context = self._build_conversation_context(state)[:500]

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
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating coding interview exercises. Generate practical, relevant problems.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                response_format={"type": "json_object"},
            )

            import json
            exercise = json.loads(response.choices[0].message.content)
            return exercise
        except Exception as e:
            logger.error(f"Error generating exercise: {e}", exc_info=True)
            # Fallback exercise
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

    async def _sandbox_guidance_node(self, state: InterviewState) -> InterviewState:
        """Guide user to use sandbox for writing code, optionally providing an exercise."""
        state["last_node"] = "sandbox_guidance"

        logger.info("Sandbox guidance node - guiding user to write code")

        if self._interview_logger:
            self._interview_logger.log_state("sandbox_guidance", state)

        # Check if we should provide an exercise
        should_provide_exercise = await self._should_provide_exercise(state)

        if should_provide_exercise:
            # Generate and set exercise
            exercise = await self._generate_coding_exercise(state)
            state["sandbox"]["initial_code"] = exercise.get("starter_code", "")
            state["sandbox"]["exercise_description"] = exercise.get(
                "description", "")
            state["sandbox"]["exercise_difficulty"] = exercise.get(
                "difficulty", "medium")
            state["sandbox"]["exercise_hints"] = exercise.get("hints", [])
            # Initialize hints_provided list when exercise is provided
            if "hints_provided" not in state["sandbox"]:
                state["sandbox"]["hints_provided"] = []
            state["sandbox"]["is_active"] = True
            state["current_code"] = exercise.get(
                "starter_code", "")  # Set initial code
            logger.info(
                f"Generated coding exercise: {exercise.get('description', '')[:50]}")

        # Generate personalized sandbox guidance
        client = self._get_openai_client()
        resume_context = self._build_resume_context(state)
        job_context = self._build_job_context(state)
        conversation_context = self._build_conversation_context(state)

        if should_provide_exercise:
            prompt = f"""Generate a message introducing a coding exercise to the candidate.

{job_context}

Resume Context:
{resume_context[:200]}

Exercise Description:
{exercise.get('description', '')}

IMPORTANT: This message will be SPOKEN ALOUD. Write it like you're speaking naturally.

Create a brief (2-3 sentences MAX) message that:
- Introduces the coding exercise naturally
- Explains what they need to do
- Guides them to the code sandbox where the exercise is already set up
- Encourages them to work on it and submit when ready
- Uses SHORT, clear sentences
- Sounds friendly and supportive

Example: "Great! I've set up a coding exercise for you in the sandbox. [Brief description]. Please work on it in the code sandbox on the right side of your screen. Take your time, and submit it when you're ready for me to review."

Return ONLY the message, no prefix."""
        else:
            prompt = f"""Generate a helpful, encouraging message guiding the candidate to use the code sandbox.

Conversation Context:
{conversation_context[:300]}

Resume Context:
{resume_context[:200]}

IMPORTANT: This message will be SPOKEN ALOUD. Write it like you're speaking naturally.

Create a brief (2-3 sentences MAX) message that:
- Acknowledges their request to write code
- Guides them to the code sandbox on the right side of their screen
- Encourages them to write code related to their projects or technical questions
- Mentions you'll review it when they submit
- Uses SHORT, clear sentences
- Sounds friendly and helpful

Example tone: "Absolutely! I'd love to see your code. Please use the code sandbox on the right side of your screen. You can write Python code there, and I'll review it when you submit it. Feel free to write code related to any project you've mentioned or any technical problem you'd like to discuss."

Return ONLY the guidance message, no prefix."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful interviewer guiding a candidate to use the code sandbox. Write naturally for speech - short, clear sentences.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )

            guidance_message = response.choices[0].message.content.strip()
            state["next_message"] = guidance_message

            if self._interview_logger:
                self._interview_logger.log_llm_call(
                    "sandbox_guidance",
                    prompt,
                    guidance_message,
                    "gpt-4o-mini"
                )

            state["conversation_history"].append({
                "role": "assistant",
                "content": guidance_message,
                "timestamp": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.error(
                f"Error generating sandbox guidance: {e}", exc_info=True)
            if self._interview_logger:
                self._interview_logger.log_error("sandbox_guidance", e)
            # Fallback message
            fallback = "Great! I'd love to see your code. Please use the code sandbox on the right side of your screen. Write your code there and submit it when you're ready, and I'll review it for you."
            state["next_message"] = fallback
            state["conversation_history"].append({
                "role": "assistant",
                "content": fallback,
                "timestamp": datetime.utcnow().isoformat(),
            })

        return state

    async def _check_sandbox_code_changes(self, state: InterviewState) -> InterviewState:
        """Poll sandbox for code changes and provide real-time guidance if needed."""
        if not state.get("sandbox", {}).get("is_active"):
            return state

        # Only poll every 10-15 seconds to avoid too frequent checks
        import time
        sandbox = state.get("sandbox", {})
        last_poll = sandbox.get("last_poll_time", 0.0)
        current_time = time.time()

        if current_time - last_poll < 10.0:  # Poll every 10 seconds minimum
            return state

        # Get current code and compare with last snapshot
        current_code = state.get("current_code", "")
        last_snapshot = sandbox.get("last_code_snapshot", "")
        initial_code = sandbox.get("initial_code", "")
        last_activity_ts = sandbox.get("last_activity_ts", 0.0)

        # Check for help requests in code comments
        help_keywords = ["# help", "# stuck", "# hint",
                         "# todo", "# ???", "// help", "// stuck"]
        asking_for_help = any(keyword in current_code.lower()
                              for keyword in help_keywords)

        # Track if user is stuck (no changes for 30+ seconds)
        time_since_activity = current_time - \
            last_activity_ts if last_activity_ts > 0 else 0
        is_stuck = time_since_activity > 30.0 and current_code != initial_code

        # If code changed, update snapshot and activity time
        if current_code and current_code != last_snapshot:
            if current_code != initial_code:  # User has modified the code
                state["sandbox"]["last_code_snapshot"] = current_code
                state["sandbox"]["last_poll_time"] = current_time
                state["sandbox"]["last_activity_ts"] = current_time

                # Provide subtle encouragement for progress (but not too frequently)
                # Only if they've made significant progress (code is different and longer)
                code_length_change = len(
                    current_code) - len(last_snapshot) if last_snapshot else len(current_code)
                if code_length_change > 50:  # Significant progress
                    # Check if we already provided encouragement recently
                    last_encouragement = sandbox.get(
                        "last_encouragement_time", 0.0)
                    if current_time - last_encouragement > 60.0:  # Once per minute max
                        # Analyze code quality for encouragement
                        if not any(keyword in current_code.lower() for keyword in ["todo", "pass", "raise", "notimplemented"]):
                            state["sandbox"]["last_encouragement_time"] = current_time
                            # Don't set next_message here - let it be subtle via signals
                            signals = sandbox.get("signals", [])
                            if "making_progress" not in signals:
                                signals.append("making_progress")
                                state["sandbox"]["signals"] = signals

        # Provide hints if user is stuck or asking for help
        if asking_for_help or is_stuck:
            exercise_hints = sandbox.get("exercise_hints", [])
            hints_provided = sandbox.get("hints_provided", [])

            # Only provide a hint if we have hints available and haven't given all of them
            if exercise_hints and len(hints_provided) < len(exercise_hints):
                # Find next hint to provide
                next_hint_index = len(hints_provided)
                next_hint = exercise_hints[next_hint_index]

                # Provide the hint
                hint_message = f"Here's a hint to help you: {next_hint}"
                if asking_for_help:
                    hint_message = f"I see you're looking for help. {hint_message}"
                elif is_stuck:
                    hint_message = f"You seem to be stuck. {hint_message}"

                state["next_message"] = hint_message
                hints_provided.append(next_hint)
                state["sandbox"]["hints_provided"] = hints_provided

                # Update signals
                signals = sandbox.get("signals", [])
                if "needs_help" not in signals:
                    signals.append("needs_help")
                    state["sandbox"]["signals"] = signals

                logger.info(
                    f"Provided hint {next_hint_index + 1}/{len(exercise_hints)} to user")
            elif asking_for_help:
                # All hints given, provide general encouragement
                state["next_message"] = "You're making progress! Try breaking the problem down into smaller steps. If you need to, you can always ask me specific questions about your approach."

        # Update poll time even if no code change
        state["sandbox"]["last_poll_time"] = current_time

        return state

    async def _code_review_node(self, state: InterviewState) -> InterviewState:
        """Execute code, analyze it, and generate feedback."""
        state["last_node"] = "code_review"

        logger.info("Code review node - reviewing submitted code")

        if self._interview_logger:
            self._interview_logger.log_state("code_review_start", state)

        code = state.get("current_code")
        if not code:
            state["next_message"] = "I don't see any code to review. Please submit your code."
            return state

        # Check if submitted code matches the exercise provided
        sandbox = state.get("sandbox", {})
        exercise_description = sandbox.get("exercise_description", "")
        initial_code = sandbox.get("initial_code", "")

        exercise_mismatch_note = ""
        if exercise_description and initial_code:
            # Use LLM to check if code matches exercise
            client = self._get_openai_client()
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

                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a code reviewer. Analyze if submitted code matches the exercise."},
                        {"role": "user", "content": check_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )

                import json
                check_result = json.loads(response.choices[0].message.content)

                if not check_result.get("matches_exercise", True):
                    reason = check_result.get(
                        "reason", "The code doesn't appear to match the exercise.")
                    exercise_mismatch_note = f"\n\nNote: I notice you submitted code that doesn't match the exercise I provided ({exercise_description[:100]}...). I'll review what you submitted, but I'd also like to see your solution to the original exercise when you're ready."
                    logger.warning(f"Code mismatch detected: {reason}")
            except Exception as e:
                logger.warning(f"Failed to check exercise match: {e}")

        # Update sandbox state
        state["sandbox"]["is_active"] = True
        state["sandbox"]["last_activity_ts"] = datetime.utcnow().timestamp()
        state["sandbox"]["signals"].append("code_submitted")

        language_str = state.get("current_language", "python").lower()
        try:
            sandbox_language = SandboxLanguage(language_str)
        except ValueError:
            sandbox_language = SandboxLanguage.PYTHON

        sandbox_service = self._get_sandbox_service()

        try:
            execution_result = await sandbox_service.execute_code(
                code=code,
                language=sandbox_language,
            )

            exec_result_dict = execution_result.to_dict()
            state["code_execution_result"] = exec_result_dict

            # Analyze code quality
            conversation_summary = self._build_conversation_context(state)
            job_context = self._build_job_context(state)
            code_quality = await self._code_analyzer.analyze_code(
                code=code,
                language=language_str,
                execution_result=exec_result_dict,
                context={
                    "question": state.get("current_question", ""),
                    "conversation_summary": conversation_summary,
                    "job_description": job_context,  # Include job requirements
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

            # Generate feedback message
            feedback_message = await self._code_analyzer.generate_code_feedback_message(
                code_quality=code_quality,
                execution_result=exec_result_dict,
            )

            followup_question = await self._code_analyzer.generate_adaptive_question(
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

            # Store submission
            submission = {
                "code": code,
                "language": language_str,
                "execution_result": exec_result_dict,
                "code_quality": state["code_quality"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            state["code_submissions"].append(submission)
            state["sandbox"]["submissions"].append(submission)

            # Record metrics
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

    # ========================================================================
    # MAIN EXECUTION FLOW
    # ========================================================================

    async def execute_step(
        self,
        state: InterviewState,
        user_response: str | None = None,
        code: str | None = None,
        language: str | None = None,
    ) -> InterviewState:
        """
        Execute one step of the interview workflow with robust state management.

        Flow: initialize → detect_intent → decide → [action nodes] → checkpoint

        Args:
            state: Current interview state
            user_response: Optional user response (if this is a user turn)
            code: Optional code submission to review
            language: Optional programming language for code submission

        Returns:
            Updated state
        """
        # Initialize if needed
        if not state.get("last_node"):
            state = await self._initialize_node(state)

        # Log conversation turn
        if self._interview_logger and user_response:
            self._interview_logger.log_conversation_turn(
                state.get("turn_count", 0),
                user_response,
                None  # Assistant message not yet generated
            )

        # Handle code submission
        if code:
            state["current_code"] = code
            if language:
                state["current_language"] = language
            logger.info(
                f"Code submission received for interview {state.get('interview_id')}")
            if self._interview_logger:
                self._interview_logger.log_state("code_submission", state)
            state = await self._code_review_node(state)

            # Log conversation turn with assistant response
            if self._interview_logger:
                self._interview_logger.log_conversation_turn(
                    state.get("turn_count", 0),
                    None,
                    state.get("next_message")
                )
            return state

        # Check for code changes if sandbox is active (polling)
        if state.get("sandbox", {}).get("is_active"):
            state = await self._check_sandbox_code_changes(state)

        # Add user response if provided
        if user_response:
            state["last_response"] = user_response
            if "conversation_history" not in state:
                state["conversation_history"] = []
            state["conversation_history"].append({
                "role": "user",
                "content": user_response,
                "timestamp": datetime.utcnow().isoformat(),
            })
            state["turn_count"] = state.get("turn_count", 0) + 1

            # CRITICAL: Detect user intent FIRST (before deciding)
            state = await self._detect_user_intent_node(state)

        # Log state before decision
        if self._interview_logger:
            self._interview_logger.log_state("pre_decision", state)

        # Decision node
        state = await self._decide_next_action(state)

        # Log state after decision
        if self._interview_logger:
            self._interview_logger.log_state("post_decision", state)

        action = state.get("_next_action", "question")
        should_evaluate = state.get("_should_evaluate", False)

        # Execute the decided action
        if action == "greeting":
            state = await self._greeting_node(state)
        elif action == "question":
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = await self._question_node(state)
        elif action == "followup":
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = await self._followup_node(state)
        elif action == "transition":
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = await self._transition_node(state)
            # Transition always followed by question
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = await self._question_node(state)
        elif action == "sandbox_guidance":
            state = await self._sandbox_guidance_node(state)
        elif action == "code_review":
            state = await self._code_review_node(state)
        elif action == "evaluation" or should_evaluate:
            state = await self._evaluation_node(state)
            # Evaluation always followed by closing
            state = await self._closing_node(state)
        elif action == "closing":
            state = await self._closing_node(state)

        # Clean up temporary state
        state.pop("_next_action", None)
        state.pop("_should_evaluate", None)

        # Note: Checkpointing should happen here (after node execution)
        # See checkpointing service for implementation

        return state

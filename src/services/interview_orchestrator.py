"""LangGraph-based interview orchestrator with robust state management."""

import logging
import json
import uuid
from typing import Optional
from datetime import datetime
from openai import AsyncOpenAI
import instructor

from src.core.config import settings
from src.services.response_analyzer import ResponseAnalyzer
from src.services.code_analyzer import CodeAnalyzer
from src.services.sandbox_service import SandboxService, Language as SandboxLanguage
from src.services.code_metrics import get_code_metrics
from src.services.feedback_generator import FeedbackGenerator
from src.services.interview_logger import InterviewLogger

# Import types and helpers from refactored modules
from src.services.orchestrator.types import (
    InterviewState, QuestionRecord, UserIntent, ResumeExploration,
    SandboxState, UserIntentDetection, NextActionDecision, QuestionGeneration
)
from src.services.orchestrator.context_builders import (
    build_decision_context, build_job_context, build_resume_context, build_conversation_context
)
from src.services.orchestrator.resume_exploration import (
    initialize_resume_exploration, find_unexplored_anchor, extract_topics_from_exploration
)
from src.services.orchestrator.intent_detection import detect_user_intent
from src.services.orchestrator.nodes import NodeHandler

logger = logging.getLogger(__name__)


# Types are now imported from orchestrator.types


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
        self._node_handler: Optional[NodeHandler] = None

    def set_interview_logger(self, logger: InterviewLogger):
        """Set the interview logger for debugging."""
        self._interview_logger = logger
        # Recreate node handler with updated logger
        if self._node_handler:
            self._node_handler.interview_logger = logger

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    def _get_sandbox_service(self):
        if self._sandbox_service is None:
            self._sandbox_service = SandboxService()
        return self._sandbox_service

    def _get_node_handler(self) -> NodeHandler:
        """Get or create node handler with all dependencies."""
        if self._node_handler is None:
            self._node_handler = NodeHandler(
                openai_client=self._get_openai_client(),
                response_analyzer=self._response_analyzer,
                code_analyzer=self._code_analyzer,
                feedback_generator=self._feedback_generator,
                sandbox_service=self._get_sandbox_service(),
                interview_logger=self._interview_logger,
                is_duplicate_question=self._is_duplicate_question,
            )
        return self._node_handler

    # ========================================================================
    # CONTEXT BUILDERS (Read-only context injection)
    # ========================================================================

    # Context builders and resume exploration helpers are now in separate modules
    # Use the imported functions directly

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

        # Layer 3: Semantic similarity (word overlap - improved threshold)
        # Note: In production, consider using embeddings for better semantic similarity detection
        question_words = set(normalized.split())
        # Filter out common stop words for better comparison
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "is", "was", "are", "were", "been", "be", "have", "has", "had", "do",
                      "does", "did", "will", "would", "could", "should", "may", "might", "can", "this", "that", "these", "those", "what", "which", "who", "whom", "whose", "where", "when", "why", "how"}
        question_words_filtered = question_words - stop_words
        for q in questions_asked:
            existing_words = set(q["text"].lower().split())
            existing_words_filtered = existing_words - stop_words
            if len(question_words_filtered) == 0 or len(existing_words_filtered) == 0:
                continue
            overlap = len(question_words_filtered & existing_words_filtered) / \
                max(len(question_words_filtered), len(existing_words_filtered))
            # 75% word overlap (lowered from 80% for better detection)
            if overlap > 0.75:
                return True

        return False

    # ========================================================================
    # DECISION NODE
    # ========================================================================
    # All other nodes (initialize, greeting, question, followup, transition,
    # evaluation, closing, sandbox_guidance, code_review) are now in
    # orchestrator.nodes.NodeHandler

    async def _decide_next_action(self, state: InterviewState) -> InterviewState:
        """Data-driven decision node with structured signals."""
        state["last_node"] = "decide"

        # Log detected intent for LLM context (but don't hard-route)
        active_request = state.get("active_user_request")
        if active_request:
            if self._interview_logger:
                self._interview_logger.log_intent_detection(
                    state.get("last_response", ""),
                    active_request
                )

        # Build full context for LLM decision
        decision_ctx = build_decision_context(state, self._interview_logger)
        conversation_context = build_conversation_context(
            state, self._interview_logger)
        resume_context = build_resume_context(state)

        client = self._get_openai_client()

        # Get answer quality (informational, not a hard rule)
        answer_quality = 0.0
        if state.get("last_response") and state.get("current_question"):
            try:
                analysis = await self._response_analyzer.analyze_answer(
                    state.get("current_question", ""),
                    state.get("last_response", ""),
                    {"resume_context": state.get("resume_structured", {})},
                )
                answer_quality = analysis.quality_score
                state["answer_quality"] = answer_quality
            except Exception:
                pass

        # Get full conversation history (not truncated)
        conversation_history = state.get("conversation_history", [])
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}"
            # Last 20 messages for full context
            for msg in conversation_history[-20:]
        ])

        # Build user intent info for context
        intent_info = ""
        if active_request:
            intent_info = f"\nDetected User Intent: {active_request.get('type')} (confidence: {active_request.get('confidence', 0):.2f})\nUser's last response: {state.get('last_response', '')}\n"
            if active_request.get('metadata'):
                intent_info += f"Intent metadata: {json.dumps(active_request.get('metadata'), indent=2)}\n"

        prompt = f"""You are an experienced interviewer deciding the next action. You have full context of the conversation and can route to any node as needed.

FULL CONVERSATION HISTORY:
{conversation_text}

CURRENT STATE:
- Turn: {decision_ctx['turn']}
- Phase: {decision_ctx['phase']}
- Questions Asked: {decision_ctx['questions_count']}
- Last Node: {state.get('last_node', 'None')}
- Answer Quality (last response): {answer_quality:.2f}
- Sandbox Active: {state.get('sandbox', {}).get('is_active', False)}
- Current Code: {'Yes' if state.get('current_code') else 'No'}
{intent_info}
RESUME COVERAGE:
{json.dumps(decision_ctx['resume_coverage'], indent=2, default=str)}

AVAILABLE NODES AND THEIR CAPABILITIES:

- **greeting**: Welcome message (only if this is truly the first interaction)

- **question**: Ask a new question about resume/job/experience. Use this to explore their background naturally.

- **followup**: Ask a follow-up to dig deeper into their last answer. Use when you want more details or clarification.

- **transition**: Smoothly move to a new topic. Use when you've covered enough on current topic and want to explore something else.

- **sandbox_guidance**: Guide user to write code. This node has powerful capabilities:
  * Can AUTOMATICALLY generate coding exercises based on job requirements and resume
  * Provides starter code with function signatures and docstrings
  * Can provide hints if user gets stuck (monitors code changes in real-time)
  * Use this when:
    - User wants to write code (intent: write_code)
    - Job requires coding skills and you want to assess them
    - Conversation naturally leads to technical discussion
    - You want to proactively offer a coding challenge (especially for technical roles)
  * The system will automatically generate an appropriate exercise if the job involves coding

- **code_review**: Review and provide feedback on submitted code. This node has powerful capabilities:
  * EXECUTES the code and sees actual results
  * Analyzes code quality: correctness, efficiency, readability, best practices
  * Provides detailed feedback with strengths and weaknesses
  * Generates adaptive follow-up questions based on the code
  * Can detect if code matches the exercise provided
  * Use this when user submits code (automatically triggered) or when you want to review their code

- **evaluation**: Generate comprehensive interview evaluation. Use when interview feels complete.

- **closing**: End the interview with closing message. Use after evaluation or when interview is complete.

YOUR TASK:
Based on the FULL conversation context above, decide what action makes the most sense RIGHT NOW. 

You have access to powerful tools - use them when appropriate:
- For technical roles, you can proactively offer coding exercises via sandbox_guidance
- You can provide hints and monitor code progress automatically
- You can execute and analyze code with detailed feedback via code_review
- Don't be limited to just asking questions - use the full range of capabilities when it makes sense

Key principles:
- Follow the natural conversation flow - don't force patterns
- Use sandbox_guidance proactively for technical roles, not just when user asks
- Use code_review when code is submitted (it will execute and provide detailed analysis)
- If user wants to code (intent detected), use sandbox_guidance (it will auto-generate exercise if appropriate)
- If user wants to change topic (intent detected), consider transition
- If user is confused (intent detected), consider followup with clarification
- If conversation feels complete, consider evaluation then closing
- You can ask multiple questions on the same topic if it's productive
- You can return to previous topics if conversation leads there
- Adapt interview length based on conversation quality, not rigid turn counts

Choose the action that best serves the conversation: greeting, question, followup, transition, closing, evaluation, sandbox_guidance, code_review"""

        try:
            decision = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=NextActionDecision,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an experienced interviewer with full autonomy and powerful tools. You have access to the complete conversation history and can make decisions based on what feels natural and productive. You have access to a code sandbox system that can generate exercises, execute code, provide hints, and give detailed feedback. For technical roles, proactively use these tools when appropriate - don't wait for the user to ask. Trust your judgment - if the conversation is going well, continue. If it needs a change, make it. If it feels complete, wrap it up. Be adaptive, natural, and conversational. Use all your capabilities when they serve the interview goals.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )

            state["_next_action"] = decision.action
            state["_should_evaluate"] = decision.should_evaluate

        except Exception:
            # Simple fallback - just default to question to keep conversation flowing
            # LLM should handle routing, this is just a safety net
            logger.warning("LLM decision failed, using fallback")
            conversation_history = state.get("conversation_history", [])
            has_assistant_messages = any(
                msg.get("role") == "assistant" for msg in conversation_history)

            if not has_assistant_messages:
                state["_next_action"] = "greeting"
            else:
                state["_next_action"] = "question"
            state["_should_evaluate"] = False

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
            state = await self._get_node_handler().initialize_node(state)

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
            state = await self._get_node_handler().code_review_node(state)

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
            state = await self._get_node_handler().check_sandbox_code_changes(state)

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
            state = await detect_user_intent(state, self._get_openai_client(), self._interview_logger)

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
        node_handler = self._get_node_handler()
        if action == "greeting":
            state = await node_handler.greeting_node(state)
        elif action == "question":
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = await node_handler.question_node(state)
        elif action == "followup":
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = await node_handler.followup_node(state)
        elif action == "transition":
            state["turn_count"] = state.get("turn_count", 0) + 1
            state = await node_handler.transition_node(state)
            # Transition typically followed by question, but let decision node decide next action
            # Don't force it - allow natural flow
        elif action == "sandbox_guidance":
            state = await node_handler.sandbox_guidance_node(state)
        elif action == "code_review":
            state = await node_handler.code_review_node(state)
        elif action == "evaluation" or should_evaluate:
            state = await node_handler.evaluation_node(state)
            # Evaluation typically followed by closing, but let LLM decide if needed
            # Don't force it - LLM can route to closing in next decision if appropriate
        elif action == "closing":
            state = await node_handler.closing_node(state)

        # Clean up temporary state
        state.pop("_next_action", None)
        state.pop("_should_evaluate", None)

        # Note: Checkpointing should happen here (after node execution)
        # See checkpointing service for implementation

        return state

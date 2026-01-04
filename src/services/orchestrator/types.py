"""Type definitions for the interview orchestrator."""

import operator
from typing import TypedDict, Literal, Optional, Annotated
from pydantic import BaseModel, Field


# ============================================================================
# STATE TYPES
# ============================================================================

class QuestionRecord(TypedDict):
    """Record of a question asked during the interview."""
    id: str
    text: str
    source: str  # resume | followup | user_request
    resume_anchor: Optional[str]  # project_1, skill_python, etc.
    aspect: str  # challenges, impact, design, tradeoffs, implementation, etc.
    asked_at_turn: int


class UserIntent(TypedDict):
    """Detected user intent from their response."""
    type: str  # technical_assessment | change_topic | clarify | stop | continue | write_code | review_code | show_code | no_intent
    confidence: float  # 0.0-1.0
    extracted_from: str  # raw text that triggered this intent
    turn: int
    metadata: Optional[dict]  # Additional context


# Simplified: Just track topics covered, no complex anchor/aspect/depth tracking
# The LLM can handle question generation without this complexity


class SandboxState(TypedDict):
    """State of code sandbox activity."""
    is_active: bool
    last_activity_ts: float  # Unix timestamp
    submissions: list[dict]  # Code submissions with results
    # struggling, confident, refactoring, idle, syntax_errors, rapid_iterations
    signals: list[str]
    initial_code: str  # Code provided by agent (exercise starter)
    exercise_description: str  # Problem description
    exercise_difficulty: str  # easy, medium, hard
    exercise_hints: list[str]  # Hints for the exercise
    last_code_snapshot: str  # Last code seen during polling
    last_poll_time: float  # Timestamp of last poll


class InterviewState(TypedDict):
    """Robust state schema for LangGraph interview workflow with reducers.

    Fields annotated with operator.add use LangGraph reducers for append-only operations.
    This ensures state updates are atomic and prevents last-writer-wins bugs.
    """
    # Core identifiers
    interview_id: int
    user_id: int
    resume_id: int | None
    candidate_name: str | None  # User's name for personalization

    # Conversation - APPEND ONLY (uses reducer)
    turn_count: int
    conversation_history: Annotated[list[dict], operator.add]

    # Questions tracking - APPEND ONLY (uses reducer)
    questions_asked: Annotated[list[QuestionRecord], operator.add]
    current_question: str | None

    # Resume understanding
    resume_structured: dict  # parsed resume data
    # Simple list of topics covered (e.g., ["Project X", "Python", "Team Leadership"])
    # NOTE: This is NOT a reducer field - topics are manually merged in nodes to allow deduplication
    topics_covered: list[str]

    # Job context
    job_description: str | None

    # User intent - APPEND ONLY (uses reducer)
    detected_intents: Annotated[list[UserIntent], operator.add]
    active_user_request: UserIntent | None

    # Sandbox / code
    sandbox: SandboxState

    # Flow control
    phase: str  # intro | exploration | technical | closing
    last_node: str
    next_node: str | None

    # Runtime fields
    answer_quality: float
    next_message: str | None  # AI's next message to send
    last_response: str | None  # User's last response
    current_code: str | None
    code_execution_result: dict | None
    code_quality: dict | None
    # APPEND ONLY (uses reducer)
    code_submissions: Annotated[list[dict], operator.add]
    feedback: dict | None

    # Conversation summary (for memory management)
    conversation_summary: str  # Summarized conversation for long interviews

    # System
    # APPEND ONLY (uses reducer)
    checkpoints: Annotated[list[str], operator.add]


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
    action: Literal[
        "greeting", "question", "followup", "closing",
        "evaluation", "sandbox_guidance", "code_review"
    ] = Field(..., description="What action to take next")
    reasoning: str = Field(...,
                           description="Brief reasoning for this decision")


class QuestionGeneration(BaseModel):
    """Generated question with metadata."""
    question: str = Field(..., description="The question text")
    resume_anchor: Optional[str] = Field(
        None, description="Which resume anchor this relates to")
    aspect: str = Field(...,
                        description="What aspect we're exploring (challenges, impact, etc.)")
    reasoning: str = Field(..., description="Why this question was chosen")

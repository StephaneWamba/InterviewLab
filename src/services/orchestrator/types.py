"""Type definitions for the interview orchestrator."""

from typing import TypedDict, Literal, Optional
from pydantic import BaseModel, Field


# ============================================================================
# STATE TYPES
# ============================================================================

class QuestionRecord(TypedDict):
    """Record of a question asked during the interview."""
    id: str
    text: str
    source: str  # resume | followup | user_request | transition
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


class ResumeExploration(TypedDict):
    """Tracking of how deeply we've explored a resume anchor."""
    anchor_id: str  # project_1, skill_python, etc.
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

    # Questions tracking
    questions_asked: list[QuestionRecord]
    current_question: str | None

    # Resume understanding
    resume_structured: dict  # parsed resume data
    # anchor_id -> exploration
    resume_exploration: dict[str, ResumeExploration]

    # Job context
    job_description: str | None

    # User intent
    detected_intents: list[UserIntent]
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
    action: Literal[
        "greeting", "question", "followup", "transition", "closing",
        "evaluation", "sandbox_guidance", "code_review"
    ] = Field(..., description="What action to take next")
    reasoning: str = Field(...,
                           description="Brief reasoning for this decision")
    should_evaluate: bool = Field(
        default=False, description="Whether to run evaluation before closing"
    )


class ResumeAnchor(BaseModel):
    """Identified resume anchor for exploration."""
    anchor_id: str = Field(...,
                           description="Unique identifier (e.g., project_1, skill_python)")
    anchor_type: Literal["project", "skill", "experience", "education"] = Field(
        ..., description="Type of anchor"
    )
    description: str = Field(..., description="Brief description")


class QuestionGeneration(BaseModel):
    """Generated question with metadata."""
    question: str = Field(..., description="The question text")
    resume_anchor: Optional[str] = Field(
        None, description="Which resume anchor this relates to")
    aspect: str = Field(...,
                        description="What aspect we're exploring (challenges, impact, etc.)")
    reasoning: str = Field(..., description="Why this question was chosen")

"""Service for managing interview state between database and LangGraph."""

from typing import TYPE_CHECKING
from src.models.interview import Interview

if TYPE_CHECKING:
    from src.services.interview_orchestrator import InterviewState


def interview_to_state(interview: Interview) -> "InterviewState":
    """Convert Interview model to LangGraph state with robust structure."""
    # Extract code submissions from conversation history
    code_submissions = []
    if interview.conversation_history:
        for msg in interview.conversation_history:
            if msg.get("metadata", {}).get("type") == "code_review":
                code_submissions.append({
                    "code": msg.get("metadata", {}).get("code", ""),
                    "language": msg.get("metadata", {}).get("language", "python"),
                    "execution_result": msg.get("metadata", {}).get("execution_result"),
                    "code_quality": msg.get("metadata", {}).get("code_quality"),
                    "timestamp": msg.get("timestamp"),
                })
    
    # Extract sandbox submissions
    sandbox_submissions = []
    for submission in code_submissions:
        sandbox_submissions.append(submission)
    
    # Initialize resume exploration (will be populated by orchestrator if needed)
    resume_exploration = {}
    
    # Extract checkpoints from conversation history
    checkpoints = []
    if interview.conversation_history:
        for msg in interview.conversation_history:
            if (msg.get("role") == "system" and 
                msg.get("content", "").startswith("CHECKPOINT:")):
                checkpoint_id = msg.get("content", "").replace("CHECKPOINT: ", "")
                checkpoints.append(checkpoint_id)
    
    # Build state with new robust structure
    state: "InterviewState" = {
        "interview_id": interview.id,
        "user_id": interview.user_id,
        "resume_id": interview.resume_id,
        "resume_context": interview.resume_context or {},
        "resume_structured": interview.resume_context or {},  # Same for now
        "job_description": interview.job_description,
        "conversation_history": interview.conversation_history or [],
        "turn_count": interview.turn_count,
        "questions_asked": [],  # Will be populated from conversation_history metadata
        "current_question": None,
        "resume_exploration": resume_exploration,
        "detected_intents": [],
        "active_user_request": None,
        "sandbox": {
            "is_active": len(code_submissions) > 0,
            "last_activity_ts": 0.0,
            "submissions": sandbox_submissions,
            "signals": ["code_submitted"] if code_submissions else [],
            "initial_code": "",
            "exercise_description": "",
            "exercise_difficulty": "medium",
            "exercise_hints": [],
            "last_code_snapshot": "",
            "last_poll_time": 0.0,
        },
        "phase": "intro",
        "last_node": "",
        "next_node": None,
        "checkpoints": checkpoints,
        # Legacy fields
        "answer_quality": 0.0,
        "topics_covered": [],  # Deprecated
        "next_message": None,
        "last_response": None,
        "current_code": None,
        "code_execution_result": None,
        "code_quality": None,
        "code_submissions": code_submissions,
        "feedback": interview.feedback,
    }
    
    # Extract questions_asked from conversation_history metadata
    if interview.conversation_history:
        for msg in interview.conversation_history:
            if msg.get("role") == "assistant" and msg.get("metadata", {}).get("question_record"):
                question_record = msg["metadata"]["question_record"]
                state["questions_asked"].append(question_record)
    
    return state


def state_to_interview(state: "InterviewState", interview: Interview) -> None:
    """Update Interview model from LangGraph state."""
    interview.conversation_history = state.get("conversation_history", [])
    interview.turn_count = state.get("turn_count", 0)
    interview.feedback = state.get("feedback")
    
    # Update resume_context if resume_structured changed
    if state.get("resume_structured"):
        interview.resume_context = state["resume_structured"]
    
    # Update job_description if present in state (shouldn't change, but for completeness)
    if "job_description" in state:
        interview.job_description = state.get("job_description")
    
    # Note: Full state checkpointing is handled by CheckpointService
    # We only update the essential fields here for backward compatibility

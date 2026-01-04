"""Service for managing interview state between database and LangGraph."""

from typing import TYPE_CHECKING, Optional
from src.models.interview import Interview

if TYPE_CHECKING:
    from src.services.orchestrator.types import InterviewState
    from src.models.user import User


def interview_to_state(interview: Interview, user: Optional["User"] = None) -> "InterviewState":
    """Convert Interview model to LangGraph state with robust structure.

    Args:
        interview: Interview model to convert
        user: Optional User model for extracting candidate name

    Returns:
        InterviewState with all required fields

    Raises:
        ValueError: If interview data is invalid
    """
    import logging
    logger = logging.getLogger(__name__)

    if user and interview.user_id != user.id:
        logger.error(
            f"Interview {interview.id} does not belong to user {user.id}")
        raise ValueError(
            f"Interview {interview.id} does not belong to user {user.id}")

    # Extract data in single pass through conversation_history
    code_submissions = []
    checkpoints = []
    questions_asked = []

    candidate_name = None
    try:
        if user and user.full_name:
            candidate_name = user.full_name
        elif hasattr(interview, 'user') and interview.user and interview.user.full_name:
            candidate_name = interview.user.full_name
        if not candidate_name and interview.resume_context:
            resume_data = interview.resume_context
            if isinstance(resume_data, dict):
                profile = resume_data.get('profile', '')
                if profile and isinstance(profile, str):
                    words = profile.split()
                    if words:
                        candidate_name = words[0]
    except Exception:
        pass

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

            if (msg.get("role") == "system" and
                    msg.get("content", "").startswith("CHECKPOINT:")):
                checkpoint_id = msg.get("content", "").replace("CHECKPOINT: ", "")
                checkpoints.append(checkpoint_id)

            if msg.get("role") == "assistant" and msg.get("metadata", {}).get("question_record"):
                questions_asked.append(msg["metadata"]["question_record"])

    sandbox_submissions = code_submissions.copy()
    resume_exploration = {}

    # Sanitize conversation_history: filter messages with mismatched interview_id or invalid timestamps
    conversation_history = interview.conversation_history or []
    sanitized_history = []
    filtered_count = 0
    for msg in conversation_history:
        if msg.get("role") == "system" and "CHECKPOINT" in msg.get("content", ""):
            continue
        if msg.get("role") and msg.get("content"):
            msg_interview_id = msg.get("metadata", {}).get("interview_id")
            if msg_interview_id and msg_interview_id != interview.id:
                logger.warning(
                    f"Filtering message with wrong interview_id in interview {interview.id}: "
                    f"expected {interview.id}, got {msg_interview_id}"
                )
                filtered_count += 1
                continue
            
            # Validate timestamp to catch messages from previous interviews
            msg_timestamp = msg.get("timestamp")
            if msg_timestamp and interview.created_at:
                try:
                    from datetime import datetime
                    if isinstance(msg_timestamp, str):
                        msg_dt = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
                    else:
                        msg_dt = msg_timestamp
                    
                    if msg_dt < interview.created_at:
                        logger.warning(
                            f"Filtering message with timestamp before interview creation in interview {interview.id}: "
                            f"message: {msg_timestamp}, created: {interview.created_at}"
                        )
                        filtered_count += 1
                        continue
                except Exception:
                    pass
            
            sanitized_history.append(msg)
    
    if filtered_count > 0:
        logger.warning(
            f"Filtered out {filtered_count} potentially contaminated messages from interview {interview.id}"
        )

    state: "InterviewState" = {
        "interview_id": interview.id,
        "user_id": interview.user_id,
        "resume_id": interview.resume_id,
        "candidate_name": candidate_name,
        "resume_structured": interview.resume_context or {},
        "job_description": interview.job_description,
        "conversation_history": sanitized_history,
        "turn_count": interview.turn_count,
        "questions_asked": questions_asked,
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
        "answer_quality": 0.0,
        "next_message": None,
        "last_response": None,
        "current_code": None,
        "code_execution_result": None,
        "code_quality": None,
        "code_submissions": code_submissions,
        "feedback": interview.feedback,
    }

    return state


def state_to_interview(state: "InterviewState", interview: Interview) -> None:
    """Update Interview model from LangGraph state.

    Args:
        state: InterviewState to convert
        interview: Interview model to update

    Raises:
        ValueError: If state interview_id doesn't match interview.id
    """
    import logging
    logger = logging.getLogger(__name__)

    # Validate interview_id to prevent cross-interview data contamination
    state_interview_id = state.get("interview_id")
    if state_interview_id != interview.id:
        logger.error(
            f"State interview_id ({state_interview_id}) does not match interview.id ({interview.id})"
        )
        raise ValueError(
            f"State interview_id ({state_interview_id}) does not match interview.id ({interview.id})"
        )

    state_user_id = state.get("user_id")
    if state_user_id != interview.user_id:
        logger.error(
            f"State user_id ({state_user_id}) does not match interview.user_id ({interview.user_id})"
        )
        raise ValueError(
            f"State user_id ({state_user_id}) does not match interview.user_id ({interview.user_id})"
        )

    interview.conversation_history = state.get("conversation_history", [])
    interview.turn_count = state.get("turn_count", 0)
    interview.feedback = state.get("feedback")

    if state.get("resume_structured"):
        resume_context = state["resume_structured"].copy() if isinstance(
            state["resume_structured"], dict) else {}
        if "sandbox" in state and state["sandbox"]:
            resume_context["_sandbox"] = state["sandbox"]
        interview.resume_context = resume_context

    if "job_description" in state:
        interview.job_description = state.get("job_description")

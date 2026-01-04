"""Context builders for interview orchestrator."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.orchestrator.types import InterviewState


def build_decision_context(state: "InterviewState", interview_logger=None) -> dict:
    """Build context for decision node."""
    ctx = {
        "turn": state["turn_count"],
        "phase": state.get("phase", "exploration"),
        "last_question": state.get("current_question"),
        "questions_asked": [q["text"] for q in state.get("questions_asked", [])],
        "questions_count": len(state.get("questions_asked", [])),
        "active_user_request": state.get("active_user_request"),
        "topics_covered": state.get("topics_covered", []),
        "sandbox_signals": state.get("sandbox", {}).get("signals", []),
        "conversation_length": len(state.get("conversation_history", [])),
    }

    if interview_logger:
        interview_logger.log_context_injection("decision", ctx)

    return ctx


def build_job_context(state: "InterviewState") -> str:
    """Build job description context string.

    Args:
        state: InterviewState to build context from

    Returns:
        Formatted job context string
    """
    job_desc = state.get("job_description")
    if not job_desc:
        return ""
    return f"Job Requirements:\n{job_desc}\n\n"


def build_resume_context(state: "InterviewState") -> str:
    """Build resume context string for prompts.

    Args:
        state: InterviewState to build context from

    Returns:
        Formatted resume context string
    """
    resume_ctx = state.get("resume_structured", {})
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
            f"Skills: {', '.join(resume_ctx['skills'][:10]) if isinstance(resume_ctx['skills'], list) else 'N/A'}"
        )

    return "\n".join(parts) if parts else "No resume details available."


def build_conversation_context(state: "InterviewState", interview_logger=None) -> str:
    """Build conversation context string.

    Args:
        state: InterviewState to build context from
        interview_logger: Optional logger for debugging

    Returns:
        Formatted conversation context string
    """
    history = state.get("conversation_history", [])
    if not history:
        ctx_str = "No conversation yet."
        if interview_logger:
            interview_logger.log_context_injection(
                "conversation", {"messages_count": 0})
        return ctx_str

    context_parts = []
    recent_messages = history[-20:]  # Last 20 messages for full context

    # Filter and format messages
    for msg in recent_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        # Skip checkpoint system messages (they're metadata, not conversation)
        if role == "system" and "CHECKPOINT" in content:
            continue

        # Skip invalid messages
        if not role or not content:
            continue

        context_parts.append(f"{role.upper()}: {content[:200]}")

    ctx_str = "\n".join(context_parts)

    if interview_logger:
        interview_logger.log_context_injection("conversation", {
            "total_messages": len(history),
            "recent_messages_count": len(recent_messages),
            "context_length": len(ctx_str),
            "last_message_role": history[-1].get("role") if history else None,
        })

    return ctx_str

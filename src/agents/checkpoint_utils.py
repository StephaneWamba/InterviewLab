"""Checkpoint utility functions for background state saving.

These functions handle checkpointing interview state in background
tasks to avoid blocking the main conversation flow.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.orchestrator.langgraph_orchestrator import LangGraphInterviewOrchestrator

logger = logging.getLogger(__name__)


async def checkpoint_greeting_in_background(
    state: dict,
    interview_id: int,
    orchestrator: "LangGraphInterviewOrchestrator"
) -> None:
    """Background task to checkpoint greeting state without blocking.

    Args:
        state: Interview state to checkpoint
        interview_id: Interview ID
        orchestrator: Orchestrator instance for logging
    """
    try:
        # Lazy import - only when function is called
        from src.core.database import AsyncSessionLocal
        from src.services.data.checkpoint_service import get_checkpoint_service

        async with AsyncSessionLocal() as bg_db:
            checkpoint_service = get_checkpoint_service()
            checkpoint_id = await checkpoint_service.checkpoint(state, bg_db)

            # Log checkpoint
            if orchestrator._interview_logger:
                orchestrator._interview_logger.log_checkpoint(
                    {"checkpoint_id": checkpoint_id,
                        "turn": state.get("turn_count", 0)},
                    "saved_after_greeting_background"
                )
    except Exception as e:
        logger.warning(
            f"Failed to checkpoint greeting in background: {e}", exc_info=True)
        if orchestrator._interview_logger:
            orchestrator._interview_logger.log_error(
                "checkpoint_greeting_background",
                e,
                {"interview_id": interview_id}
            )

"""Service for checkpointing interview state to PostgreSQL."""

import logging
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.models.interview import Interview
from src.services.orchestrator.types import InterviewState

logger = logging.getLogger(__name__)


class CheckpointService:
    """Service for managing interview state checkpoints."""

    async def checkpoint(
        self,
        state: InterviewState,
        db: AsyncSession,
    ) -> str:
        """
        Save a checkpoint of the interview state.

        Args:
            state: Current interview state
            db: Database session

        Returns:
            Checkpoint ID (timestamp-based)
        """
        try:
            interview_id = state["interview_id"]
            checkpoint_id = datetime.utcnow().isoformat()

            result = await db.execute(
                select(Interview).where(Interview.id == interview_id)
            )
            interview = result.scalar_one_or_none()

            if not interview:
                logger.error(
                    f"Interview {interview_id} not found for checkpointing")
                return checkpoint_id

            state_json = self._serialize_state(state)

            interview.conversation_history = state.get(
                "conversation_history", [])
            interview.turn_count = state.get("turn_count", 0)
            interview.feedback = state.get("feedback")

            checkpoint_metadata = {
                "checkpoint_id": checkpoint_id,
                "last_node": state.get("last_node", ""),
                "phase": state.get("phase", "intro"),
                "state_snapshot": state_json,
            }

            if "checkpoints" not in state:
                state["checkpoints"] = []
            state["checkpoints"].append(checkpoint_id)

            if interview.conversation_history is None:
                interview.conversation_history = []

            checkpoint_msg = {
                "role": "system",
                "content": f"CHECKPOINT: {checkpoint_id}",
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": checkpoint_metadata,
            }

            if (not interview.conversation_history or
                    interview.conversation_history[-1].get("content") != f"CHECKPOINT: {checkpoint_id}"):
                interview.conversation_history.append(checkpoint_msg)

            await db.commit()

            return checkpoint_id

        except Exception as e:
            logger.error(f"Failed to checkpoint state: {e}", exc_info=True)
            await db.rollback()
            raise

    async def restore(
        self,
        interview_id: int,
        db: AsyncSession,
        checkpoint_id: Optional[str] = None,
    ) -> Optional[InterviewState]:
        """
        Restore interview state from a checkpoint.

        Args:
            interview_id: Interview ID
            db: Database session
            checkpoint_id: Optional specific checkpoint ID (defaults to latest)

        Returns:
            Restored state or None if not found
        """
        try:
            result = await db.execute(
                select(Interview).where(Interview.id == interview_id)
            )
            interview = result.scalar_one_or_none()

            if not interview:
                logger.error(
                    f"Interview {interview_id} not found for restoration")
                return None

            # Find checkpoint in conversation_history
            if not interview.conversation_history:
                logger.warning(
                    f"No conversation history for interview {interview_id}")
                return None

            # Search backwards from end (most recent checkpoints are at the end)
            checkpoint_msg = None
            if interview.conversation_history:
                for i in range(len(interview.conversation_history) - 1, -1, -1):
                    msg = interview.conversation_history[i]
                    if (msg.get("role") == "system" and
                            msg.get("content", "").startswith("CHECKPOINT:")):
                        if checkpoint_id is None or checkpoint_id in msg.get("content", ""):
                            checkpoint_msg = msg
                            break

            if checkpoint_msg and checkpoint_msg.get("metadata", {}).get("state_snapshot"):
                state_json = checkpoint_msg["metadata"]["state_snapshot"]
                state = self._deserialize_state(state_json)

                # Validate restored state belongs to this interview to prevent contamination
                restored_interview_id = state.get("interview_id")
                if restored_interview_id != interview_id:
                    logger.error(
                        f"Restored checkpoint has wrong interview_id: "
                        f"expected {interview_id}, got {restored_interview_id}. Rejecting."
                    )
                    return None

                # Sanitize conversation_history: filter messages with mismatched interview_id
                conv_history = state.get("conversation_history", [])
                sanitized_history = []
                for msg in conv_history:
                    if msg.get("role") == "system" and "CHECKPOINT" in msg.get("content", ""):
                        continue
                    if msg.get("role") and msg.get("content"):
                        msg_interview_id = msg.get(
                            "metadata", {}).get("interview_id")
                        if msg_interview_id and msg_interview_id != interview_id:
                            logger.warning(
                                f"Filtering message with wrong interview_id: "
                                f"expected {interview_id}, got {msg_interview_id}"
                            )
                            continue
                        sanitized_history.append(msg)

                state["conversation_history"] = sanitized_history
                state["interview_id"] = interview_id

                return state

        except Exception as e:
            logger.error(f"Failed to restore state: {e}", exc_info=True)
            return None

        except Exception as e:
            logger.error(f"Failed to restore state: {e}", exc_info=True)
            return None

    def _serialize_state(self, state: InterviewState) -> dict:
        """Serialize state to JSON-compatible dict, converting sets to lists."""
        state_dict = dict(state)

        if "resume_exploration" in state_dict:
            for anchor_id, anchor_data in state_dict["resume_exploration"].items():
                if isinstance(anchor_data, dict) and "aspects_covered" in anchor_data:
                    if isinstance(anchor_data["aspects_covered"], set):
                        anchor_data["aspects_covered"] = list(
                            anchor_data["aspects_covered"])

        return json.loads(json.dumps(state_dict, default=str))

    def _deserialize_state(self, state_json: dict) -> InterviewState:
        """Deserialize state from JSON dict, converting lists back to sets."""
        state = dict(state_json)

        if "resume_exploration" in state:
            for anchor_id, anchor_data in state["resume_exploration"].items():
                if isinstance(anchor_data, dict) and "aspects_covered" in anchor_data:
                    if isinstance(anchor_data["aspects_covered"], list):
                        anchor_data["aspects_covered"] = set(
                            anchor_data["aspects_covered"])

        return state  # type: ignore


_checkpoint_service: Optional[CheckpointService] = None


def get_checkpoint_service() -> CheckpointService:
    """Get or create checkpoint service instance."""
    global _checkpoint_service
    if _checkpoint_service is None:
        _checkpoint_service = CheckpointService()
    return _checkpoint_service

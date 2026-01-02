"""Service for checkpointing interview state to PostgreSQL."""

import logging
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.models.interview import Interview
from src.services.interview_orchestrator import InterviewState

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

            # Load interview
            result = await db.execute(
                select(Interview).where(Interview.id == interview_id)
            )
            interview = result.scalar_one_or_none()

            if not interview:
                logger.error(f"Interview {interview_id} not found for checkpointing")
                return checkpoint_id

            # Serialize state to JSON (handle sets by converting to lists)
            state_json = self._serialize_state(state)

            # Update interview with checkpoint data
            # Note: We're storing in the Interview model's JSON fields
            # In production, you might want a separate Checkpoint table
            interview.conversation_history = state.get("conversation_history", [])
            interview.turn_count = state.get("turn_count", 0)
            interview.feedback = state.get("feedback")
            
            # Store full state in a metadata field (if available) or conversation_history metadata
            # For now, we'll store checkpoint info in conversation_history metadata
            checkpoint_metadata = {
                "checkpoint_id": checkpoint_id,
                "last_node": state.get("last_node", ""),
                "phase": state.get("phase", "intro"),
                "state_snapshot": state_json,  # Full state snapshot
            }

            # Add checkpoint to state
            if "checkpoints" not in state:
                state["checkpoints"] = []
            state["checkpoints"].append(checkpoint_id)

            # Store checkpoint metadata in conversation_history as a system message
            # (Alternative: use a separate state_json field in Interview model)
            if interview.conversation_history is None:
                interview.conversation_history = []
            
            # Store checkpoint in a dedicated metadata location
            # We'll add this to the interview's JSON field structure
            # For now, append as a system message (not ideal, but works)
            checkpoint_msg = {
                "role": "system",
                "content": f"CHECKPOINT: {checkpoint_id}",
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": checkpoint_metadata,
            }
            
            # Only append if not already the last message
            if (not interview.conversation_history or 
                interview.conversation_history[-1].get("content") != f"CHECKPOINT: {checkpoint_id}"):
                interview.conversation_history.append(checkpoint_msg)

            await db.commit()
            logger.info(f"Checkpointed state for interview {interview_id} (checkpoint: {checkpoint_id})")
            
            # Log checkpoint details
            logger.debug(f"Checkpoint details - Turn: {state.get('turn_count', 0)}, "
                        f"Last Node: {state.get('last_node', 'unknown')}, "
                        f"Phase: {state.get('phase', 'unknown')}, "
                        f"Conversation History Length: {len(state.get('conversation_history', []))}, "
                        f"Questions Asked: {len(state.get('questions_asked', []))}")
            
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
                logger.error(f"Interview {interview_id} not found for restoration")
                return None

            # Find checkpoint in conversation_history
            if not interview.conversation_history:
                logger.warning(f"No conversation history for interview {interview_id}")
                return None

            # Look for checkpoint messages
            checkpoint_msg = None
            for msg in reversed(interview.conversation_history):
                if (msg.get("role") == "system" and 
                    msg.get("content", "").startswith("CHECKPOINT:")):
                    if checkpoint_id is None or checkpoint_id in msg.get("content", ""):
                        checkpoint_msg = msg
                        break

            if checkpoint_msg and checkpoint_msg.get("metadata", {}).get("state_snapshot"):
                # Restore from checkpoint
                state_json = checkpoint_msg["metadata"]["state_snapshot"]
                state = self._deserialize_state(state_json)
                logger.info(f"Restored state from checkpoint {checkpoint_id or 'latest'}")
                logger.debug(f"Restored checkpoint details - Turn: {state.get('turn_count', 0)}, "
                            f"Last Node: {state.get('last_node', 'unknown')}, "
                            f"Phase: {state.get('phase', 'unknown')}, "
                            f"Conversation History Length: {len(state.get('conversation_history', []))}")
                return state
            else:
                # Fallback: reconstruct from interview data (legacy)
                logger.info(f"No checkpoint found, reconstructing state from interview data")
                return None

        except Exception as e:
            logger.error(f"Failed to restore state: {e}", exc_info=True)
            return None

    def _serialize_state(self, state: InterviewState) -> dict:
        """Serialize state to JSON-compatible dict (converts sets to lists)."""
        state_dict = dict(state)
        
        # Convert sets to lists
        if "resume_exploration" in state_dict:
            for anchor_id, anchor_data in state_dict["resume_exploration"].items():
                if isinstance(anchor_data, dict) and "aspects_covered" in anchor_data:
                    if isinstance(anchor_data["aspects_covered"], set):
                        anchor_data["aspects_covered"] = list(anchor_data["aspects_covered"])
        
        # Convert TypedDict to regular dict
        return json.loads(json.dumps(state_dict, default=str))

    def _deserialize_state(self, state_json: dict) -> InterviewState:
        """Deserialize state from JSON dict (converts lists back to sets)."""
        state = dict(state_json)
        
        # Convert lists back to sets
        if "resume_exploration" in state:
            for anchor_id, anchor_data in state["resume_exploration"].items():
                if isinstance(anchor_data, dict) and "aspects_covered" in anchor_data:
                    if isinstance(anchor_data["aspects_covered"], list):
                        anchor_data["aspects_covered"] = set(anchor_data["aspects_covered"])
        
        return state  # type: ignore


# Global instance
_checkpoint_service: Optional[CheckpointService] = None


def get_checkpoint_service() -> CheckpointService:
    """Get or create checkpoint service instance."""
    global _checkpoint_service
    if _checkpoint_service is None:
        _checkpoint_service = CheckpointService()
    return _checkpoint_service


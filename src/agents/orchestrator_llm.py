"""Custom LLM implementation that uses the interview orchestrator.

This module provides OrchestratorLLM and OrchestratorLLMStream classes
that integrate the interview orchestrator with LiveKit's LLM interface.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from livekit.agents import llm

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.models.interview import Interview
    from src.services.interview_orchestrator import InterviewOrchestrator

logger = logging.getLogger(__name__)


class OrchestratorLLMStream(llm.LLMStream):
    """Custom LLMStream for the interview orchestrator."""

    def __init__(
        self,
        llm_instance: "OrchestratorLLM",
        chat_ctx: llm.ChatContext,
        tools: list[Any],
        conn_options,
    ):
        super().__init__(llm_instance, chat_ctx=chat_ctx,
                         tools=tools, conn_options=conn_options)
        self._llm_instance = llm_instance

    async def _run(self) -> None:
        """Run the orchestrator and push results to the stream."""
        try:
            # Lazy imports - only when method is called (after handshake)
            from src.services.checkpoint_service import CheckpointService
            from src.core.database import AsyncSessionLocal
            from src.models.interview import Interview
            from src.services.state_manager import interview_to_state, state_to_interview
            from sqlalchemy import select

            logger.debug(
                f"OrchestratorLLMStream._run started for interview {self._llm_instance.interview_id}")

            # OPTIMIZATION: Get user message more efficiently
            user_message = ""
            if self._chat_ctx.items:
                # Find the last user message - iterate backwards for efficiency
                for item in reversed(self._chat_ctx.items):
                    if item.type == "message" and item.role == "user":
                        user_message = item.text_content or ""
                        break

            logger.debug(
                f"Processing user message: {user_message[:100] if user_message else '(empty)'}")

            checkpoint_service = CheckpointService()

            # Create separate functions with proper session handling
            async def load_interview():
                """Load interview using the main session."""
                result = await self._llm_instance.db.execute(
                    select(Interview).where(Interview.id ==
                                            self._llm_instance.interview_id)
                )
                return result.scalar_one_or_none()

            async def load_checkpoint():
                """Load checkpoint using a separate session to avoid concurrent operation errors."""
                try:
                    async with AsyncSessionLocal() as checkpoint_db:
                        return await checkpoint_service.restore(
                            self._llm_instance.interview_id, checkpoint_db
                        )
                except Exception as e:
                    logger.warning(f"Failed to restore checkpoint: {e}")
                    return None

            # Parallelize database queries using separate sessions
            interview_result, checkpoint_state = await asyncio.gather(
                load_interview(),
                load_checkpoint(),
                return_exceptions=True
            )

            # Ensure orchestrator is initialized
            if not self._llm_instance._initialized or not self._llm_instance.orchestrator:
                logger.error("OrchestratorLLM not initialized")
                self._event_ch.send_nowait(llm.ChatChunk(
                    id="error",
                    delta=llm.ChoiceDelta(
                        content="I'm sorry, the interview session is not properly initialized.")
                ))
                return

            # Handle interview load result
            if isinstance(interview_result, Exception):
                logger.error(
                    f"Failed to load interview: {interview_result}", exc_info=True)
                self._event_ch.send_nowait(llm.ChatChunk(
                    id="error",
                    delta=llm.ChoiceDelta(
                        content="I'm sorry, I encountered an error loading the interview session.")
                ))
                return

            interview = interview_result
            if not interview:
                logger.error(
                    f"Interview {self._llm_instance.interview_id} not found")
                self._event_ch.send_nowait(llm.ChatChunk(
                    id="error",
                    delta=llm.ChoiceDelta(
                        content="I'm sorry, I couldn't find the interview session.")
                ))
                return

            # Handle checkpoint restore result
            state = None if isinstance(
                checkpoint_state, Exception) else checkpoint_state
            if isinstance(checkpoint_state, Exception):
                logger.warning(
                    f"Failed to restore checkpoint, will initialize from interview: {checkpoint_state}")

            if not state:
                # No checkpoint found, initialize from interview
                logger.debug(
                    f"No checkpoint found, initializing state from interview {self._llm_instance.interview_id}")
                state = interview_to_state(interview)
                if self._llm_instance.orchestrator._interview_logger:
                    self._llm_instance.orchestrator._interview_logger.log_state(
                        "state_initialized_from_interview", state)
            else:
                logger.debug(
                    f"Loaded state from checkpoint for interview {self._llm_instance.interview_id}")
                if self._llm_instance.orchestrator._interview_logger:
                    self._llm_instance.orchestrator._interview_logger.log_checkpoint(
                        {"interview_id": self._llm_instance.interview_id,
                            "state_keys": list(state.keys())},
                        "loaded"
                    )
                    self._llm_instance.orchestrator._interview_logger.log_state(
                        "state_restored_from_checkpoint", state)

            # Execute orchestrator step with user response
            logger.debug("Executing orchestrator step...")
            state = await self._llm_instance.orchestrator.execute_step(state, user_response=user_message)

            # Get the response message
            response = state.get(
                "next_message", "I'm here to help with your interview.")

            logger.debug(f"Generated response (raw): {response[:100]}...")

            # Post-process text for natural TTS delivery
            # Lazy import - only when needed
            from src.agents import tts_utils
            response = tts_utils.normalize_numbers_and_symbols(response)
            response = tts_utils.prepare_text_for_tts(response)

            logger.debug(
                f"Generated response (processed): {response[:100]}...")

            # Update interview and commit
            state_to_interview(state, interview)
            await self._llm_instance.db.commit()

            # Push response to stream FIRST (before checkpointing)
            logger.debug("Sending response chunk to stream for TTS...")
            self._event_ch.send_nowait(llm.ChatChunk(
                id="response",
                delta=llm.ChoiceDelta(content=response)
            ))
            logger.debug("Response chunk sent successfully")

            # Checkpoint in background after response is sent
            asyncio.create_task(self._checkpoint_in_background(
                state, interview, checkpoint_service
            ))

        except Exception as e:
            logger.error(
                f"Error in OrchestratorLLMStream._run: {e}", exc_info=True)
            self._event_ch.send_nowait(llm.ChatChunk(
                id="error",
                delta=llm.ChoiceDelta(
                    content="I'm sorry, I encountered an error. Please try again.")
            ))

    async def _checkpoint_in_background(
        self,
        state: dict,
        interview: "Interview",
        checkpoint_service
    ) -> None:
        """Background task to checkpoint state without blocking response.

        Args:
            state: Interview state to checkpoint
            interview: Interview object (already committed)
            checkpoint_service: Checkpoint service instance to reuse
        """
        try:
            # Lazy import - only when function is called
            from src.core.database import AsyncSessionLocal
            from src.models.interview import Interview
            from sqlalchemy import select

            async with AsyncSessionLocal() as bg_db:
                # Reload interview in background session
                result = await bg_db.execute(
                    select(Interview).where(
                        Interview.id == state["interview_id"])
                )
                bg_interview = result.scalar_one_or_none()

                if not bg_interview:
                    logger.warning(
                        f"Interview {state['interview_id']} not found in background checkpoint task")
                    return

                checkpoint_id = await checkpoint_service.checkpoint(state, bg_db)
                logger.info(
                    f"Checkpointed state in background: {checkpoint_id}")

                # Log checkpoint operation
                if self._llm_instance.orchestrator._interview_logger:
                    self._llm_instance.orchestrator._interview_logger.log_checkpoint(
                        {
                            "checkpoint_id": checkpoint_id,
                            "turn": state.get("turn_count", 0),
                            "last_node": state.get("last_node"),
                            "phase": state.get("phase"),
                        },
                        "saved_background"
                    )
        except Exception as e:
            logger.warning(
                f"Failed to checkpoint state in background: {e}", exc_info=True)
            if self._llm_instance.orchestrator._interview_logger:
                self._llm_instance.orchestrator._interview_logger.log_error(
                    "checkpoint_save_background",
                    e,
                    {"interview_id": self._llm_instance.interview_id}
                )


class OrchestratorLLM(llm.LLM):
    """Custom LLM that uses the interview orchestrator instead of OpenAI.

    Uses two-phase initialization to avoid blocking during handshake.
    """

    def __init__(self, interview_id: int):
        super().__init__()
        self.interview_id = interview_id
        self.db: "AsyncSession | None" = None
        self.orchestrator: "InterviewOrchestrator | None" = None
        self._initialized = False

    async def init(self, db: "AsyncSession"):
        """Initialize orchestrator and load interview state.

        Called after handshake completes to avoid blocking initialization.
        """
        # Lazy imports - only when init is called (after handshake)
        from src.services.interview_orchestrator import InterviewOrchestrator
        from src.services.interview_logger import InterviewLogger

        self.db = db
        self.orchestrator = InterviewOrchestrator()

        # Initialize interview logger
        interview_logger = InterviewLogger(self.interview_id)
        self.orchestrator.set_interview_logger(interview_logger)

        self._initialized = True
        logger.info(
            f"OrchestratorLLM initialized for interview {self.interview_id}")

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[Any] | None = None,
        conn_options=None,
        parallel_tool_calls=None,
        tool_choice=None,
        extra_kwargs=None,
    ) -> llm.LLMStream:
        """Process chat using the interview orchestrator."""
        if not self._initialized:
            raise RuntimeError(
                "OrchestratorLLM must be initialized with init() before use")

        from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

        conn_options = conn_options or DEFAULT_API_CONNECT_OPTIONS

        return OrchestratorLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options
        )

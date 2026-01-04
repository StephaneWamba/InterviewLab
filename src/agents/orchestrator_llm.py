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
    from src.services.orchestrator.langgraph_orchestrator import LangGraphInterviewOrchestrator

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
            from src.services.data.checkpoint_service import CheckpointService
            from src.core.database import AsyncSessionLocal
            from src.models.interview import Interview
            from src.services.data.state_manager import interview_to_state, state_to_interview
            from sqlalchemy import select

            # Rollback any pending transactions to ensure session is in valid state
            if self._llm_instance.db:
                try:
                    await self._llm_instance.db.rollback()
                except Exception as rollback_error:
                    logger.warning(
                        f"Could not rollback session (will use fresh sessions): {rollback_error}")

            user_message = ""
            if self._chat_ctx.items:
                for item in reversed(self._chat_ctx.items):
                    if item.type == "message" and item.role == "user":
                        user_message = item.text_content or ""
                        break

            checkpoint_service = CheckpointService()

            async def load_interview():
                """Load interview using main session with fallback to fresh session and retries."""
                interview_id = self._llm_instance.interview_id
                max_retries = 3
                retry_delay = 0.5  # 500ms delay between retries
                
                for attempt in range(max_retries):
                    try:
                        # Try main session first
                        if self._llm_instance.db:
                            try:
                                await self._llm_instance.db.rollback()
                            except Exception:
                                pass

                            result = await self._llm_instance.db.execute(
                                select(Interview).where(Interview.id == interview_id)
                            )
                            interview = result.scalar_one_or_none()
                            if interview:
                                logger.info(f"Interview {interview_id} found using main session (attempt {attempt + 1})")
                                return interview
                        
                        # Fallback: use fresh session (avoids transaction isolation issues)
                        async with AsyncSessionLocal() as fresh_db:
                            result = await fresh_db.execute(
                                select(Interview).where(Interview.id == interview_id)
                            )
                            interview = result.scalar_one_or_none()
                            if interview:
                                logger.info(f"Interview {interview_id} found using fresh session (attempt {attempt + 1})")
                                # Merge into main session for commit
                                if self._llm_instance.db:
                                    interview = await self._llm_instance.db.merge(interview)
                                return interview
                        
                        # If not found and not last attempt, wait and retry
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Interview {interview_id} not found (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s..."
                            )
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            logger.error(
                                f"Interview {interview_id} not found after {max_retries} attempts. "
                                f"Check if interview exists in database and if DATABASE_URL is correct."
                            )
                            return None
                            
                    except Exception as e:
                        logger.error(
                            f"Error loading interview (attempt {attempt + 1}): {e}", exc_info=True)
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            raise
                
                return None

            async def load_checkpoint():
                """Load checkpoint using separate session to avoid transaction conflicts."""
                try:
                    async with AsyncSessionLocal() as checkpoint_db:
                        return await checkpoint_service.restore(
                            self._llm_instance.interview_id, checkpoint_db
                        )
                except Exception as e:
                    return None

            # Parallelize database queries to improve performance
            interview_result, checkpoint_state = await asyncio.gather(
                load_interview(),
                load_checkpoint(),
                return_exceptions=True
            )

            if not self._llm_instance._initialized or not self._llm_instance.orchestrator:
                logger.error("OrchestratorLLM not initialized")
                self._event_ch.send_nowait(llm.ChatChunk(
                    id="error",
                    delta=llm.ChoiceDelta(
                        content="I'm sorry, the interview session is not properly initialized.")
                ))
                return

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

            # Stop processing if interview is already completed
            if interview.status == "completed":
                self._event_ch.send_nowait(llm.ChatChunk(
                    id="completed",
                    delta=llm.ChoiceDelta(
                        content="This interview has been completed. Thank you for your time!")
                ))
                return

            state = None if isinstance(
                checkpoint_state, Exception) else checkpoint_state
            if isinstance(checkpoint_state, Exception):
                pass  # State already set to None above

            user = None
            try:
                from src.models.user import User
                async with AsyncSessionLocal() as user_db:
                    result = await user_db.execute(
                        select(User).where(User.id == interview.user_id)
                    )
                    user = result.scalar_one_or_none()
            except Exception:
                pass

            if not state:
                state = interview_to_state(interview, user=user)

                if state.get("interview_id") != self._llm_instance.interview_id:
                    logger.error(
                        f"State interview_id ({state.get('interview_id')}) does not match "
                        f"expected interview_id ({self._llm_instance.interview_id})"
                    )
                    raise ValueError("State interview_id mismatch")

                if self._llm_instance.orchestrator._interview_logger:
                    self._llm_instance.orchestrator._interview_logger.log_state(
                        "state_initialized_from_interview", state)
            else:
                # Validate checkpoint belongs to this interview to prevent state contamination
                checkpoint_interview_id = state.get("interview_id")
                if checkpoint_interview_id != self._llm_instance.interview_id:
                    logger.error(
                        f"Checkpoint state interview_id ({checkpoint_interview_id}) does not match "
                        f"expected interview_id ({self._llm_instance.interview_id}). "
                        f"Rejecting checkpoint and reconstructing from interview."
                    )
                    state = interview_to_state(interview, user=user)
                else:
                    # Reload conversation_history from database to get latest code submissions
                    # Checkpoint may be stale if code was submitted via API after checkpoint was saved
                    interview_state = interview_to_state(interview, user=user)
                    state["conversation_history"] = interview_state.get(
                        "conversation_history", [])
                    state["code_submissions"] = interview_state.get(
                        "code_submissions", [])
                    state["feedback"] = interview_state.get("feedback")

                    if self._llm_instance.orchestrator._interview_logger:
                        self._llm_instance.orchestrator._interview_logger.log_checkpoint(
                            {"interview_id": self._llm_instance.interview_id,
                                "state_keys": list(state.keys())},
                            "loaded"
                        )
                        self._llm_instance.orchestrator._interview_logger.log_state(
                            "state_restored_from_checkpoint", state)

            # Execute orchestrator step with user response
            # Code submissions via /submit-code are already in conversation_history
            state = await self._llm_instance.orchestrator.execute_step(state, user_response=user_message)

            if state.get("interview_id") != self._llm_instance.interview_id:
                logger.error(
                    f"State interview_id ({state.get('interview_id')}) changed after execution. "
                    f"Expected {self._llm_instance.interview_id}"
                )
                raise ValueError("State interview_id changed after execution")

            # Extract response: prefer next_message, fallback to conversation_history
            response = state.get("next_message")

            if not response:
                conversation_history = state.get("conversation_history", [])
                for msg in reversed(conversation_history):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        response = msg["content"]
                        break

                if not response:
                    response = "I'm here to help with your interview."
                    logger.warning(
                        "No response found in state or conversation_history, using fallback")

            if not response or not response.strip():
                logger.error("Response is empty or whitespace only!")
                response = "I'm here to help with your interview."

            from src.agents.tts_utils import prepare_text_for_tts
            response_tts = prepare_text_for_tts(response)

            state_to_interview(state, interview)
            try:
                await self._llm_instance.db.commit()
            except Exception as commit_error:
                logger.error(
                    f"Error committing interview update: {commit_error}", exc_info=True)
                try:
                    await self._llm_instance.db.rollback()
                except Exception as rollback_error:
                    logger.error(
                        f"Error rolling back transaction: {rollback_error}", exc_info=True)

            # Send response to TTS stream (checkpointing handled by LangGraph)
            self._event_ch.send_nowait(llm.ChatChunk(
                id="response",
                delta=llm.ChoiceDelta(content=response_tts)
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
            from src.core.database import AsyncSessionLocal
            from src.models.interview import Interview
            from sqlalchemy import select

            async with AsyncSessionLocal() as bg_db:
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
            logger.error(
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
        self.orchestrator: "LangGraphInterviewOrchestrator | None" = None
        self._initialized = False

    async def init(self, db: "AsyncSession"):
        """Initialize orchestrator and load interview state.

        Called after handshake completes to avoid blocking initialization.
        """
        # Lazy imports - only when init is called (after handshake)
        from src.services.orchestrator.langgraph_orchestrator import LangGraphInterviewOrchestrator
        from src.services.logging.interview_logger import InterviewLogger

        self.db = db
        # Use LangGraph orchestrator (production orchestrator with full feature set)
        self.orchestrator = LangGraphInterviewOrchestrator()

        interview_logger = InterviewLogger(self.interview_id)
        self.orchestrator.set_interview_logger(interview_logger)
        self.orchestrator.set_db_session(db)

        self._initialized = True

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

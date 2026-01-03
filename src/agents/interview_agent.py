"""LiveKit agent for interview voice conversations.

This agent connects to LiveKit rooms and handles voice conversations
by integrating with the interview orchestrator.

CRITICAL: This module must import in <100ms for LiveKit handshake.
All heavy imports are lazy-loaded after handshake completes.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Only stdlib + livekit core imports at module level
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    cli,
    llm,
    stt,
    tts,
    vad,
)
from livekit.agents.voice import room_io

# Type hints only - never executed at runtime
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.models.interview import Interview
    from src.services.interview_orchestrator import InterviewOrchestrator

# Add src to path for imports (only if needed, should be in PYTHONPATH)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


def prepare_text_for_tts(text: str) -> str:
    """
    Prepare text for natural TTS delivery.

    Based on best practices:
    - Normalize punctuation for better prosody
    - Fix common formatting issues
    - Ensure proper sentence structure
    """
    if not text:
        return text

    # Strip whitespace
    text = text.strip()

    # Replace colons with periods (colons can sound awkward in TTS)
    text = text.replace(":", ".")

    # Normalize em dashes to commas (better for natural pauses)
    text = text.replace("—", ",")
    text = text.replace("–", ",")

    # Remove multiple spaces
    while "  " in text:
        text = text.replace("  ", " ")

    # Ensure sentences end with proper punctuation
    if text and text[-1] not in ".!?":
        text += "."

    return text


def normalize_numbers_and_symbols(text: str) -> str:
    """
    Normalize numbers and symbols for better TTS pronunciation.

    This helps with:
    - Percentage pronunciation (5% -> "5 percent")
    - Clean up common formatting issues
    """
    import re

    # Normalize percentages: 5% -> 5 percent (for better pronunciation)
    text = re.sub(r'(\d+)%', r'\1 percent', text)

    return text


def split_into_sentences(text: str, max_length: int = 200) -> list[str]:
    """
    Split text into sentences for chunked delivery.

    Shorter sentences = better TTS naturalness
    Max length ensures we don't send overly long chunks
    """
    import re

    # Split on sentence boundaries (. ! ?)
    sentences = re.split(r'([.!?]+)', text)

    # Recombine sentences with their punctuation
    result = []
    i = 0
    while i < len(sentences):
        sentence = sentences[i].strip()
        if i + 1 < len(sentences):
            punctuation = sentences[i + 1]
            sentence += punctuation
            i += 2
        else:
            i += 1

        if not sentence:
            continue

        # If sentence is too long, split on commas or conjunctions
        if len(sentence) > max_length:
            # Try splitting on commas first
            parts = re.split(r'(,+)', sentence)
            current = ""
            for part in parts:
                if len(current + part) > max_length and current:
                    result.append(current.strip())
                    current = part
                else:
                    current += part
            if current:
                result.append(current.strip())
        else:
            result.append(sentence)

    return [s.strip() for s in result if s.strip()]


async def _checkpoint_greeting_in_background(
    state: dict,
    interview_id: int,
    orchestrator: "InterviewOrchestrator"
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
        from src.services.checkpoint_service import get_checkpoint_service

        async with AsyncSessionLocal() as bg_db:
            checkpoint_service = get_checkpoint_service()
            checkpoint_id = await checkpoint_service.checkpoint(state, bg_db)
            logger.info(
                f"Checkpointed greeting state in background: {checkpoint_id}")

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
            response = normalize_numbers_and_symbols(response)
            response = prepare_text_for_tts(response)

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


# Create server instance (OK at module level - AgentServer is lightweight)
server = AgentServer()

# Per-process VAD cache (lazy loaded, async, with lock protection)
_vad: vad.VAD | None = None
_vad_lock = asyncio.Lock()


async def get_vad() -> vad.VAD | None:
    """Get VAD instance with per-process lazy caching.

    Loads Silero VAD asynchronously in executor to avoid blocking event loop.
    Returns None if loading fails (graceful degradation).

    CRITICAL: Only called after handshake completes.
    """
    global _vad

    # Fast path - already loaded
    if _vad is not None:
        return _vad

    # Lock-protected lazy load (only once per process)
    async with _vad_lock:
        # Double-check after acquiring lock
        if _vad is not None:
            return _vad

        try:
            # Lazy import - only when function is called (after handshake)
            from livekit.plugins import silero

            logger.info("Loading VAD model asynchronously...")
            loop = asyncio.get_running_loop()
            _vad = await loop.run_in_executor(None, silero.VAD.load)
            logger.info("VAD model loaded successfully")
            return _vad
        except Exception as e:
            logger.error(f"VAD loading failed: {e}", exc_info=True)
            # Return None for graceful degradation
            return None


class AgentResources:
    """Resource container for agent components with proper cleanup."""

    def __init__(self):
        self.db: "AsyncSession | None" = None
        self.orchestrator_llm: OrchestratorLLM | None = None
        self.tts: tts.TTS | None = None
        self.stt: stt.STT | None = None
        self.vad: vad.VAD | None = None
        self.session: AgentSession | None = None

    async def aclose(self):
        """Clean up all resources."""
        if self.db:
            await self.db.close()
            self.db = None
        logger.debug("Agent resources cleaned up")


async def bootstrap_resources(ctx: JobContext, interview_id: int) -> AgentResources:
    """Bootstrap all agent resources after handshake completes.

    This is the SAFE ZONE - handshake is complete, we can do heavy operations.
    All heavy imports happen here, not at module level.
    """
    import time
    t0 = time.monotonic()
    logger.info(f"bootstrap_start (interview_id={interview_id})")

    resources = AgentResources()

    try:
        # Lazy imports - only when bootstrap is called (after handshake)
        from src.core.database import AsyncSessionLocal
        from src.core.config import settings
        from livekit.plugins import openai

        # Create database session (async-safe, per-process pool)
        resources.db = AsyncSessionLocal()
        logger.debug("Database session created")

        # Create and initialize orchestrator LLM (two-phase init)
        resources.orchestrator_llm = OrchestratorLLM(interview_id)
        await resources.orchestrator_llm.init(resources.db)
        logger.debug("Orchestrator LLM initialized")

        # Create TTS with graceful degradation
        try:
            resources.tts = openai.TTS(
                voice=settings.OPENAI_TTS_VOICE or "alloy",
                model=settings.OPENAI_TTS_MODEL or "tts-1-hd"
            )
            logger.debug("TTS instance created")
        except Exception as e:
            logger.exception("TTS creation failed, will retry later")
            resources.tts = None

        # Create STT
        try:
            resources.stt = openai.STT()
            logger.debug("STT instance created")
        except Exception as e:
            logger.exception("STT creation failed, will retry later")
            resources.stt = None

        # VAD DISABLED - Skip loading entirely to avoid timeout issues
        # Silero VAD inference takes 4-7 seconds, causing "process is unresponsive" warnings
        # Agent will work fine without VAD in controlled interview environments
        resources.vad = None
        logger.info(
            "VAD disabled - skipping Silero VAD loading to avoid performance issues")

        elapsed = time.monotonic() - t0
        logger.info(
            f"bootstrap_complete (elapsed={elapsed:.3f}s, interview_id={interview_id})")
        return resources

    except Exception as e:
        logger.error(f"Bootstrap failed: {e}", exc_info=True)
        await resources.aclose()
        raise


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    """Entry point for the LiveKit agent job.

    Production-ready pattern:
    1. Handshake completes at ctx.connect() (must be fast)
    2. Bootstrap resources after handshake (heavy operations safe here)
    3. Start session with all resources ready
    4. Clean up on exit
    """
    import time
    t0 = time.monotonic()

    # Log immediately (before any imports or heavy operations)
    try:
        room_name = ctx.room.name if hasattr(ctx, 'room') else 'no-room'
        logger.info(f"entrypoint_called (room={room_name})")
    except Exception:
        pass

    logger.info("handshake_start")

    # CRITICAL: ctx.connect() must return quickly (handshake completes here)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    t_connect = time.monotonic()
    logger.info(f"ctx_connected (elapsed={(t_connect - t0):.3f}s)")

    # ---- SAFE ZONE: Handshake complete, can do heavy imports now ----

    # Extract interview_id from room name (format: "interview-{id}")
    try:
        interview_id = int(ctx.room.name.replace("interview-", ""))
    except ValueError:
        logger.error(
            f"Could not extract interview_id from room name: {ctx.room.name}")
        return

    logger.info(
        f"Agent connected to room: {ctx.room.name} (interview_id={interview_id})")

    resources: AgentResources | None = None

    try:
        # Bootstrap all resources (VAD, DB, orchestrator, TTS, STT)
        resources = await bootstrap_resources(ctx, interview_id)

        # Create agent session with bootstrapped resources
        # DISABLED: VAD causing 4-7 second inference delays, making processes unresponsive
        # resources.vad loaded but not used - Silero VAD too slow for real-time voice processing
        resources.session = AgentSession(
            vad=None,  # Disabled - causes unresponsive processes due to slow inference
            stt=resources.stt,
            llm=resources.orchestrator_llm,
            tts=resources.tts,
        )

        # Create agent with instructions
        agent = Agent(
            instructions=(
                "You are a professional interviewer conducting a technical interview. "
                "IMPORTANT: The candidate has access to a code sandbox where they can write and submit code. "
                "If the candidate asks to write code, show code, or review code, guide them to use the sandbox. "
                "Always acknowledge and respond to candidate requests, especially requests related to code or the sandbox. "
                "All your responses will be SPOKEN ALOUD. "
                "Therefore, use short, clear sentences and natural, conversational language. "
                "Ensure your questions are focused and easy to understand when spoken."
            ),
        )

        # Start the session
        t_session_start = time.monotonic()
        await resources.session.start(
            agent=agent,
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_output=True,
                text_output=True,
            )
        )

        t_session_ready = time.monotonic()
        logger.info(
            f"session_started (elapsed={(t_session_ready - t_session_start):.3f}s)")
        logger.info(
            "AgentSession started with transcription enabled. "
            "Transcriptions will be sent to frontend via lk.transcription text stream."
        )

        t_init_total = time.monotonic() - t0
        logger.info(
            f"init_done (elapsed={t_init_total:.3f}s, interview_id={interview_id})")

        # Listen for test audio requests via data messages
        def handle_data_message(data_packet):
            """Handle data messages, including test audio requests."""
            try:
                import json
                import asyncio
                if data_packet.user and data_packet.user.payload:
                    data = data_packet.user.payload
                    message = json.loads(data.decode('utf-8'))
                    if message.get('type') == 'test_audio' and resources.session:
                        logger.info("Received test audio request")
                        test_message = prepare_text_for_tts(
                            "Hello! This is an audio test. Can you hear me clearly?"
                        )
                        asyncio.create_task(
                            resources.session.say(test_message))
            except Exception as e:
                logger.debug(f"Error processing data message: {e}")

        ctx.room.on("data_received", handle_data_message)

        # Send initial greeting after session starts
        try:
            logger.info(
                f"Checking for interview {interview_id} to send greeting")

            # Lazy imports - only when needed (after handshake)
            from src.services.checkpoint_service import get_checkpoint_service
            from src.core.database import AsyncSessionLocal
            from src.models.interview import Interview
            from src.services.state_manager import interview_to_state, state_to_interview
            from sqlalchemy import select

            checkpoint_service = get_checkpoint_service()

            async def load_interview_for_greeting():
                """Load interview using the main session."""
                if not resources.db:
                    return None
                result = await resources.db.execute(select(Interview).where(Interview.id == interview_id))
                return result.scalar_one_or_none()

            async def load_checkpoint_for_greeting():
                """Load checkpoint using a separate session."""
                try:
                    async with AsyncSessionLocal() as checkpoint_db:
                        return await checkpoint_service.restore(interview_id, checkpoint_db)
                except Exception as e:
                    logger.warning(
                        f"Failed to restore checkpoint for greeting: {e}")
                    return None

            interview_result, existing_state = await asyncio.gather(
                load_interview_for_greeting(),
                load_checkpoint_for_greeting(),
                return_exceptions=True
            )

            # Handle results
            if isinstance(interview_result, Exception):
                logger.error(
                    f"Failed to load interview for greeting: {interview_result}", exc_info=True)
                interview = None
            else:
                interview = interview_result

            if isinstance(existing_state, Exception):
                logger.warning(
                    f"Failed to restore checkpoint for greeting: {existing_state}")
                existing_state = None

            if interview and interview.status == "in_progress":
                logger.info(
                    f"Interview {interview_id} found, status: {interview.status}")

                has_any_messages = interview.conversation_history and len(
                    interview.conversation_history) > 0

                if not has_any_messages and not existing_state:
                    logger.info(
                        "No conversation history or checkpoint, generating initial greeting")
                    if not resources.orchestrator_llm or not resources.orchestrator_llm.orchestrator:
                        logger.error(
                            "Orchestrator not initialized, cannot send greeting")
                    else:
                        state = interview_to_state(interview)
                        state = await resources.orchestrator_llm.orchestrator.execute_step(state)
                        greeting = state.get("next_message")

                        if resources.orchestrator_llm.orchestrator._interview_logger:
                            resources.orchestrator_llm.orchestrator._interview_logger.log_state(
                                "greeting_generated", state)

                        if greeting:
                            greeting = normalize_numbers_and_symbols(greeting)
                            greeting = prepare_text_for_tts(greeting)

                            logger.info(
                                f"Sending greeting (processed): {greeting[:100]}...")
                            state_to_interview(state, interview)
                            if resources.db:
                                await resources.db.commit()

                            if resources.session:
                                await resources.session.say(greeting)
                            logger.info("Greeting sent successfully")

                            asyncio.create_task(
                                _checkpoint_greeting_in_background(
                                    state, interview_id, resources.orchestrator_llm.orchestrator)
                            )
                        else:
                            logger.warning(
                                "No greeting generated from orchestrator")
                else:
                    logger.info(
                        f"Interview has conversation history or checkpoint (messages: {len(interview.conversation_history) if interview.conversation_history else 0}), "
                        f"skipping automatic greeting. Agent will respond when user speaks.")
            else:
                logger.warning(
                    f"Interview {interview_id} not found or not in_progress: {interview.status if interview else 'not found'}")
        except Exception as e:
            logger.error(
                f"Error sending initial greeting: {e}", exc_info=True)

        # Wait for room to disconnect (or timeout)
        try:
            await asyncio.sleep(3600)  # Run for up to 1 hour
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.error(f"Agent entrypoint error: {e}", exc_info=True)
    finally:
        # Clean up all resources
        if resources:
            await resources.aclose()


if __name__ == "__main__":
    cli.run_app(server)

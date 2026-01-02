"""LiveKit agent for interview voice conversations.

This agent connects to LiveKit rooms and handles voice conversations
by integrating with the interview orchestrator.
"""

from src.models.interview import Interview
from src.services.state_manager import interview_to_state, state_to_interview
from src.services.interview_orchestrator import InterviewOrchestrator
from src.services.checkpoint_service import get_checkpoint_service
from src.core.config import settings
from src.core.database import AsyncSessionLocal
import asyncio
import logging
import sys
from pathlib import Path
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    cli,
    llm,
    stt,
    tts,
    vad,
    voice,
)
from livekit.agents.voice import room_io
from typing import Any
from livekit.plugins import openai, silero
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Add src to path for imports
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

    # Note: Year normalization is complex and can break in edge cases
    # Leaving it out for now - TTS handles years reasonably well
    # If needed, can be added later with careful testing

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
            logger.info(
                f"OrchestratorLLMStream._run started for interview {self._llm_instance.interview_id}")

            # Get the user's last message from chat context
            user_message = ""
            if self._chat_ctx.items:
                # Find the last user message
                for item in reversed(self._chat_ctx.items):
                    if item.type == "message" and item.role == "user":
                        user_message = item.text_content or ""
                        break

            logger.info(
                f"Processing user message: {user_message[:100] if user_message else '(empty)'}")

            # Load interview from database
            result = await self._llm_instance.db.execute(
                select(Interview).where(Interview.id ==
                                        self._llm_instance.interview_id)
            )
            interview = result.scalar_one_or_none()

            if not interview:
                logger.error(
                    f"Interview {self._llm_instance.interview_id} not found")
                self._event_ch.send_nowait(llm.ChatChunk(
                    id="error",
                    delta=llm.ChoiceDelta(
                        content="I'm sorry, I couldn't find the interview session.")
                ))
                return

            # Load state from checkpoint or initialize from interview
            from src.services.checkpoint_service import CheckpointService
            checkpoint_service = CheckpointService()
            state = await checkpoint_service.restore(self._llm_instance.interview_id, self._llm_instance.db)

            if not state:
                # No checkpoint found, initialize from interview
                logger.info(
                    f"No checkpoint found, initializing state from interview {self._llm_instance.interview_id}")
                state = interview_to_state(interview)
                if self._llm_instance.orchestrator._interview_logger:
                    self._llm_instance.orchestrator._interview_logger.log_state(
                        "state_initialized_from_interview", state)
            else:
                logger.info(
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
            logger.info("Executing orchestrator step...")
            state = await self._llm_instance.orchestrator.execute_step(state, user_response=user_message)

            # Get the response message
            response = state.get(
                "next_message", "I'm here to help with your interview.")

            logger.info(f"Generated response (raw): {response[:100]}...")

            # Post-process text for natural TTS delivery
            # This is critical for human-like speech quality
            response = normalize_numbers_and_symbols(response)
            response = prepare_text_for_tts(response)

            logger.info(f"Generated response (processed): {response[:100]}...")

            # Update interview from state (save original response, not processed)
            state_to_interview(state, interview)
            await self._llm_instance.db.commit()

            # Checkpoint state after each step (critical for recovery)
            try:
                checkpoint_service = get_checkpoint_service()
                checkpoint_id = await checkpoint_service.checkpoint(state, self._llm_instance.db)
                logger.info(f"Checkpointed state: {checkpoint_id}")

                # Log checkpoint operation
                if self._llm_instance.orchestrator._interview_logger:
                    self._llm_instance.orchestrator._interview_logger.log_checkpoint(
                        {
                            "checkpoint_id": checkpoint_id,
                            "turn": state.get("turn_count", 0),
                            "last_node": state.get("last_node"),
                            "phase": state.get("phase"),
                        },
                        "saved"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to checkpoint state: {e}", exc_info=True)
                if self._llm_instance.orchestrator._interview_logger:
                    self._llm_instance.orchestrator._interview_logger.log_error(
                        "checkpoint_save",
                        e,
                        {"interview_id": self._llm_instance.interview_id}
                    )
                # Don't fail the entire request if checkpointing fails

            # Push response to stream - this should trigger TTS
            # The processed text will result in more natural speech
            logger.info("Sending response chunk to stream for TTS...")
            self._event_ch.send_nowait(llm.ChatChunk(
                id="response",
                delta=llm.ChoiceDelta(content=response)
            ))
            logger.info("Response chunk sent successfully")

        except Exception as e:
            logger.error(
                f"Error in OrchestratorLLMStream._run: {e}", exc_info=True)
            self._event_ch.send_nowait(llm.ChatChunk(
                id="error",
                delta=llm.ChoiceDelta(
                    content="I'm sorry, I encountered an error. Please try again.")
            ))


class OrchestratorLLM(llm.LLM):
    """Custom LLM that uses the interview orchestrator instead of OpenAI."""

    def __init__(self, interview_id: int, db: AsyncSession, orchestrator: InterviewOrchestrator):
        super().__init__()
        self.interview_id = interview_id
        self.db = db
        self.orchestrator = orchestrator

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
        from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

        conn_options = conn_options or DEFAULT_API_CONNECT_OPTIONS

        return OrchestratorLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options
        )


server = AgentServer()

# Note: Prewarm disabled to avoid initialization timeouts
# VAD will be loaded on-demand in the entrypoint
# If you need prewarming, ensure it's non-blocking and doesn't delay process initialization


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    """Entry point for the LiveKit agent job."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    logger.info(f"Agent connected to room: {ctx.room.name}")

    # Extract interview_id from room name (format: "interview-{id}")
    try:
        interview_id = int(ctx.room.name.replace("interview-", ""))
    except ValueError:
        logger.error(
            f"Could not extract interview_id from room name: {ctx.room.name}")
        return

    # Create database session and orchestrator
    db = AsyncSessionLocal()
    orchestrator = InterviewOrchestrator()

    try:
        # Create custom LLM that uses orchestrator
        orchestrator_llm = OrchestratorLLM(interview_id, db, orchestrator)

        # Create agent session with custom LLM
        # Use tts-1-hd model for more natural, humanized voice
        tts_instance = openai.TTS(
            voice=settings.OPENAI_TTS_VOICE or "alloy",
            model=settings.OPENAI_TTS_MODEL or "tts-1-hd"
        )
        # Load VAD on demand (prewarm was causing initialization timeouts)
        # For production, consider async prewarming or lazy loading
        try:
            logger.info("Loading VAD model...")
            vad_instance = silero.VAD.load()
            logger.info("VAD model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load VAD model: {e}", exc_info=True)
            # Continue without VAD - turn detection will be less accurate
            vad_instance = None

        session = AgentSession(
            vad=vad_instance,
            stt=openai.STT(),
            llm=orchestrator_llm,
            tts=tts_instance,
        )

        # Initialize interview logger for debugging
        from src.services.interview_logger import InterviewLogger
        interview_logger = InterviewLogger(interview_id)
        orchestrator.set_interview_logger(interview_logger)
        logger.info(
            f"Initialized interview logger for interview {interview_id}")

        # Create agent with instructions
        # Note: These instructions guide the agent's behavior, but the orchestrator
        # handles the actual text generation with oral-friendly prompts
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

        # Start the session with explicit audio and text output enabled
        # RoomIO will automatically publish audio tracks when TTS generates speech
        # Transcription is enabled automatically when STT is configured (which we have)
        # Text output sends transcriptions to the frontend via lk.transcription text stream
        await session.start(
            agent=agent,
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_output=True,  # Enable audio output (TTS speech)
                # Enable text output (transcriptions) - defaults to True but explicit
                text_output=True,
            )
        )

        logger.info(
            "AgentSession started with transcription enabled. "
            "Transcriptions will be sent to frontend via lk.transcription text stream."
        )
        logger.info("AgentSession started successfully")

        # Listen for test audio requests via data messages
        def handle_data_message(data_packet):
            """Handle data messages, including test audio requests.

            Args:
                data_packet: DataPacket object containing the received data
            """
            try:
                import json
                import asyncio
                # Extract data from DataPacket.user.payload
                if data_packet.user and data_packet.user.payload:
                    data = data_packet.user.payload
                    message = json.loads(data.decode('utf-8'))
                    if message.get('type') == 'test_audio':
                        logger.info("Received test audio request")
                        # Use processed text for natural speech
                        test_message = prepare_text_for_tts(
                            "Hello! This is an audio test. Can you hear me clearly?"
                        )
                        # Run async function in event loop
                        asyncio.create_task(session.say(test_message))
            except Exception as e:
                logger.debug(f"Error processing data message: {e}")

        ctx.room.on("data_received", handle_data_message)

        # Send initial greeting after session starts
        try:
            logger.info(
                f"Checking for interview {interview_id} to send greeting")
            result = await db.execute(
                select(Interview).where(Interview.id == interview_id)
            )
            interview = result.scalar_one_or_none()

            if interview and interview.status == "in_progress":
                logger.info(
                    f"Interview {interview_id} found, status: {interview.status}")
                # Check for existing checkpoint first
                checkpoint_service = get_checkpoint_service()
                existing_state = await checkpoint_service.restore(interview_id, db)

                # Only send greeting if no existing state/checkpoint (truly first interaction)
                has_any_messages = interview.conversation_history and len(
                    interview.conversation_history) > 0

                if not has_any_messages and not existing_state:
                    logger.info(
                        "No conversation history or checkpoint, generating initial greeting")
                    # Get greeting from orchestrator
                    state = interview_to_state(interview)
                    state = await orchestrator.execute_step(state)
                    greeting = state.get("next_message")

                    # Log greeting generation
                    if orchestrator._interview_logger:
                        orchestrator._interview_logger.log_state(
                            "greeting_generated", state)

                    if greeting:
                        # Post-process greeting for natural TTS
                        greeting = normalize_numbers_and_symbols(greeting)
                        greeting = prepare_text_for_tts(greeting)

                        logger.info(
                            f"Sending greeting (processed): {greeting[:100]}...")
                        state_to_interview(state, interview)
                        await db.commit()

                        # Checkpoint after greeting
                        try:
                            checkpoint_id = await checkpoint_service.checkpoint(state, db)
                            logger.info(
                                f"Checkpointed state after greeting: {checkpoint_id}")

                            # Log checkpoint
                            if orchestrator._interview_logger:
                                orchestrator._interview_logger.log_checkpoint(
                                    {"checkpoint_id": checkpoint_id,
                                        "turn": state.get("turn_count", 0)},
                                    "saved_after_greeting"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to checkpoint after greeting: {e}", exc_info=True)
                            if orchestrator._interview_logger:
                                orchestrator._interview_logger.log_error(
                                    "checkpoint_greeting",
                                    e,
                                    {"interview_id": interview_id}
                                )

                        await session.say(greeting)
                        logger.info("Greeting sent successfully")
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

    finally:
        # Clean up database session
        await db.close()


if __name__ == "__main__":
    cli.run_app(server)

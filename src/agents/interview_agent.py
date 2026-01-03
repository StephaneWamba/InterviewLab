"""LiveKit agent for interview voice conversations.

This agent connects to LiveKit rooms and handles voice conversations
by integrating with the interview orchestrator.

CRITICAL: This module must import in <100ms for LiveKit handshake.
All heavy imports are lazy-loaded after handshake completes.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

# Only stdlib + livekit core imports at module level
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    cli,
    room_io,
)

# Type hints only - never executed at runtime
if TYPE_CHECKING:
    from src.agents.resources import AgentResources

# Add src to path for imports (only if needed, should be in PYTHONPATH)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# Create server instance (OK at module level - AgentServer is lightweight)
server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    """Entry point for the LiveKit agent job.

    Production-ready pattern (per LiveKit best practices):
    1. Extract metadata BEFORE connection (room.name available without connecting)
    2. Bootstrap resources BEFORE ctx.connect() (agent ready before handshake)
    3. Connect to room (handshake completes, agent is already initialized)
    4. Start session with all resources ready
    5. Clean up on exit

    This ensures frontend doesn't show agent participant before it's ready to listen.
    """
    import time
    t0 = time.monotonic()

    # Log immediately (before any imports or heavy operations)
    try:
        room_name = ctx.room.name if hasattr(ctx, 'room') else 'no-room'
        logger.info(f"entrypoint_called (room={room_name})")
    except Exception:
        pass

    # Extract interview_id from room name BEFORE connection
    # Room name is available without connecting (format: "interview-{id}")
    try:
        interview_id = int(ctx.room.name.replace("interview-", ""))
        logger.info(
            f"Extracted interview_id: {interview_id} from room: {ctx.room.name}")
    except ValueError:
        logger.error(
            f"Could not extract interview_id from room name: {ctx.room.name}")
        return

    # Bootstrap all resources BEFORE connection (per LiveKit best practices)
    # This ensures agent is ready before frontend shows it as connected
    logger.info("bootstrap_start (before connection)")

    # Lazy import - only when needed (after metadata extraction, before connection)
    from src.agents.resources import bootstrap_resources
    from src.agents.tts_utils import prepare_text_for_tts, normalize_numbers_and_symbols
    from src.agents.checkpoint_utils import checkpoint_greeting_in_background

    resources: "AgentResources | None" = None
    try:
        resources = await bootstrap_resources(ctx, interview_id)
    except Exception as e:
        logger.error(f"Bootstrap failed before connection: {e}", exc_info=True)
        return

    logger.info("handshake_start")

    # CRITICAL: Connect AFTER bootstrap (agent is ready, frontend won't show it until ready)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    t_connect = time.monotonic()
    logger.info(f"ctx_connected (elapsed={(t_connect - t0):.3f}s)")

    # ---- SAFE ZONE: Handshake complete, agent already initialized ----

    logger.info(
        f"Agent connected to room: {ctx.room.name} (interview_id={interview_id})")

    try:
        # Create agent session with bootstrapped resources
        # VAD is required for OpenAI STT (non-streaming STT needs VAD for streaming)
        resources.session = AgentSession(
            vad=resources.vad,  # Required for non-streaming STT to work
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
                            logger.info(
                                f"Sending greeting: {greeting[:100]}...")
                            state_to_interview(state, interview)
                            if resources.db:
                                await resources.db.commit()

                            if resources.session:
                                await resources.session.say(greeting)
                            logger.info("Greeting sent successfully")

                            asyncio.create_task(
                                checkpoint_greeting_in_background(
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

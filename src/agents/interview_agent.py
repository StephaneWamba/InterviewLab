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

# Module-level imports: only standard library and LiveKit core
# Heavy imports are deferred until after handshake to meet <100ms requirement
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    cli,
    room_io,
)

# Type hints are conditionally imported to avoid runtime overhead
if TYPE_CHECKING:
    from src.agents.resources import AgentResources

# Ensure src directory is in Python path for imports
# Note: In production, this should be handled via PYTHONPATH environment variable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# AgentServer is lightweight and safe to instantiate at module level
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
    # Extract interview ID from room name before establishing connection
    # Room name format: "interview-{id}" and is available without connecting
    try:
        interview_id = int(ctx.room.name.replace("interview-", ""))
    except ValueError:
        logger.error(
            f"Could not extract interview_id from room name: {ctx.room.name}")
        return

    # Bootstrap all resources before connection to ensure agent is ready
    # This follows LiveKit best practices: agent should be initialized before handshake
    # so the frontend doesn't display the agent participant until it's ready to listen

    # Defer heavy imports until after metadata extraction but before connection
    from src.agents.resources import bootstrap_resources

    resources: "AgentResources | None" = None
    try:
        resources = await bootstrap_resources(ctx, interview_id)
    except Exception as e:
        logger.error(f"Bootstrap failed before connection: {e}", exc_info=True)
        return

    # Connect to room after bootstrap completes
    # Agent is now fully initialized, so frontend won't display it until ready
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Handshake complete: safe to perform heavy operations and start session

    try:
        resources.session = AgentSession(
            vad=resources.vad,  # Required for OpenAI non-streaming STT
            stt=resources.stt,
            llm=resources.orchestrator_llm,
            tts=resources.tts,
        )

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

        await resources.session.start(
            agent=agent,
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_output=True,
                text_output=True,
            )
        )

        # Brief delay to ensure TTS audio output is initialized
        await asyncio.sleep(0.5)

        def handle_data_message(data_packet):
            """Handle data messages, including test audio requests."""
            try:
                import json
                if data_packet.user and data_packet.user.payload:
                    data = data_packet.user.payload
                    message = json.loads(data.decode('utf-8'))
                    if message.get('type') == 'test_audio' and resources.session:
                        test_message = prepare_text_for_tts(
                            "Hello! This is an audio test. Can you hear me clearly?"
                        )
                        asyncio.create_task(
                            resources.session.say(test_message))
            except Exception:
                pass

        ctx.room.on("data_received", handle_data_message)

        # Execute LangGraph on first connection to generate initial greeting
        # LangGraph routes to greeting node when conversation_history is empty
        try:
            from src.core.database import AsyncSessionLocal
            from src.models.interview import Interview
            from src.models.user import User
            from src.services.data.state_manager import interview_to_state
            from sqlalchemy import select

            if resources.db:
                interview_result = await resources.db.execute(
                    select(Interview).where(Interview.id == interview_id)
                )
                interview = interview_result.scalar_one_or_none()

                if interview and interview.status == "in_progress":
                    user_result = await resources.db.execute(
                        select(User).where(User.id == interview.user_id)
                    )
                    user = user_result.scalar_one_or_none()

                    conv_history = interview.conversation_history or []
                    actual_messages = [
                        msg for msg in conv_history if msg.get("role") != "system"]

                    if not actual_messages:
                        state = interview_to_state(interview, user=user)
                        state = await resources.orchestrator_llm.orchestrator.execute_step(state)

                        greeting = state.get("next_message")
                        if not greeting:
                            conv_history = state.get(
                                "conversation_history", [])
                            for msg in reversed(conv_history):
                                if msg.get("role") == "assistant" and msg.get("content"):
                                    greeting = msg.get("content")
                                    break

                        if greeting and resources.session:
                            from src.agents.tts_utils import prepare_text_for_tts
                            from src.services.data.state_manager import state_to_interview

                            greeting_tts = prepare_text_for_tts(greeting)
                            await resources.session.say(greeting_tts)

                            state_to_interview(state, interview)
                            if resources.db:
                                await resources.db.commit()
                else:
                    logger.error(
                        f"Interview {interview_id} not found or not in_progress")
        except Exception as e:
            logger.error(
                f"Error executing initial LangGraph step: {e}", exc_info=True)

        # Monitor interview status and room connection state
        try:

            while True:
                await asyncio.sleep(5)

                try:
                    async with AsyncSessionLocal() as check_db:
                        result = await check_db.execute(
                            select(Interview).where(
                                Interview.id == interview_id)
                        )
                        interview = result.scalar_one_or_none()

                        if interview and interview.status == "completed":
                            # Clean up orchestrator state before exiting
                            if resources and resources.orchestrator_llm and resources.orchestrator_llm.orchestrator:
                                try:
                                    await resources.orchestrator_llm.orchestrator.cleanup_interview(interview_id)
                                except Exception as cleanup_error:
                                    logger.error(
                                        f"Failed to cleanup orchestrator: {cleanup_error}", exc_info=True)
                            break
                except Exception:
                    pass

                if not ctx.room or not ctx.room.isconnected():
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in agent monitoring loop: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Agent entrypoint error: {e}", exc_info=True)
    finally:
        if resources:
            await resources.aclose()


if __name__ == "__main__":
    cli.run_app(server)

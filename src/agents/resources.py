"""Resource management for the interview agent.

This module handles bootstrapping and managing agent resources including
database connections, orchestrator LLM, TTS, STT, and VAD components.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from livekit.agents import JobContext, stt, tts, vad

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.agents.orchestrator_llm import OrchestratorLLM
    from livekit.agents import AgentSession

logger = logging.getLogger(__name__)


class AgentResources:
    """Resource container for agent components with proper cleanup."""

    def __init__(self):
        self.db: "AsyncSession | None" = None
        self.orchestrator_llm: "OrchestratorLLM | None" = None
        self.tts: tts.TTS | None = None
        self.stt: stt.STT | None = None
        self.vad: vad.VAD | None = None
        self.session: "AgentSession | None" = None

    async def aclose(self):
        """Clean up all resources."""
        if self.db:
            await self.db.close()
            self.db = None
        logger.debug("Agent resources cleaned up")


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
        from src.agents.orchestrator_llm import OrchestratorLLM

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



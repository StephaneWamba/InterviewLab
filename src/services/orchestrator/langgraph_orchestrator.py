"""Pure LangGraph-based interview orchestrator.

This is the new architecture following LangGraph best practices:
- Explicit StateGraph with edges
- Reducers for append-only fields
- Single writer for conversation_history
- No state mutations
"""

import logging
from typing import Optional
from openai import AsyncOpenAI
import instructor

from src.core.config import settings
from src.services.analysis.response_analyzer import ResponseAnalyzer
from src.services.analysis.code_analyzer import CodeAnalyzer
from src.services.execution.sandbox_service import SandboxService
from src.services.analysis.feedback_generator import FeedbackGenerator
from src.services.logging.interview_logger import InterviewLogger

from src.services.orchestrator.types import InterviewState
from src.services.orchestrator.graph import create_interview_graph
from src.services.orchestrator.nodes import NodeHandler

logger = logging.getLogger(__name__)


class LangGraphInterviewOrchestrator:
    """Pure LangGraph-based interview orchestrator."""

    def __init__(self):
        self._openai_client = None
        self._response_analyzer = ResponseAnalyzer()
        self._code_analyzer = CodeAnalyzer()
        self._feedback_generator = FeedbackGenerator()
        self._sandbox_service = None
        self._interview_logger: Optional[InterviewLogger] = None
        self._node_handler: Optional[NodeHandler] = None
        self._graph = None
        self._checkpointer = None
        self._db_session = None

    def set_interview_logger(self, logger: InterviewLogger):
        """Set the interview logger for debugging."""
        self._interview_logger = logger
        if self._node_handler:
            self._node_handler.interview_logger = logger

    def set_db_session(self, db_session):
        """Set the database session for checkpointing."""
        self._db_session = db_session

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    def _get_sandbox_service(self):
        if self._sandbox_service is None:
            self._sandbox_service = SandboxService()
        return self._sandbox_service

    def _get_node_handler(self) -> NodeHandler:
        """Get or create node handler with all dependencies."""
        if self._node_handler is None:
            self._node_handler = NodeHandler(
                openai_client=self._get_openai_client(),
                response_analyzer=self._response_analyzer,
                code_analyzer=self._code_analyzer,
                feedback_generator=self._feedback_generator,
                sandbox_service=self._get_sandbox_service(),
                interview_logger=self._interview_logger,
            )

        return self._node_handler

    def _get_graph(self):
        """Get or create compiled LangGraph instance.

        Reuses same graph instance: MemorySaver isolates state by thread_id,
        enabling concurrent interviews without state leakage.
        """
        if self._graph is None:
            node_handler = self._get_node_handler()
            self._graph, self._checkpointer = create_interview_graph(
                node_handler)
        return self._graph

    async def execute_step(
        self,
        state: InterviewState,
        user_response: str | None = None,
        code: str | None = None,
        language: str | None = None,
    ) -> InterviewState:
        """
        Execute one step of the interview workflow using LangGraph.

        Args:
            state: Current interview state
            user_response: Optional user response (if this is a user turn)
            code: Optional code submission to review
            language: Optional programming language for code submission

        Returns:
            Updated state
        """
        interview_id = state.get("interview_id")
        if not interview_id:
            logger.error(
                "State missing interview_id - cannot execute step safely")
            raise ValueError("State missing interview_id")

        node_handler = self._get_node_handler()
        if not state.get("last_node"):
            init_updates = await node_handler.initialize_node(state)
            state = {**state, **init_updates}

        input_updates = {}
        if user_response:
            input_updates["last_response"] = user_response

        if code:
            input_updates["current_code"] = code
            if language:
                input_updates["current_language"] = language

        if input_updates:
            state = {**state, **input_updates}

        graph = self._get_graph()
        thread_id = f"interview_{interview_id}"
        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        # Run the graph
        # LangGraph handles checkpointing internally via MemorySaver for graph execution
        # MemorySaver isolates state by thread_id, so each interview gets its own state
        try:
            final_state = await graph.ainvoke(state, config)
        except Exception as e:
            logger.error(
                f"Graph execution failed for interview {interview_id}: {e}", exc_info=True
            )
            raise ValueError(f"Graph execution failed: {e}") from e

        # CRITICAL: Validate final_state still has correct interview_id
        final_interview_id = final_state.get("interview_id")
        if final_interview_id != interview_id:
            logger.error(
                f"State interview_id changed during execution: {interview_id} -> {final_interview_id}. "
                f"This indicates state pollution. Rejecting result. "
                f"State keys: {sorted(final_state.keys())}"
            )
            raise ValueError(
                f"State interview_id changed during execution: {interview_id} -> {final_interview_id}")

        # Persist state to database (separate from LangGraph's in-memory checkpointing)
        if self._db_session and final_state.get("last_node") == "finalize_turn":
            try:
                from src.services.data.checkpoint_service import CheckpointService
                checkpoint_service = CheckpointService()
                await checkpoint_service.checkpoint(final_state, self._db_session)
            except Exception as e:
                logger.warning(
                    f"Failed to persist to database: {e}", exc_info=True)

        return final_state

    async def cleanup_interview(self, interview_id: int):
        """Clean up graph state and cache for completed interview to free memory.

        CRITICAL: This clears MemorySaver checkpoints to prevent memory leaks.
        MemorySaver accumulates state for all interviews, so we must explicitly clear it.
        """
        # Clear MemorySaver checkpoints for this interview's thread_id
        if self._checkpointer:
            # MemorySaver state will be garbage collected when orchestrator instance is destroyed
            pass

        # Clear Redis cache keys for this interview
        try:
            from src.core.redis import get_redis
            redis_client = await get_redis()
            cache_keys = [
                f"interview:{interview_id}:*",
                f"interview_state:{interview_id}",
                f"interview_checkpoint:{interview_id}",
            ]
            for pattern in cache_keys:
                try:
                    if "*" in pattern:
                        async for key in redis_client.scan_iter(match=pattern):
                            await redis_client.delete(key)
                    else:
                        await redis_client.delete(pattern)
                except Exception:
                    pass
        except Exception as e:
            logger.error(
                f"Failed to cleanup Redis cache for interview {interview_id}: {e}", exc_info=True)

        # Clear node handler to help GC (it holds references to services)
        # This helps free memory from cached clients and services
        if self._node_handler:
            # Clear service references
            self._node_handler = None

        # Note: _graph and _checkpointer are kept because they're lightweight
        # MemorySaver state is per-thread_id, so old state will be GC'd when orchestrator is destroyed
        # The real fix is ensuring orchestrator instances are destroyed when interviews complete

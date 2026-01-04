"""LangGraph StateGraph definition for interview orchestration.

This module defines the explicit graph structure with edges and conditional routing.
Following LangGraph best practices:
- Explicit edges for deterministic flow
- Single writer for conversation_history (finalize_turn_node)
- Reducers for append-only fields
- Clear node boundaries
"""

import logging
from typing import Literal, Tuple
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.services.orchestrator.types import InterviewState
from src.services.orchestrator.nodes import NodeHandler

logger = logging.getLogger(__name__)


def create_interview_graph(node_handler: NodeHandler) -> Tuple[StateGraph, MemorySaver]:
    """Create the LangGraph StateGraph for interview orchestration.

    Graph structure:
        START
          ↓
        ingest_input (if user input provided)
          ↓
        detect_intent
          ↓
        decide_next_action
          ↓ (conditional)
        [action nodes: greeting, question, followup, sandbox_guidance, code_review, evaluation, closing]
          ↓
        finalize_turn (writes conversation_history and updates summary)
          ↓
        END

    Args:
        node_handler: NodeHandler instance with all dependencies

    Returns:
        Compiled StateGraph ready for execution
    """
    graph = StateGraph(InterviewState)

    graph.add_node("ingest_input", node_handler.ingest_input_node)
    graph.add_node("detect_intent", node_handler.detect_intent_node)
    graph.add_node("decide_next_action", node_handler.decide_next_action_node)
    graph.add_node("greeting", node_handler.greeting_node)
    graph.add_node("question", node_handler.question_node)
    graph.add_node("followup", node_handler.followup_node)
    graph.add_node("sandbox_guidance", node_handler.sandbox_guidance_node)
    graph.add_node("code_review", node_handler.code_review_node)
    graph.add_node("evaluation", node_handler.evaluation_node)
    graph.add_node("closing", node_handler.closing_node)
    graph.add_node("finalize_turn", node_handler.finalize_turn_node)

    graph.set_entry_point("ingest_input")

    def route_from_ingest(state: InterviewState) -> Literal["greeting", "code_review", "detect_intent"]:
        """Route from ingest_input: greeting on first turn, code_review if code submitted, else detect_intent."""
        # Check if greeting already exists in conversation (prevents duplicates on state restore)
        has_greeting = False
        conv_history = state.get("conversation_history", [])
        if conv_history:
            for msg in conv_history:
                if msg.get("role") == "assistant" and msg.get("content"):
                    has_greeting = True
                    break

        # Show greeting if it hasn't been shown yet (first turn and no greeting in history)
        if not has_greeting and state.get("turn_count", 0) == 0:
            return "greeting"

        if state.get("current_code"):
            return "code_review"

        return "detect_intent"

    graph.add_conditional_edges(
        "ingest_input",
        route_from_ingest,
        {
            "greeting": "greeting",
            "code_review": "code_review",
            "detect_intent": "detect_intent",
        }
    )

    graph.add_edge("detect_intent", "decide_next_action")

    # route_action_node reads state["next_node"] set by decide_next_action_node
    graph.add_conditional_edges(
        "decide_next_action",
        route_action_node,
        {
            "greeting": "greeting",
            "question": "question",
            "followup": "followup",
            "sandbox_guidance": "sandbox_guidance",
            "code_review": "code_review",
            "evaluation": "evaluation",
            "closing": "closing",
        }
    )

    graph.add_edge("greeting", "finalize_turn")
    graph.add_edge("question", "finalize_turn")
    graph.add_edge("followup", "finalize_turn")
    graph.add_edge("sandbox_guidance", "finalize_turn")
    graph.add_edge("code_review", "finalize_turn")
    graph.add_edge("evaluation", "finalize_turn")
    graph.add_edge("closing", "finalize_turn")
    graph.add_edge("finalize_turn", END)

    # MemorySaver isolates state by thread_id, enabling concurrent interviews
    checkpointer = MemorySaver()
    compiled_graph = graph.compile(checkpointer=checkpointer)

    return compiled_graph, checkpointer


def route_action_node(state: InterviewState) -> Literal[
    "greeting", "question", "followup",
    "sandbox_guidance", "code_review", "evaluation", "closing"
]:
    """Route to action node based on next_node in state."""
    action = state.get("next_node")

    if not action:
        logger.error(
            f"next_node is None or missing. State keys: {sorted(state.keys())}, "
            f"last_node: {state.get('last_node')}"
        )
        return "question"

    valid_actions = [
        "greeting", "question", "followup",
        "sandbox_guidance", "code_review", "evaluation", "closing"
    ]

    if action not in valid_actions:
        logger.error(
            f"Invalid action '{action}', defaulting to question. "
            f"Valid actions: {valid_actions}"
        )
        return "question"

    return action

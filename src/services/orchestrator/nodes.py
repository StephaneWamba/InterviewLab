"""Node implementations for interview orchestrator.

This module provides the NodeHandler class that combines action and control nodes.
"""

import logging
from typing import TYPE_CHECKING, Optional
from openai import AsyncOpenAI

from src.services.execution.sandbox_service import SandboxService
from src.services.orchestrator.action_nodes import ActionNodeMixin
from src.services.orchestrator.control_nodes import ControlNodeMixin
from src.services.orchestrator.llm_helpers import LLMHelper

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.services.analysis.response_analyzer import ResponseAnalyzer
    from src.services.analysis.code_analyzer import CodeAnalyzer
    from src.services.analysis.feedback_generator import FeedbackGenerator
    from src.services.logging.interview_logger import InterviewLogger


class NodeHandler(ActionNodeMixin, ControlNodeMixin):
    """Handler for all interview orchestrator nodes with shared dependencies.

    Combines action nodes (greeting, question, etc.) and control nodes
    (initialize, decide_next_action, etc.) through multiple inheritance.
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        response_analyzer: "ResponseAnalyzer",
        code_analyzer: "CodeAnalyzer",
        feedback_generator: "FeedbackGenerator",
        sandbox_service: SandboxService,
        interview_logger: Optional["InterviewLogger"] = None,
    ):
        self.openai_client = openai_client
        self.llm_helper = LLMHelper(openai_client)
        self.response_analyzer = response_analyzer
        self.code_analyzer = code_analyzer
        self.feedback_generator = feedback_generator
        self.sandbox_service = sandbox_service
        self.interview_logger = interview_logger

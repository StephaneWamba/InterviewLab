"""Helper utilities for LLM calls in orchestrator nodes."""

import logging
from typing import Optional, Any
from openai import AsyncOpenAI
import instructor

from src.services.orchestrator.constants import (
    DEFAULT_MODEL,
    TEMPERATURE_CREATIVE,
    TEMPERATURE_BALANCED,
    TEMPERATURE_ANALYTICAL,
    TEMPERATURE_QUESTION,
)

logger = logging.getLogger(__name__)


class LLMHelper:
    """Helper class for standardized LLM calls."""

    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
        self._instructor_client = None

    @property
    def instructor_client(self):
        """Get or create instructor-patched client."""
        if self._instructor_client is None:
            self._instructor_client = instructor.patch(self.client)
        return self._instructor_client

    async def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_MODEL,
        temperature: float = TEMPERATURE_BALANCED,
        response_format: Optional[dict] = None,
    ) -> str:
        """
        Standard LLM call returning text response.

        Args:
            system_prompt: System message content
            user_prompt: User message content
            model: Model name (default: gpt-4o-mini)
            temperature: Temperature setting
            response_format: Optional response format (e.g., {"type": "json_object"})

        Returns:
            Response text content
        """
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                response_format=response_format,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise

    async def call_llm_with_instructor(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Any,
        model: str = DEFAULT_MODEL,
        temperature: float = TEMPERATURE_BALANCED,
    ) -> Any:
        """
        LLM call with structured output using Instructor.

        Args:
            system_prompt: System message content
            user_prompt: User message content
            response_model: Pydantic model for structured output
            model: Model name (default: gpt-4o-mini)
            temperature: Temperature setting

        Returns:
            Parsed response model instance
        """
        try:
            response = await self.instructor_client.chat.completions.create(
                model=model,
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            return response
        except Exception as e:
            logger.error(f"Instructor LLM call failed: {e}", exc_info=True)
            raise

    async def call_llm_creative(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_MODEL,
    ) -> str:
        """LLM call with creative temperature (0.8)."""
        return await self.call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=TEMPERATURE_CREATIVE,
        )

    async def call_llm_analytical(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_MODEL,
    ) -> str:
        """LLM call with analytical temperature (0.3)."""
        return await self.call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=TEMPERATURE_ANALYTICAL,
        )

    async def call_llm_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_MODEL,
        temperature: float = TEMPERATURE_BALANCED,
    ) -> str:
        """LLM call with JSON response format."""
        return await self.call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
        )



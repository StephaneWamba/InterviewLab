"""Service for analyzing user responses during interviews."""

from typing import Optional
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field

from src.core.config import settings


class AnswerQuality(BaseModel):
    """Schema for answer quality analysis."""

    quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall quality score (0-1)"
    )
    depth_score: float = Field(
        ..., ge=0.0, le=1.0, description="Answer depth/detail score (0-1)"
    )
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0, description="Relevance to question score (0-1)"
    )
    completeness_score: float = Field(
        ..., ge=0.0, le=1.0, description="Completeness score (0-1)"
    )
    topics_mentioned: list[str] = Field(
        default_factory=list, description="Topics/skills mentioned in the answer"
    )
    needs_followup: bool = Field(
        ..., description="Whether a follow-up question is needed"
    )
    feedback: str = Field(
        ..., description="Brief feedback on the answer quality"
    )


class ResponseAnalyzer:
    """Service for analyzing interview responses."""

    def __init__(self):
        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    async def analyze_answer(
        self, question: str, answer: str, context: Optional[dict] = None
    ) -> AnswerQuality:
        """
        Analyze the quality of an answer.

        Args:
            question: The question that was asked
            answer: The user's answer
            context: Optional context (resume data, conversation history)

        Returns:
            AnswerQuality object with scores and feedback
        """
        client = self._get_openai_client()

        context_text = ""
        if context:
            resume_context = context.get("resume_context", {})
            if resume_context:
                context_text = f"""
Resume Context:
- Profile: {resume_context.get('profile', 'N/A')[:200]}
- Experience: {resume_context.get('experience', 'N/A')[:200]}
- Education: {resume_context.get('education', 'N/A')[:200]}
"""

        prompt = f"""Analyze the quality of this interview answer.

Question: {question}

Answer: {answer}
{context_text}

Evaluate:
1. **Depth**: How detailed and thorough is the answer? (0-1)
2. **Relevance**: How well does it address the question? (0-1)
3. **Completeness**: Is the answer complete or does it need more information? (0-1)
4. **Topics**: What specific topics, skills, or technologies are mentioned?
5. **Follow-up needed**: Does this answer need a follow-up question? (Yes if vague, incomplete, or interesting topics mentioned)

Calculate an overall quality score (average of depth, relevance, completeness).

Provide brief feedback on the answer quality."""

        try:
            result = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=AnswerQuality,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer analyzing candidate answers. Provide objective, helpful analysis.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

            return result

        except Exception as e:
            # Return default quality on error
            return AnswerQuality(
                quality_score=0.5,
                depth_score=0.5,
                relevance_score=0.5,
                completeness_score=0.5,
                topics_mentioned=[],
                needs_followup=True,
                feedback="Unable to analyze answer quality.",
            )








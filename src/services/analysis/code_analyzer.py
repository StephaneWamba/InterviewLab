"""Service for analyzing code quality and execution results."""

from typing import Optional, List
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field

from src.core.config import settings
from src.services.execution.sandbox_service import SandboxService, Language as SandboxLanguage


class CodeQuality(BaseModel):
    """Schema for code quality analysis."""

    quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall code quality score (0-1)"
    )
    correctness_score: float = Field(
        ..., ge=0.0, le=1.0, description="Code correctness score (0-1)"
    )
    efficiency_score: float = Field(
        ..., ge=0.0, le=1.0, description="Code efficiency score (0-1)"
    )
    readability_score: float = Field(
        ..., ge=0.0, le=1.0, description="Code readability score (0-1)"
    )
    best_practices_score: float = Field(
        ..., ge=0.0, le=1.0, description="Best practices adherence score (0-1)"
    )
    strengths: list[str] = Field(
        default_factory=list, description="List of code strengths"
    )
    weaknesses: list[str] = Field(
        default_factory=list, description="List of code weaknesses or areas for improvement"
    )
    feedback: str = Field(
        ..., description="Detailed feedback on the code"
    )
    suggestions: list[str] = Field(
        default_factory=list, description="Specific suggestions for improvement"
    )


class CodeAnalyzer:
    """Service for analyzing code quality and execution results."""

    def __init__(self):
        self._openai_client = None
        self._sandbox_service = None

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    def _get_sandbox_service(self):
        if self._sandbox_service is None:
            self._sandbox_service = SandboxService()
        return self._sandbox_service

    async def analyze_code(
        self,
        code: str,
        language: str,
        execution_result: Optional[dict] = None,
        problem_statement: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> CodeQuality:
        """
        Analyze code quality and execution results.

        Args:
            code: The code to analyze
            language: Programming language (python, javascript, etc.)
            execution_result: Optional execution result from sandbox (stdout, stderr, exit_code)
            problem_statement: Optional problem statement or requirements
            context: Optional context (interview question, conversation history)

        Returns:
            CodeQuality object with scores and feedback
        """
        client = self._get_openai_client()

        execution_context = ""
        if execution_result:
            stdout = execution_result.get("stdout", "")
            stderr = execution_result.get("stderr", "")
            exit_code = execution_result.get("exit_code", 0)
            success = execution_result.get("success", exit_code == 0)

            execution_context = f"""
Execution Results:
- Success: {success}
- Exit Code: {exit_code}
- Stdout: {stdout[:500] if stdout else 'No output'}
- Stderr: {stderr[:500] if stderr else 'No errors'}
"""

        problem_context = ""
        if problem_statement:
            problem_context = f"""
Problem Statement:
{problem_statement}
"""

        interview_context = ""
        if context:
            interview_context = f"""
Interview Context:
- Question: {context.get('question', 'N/A')}
- Conversation: {context.get('conversation_summary', 'N/A')[:300]}
"""

        prompt = f"""Analyze this code submission for quality, correctness, and best practices.

Language: {language}

Code:
```{language}
{code}
```
{execution_context}
{problem_context}
{interview_context}

Evaluate on:
1. **Correctness** (0-1): Solves problem correctly, handles edge cases
2. **Efficiency** (0-1): Time/space complexity
3. **Readability** (0-1): Clean, well-structured, easy to understand
4. **Best Practices** (0-1): Follows language-specific best practices

Calculate overall quality score (weighted: correctness 40%, efficiency 20%, readability 20%, best practices 20%).

Identify:
- Strengths: What they did well
- Weaknesses: Areas for improvement
- Suggestions: Specific, actionable improvements

Provide detailed, constructive feedback."""

        try:
            result = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=CodeQuality,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert code reviewer analyzing interview code submissions. Provide constructive, detailed feedback that helps candidates improve. Be specific and actionable.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

            return result

        except Exception:
            return CodeQuality(
                quality_score=0.5,
                correctness_score=0.5,
                efficiency_score=0.5,
                readability_score=0.5,
                best_practices_score=0.5,
                strengths=[],
                weaknesses=["Unable to analyze code quality."],
                feedback="Unable to analyze code quality due to an error.",
                suggestions=[],
            )

    async def generate_code_feedback_message(
        self,
        code_quality: CodeQuality,
        execution_result: Optional[dict] = None,
    ) -> str:
        """
        Generate a conversational feedback message for the interview.

        Args:
            code_quality: Code quality analysis results
            execution_result: Optional execution result

        Returns:
            Natural language feedback message
        """
        client = self._get_openai_client()

        quality_summary = f"""
Code Quality Analysis:
- Overall Score: {code_quality.quality_score:.2f}/1.0
- Correctness: {code_quality.correctness_score:.2f}/1.0
- Efficiency: {code_quality.efficiency_score:.2f}/1.0
- Readability: {code_quality.readability_score:.2f}/1.0
- Best Practices: {code_quality.best_practices_score:.2f}/1.0

Strengths: {', '.join(code_quality.strengths) if code_quality.strengths else 'None identified'}
Weaknesses: {', '.join(code_quality.weaknesses) if code_quality.weaknesses else 'None identified'}

Feedback: {code_quality.feedback}
"""

        execution_info = ""
        if execution_result:
            success = execution_result.get("success", False)
            execution_info = f"""
Execution: {'Success' if success else 'Failed'}
Output: {execution_result.get('stdout', 'No output')[:200]}
"""

        prompt = f"""Generate a natural, conversational feedback message for the candidate about their code submission.

{quality_summary}
{execution_info}

Create a message that:
- Acknowledges strengths (if any)
- Provides constructive feedback on improvements
- Is encouraging and supportive
- Sounds natural and conversational
- Is concise (2-3 sentences)

Return ONLY the feedback message, no prefix or explanation."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a friendly, supportive interviewer providing code feedback. Be encouraging and constructive.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )

            return response.choices[0].message.content.strip()

        except Exception:
            if code_quality.quality_score >= 0.7:
                return "Great work on your code! I can see you've put thought into the solution. Let's discuss a few areas where we could refine it further."
            elif code_quality.quality_score >= 0.5:
                return "Thanks for sharing your code! I can see some good ideas here. Let's talk through a few improvements that could make it even better."
            else:
                return "I appreciate you sharing your code. Let's work through this together and discuss some ways we could improve the approach."

    async def generate_adaptive_question(
        self,
        code_quality: CodeQuality,
        execution_result: Optional[dict] = None,
        conversation_context: Optional[str] = None,
    ) -> str:
        """
        Generate an adaptive follow-up question based on code quality analysis.

        Args:
            code_quality: Code quality analysis results
            execution_result: Optional execution result
            conversation_context: Optional conversation context

        Returns:
            Natural language follow-up question
        """
        client = self._get_openai_client()

        quality_summary = f"""
Code Quality Analysis:
- Overall Score: {code_quality.quality_score:.2f}/1.0
- Correctness: {code_quality.correctness_score:.2f}/1.0
- Efficiency: {code_quality.efficiency_score:.2f}/1.0
- Readability: {code_quality.readability_score:.2f}/1.0
- Best Practices: {code_quality.best_practices_score:.2f}/1.0

Strengths: {', '.join(code_quality.strengths) if code_quality.strengths else 'None identified'}
Weaknesses: {', '.join(code_quality.weaknesses) if code_quality.weaknesses else 'None identified'}
Suggestions: {', '.join(code_quality.suggestions[:3]) if code_quality.suggestions else 'None'}
"""

        execution_info = ""
        if execution_result:
            success = execution_result.get("success", False)
            execution_info = f"""
Execution: {'Success' if success else 'Failed'}
"""

        context_info = ""
        if conversation_context:
            context_info = f"""
Conversation Context:
{conversation_context[:300]}
"""

        prompt = f"""Generate a natural, conversational follow-up question based on the code review.

{quality_summary}
{execution_info}
{context_info}

Generate ONE simple, focused follow-up question that:
- Builds on the code review feedback naturally
- Is relevant to weaknesses or suggestions identified
- Encourages deeper thinking or improvement
- Is conversational and engaging

Examples:
- "How would you handle edge cases like empty input or negative numbers?"
- "What would you do differently if you needed to optimize this for large datasets?"
- "Can you walk me through how you would test this function?"

Return ONLY the question, no prefix or explanation."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer asking follow-up questions after code review. Be conversational and natural. Prefer single, focused questions for clarity, but compound questions (with 'and') are acceptable when exploring related technical aspects naturally.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
            )

            return response.choices[0].message.content.strip()

        except Exception:
            if code_quality.quality_score >= 0.7:
                return "How would you optimize this solution for better performance?"
            elif code_quality.quality_score >= 0.5:
                return "What edge cases should we consider for this code?"
            else:
                return "Can you walk me through your thought process for this approach?"

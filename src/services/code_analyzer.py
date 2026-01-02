"""Service for analyzing code quality and execution results."""

from typing import Optional, List
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field

from src.core.config import settings
from src.services.sandbox_service import SandboxService, Language as SandboxLanguage


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


class TestCaseResult(BaseModel):
    """Schema for test case validation result."""

    test_case: str = Field(..., description="The test case description")
    passed: bool = Field(..., description="Whether the test case passed")
    expected_output: str = Field(..., description="Expected output")
    actual_output: str = Field(...,
                               description="Actual output from code execution")
    error: Optional[str] = Field(
        None, description="Error message if test failed")


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

        # Build execution context
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

        # Build problem context
        problem_context = ""
        if problem_statement:
            problem_context = f"""
Problem Statement:
{problem_statement}
"""

        # Build interview context
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

Evaluate the code on:
1. **Correctness**: Does it solve the problem correctly? Does it handle edge cases? (0-1)
2. **Efficiency**: Is it efficient? Time/space complexity? (0-1)
3. **Readability**: Is it clean, well-structured, and easy to understand? (0-1)
4. **Best Practices**: Does it follow language-specific best practices? (0-1)

Calculate an overall quality score (weighted average: correctness 40%, efficiency 20%, readability 20%, best practices 20%).

Identify:
- **Strengths**: What the candidate did well
- **Weaknesses**: Areas that need improvement
- **Suggestions**: Specific, actionable suggestions for improvement

Provide detailed, constructive feedback that would help the candidate improve."""

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

        except Exception as e:
            # Return default quality on error
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

        # Build summary
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
- Acknowledges what they did well (if any strengths)
- Provides constructive feedback on areas for improvement
- Is encouraging and supportive, not harsh
- Sounds like a real interviewer, not a robot
- Is concise (2-3 sentences)
- Can be used as the next message in the interview conversation

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
            # Fallback message
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

        # Build quality summary
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
- Is relevant to the weaknesses or suggestions identified
- Encourages the candidate to think deeper or improve
- Is conversational and engaging (not interrogative)
- Is SIMPLE and FOCUSED - ONE question only
- Can be about: optimization, edge cases, testing, best practices, or alternative approaches

CRITICAL RULES:
❌ NEVER use "and" to connect two questions
❌ NEVER ask multiple questions in one sentence
✅ ONLY ask ONE simple, focused question

Examples of good questions:
- "How would you handle edge cases like empty input or negative numbers?"
- "What would you do differently if you needed to optimize this for large datasets?"
- "Can you walk me through how you would test this function?"
- "What are some alternative approaches you considered?"

Return ONLY the question, no prefix or explanation."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer asking follow-up questions after code review. Be conversational and natural. CRITICAL: Always generate ONE simple question only - never combine multiple questions with 'and'.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
            )

            return response.choices[0].message.content.strip()

        except Exception:
            # Fallback questions based on quality
            if code_quality.quality_score >= 0.7:
                return "How would you optimize this solution for better performance?"
            elif code_quality.quality_score >= 0.5:
                return "What edge cases should we consider for this code?"
            else:
                return "Can you walk me through your thought process for this approach?"

    async def validate_test_cases(
        self,
        code: str,
        language: str,
        test_cases: List[dict],
    ) -> List[TestCaseResult]:
        """
        Validate code against test cases.

        Args:
            code: The code to test
            language: Programming language
            test_cases: List of test cases with 'input' and 'expected_output'

        Returns:
            List of TestCaseResult objects
        """
        results = []
        sandbox_service = self._get_sandbox_service()

        try:
            sandbox_language = SandboxLanguage(language.lower())
        except ValueError:
            sandbox_language = SandboxLanguage.PYTHON

        for test_case in test_cases:
            test_input = test_case.get("input", "")
            expected_output = str(test_case.get("expected_output", "")).strip()
            test_description = test_case.get(
                "description", f"Test with input: {test_input}")

            # Modify code to include test input
            # For Python: wrap in a test function or modify main execution
            test_code = self._prepare_test_code(code, language, test_input)

            try:
                # Execute test code
                execution_result = await sandbox_service.execute_code(
                    code=test_code,
                    language=sandbox_language,
                )

                actual_output = execution_result.stdout.strip() if execution_result.stdout else ""
                passed = actual_output == expected_output and execution_result.success

                results.append(
                    TestCaseResult(
                        test_case=test_description,
                        passed=passed,
                        expected_output=expected_output,
                        actual_output=actual_output,
                        error=execution_result.stderr if not execution_result.success else None,
                    )
                )

            except Exception as e:
                results.append(
                    TestCaseResult(
                        test_case=test_description,
                        passed=False,
                        expected_output=expected_output,
                        actual_output="",
                        error=str(e),
                    )
                )

        return results

    def _prepare_test_code(self, code: str, language: str, test_input: str) -> str:
        """Prepare code with test input for execution."""
        if language.lower() == "python":
            # For Python, try to inject test input
            # Simple approach: append test execution
            # This assumes the code defines a function that can be called
            # More sophisticated parsing could be added later
            if "def " in code and "print(" not in code:
                # If code has a function but no print, add test call
                return f"{code}\n\n# Test execution\nresult = {test_input}\nprint(result)"
            else:
                # If code already has execution, try to modify it
                # For now, just append the test input as a comment and execute
                return f"{code}\n\n# Test input: {test_input}"
        elif language.lower() == "javascript":
            # Similar approach for JavaScript
            if "function " in code or "const " in code or "let " in code:
                return f"{code}\n\n// Test execution\nconsole.log({test_input})"
            else:
                return f"{code}\n\n// Test input: {test_input}"
        else:
            return code

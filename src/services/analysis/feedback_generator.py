"""Service for generating comprehensive interview feedback with skill-specific breakdowns."""

from typing import Optional, List, Dict
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field

from src.core.config import settings


class InterviewFeedback(BaseModel):
    """Schema for comprehensive interview feedback with skill breakdowns."""

    overall_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall interview performance score (0-1)"
    )
    communication_score: float = Field(
        ..., ge=0.0, le=1.0, description="Communication quality score (0-1)"
    )
    technical_score: float = Field(
        ..., ge=0.0, le=1.0, description="Technical knowledge score (0-1)"
    )
    problem_solving_score: float = Field(
        ..., ge=0.0, le=1.0, description="Problem-solving ability score (0-1)"
    )
    code_quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Code quality score (0-1, 0 if no code submitted)"
    )

    # Skill-specific breakdowns
    skill_breakdown: Dict[str, Dict] = Field(
        default_factory=dict,
        description="Detailed breakdown per skill with strengths, weaknesses, and recommendations"
    )

    # Global feedback (for backward compatibility)
    strengths: List[str] = Field(
        default_factory=list, description="Key strengths demonstrated (global)"
    )
    weaknesses: List[str] = Field(
        default_factory=list, description="Areas for improvement (global)"
    )

    summary: str = Field(
        ..., description="Overall interview summary"
    )
    detailed_feedback: str = Field(
        ..., description="Detailed feedback on performance"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Actionable recommendations for improvement (global)"
    )

    topics_covered: List[str] = Field(
        default_factory=list, description="Topics discussed during interview"
    )
    code_submissions_count: int = Field(
        default=0, description="Number of code submissions"
    )
    average_code_quality: float = Field(
        default=0.0, description="Average code quality score"
    )


class FeedbackGenerator:
    """Service for generating comprehensive interview feedback with skill-specific insights."""

    def __init__(self):
        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    async def generate_feedback(
        self,
        conversation_history: List[dict],
        resume_context: Optional[dict] = None,
        code_submissions: Optional[List[dict]] = None,
        topics_covered: Optional[List[str]] = None,
        job_description: Optional[str] = None,
    ) -> InterviewFeedback:
        """
        Generate comprehensive interview feedback with skill-specific breakdowns.

        Args:
            conversation_history: List of conversation messages
            resume_context: Resume context (optional)
            code_submissions: List of code submissions with quality scores (optional)
            topics_covered: List of topics discussed (optional)
            job_description: Job description/requirements (optional)

        Returns:
            InterviewFeedback object with comprehensive analysis and skill breakdowns
        """
        client = self._get_openai_client()

        conversation_summary = self._build_conversation_summary(
            conversation_history)

        resume_summary = ""
        if resume_context:
            resume_summary = f"""
Resume Context:
- Profile: {resume_context.get('profile', 'N/A')[:200]}
- Experience: {resume_context.get('experience', 'N/A')[:300]}
- Education: {resume_context.get('education', 'N/A')[:200]}
"""

        code_analysis = ""
        code_submissions_count = 0
        average_code_quality = 0.0

        if code_submissions:
            code_submissions_count = len(code_submissions)
            quality_scores = [
                sub.get("code_quality", {}).get("quality_score", 0.0)
                for sub in code_submissions
                if sub.get("code_quality", {}).get("quality_score")
            ]
            if quality_scores:
                average_code_quality = sum(
                    quality_scores) / len(quality_scores)

            code_analysis = f"""
Code Submissions: {code_submissions_count}
Average Code Quality: {average_code_quality:.2f}/1.0
"""
            if code_submissions:
                latest = code_submissions[-1]
                latest_quality = latest.get("code_quality", {})
                code_analysis += f"""
Latest Code Quality:
- Correctness: {latest_quality.get('correctness_score', 0):.2f}
- Efficiency: {latest_quality.get('efficiency_score', 0):.2f}
- Readability: {latest_quality.get('readability_score', 0):.2f}
- Best Practices: {latest_quality.get('best_practices_score', 0):.2f}
"""

        topics_list = topics_covered or []

        job_context = ""
        if job_description:
            job_context = f"""
Job Requirements:
{job_description[:500]}

"""

        # Combined prompt for single LLM call
        combined_prompt = f"""Generate comprehensive interview feedback.

{job_context}{resume_summary}

Conversation:
{conversation_summary}

{code_analysis}

Topics: {', '.join(topics_list) if topics_list else 'None'}

Evaluate 4 skills (0-1 each):
1. Communication: clarity, articulation, engagement
2. Technical: depth, accuracy, expertise
3. Problem-Solving: approach, logic, creativity
4. Code Quality: correctness, efficiency, readability, best practices (0.0 if no code)

For each skill, provide: score, 2-3 strengths, 2-3 weaknesses, 2-3 recommendations.
For code_quality: return empty lists [] if no code submitted.

Calculate overall score (weighted: Communication 25%, Technical 30%, Problem-Solving 25%, Code Quality 20%).

Provide:
- Summary (2-3 sentences)
- Detailed feedback (4-5 sentences)
- Overall strengths (2-3)
- Overall weaknesses (2-3)
- Overall recommendations (3-5)

Be specific and reference actual examples from the conversation."""

        try:
            result = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=InterviewFeedback,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer providing comprehensive feedback. Be objective, specific, actionable. For code_quality: return empty lists [] when no code submitted, never 'N/A'.",
                    },
                    {"role": "user", "content": combined_prompt},
                ],
                temperature=0.3,
            )

            # Build skill breakdown from individual scores
            skill_breakdown_dict = {
                "communication": {
                    "score": result.communication_score,
                    "strengths": result.strengths[:2] if result.strengths else [],
                    "weaknesses": result.weaknesses[:2] if result.weaknesses else [],
                    "recommendations": result.recommendations[:2] if result.recommendations else [],
                },
                "technical": {
                    "score": result.technical_score,
                    "strengths": result.strengths[:2] if result.strengths else [],
                    "weaknesses": result.weaknesses[:2] if result.weaknesses else [],
                    "recommendations": result.recommendations[:2] if result.recommendations else [],
                },
                "problem_solving": {
                    "score": result.problem_solving_score,
                    "strengths": result.strengths[:2] if result.strengths else [],
                    "weaknesses": result.weaknesses[:2] if result.weaknesses else [],
                    "recommendations": result.recommendations[:2] if result.recommendations else [],
                },
                "code_quality": {
                    "score": result.code_quality_score if code_submissions_count > 0 else 0.0,
                    "strengths": [] if code_submissions_count == 0 else (result.strengths[:2] if result.strengths else []),
                    "weaknesses": [] if code_submissions_count == 0 else (result.weaknesses[:2] if result.weaknesses else []),
                    "recommendations": [] if code_submissions_count == 0 else (result.recommendations[:2] if result.recommendations else []),
                },
            }

            result.skill_breakdown = skill_breakdown_dict
            result.code_submissions_count = code_submissions_count
            result.average_code_quality = average_code_quality
            result.topics_covered = topics_list

            return result

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to generate feedback: {e}", exc_info=True)

            # Fallback with default values
            skill_breakdown_dict = {
                "communication": {"score": 0.5, "strengths": [], "weaknesses": [], "recommendations": []},
                "technical": {"score": 0.5, "strengths": [], "weaknesses": [], "recommendations": []},
                "problem_solving": {"score": 0.5, "strengths": [], "weaknesses": [], "recommendations": []},
                "code_quality": {"score": average_code_quality, "strengths": [], "weaknesses": [], "recommendations": []},
            }

            return InterviewFeedback(
                overall_score=0.5,
                communication_score=0.5,
                technical_score=0.5,
                problem_solving_score=0.5,
                code_quality_score=average_code_quality,
                skill_breakdown=skill_breakdown_dict,
                strengths=[],
                weaknesses=["Unable to generate detailed feedback"],
                summary="Interview completed. Feedback generation encountered an issue.",
                detailed_feedback="Unable to generate detailed feedback due to an error.",
                recommendations=["Review the interview transcript manually"],
                topics_covered=topics_list or [],
                code_submissions_count=code_submissions_count,
                average_code_quality=average_code_quality,
            )

    def _build_conversation_summary(self, conversation_history: List[dict]) -> str:
        """Build a summary of the conversation."""
        if not conversation_history:
            return "No conversation recorded."

        user_messages = [
            msg.get("content", "") for msg in conversation_history
            if msg.get("role") == "user"
        ]
        assistant_messages = [
            msg.get("content", "") for msg in conversation_history
            if msg.get("role") == "assistant"
        ]

        summary_parts = []
        summary_parts.append(f"Total Messages: {len(conversation_history)}")
        summary_parts.append(f"User Responses: {len(user_messages)}")
        summary_parts.append(
            f"Interviewer Questions: {len(assistant_messages)}")

        if user_messages:
            summary_parts.append("\nSample User Responses:")
            for i, msg in enumerate(user_messages[:5], 1):
                summary_parts.append(f"{i}. {msg[:150]}...")

        if assistant_messages:
            summary_parts.append("\nSample Interviewer Questions:")
            for i, msg in enumerate(assistant_messages[:5], 1):
                summary_parts.append(f"{i}. {msg[:150]}...")

        return "\n".join(summary_parts)

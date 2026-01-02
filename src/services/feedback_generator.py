"""Service for generating comprehensive interview feedback with skill-specific breakdowns."""

from typing import Optional, List, Dict
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field

from src.core.config import settings


class SkillBreakdown(BaseModel):
    """Detailed breakdown for a specific skill."""
    score: float = Field(..., ge=0.0, le=1.0, description="Skill score (0-1)")
    strengths: List[str] = Field(
        default_factory=list, description="Specific strengths in this skill area"
    )
    weaknesses: List[str] = Field(
        default_factory=list, description="Specific weaknesses in this skill area"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Specific recommendations for improving this skill"
    )


class SkillBreakdownResponse(BaseModel):
    """LLM response for skill breakdown generation."""
    communication: SkillBreakdown = Field(..., description="Communication skill breakdown")
    technical: SkillBreakdown = Field(..., description="Technical knowledge skill breakdown")
    problem_solving: SkillBreakdown = Field(..., description="Problem-solving skill breakdown")
    code_quality: SkillBreakdown = Field(..., description="Code quality skill breakdown")


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

        # Build conversation summary
        conversation_summary = self._build_conversation_summary(conversation_history)

        # Build resume context
        resume_summary = ""
        if resume_context:
            resume_summary = f"""
Resume Context:
- Profile: {resume_context.get('profile', 'N/A')[:200]}
- Experience: {resume_context.get('experience', 'N/A')[:300]}
- Education: {resume_context.get('education', 'N/A')[:200]}
"""

        # Build code analysis
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
                average_code_quality = sum(quality_scores) / len(quality_scores)

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
        
        # Build job description context
        job_context = ""
        if job_description:
            job_context = f"""
Job Requirements:
{job_description[:500]}

"""
        else:
            job_context = ""

        # First, generate skill-specific breakdowns
        skill_breakdown_prompt = f"""Analyze the interview performance and provide detailed skill-specific breakdowns.

{job_context}{resume_summary}

Conversation Summary:
{conversation_summary}

{code_analysis}

Topics Covered: {', '.join(topics_list) if topics_list else 'None'}

For EACH of the following skills, provide:

1. **Communication** (0-1):
   - Score based on: clarity of explanations, ability to articulate thoughts, engagement, professionalism
   - 2-3 specific strengths (what they did well in communication)
   - 2-3 specific weaknesses (what could be improved in communication)
   - 2-3 specific recommendations (actionable ways to improve communication)

2. **Technical Knowledge** (0-1):
   - Score based on: depth of understanding, accuracy of answers, relevance, demonstration of expertise
   - 2-3 specific strengths (what they did well technically)
   - 2-3 specific weaknesses (what could be improved technically)
   - 2-3 specific recommendations (actionable ways to improve technical knowledge)

3. **Problem-Solving** (0-1):
   - Score based on: approach to problems, logical thinking, creativity, handling of challenges
   - 2-3 specific strengths (what they did well in problem-solving)
   - 2-3 specific weaknesses (what could be improved in problem-solving)
   - 2-3 specific recommendations (actionable ways to improve problem-solving)

4. **Code Quality** (0-1):
   - Score based on: correctness, efficiency, readability, best practices
   - 2-3 specific strengths (what they did well in code quality) - use "N/A" if no code submitted
   - 2-3 specific weaknesses (what could be improved in code quality) - use "N/A" if no code submitted
   - 2-3 specific recommendations (actionable ways to improve code quality) - use "N/A" if no code submitted
   - Score should be 0.0 if no code was submitted

Be specific and concrete. Reference actual examples from the conversation where possible."""

        try:
            # Generate skill breakdowns
            skill_breakdown_result = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=SkillBreakdownResponse,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer providing detailed, skill-specific feedback. Be specific, concrete, and actionable. Reference actual examples from the conversation.",
                    },
                    {"role": "user", "content": skill_breakdown_prompt},
                ],
                temperature=0.3,
            )

            # Convert skill breakdowns to dict format
            skill_breakdown_dict = {
                "communication": {
                    "score": skill_breakdown_result.communication.score,
                    "strengths": skill_breakdown_result.communication.strengths,
                    "weaknesses": skill_breakdown_result.communication.weaknesses,
                    "recommendations": skill_breakdown_result.communication.recommendations,
                },
                "technical": {
                    "score": skill_breakdown_result.technical.score,
                    "strengths": skill_breakdown_result.technical.strengths,
                    "weaknesses": skill_breakdown_result.technical.weaknesses,
                    "recommendations": skill_breakdown_result.technical.recommendations,
                },
                "problem_solving": {
                    "score": skill_breakdown_result.problem_solving.score,
                    "strengths": skill_breakdown_result.problem_solving.strengths,
                    "weaknesses": skill_breakdown_result.problem_solving.weaknesses,
                    "recommendations": skill_breakdown_result.problem_solving.recommendations,
                },
                "code_quality": {
                    "score": skill_breakdown_result.code_quality.score if code_submissions_count > 0 else 0.0,
                    "strengths": skill_breakdown_result.code_quality.strengths if code_submissions_count > 0 else [],
                    "weaknesses": skill_breakdown_result.code_quality.weaknesses if code_submissions_count > 0 else [],
                    "recommendations": skill_breakdown_result.code_quality.recommendations if code_submissions_count > 0 else [],
                },
            }

        except Exception as e:
            # Fallback: create basic skill breakdowns from scores
            skill_breakdown_dict = {
                "communication": {"score": 0.5, "strengths": [], "weaknesses": [], "recommendations": []},
                "technical": {"score": 0.5, "strengths": [], "weaknesses": [], "recommendations": []},
                "problem_solving": {"score": 0.5, "strengths": [], "weaknesses": [], "recommendations": []},
                "code_quality": {"score": average_code_quality, "strengths": [], "weaknesses": [], "recommendations": []},
            }

        # Now generate overall feedback
        overall_prompt = f"""Generate comprehensive interview feedback based on the conversation and code submissions.

{resume_summary}

Conversation Summary:
{conversation_summary}

{code_analysis}

Topics Covered: {', '.join(topics_list) if topics_list else 'None'}

Skill Scores:
- Communication: {skill_breakdown_dict['communication']['score']:.2f}
- Technical: {skill_breakdown_dict['technical']['score']:.2f}
- Problem-Solving: {skill_breakdown_dict['problem_solving']['score']:.2f}
- Code Quality: {skill_breakdown_dict['code_quality']['score']:.2f}

Calculate an overall score (weighted: Communication 25%, Technical 30%, Problem-Solving 25%, Code Quality 20%).

Provide:
- A concise summary (2-3 sentences)
- Detailed feedback (4-5 sentences) covering all aspects
- Overall strengths (2-3 high-level strengths)
- Overall weaknesses (2-3 high-level areas for improvement)
- Overall recommendations (3-5 specific, actionable recommendations)

Be constructive, specific, and encouraging. Focus on actionable insights."""

        try:
            overall_result = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=InterviewFeedback,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer providing comprehensive, constructive feedback. Be specific, actionable, and encouraging. Focus on helping the candidate improve.",
                    },
                    {"role": "user", "content": overall_prompt},
                ],
                temperature=0.3,
            )

            # Merge skill breakdowns into the result
            overall_result.skill_breakdown = skill_breakdown_dict
            overall_result.communication_score = skill_breakdown_dict["communication"]["score"]
            overall_result.technical_score = skill_breakdown_dict["technical"]["score"]
            overall_result.problem_solving_score = skill_breakdown_dict["problem_solving"]["score"]
            overall_result.code_quality_score = skill_breakdown_dict["code_quality"]["score"]

            # Set code-related fields
            overall_result.code_submissions_count = code_submissions_count
            overall_result.average_code_quality = average_code_quality
            overall_result.topics_covered = topics_list

            return overall_result

        except Exception as e:
            # Return default feedback on error
            return InterviewFeedback(
                overall_score=0.5,
                communication_score=skill_breakdown_dict["communication"]["score"],
                technical_score=skill_breakdown_dict["technical"]["score"],
                problem_solving_score=skill_breakdown_dict["problem_solving"]["score"],
                code_quality_score=skill_breakdown_dict["code_quality"]["score"],
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

        # Extract key messages
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

        # Sample of conversation
        if user_messages:
            summary_parts.append("\nSample User Responses:")
            for i, msg in enumerate(user_messages[:5], 1):
                summary_parts.append(f"{i}. {msg[:150]}...")

        if assistant_messages:
            summary_parts.append("\nSample Interviewer Questions:")
            for i, msg in enumerate(assistant_messages[:5], 1):
                summary_parts.append(f"{i}. {msg[:150]}...")

        return "\n".join(summary_parts)

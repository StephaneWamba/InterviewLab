"""Service for generating interview questions based on resume data."""

from typing import Optional
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field

from src.core.config import settings
from src.models.resume import Resume


class QuestionList(BaseModel):
    """Schema for list of questions."""

    questions: list[dict] = Field(
        ...,
        description="List of interview questions with id, text, type, and context"
    )


class QuestionGenerator:
    """Service for generating interview questions from resume data."""

    def __init__(self):
        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    async def generate_questions(
        self, resume: Resume, question_count: int = 5
    ) -> list[dict]:
        """Generate interview questions based on resume data."""

        if not resume.extracted_data:
            raise ValueError(
                "Resume has no extracted data. Please analyze the resume first.")

        extracted_data = resume.extracted_data

        profile = extracted_data.get("profile", "")
        experience = extracted_data.get("experience", "")
        education = extracted_data.get("education", "")
        projects = extracted_data.get("projects", "")
        hobbies = extracted_data.get("hobbies", "")

        resume_text = f"""
PROFILE:
{profile if profile else "Not provided"}

EXPERIENCE:
{experience if experience else "Not provided"}

EDUCATION:
{education if education else "Not provided"}

PROJECTS:
{projects if projects else "Not provided"}

HOBBIES/INTERESTS:
{hobbies if hobbies else "Not provided"}
"""

        prompt = f"""Generate {question_count} interview questions based on this resume. 
Create a mix of:
- Technical questions (based on experience, projects, and skills mentioned)
- Behavioral questions (based on experience and projects)
- General questions (based on profile and background)

For each question, provide:
- id: sequential number (1, 2, 3, ...)
- text: the question text
- type: "technical", "behavioral", or "general"
- context: brief context about why this question is relevant (optional)

Resume Data:
{resume_text}

Generate diverse, relevant questions that would help assess the candidate's skills and experience."""

        client = self._get_openai_client()

        try:
            result = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=QuestionList,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interviewer. Generate relevant, diverse interview questions based on resume data.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )

            return result.questions

        except Exception as e:
            raise ValueError(f"Failed to generate questions: {str(e)}") from e

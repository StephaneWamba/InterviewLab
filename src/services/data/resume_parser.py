"""Service for parsing and analyzing resumes using pdfplumber and GPT-4o mini with Instructor."""

import asyncio
from pathlib import Path
from typing import Optional
from openai import AsyncOpenAI
import instructor
import pdfplumber
from pydantic import BaseModel, Field

from src.core.config import settings
from src.schemas.resume import ResumeAnalysis


class ResumeParser:
    def __init__(self):
        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self._openai_client = instructor.patch(client)
        return self._openai_client

    async def parse_and_analyze(self, file_path: str, file_type: str) -> ResumeAnalysis:
        path = Path(file_path)
        if not path.is_absolute():
            path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"Resume file not found: {file_path} (resolved: {path})")
        if file_type != "pdf":
            raise ValueError(
                f"Unsupported file type: {file_type}. Only PDF is supported.")
        return await self._parse_pdf_direct(path)

    async def _parse_pdf_direct(self, file_path: Path) -> ResumeAnalysis:
        loop = asyncio.get_event_loop()

        def extract_text():
            text_parts = []
            try:
                with pdfplumber.open(str(file_path)) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
            except Exception as e:
                raise ValueError(
                    f"Failed to extract text from PDF: {file_path}") from e
            return "\n\n".join(text_parts)

        try:
            clean_text = await loop.run_in_executor(None, extract_text)
            if not clean_text or not clean_text.strip():
                raise ValueError(f"No text extracted from PDF: {file_path}")
        except Exception as e:
            raise ValueError(
                f"Failed to extract text from PDF: {file_path}") from e

        return await self._analyze_text(clean_text)

    async def _analyze_text(self, text: str) -> ResumeAnalysis:
        client = self._get_openai_client()

        class ResumeSections(BaseModel):
            profile: Optional[str] = Field(
                None, description="Professional summary, title, objective, or profile information")
            experience: Optional[str] = Field(
                None, description="All work experience entries with companies, roles, dates, locations, and responsibilities")
            education: Optional[str] = Field(
                None, description="All education entries with institutions, degrees, dates, locations, and courses")
            projects: Optional[str] = Field(
                None, description="All project entries with names, descriptions, technologies, and achievements")
            hobbies: Optional[str] = Field(
                None, description="Hobbies, interests, or additional information")

        prompt = f"""Extract the following sections from this resume text as plain text strings.

Resume Text:
{text}

Extract each section as a plain text string. Include ALL information from that section.

1. **profile** - Professional summary, title, objective, or profile information (if present)
2. **experience** - ALL work experience entries. Include: company names, job titles/roles, dates, locations, and responsibilities
3. **education** - ALL education entries. Include: institution names, degrees, fields of study, dates, locations, and courses
4. **projects** - ALL project entries. Include: project names, descriptions, technologies used, and achievements
5. **hobbies** - Hobbies, interests, or additional sections (if present)

Look for sections like: "Expériences professionnelles", "Experience", "Formations", "Education", "Projets personnels", "Projects", "Hobbies", "Interests".

Return each section as a plain text string with all relevant information."""

        try:
            sections_result = await client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=ResumeSections,
                messages=[
                    {"role": "system", "content": "Extract sections from resume text as plain text strings. Include ALL information from each section."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            return ResumeAnalysis(
                profile=sections_result.profile.strip() if sections_result.profile else None,
                experience=sections_result.experience.strip(
                ) if sections_result.experience else None,
                education=sections_result.education.strip() if sections_result.education else None,
                projects=sections_result.projects.strip() if sections_result.projects else None,
                hobbies=sections_result.hobbies.strip() if sections_result.hobbies else None,
            )
        except Exception:
            return ResumeAnalysis()

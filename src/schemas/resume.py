"""Resume-related Pydantic schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class ResumeUpload(BaseModel):
    resume_id: int
    file_name: str
    message: str = "Resume uploaded successfully"


class ResumeAnalysis(BaseModel):
    profile: Optional[str] = Field(
        None, description="Professional summary, title, objective, or profile information as plain text")
    experience: Optional[str] = Field(
        None, description="All work experience entries as plain text")
    education: Optional[str] = Field(
        None, description="All education entries as plain text")
    projects: Optional[str] = Field(
        None, description="All project entries as plain text")
    hobbies: Optional[str] = Field(
        None, description="Hobbies, interests, or additional information as plain text")


class ResumeResponse(BaseModel):
    id: int
    user_id: int
    file_name: str
    file_size: int
    file_type: str
    analysis_status: str
    extracted_data: Optional[dict] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

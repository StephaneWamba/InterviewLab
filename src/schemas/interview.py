"""Interview-related Pydantic schemas."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class InterviewCreate(BaseModel):
    """Schema for creating a new interview."""

    resume_id: Optional[int] = Field(
        None, description="Resume ID to base interview on")
    title: str = Field(..., description="Interview title")
    job_description: Optional[str] = Field(
        None, description="Job description/requirements for the position"
    )


class InterviewResponse(BaseModel):
    """Schema for interview response."""

    id: int
    user_id: int
    resume_id: Optional[int]
    title: str
    status: str
    conversation_history: Optional[list[dict]] = None
    resume_context: Optional[dict] = None
    job_description: Optional[str] = None
    feedback: Optional[dict] = None
    turn_count: int
    current_message: Optional[str] = Field(
        None, description="Current AI message to display")
    sandbox: Optional[dict] = Field(
        None, description="Sandbox state including initial_code, exercise_description, etc.")
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class InterviewStart(BaseModel):
    """Schema for starting an interview."""

    interview_id: int


class InterviewRespond(BaseModel):
    """Schema for submitting a response to the interview."""

    interview_id: int
    message: str = Field(..., description="User's response message")


class InterviewComplete(BaseModel):
    """Schema for completing an interview."""

    interview_id: int


class InterviewSubmitCode(BaseModel):
    """Schema for submitting code during an interview."""

    interview_id: int
    code: str = Field(..., description="Code to execute and review")
    language: str = Field(
        default="python", description="Programming language (python, javascript)"
    )

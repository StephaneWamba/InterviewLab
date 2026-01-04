"""Sandbox-related Pydantic schemas."""

from typing import Optional, Dict
from pydantic import BaseModel, Field


class CodeExecutionRequest(BaseModel):
    """Schema for code execution request."""

    code: str = Field(..., description="Code to execute")
    language: str = Field(
        default="python", description="Programming language (python, javascript)"
    )
    files: Optional[Dict[str, str]] = Field(
        None, description="Additional files (filename -> content)"
    )
    timeout_seconds: Optional[int] = Field(
        None, ge=1, le=300, description="Execution timeout in seconds (1-300)"
    )
    memory_limit: Optional[str] = Field(
        None, description="Memory limit (e.g., '128m', '256m')"
    )
    cpu_limit: Optional[str] = Field(
        None, description="CPU limit (e.g., '0.5' for 50%)"
    )


class CodeExecutionResponse(BaseModel):
    """Schema for code execution response."""

    stdout: str = Field(..., description="Standard output")
    stderr: str = Field(..., description="Standard error output")
    exit_code: int = Field(..., description="Exit code (0 = success)")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")
    success: bool = Field(..., description="Whether execution was successful")
    error: Optional[str] = Field(None, description="Error message if any")


class SandboxSessionCreate(BaseModel):
    """Schema for creating a sandbox session."""

    interview_id: int = Field(..., description="Associated interview ID")
    language: str = Field(
        default="python", description="Programming language"
    )


class SandboxSessionResponse(BaseModel):
    """Schema for sandbox session response."""

    session_id: str = Field(..., description="Unique session ID")
    interview_id: int = Field(..., description="Associated interview ID")
    language: str = Field(..., description="Programming language")
    created_at: str = Field(..., description="Session creation timestamp")


class CodeSubmissionRequest(BaseModel):
    """Schema for submitting code for review."""

    code: str = Field(..., description="Code to submit")
    files: Optional[Dict[str, str]] = Field(
        None, description="Additional files"
    )


class CodeReviewResponse(BaseModel):
    """Schema for code review response."""

    quality_score: float = Field(
        ..., ge=0, le=100, description="Code quality score (0-100)"
    )
    feedback: str = Field(..., description="Detailed feedback")
    strengths: list[str] = Field(..., description="Code strengths")
    weaknesses: list[str] = Field(..., description="Code weaknesses")
    suggestions: list[str] = Field(..., description="Improvement suggestions")










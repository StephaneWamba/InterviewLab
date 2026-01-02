"""Sandbox endpoints for code execution."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.models.user import User
from src.models.interview import Interview
from src.api.v1.dependencies import get_current_user
from src.schemas.sandbox import (
    CodeExecutionRequest,
    CodeExecutionResponse,
    SandboxSessionCreate,
    SandboxSessionResponse,
    CodeSubmissionRequest,
)
from src.services.sandbox_service import SandboxService, Language
from src.services.code_analyzer import CodeAnalyzer
from src.services.code_metrics import get_code_metrics

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared sandbox service instance (thread-safe, can handle concurrent requests)
_sandbox_service = None


def get_sandbox_service() -> SandboxService:
    """Get or create shared sandbox service instance."""
    global _sandbox_service
    if _sandbox_service is None:
        _sandbox_service = SandboxService()
    return _sandbox_service


@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    user: User = Depends(get_current_user),
):
    """
    Execute code in isolated sandbox container.

    Supports Python and JavaScript.
    """
    try:
        # Validate language
        try:
            language = Language(request.language.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported language: {request.language}. Supported: python, javascript",
            )

        sandbox_service = get_sandbox_service()
        logger.info(f"User {user.id} executing {language.value} code")
        result = await sandbox_service.execute_code(
            code=request.code,
            language=language,
            files=request.files,
            timeout_seconds=request.timeout_seconds,
            memory_limit=request.memory_limit,
            cpu_limit=request.cpu_limit,
        )

        return CodeExecutionResponse(**result.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing code: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute code: {str(e)}",
        )


@router.post("/session", response_model=SandboxSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: SandboxSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a sandbox session for an interview.

    Sessions allow tracking code submissions across an interview.
    """
    try:
        # Verify interview exists and belongs to user
        result = await db.execute(
            select(Interview).where(
                Interview.id == request.interview_id,
                Interview.user_id == user.id,
            )
        )
        interview = result.scalar_one_or_none()

        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found",
            )

        # Generate session ID (in production, store in database)
        import uuid
        from datetime import datetime

        session_id = str(uuid.uuid4())

        # TODO: Store session in database (create SandboxSession model)
        # For now, return session info

        return SandboxSessionResponse(
            session_id=session_id,
            interview_id=request.interview_id,
            language=request.language,
            created_at=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        )


@router.post("/session/{session_id}/code", response_model=CodeExecutionResponse)
async def submit_code(
    session_id: str,
    request: CodeSubmissionRequest,
    user: User = Depends(get_current_user),
):
    """
    Submit code for execution in a sandbox session.

    Note: In production, verify session belongs to user and interview.
    """
    try:
        # TODO: Load session from database and verify ownership
        # For now, use default language (python)
        language = Language.PYTHON

        sandbox_service = get_sandbox_service()
        logger.info(f"User {user.id} submitting code to session {session_id}")
        result = await sandbox_service.execute_code(
            code=request.code,
            language=language,
            files=request.files,
        )

        return CodeExecutionResponse(**result.to_dict())

    except Exception as e:
        logger.error(f"Error submitting code: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute code: {str(e)}",
        )


@router.get("/health")
async def sandbox_health():
    """Check sandbox service health."""
    try:
        sandbox_service = get_sandbox_service()
        is_healthy = await sandbox_service.health_check()

        if not is_healthy:
            return {
                "status": "degraded",
                "message": "Docker not available, using fallback execution",
            }

        return {"status": "healthy", "message": "Sandbox service operational"}
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": f"Sandbox service error: {str(e)}",
        }


@router.get("/metrics")
async def get_code_metrics_endpoint(
    user: User = Depends(get_current_user),
    interview_id: int | None = None,
):
    """Get code execution metrics."""
    try:
        metrics = get_code_metrics()

        if interview_id:
            return metrics.get_interview_metrics(interview_id)
        else:
            return metrics.get_user_metrics(user.id)

    except Exception as e:
        logger.error(f"Error getting metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get metrics",
        )

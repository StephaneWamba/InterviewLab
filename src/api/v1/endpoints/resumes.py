"""Resume upload and analysis endpoints."""

import logging
from pathlib import Path
from typing import Annotated
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.core.config import settings
from src.models.user import User
from src.models.resume import Resume
from src.schemas.resume import ResumeUpload, ResumeResponse
from src.services.resume_parser import ResumeParser
from src.api.v1.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=ResumeUpload, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: Annotated[UploadFile, File(...)],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a resume file (PDF only)."""
    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only PDF files are supported.",
        )

    # Validate file size
    file_content = await file.read()
    if len(file_content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE} bytes",
        )

    # Create upload directory if it doesn't exist
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_name = f"{user.id}_{file.filename}"
    file_path = upload_dir / file_name

    with open(file_path, "wb") as f:
        f.write(file_content)

    # Create resume record
    resume = Resume(
        user_id=user.id,
        file_name=file.filename,
        file_path=str(file_path),
        file_size=len(file_content),
        file_type="pdf",
        analysis_status="pending",
    )

    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    # Start async analysis (fire and forget for now)
    # In production, use a task queue like Celery
    try:
        await analyze_resume_background(resume.id, db)
    except Exception as e:
        logger.error(f"Error starting resume analysis: {e}", exc_info=True)

    return ResumeUpload(
        resume_id=resume.id,
        file_name=resume.file_name,
        message="Resume uploaded successfully. Analysis in progress.",
    )


@router.get("/", response_model=list[ResumeResponse])
async def list_resumes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all resumes for the current user."""
    result = await db.execute(
        select(Resume).where(Resume.user_id == user.id).order_by(
            Resume.created_at.desc()
        )
    )
    resumes = result.scalars().all()

    return [
        ResumeResponse(
            id=resume.id,
            user_id=resume.user_id,
            file_name=resume.file_name,
            file_size=resume.file_size,
            file_type=resume.file_type,
            analysis_status=resume.analysis_status,
            extracted_data=resume.extracted_data,
            created_at=resume.created_at.isoformat(),
            updated_at=resume.updated_at.isoformat(),
        )
        for resume in resumes
    ]


@router.get("/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific resume by ID."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()

    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )

    return ResumeResponse(
        id=resume.id,
        user_id=resume.user_id,
        file_name=resume.file_name,
        file_size=resume.file_size,
        file_type=resume.file_type,
        analysis_status=resume.analysis_status,
        extracted_data=resume.extracted_data,
        created_at=resume.created_at.isoformat(),
        updated_at=resume.updated_at.isoformat(),
    )


async def analyze_resume_background(resume_id: int, db: AsyncSession):
    """Background task to analyze resume directly from file."""
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    resume = result.scalar_one_or_none()

    if not resume:
        return

    try:
        # Update status to processing
        resume.analysis_status = "processing"
        await db.commit()

        # Parse and analyze directly (one step)
        parser = ResumeParser()
        analysis = await parser.parse_and_analyze(resume.file_path, resume.file_type)

        resume.extracted_data = analysis.model_dump()
        resume.analysis_status = "completed"
        await db.commit()

    except Exception as e:
        resume.analysis_status = "failed"
        resume.analysis_error = str(e)
        await db.commit()
        raise

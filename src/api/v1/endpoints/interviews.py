"""Interview management endpoints."""

import logging
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.models.user import User
from src.models.resume import Resume
from src.models.interview import Interview
from src.schemas.interview import (
    InterviewCreate,
    InterviewResponse,
    InterviewStart,
    InterviewRespond,
    InterviewComplete,
    InterviewSubmitCode,
)
from src.services.interview_orchestrator import InterviewOrchestrator
from src.services.state_manager import interview_to_state, state_to_interview
from src.services.feedback_generator import FeedbackGenerator
from src.services.analytics_service import InterviewAnalytics
from src.services.livekit_service import LiveKitService
from src.api.v1.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    interview_data: InterviewCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new interview session."""

    resume_context = None
    if interview_data.resume_id:
        result = await db.execute(
            select(Resume).where(
                Resume.id == interview_data.resume_id,
                Resume.user_id == user.id,
                Resume.analysis_status == "completed"
            )
        )
        resume = result.scalar_one_or_none()

        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resume not found or not analyzed yet",
            )

        resume_context = resume.extracted_data or {}

    interview = Interview(
        user_id=user.id,
        resume_id=interview_data.resume_id,
        title=interview_data.title,
        status="pending",
        resume_context=resume_context,
        job_description=interview_data.job_description,
        conversation_history=[],
        turn_count=0,
    )

    db.add(interview)
    await db.commit()
    await db.refresh(interview)

    return _interview_to_response(interview)


@router.get("/", response_model=list[InterviewResponse])
async def list_interviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all interviews for the current user."""
    result = await db.execute(
        select(Interview)
        .where(Interview.user_id == user.id)
        .order_by(Interview.created_at.desc())
    )
    interviews = result.scalars().all()

    return [_interview_to_response(interview) for interview in interviews]


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific interview by ID."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    return _interview_to_response(interview)


@router.post("/start", response_model=InterviewResponse)
async def start_interview(
    data: InterviewStart,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start an interview session - initializes and runs greeting node."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == data.interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    if interview.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Interview is already {interview.status}",
        )

    try:
        orchestrator = InterviewOrchestrator()

        # Convert interview to state
        state = interview_to_state(interview)

        # Execute initialize and greeting nodes
        state = await orchestrator.execute_step(state)

        # Update interview from state
        state_to_interview(state, interview)
        interview.status = "in_progress"
        interview.started_at = datetime.utcnow()

        await db.commit()
        await db.refresh(interview)

        return _interview_to_response(interview)

    except Exception as e:
        logger.error(f"Failed to start interview: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start interview",
        )


@router.post("/respond", response_model=InterviewResponse)
async def respond_to_interview(
    data: InterviewRespond,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a response to the interview - runs adaptive conversation flow."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == data.interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    if interview.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is not in progress",
        )

    try:
        orchestrator = InterviewOrchestrator()

        # Convert interview to state
        state = interview_to_state(interview)

        # Execute graph with user response
        state = await orchestrator.execute_step(state, user_response=data.message)

        # Update interview from state
        state_to_interview(state, interview)

        # Check if interview should be closed
        if state.get("should_close") and state.get("current_node") == "closing":
            interview.status = "completed"
            interview.completed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(interview)

        return _interview_to_response(interview)

    except Exception as e:
        logger.error(
            f"Failed to process interview response: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process response",
        )


@router.post("/complete", response_model=InterviewResponse)
async def complete_interview(
    data: InterviewComplete,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Complete an interview session - runs closing node if not already closed."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == data.interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    if interview.status == "completed":
        return _interview_to_response(interview)

    if interview.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Interview is not in progress (current status: {interview.status})",
        )

    try:
        orchestrator = InterviewOrchestrator()

        # Convert interview to state
        state = interview_to_state(interview)

        # Force closing
        state["should_close"] = True

        # Execute closing node
        state["current_node"] = "closing"
        state = await orchestrator._closing_node(state)

        # Update interview from state
        state_to_interview(state, interview)
        interview.status = "completed"
        interview.completed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(interview)

        return _interview_to_response(interview)

    except Exception as e:
        logger.error(f"Failed to complete interview: {e}", exc_info=True)
        # Still mark as completed even if closing node fails
        interview.status = "completed"
        interview.completed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(interview)
        return _interview_to_response(interview)


@router.post("/submit-code", response_model=InterviewResponse)
async def submit_code_to_interview(
    data: InterviewSubmitCode,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit code for execution and review during an interview."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == data.interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    if interview.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is not in progress",
        )

    try:
        orchestrator = InterviewOrchestrator()

        # Convert interview to state
        state = interview_to_state(interview)

        # Execute code review node
        state = await orchestrator.execute_step(
            state, code=data.code, language=data.language
        )

        # Update interview from state
        state_to_interview(state, interview)

        await db.commit()
        await db.refresh(interview)

        return _interview_to_response(interview)

    except Exception as e:
        logger.error(f"Failed to process code submission: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process code submission",
        )


@router.put("/{interview_id}/sandbox/code")
async def update_sandbox_code(
    interview_id: int,
    code: str = Query(..., description="Current code in sandbox"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update current sandbox code (for polling).
    
    Frontend calls this periodically to update the agent's view of current code.
    This enables real-time interaction like a real interviewer watching over your shoulder.
    """
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    if interview.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is not in progress",
        )

    try:
        orchestrator = InterviewOrchestrator()
        state = interview_to_state(interview)
        
        # Update current code in state (for polling)
        state["current_code"] = code
        state["sandbox"]["is_active"] = True
        state["sandbox"]["last_activity_ts"] = datetime.utcnow().timestamp()
        
        # Check for code changes and provide real-time guidance if needed
        state = await orchestrator._check_sandbox_code_changes(state)
        
        # Update interview from state
        state_to_interview(state, interview)
        await db.commit()
        
        return {"status": "updated", "has_guidance": state.get("next_message") is not None}
        
    except Exception as e:
        logger.error(f"Failed to update sandbox code: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update sandbox code",
        )


@router.get("/{interview_id}/feedback")
async def get_interview_feedback(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive feedback for a completed interview."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    if interview.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview must be completed to generate feedback",
        )

    try:
        # Use existing feedback if available
        if interview.feedback and isinstance(interview.feedback, dict):
            # Check if it's comprehensive feedback (has overall_score)
            if "overall_score" in interview.feedback:
                return interview.feedback

        # Generate new comprehensive feedback
        feedback_generator = FeedbackGenerator()

        # Extract code submissions from conversation history
        code_submissions = []
        if interview.conversation_history:
            for msg in interview.conversation_history:
                if msg.get("metadata", {}).get("type") == "code_review":
                    code_submissions.append({
                        "code": msg.get("metadata", {}).get("code", ""),
                        "code_quality": msg.get("metadata", {}).get("code_quality", {}),
                        "execution_result": msg.get("metadata", {}).get("execution_result", {}),
                    })

        feedback = await feedback_generator.generate_feedback(
            conversation_history=interview.conversation_history or [],
            resume_context=interview.resume_context,
            code_submissions=code_submissions,
            topics_covered=interview.feedback.get(
                "topics_covered", []) if interview.feedback else [],
        )

        # Update interview with comprehensive feedback
        interview.feedback = feedback.model_dump()
        await db.commit()

        return feedback.model_dump()

    except Exception as e:
        logger.error(f"Failed to generate feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate feedback",
        )


@router.get("/analytics/user")
async def get_user_analytics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics for the current user."""
    try:
        analytics_service = InterviewAnalytics()
        analytics = await analytics_service.get_user_analytics(user.id, db)
        return analytics
    except Exception as e:
        logger.error(f"Failed to get user analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get analytics",
        )


@router.get("/analytics/skills/progression")
async def get_skill_progression(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get skill progression over time for charts."""
    try:
        analytics_service = InterviewAnalytics()
        progression = await analytics_service.get_skill_progression(user.id, db)
        return progression
    except Exception as e:
        logger.error(f"Failed to get skill progression: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get skill progression",
        )


@router.get("/analytics/skills/averages")
async def get_skill_averages(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get average skill scores across all completed interviews."""
    try:
        analytics_service = InterviewAnalytics()
        averages = await analytics_service.get_skill_averages(user.id, db)
        return averages
    except Exception as e:
        logger.error(f"Failed to get skill averages: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get skill averages",
        )


@router.get("/analytics/skills/compare")
async def compare_interview_skills(
    interview_ids: str = Query(..., description="Comma-separated list of interview IDs"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare skills across multiple interviews."""
    try:
        # Parse comma-separated interview IDs
        interview_id_list = [int(id.strip()) for id in interview_ids.split(",") if id.strip().isdigit()]
        
        if not interview_id_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please provide valid interview IDs (comma-separated)",
            )

        # Verify all interviews belong to user
        result = await db.execute(
            select(Interview).where(
                Interview.id.in_(interview_id_list),
                Interview.user_id == user.id
            )
        )
        interviews = result.scalars().all()

        if len(interviews) != len(interview_id_list):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more interviews not found",
            )

        analytics_service = InterviewAnalytics()
        comparison = await analytics_service.get_skill_comparison(interview_id_list, db)
        
        # Add interview metadata
        return {
            "comparison": comparison,
            "interviews": [
                {
                    "id": i.id,
                    "title": i.title,
                    "completed_at": i.completed_at.isoformat() if i.completed_at else None,
                }
                for i in interviews
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to compare interview skills: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare interview skills",
        )


@router.get("/{interview_id}/skills")
async def get_interview_skill_breakdown(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed skill breakdown for a specific interview."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    try:
        analytics_service = InterviewAnalytics()
        breakdown = await analytics_service.get_skill_breakdown(interview_id, db)
        
        return {
            "interview_id": interview.id,
            "interview_title": interview.title,
            "completed_at": interview.completed_at.isoformat() if interview.completed_at else None,
            "skill_breakdown": breakdown,
        }
    except Exception as e:
        logger.error(f"Failed to get skill breakdown: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get skill breakdown",
        )


@router.get("/{interview_id}/insights")
async def get_interview_insights(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed insights for a specific interview."""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id, Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    try:
        analytics_service = InterviewAnalytics()
        insights = await analytics_service.get_interview_insights(interview_id, db)
        return insights
    except Exception as e:
        logger.error(f"Failed to get interview insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get insights",
        )


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an interview and clean up associated resources."""
    # Find the interview
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.user_id == user.id
        )
    )
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    try:
        # Delete associated LiveKit room if it exists
        room_name = f"interview-{interview_id}"
        try:
            livekit_service = LiveKitService()
            await livekit_service.delete_room(room_name)
            logger.info(f"Deleted LiveKit room: {room_name}")
        except Exception as e:
            # Don't fail if room doesn't exist or can't be deleted
            logger.warning(f"Could not delete LiveKit room {room_name}: {e}")

        # Delete the interview from database
        await db.delete(interview)
        await db.commit()

        logger.info(f"Deleted interview {interview_id} for user {user.id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        logger.error(f"Failed to delete interview {interview_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete interview",
        )


def _interview_to_response(interview: Interview) -> InterviewResponse:
    """Convert Interview model to InterviewResponse schema."""
    # Get current message from last assistant message in conversation_history
    current_message = None
    if interview.conversation_history:
        for msg in reversed(interview.conversation_history):
            if msg.get("role") == "assistant":
                current_message = msg.get("content")
                break

    return InterviewResponse(
        id=interview.id,
        user_id=interview.user_id,
        resume_id=interview.resume_id,
        title=interview.title,
        status=interview.status,
        conversation_history=interview.conversation_history,
        resume_context=interview.resume_context,
        feedback=interview.feedback,
        turn_count=interview.turn_count,
        current_message=current_message,
        started_at=interview.started_at.isoformat() if interview.started_at else None,
        completed_at=interview.completed_at.isoformat() if interview.completed_at else None,
        created_at=interview.created_at.isoformat(),
        updated_at=interview.updated_at.isoformat(),
    )

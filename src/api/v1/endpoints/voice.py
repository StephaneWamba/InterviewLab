"""Voice endpoints for LiveKit integration."""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import base64

from src.core.database import get_db
from src.models.user import User
from src.models.interview import Interview
from src.api.v1.dependencies import get_current_user
from src.schemas.voice import (
    VoiceTokenRequest,
    VoiceTokenResponse,
    TranscribeRequest,
    TranscribeResponse,
    TTSRequest,
    TTSResponse,
)
from src.services.voice.livekit_service import LiveKitService
from src.services.voice.stt_service import STTService
from src.services.voice.tts_service import TTSService

router = APIRouter()


@router.post("/token", response_model=VoiceTokenResponse)
async def get_voice_token(
    request: VoiceTokenRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a LiveKit access token for a participant.
    
    Also ensures the LiveKit room exists and the interview is in the correct state.
    """
    try:
        livekit_service = LiveKitService()
        
        # Extract interview ID from room name (format: "interview-{id}")
        try:
            interview_id = int(request.room_name.replace("interview-", ""))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid room name format: {request.room_name}. Expected format: 'interview-{{id}}'"
            )
        
        # Verify interview exists and is accessible by user
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
                detail=f"Interview {interview_id} not found"
            )
        
        # Ensure interview is in_progress (should be started before getting token)
        if interview.status != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Interview must be started before connecting. Current status: {interview.status}"
            )
        
        # Create or ensure room exists in LiveKit
        # This ensures the room exists before the agent tries to join
        try:
            await livekit_service.create_room(
                room_name=request.room_name,
                empty_timeout=300,
                max_participants=2,
            )
        except Exception as e:
            # Room might already exist, which is fine
            # Log but don't fail - LiveKit will handle existing rooms
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Room {request.room_name} may already exist: {e}")

        token = livekit_service.create_access_token(
            room_name=request.room_name,
            participant_name=request.participant_name,
            participant_identity=request.participant_identity or str(user.id),
            can_publish=request.can_publish,
            can_subscribe=request.can_subscribe,
        )

        return VoiceTokenResponse(
            token=token,
            room_name=request.room_name,
            url=livekit_service.url,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LiveKit configuration error: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate access token",
        )


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    interview_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Transcribe audio file to text and associate with interview.

    Supports: mp3, mp4, mpeg, mpga, m4a, wav, webm
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

    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an audio file",
        )

    try:
        audio_bytes = await file.read()
        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audio file is empty",
            )

        stt_service = STTService()
        text = await stt_service.transcribe_audio(audio_bytes)

        return TranscribeResponse(text=text, language=None)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to transcribe audio: {str(e)}",
        )


@router.post("/room/create")
async def create_room(
    room_name: str,
    empty_timeout: int = 300,
    max_participants: int = 2,
    user: User = Depends(get_current_user),
):
    """Create a LiveKit room."""
    try:
        livekit_service = LiveKitService()
        room = await livekit_service.create_room(
            room_name=room_name,
            empty_timeout=empty_timeout,
            max_participants=max_participants,
        )

        return room

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LiveKit configuration error: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create room",
        )


@router.get("/room/list")
async def list_rooms(
    user: User = Depends(get_current_user),
):
    """List all active LiveKit rooms."""
    try:
        livekit_service = LiveKitService()
        rooms = await livekit_service.list_rooms()
        return {"rooms": rooms}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LiveKit configuration error: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list rooms",
        )


@router.get("/room/{room_name}")
async def get_room(
    room_name: str,
    user: User = Depends(get_current_user),
):
    """Get information about a specific LiveKit room."""
    try:
        livekit_service = LiveKitService()
        room = await livekit_service.get_room(room_name)
        if room is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Room not found",
            )
        return room
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LiveKit configuration error: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get room",
        )


@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(
    request: TTSRequest,
    user: User = Depends(get_current_user),
):
    """
    Convert text to speech audio.

    Returns base64-encoded MP3 audio data.
    """
    try:
        tts_service = TTSService()
        audio_bytes = await tts_service.text_to_speech(
            text=request.text,
            voice=request.voice,
            model=request.model,
        )

        # Encode audio as base64
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        return TTSResponse(
            audio_base64=audio_base64,
            text=request.text,
            voice=request.voice or "alloy",
            model=request.model or "tts-1",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate speech: {str(e)}",
        )


@router.post("/tts/stream")
async def text_to_speech_stream(
    request: TTSRequest,
    user: User = Depends(get_current_user),
):
    """
    Convert text to speech audio stream.

    Returns MP3 audio stream directly.
    """
    try:
        tts_service = TTSService()
        audio_bytes = await tts_service.text_to_speech(
            text=request.text,
            voice=request.voice,
            model=request.model,
        )

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "attachment; filename=speech.mp3"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate speech: {str(e)}",
        )

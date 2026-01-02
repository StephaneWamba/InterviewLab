"""Voice-related Pydantic schemas."""

from pydantic import BaseModel, Field


class VoiceTokenRequest(BaseModel):
    """Schema for requesting a LiveKit access token."""

    room_name: str = Field(..., description="Name of the LiveKit room")
    participant_name: str = Field(...,
                                  description="Display name of the participant")
    participant_identity: str = Field(
        ..., description="Unique identity of the participant (e.g., user_id)"
    )
    can_publish: bool = Field(
        True, description="Whether the participant can publish tracks")
    can_subscribe: bool = Field(
        True, description="Whether the participant can subscribe to tracks")


class VoiceTokenResponse(BaseModel):
    """Schema for LiveKit access token response."""

    token: str = Field(..., description="JWT access token for LiveKit")
    room_name: str = Field(..., description="Name of the room")
    url: str = Field(..., description="LiveKit server URL")


class TranscribeRequest(BaseModel):
    """Schema for audio transcription request."""

    interview_id: int = Field(...,
                              description="Interview ID to associate transcription with")
    language: str | None = Field(
        None, description="Language code (e.g., 'en', 'es')")


class TranscribeResponse(BaseModel):
    """Schema for transcription response."""

    text: str = Field(..., description="Transcribed text")
    language: str | None = Field(None, description="Detected language code")


class TTSRequest(BaseModel):
    """Schema for text-to-speech request."""

    text: str = Field(..., description="Text to convert to speech")
    voice: str | None = Field(
        None, description="Voice to use (alloy, echo, fable, onyx, nova, shimmer)"
    )
    model: str | None = Field(
        None, description="Model to use (tts-1 or tts-1-hd)"
    )


class TTSResponse(BaseModel):
    """Schema for text-to-speech response."""

    audio_base64: str = Field(...,
                              description="Base64-encoded audio data (MP3 format)")
    text: str = Field(..., description="Original text that was converted")
    voice: str = Field(..., description="Voice used for synthesis")
    model: str = Field(..., description="Model used for synthesis")

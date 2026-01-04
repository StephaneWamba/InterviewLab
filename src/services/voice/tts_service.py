"""Text-to-Speech service using OpenAI TTS API."""

from io import BytesIO
from openai import AsyncOpenAI

from src.core.config import settings


class TTSService:
    """Service for converting text to speech using OpenAI TTS."""

    def __init__(self):
        self._client = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def text_to_speech(
        self,
        text: str,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes:
        """
        Convert text to speech audio.

        Args:
            text: Text to convert to speech
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer). Defaults to config.
            model: Model to use (tts-1 or tts-1-hd). Defaults to config.

        Returns:
            Audio data as bytes (MP3 format)
        """
        client = self._get_client()

        response = await client.audio.speech.create(
            model=model or settings.OPENAI_TTS_MODEL,
            voice=voice or settings.OPENAI_TTS_VOICE,
            input=text,
        )

        return response.content

    async def text_to_speech_stream(
        self,
        text: str,
        voice: str | None = None,
        model: str | None = None,
    ) -> BytesIO:
        """
        Convert text to speech audio stream.

        Args:
            text: Text to convert to speech
            voice: Voice to use. Defaults to config.
            model: Model to use. Defaults to config.

        Returns:
            Audio stream as BytesIO (MP3 format)
        """
        audio_bytes = await self.text_to_speech(text, voice, model)
        return BytesIO(audio_bytes)


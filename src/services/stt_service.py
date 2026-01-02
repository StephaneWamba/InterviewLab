"""Speech-to-Text service using OpenAI Whisper API."""

from io import BytesIO
from openai import AsyncOpenAI

from src.core.config import settings


class STTService:
    """Service for converting speech to text using OpenAI Whisper."""

    def __init__(self):
        self._client = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """
        Transcribe audio to text using OpenAI Whisper API.

        Args:
            audio_bytes: Audio data as bytes (supports mp3, mp4, mpeg, mpga, m4a, wav, webm)
            language: Language code (e.g., 'en', 'es') - optional, will auto-detect if not provided
            prompt: Optional text prompt to guide the model's style or vocabulary

        Returns:
            Transcribed text string
        """
        client = self._get_client()

        # Create BytesIO object for the audio file
        audio_file = BytesIO(audio_bytes)
        audio_file.name = "audio.mp3"

        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language,
            prompt=prompt,
        )

        return response.text

    async def transcribe_audio_file(
        self,
        file_path: str,
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """
        Transcribe audio file to text.

        Args:
            file_path: Path to audio file
            language: Language code (optional)
            prompt: Optional text prompt

        Returns:
            Transcribed text string
        """
        with open(file_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        return await self.transcribe_audio(audio_bytes, language, prompt)

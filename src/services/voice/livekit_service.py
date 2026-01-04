"""LiveKit service for real-time voice communication."""

from typing import Optional
from livekit import api

from src.core.config import settings


class LiveKitService:
    """Service for LiveKit room and token management."""

    def __init__(self):
        """Initialize LiveKit service with API credentials."""
        if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
            raise ValueError(
                "LiveKit API key and secret must be set in environment variables"
            )

        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET
        self.url = settings.LIVEKIT_URL or "wss://interviewlab-livekit.livekit.cloud"

    def create_access_token(
        self,
        room_name: str,
        participant_name: str,
        participant_identity: str,
        can_publish: bool = True,
        can_subscribe: bool = True,
    ) -> str:
        """
        Create a LiveKit access token for a participant.

        Args:
            room_name: Name of the room
            participant_name: Display name of the participant
            participant_identity: Unique identity of the participant (e.g., user_id)
            can_publish: Whether the participant can publish tracks
            can_subscribe: Whether the participant can subscribe to tracks

        Returns:
            JWT token string
        """
        token = api.AccessToken(self.api_key, self.api_secret) \
            .with_identity(participant_identity) \
            .with_name(participant_name) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=can_publish,
                can_subscribe=can_subscribe,
            )) \
            .to_jwt()

        return token

    async def create_room(
        self,
        room_name: str,
        empty_timeout: int = 300,
        max_participants: int = 2,
        enable_transcription: bool = True,
    ) -> dict:
        """
        Create a LiveKit room.

        Args:
            room_name: Name of the room to create
            empty_timeout: Timeout in seconds before room is deleted when empty
            max_participants: Maximum number of participants allowed
            enable_transcription: Enable transcription for the room

        Returns:
            Room information dictionary
        """
        livekit_api = api.LiveKitAPI(self.url, self.api_key, self.api_secret)

        # Create room request - transcription is typically enabled at server level
        # but we can enable it here if the API supports it
        room_request = api.CreateRoomRequest(
            name=room_name,
            empty_timeout=empty_timeout,
            max_participants=max_participants,
        )
        
        room = await livekit_api.room.create_room(room_request)

        return {
            "room_name": room.name,
            "room_sid": room.sid,
            "empty_timeout": room.empty_timeout,
            "max_participants": room.max_participants,
        }

    async def list_rooms(self) -> list[dict]:
        """
        List all active rooms.

        Returns:
            List of room information dictionaries
        """
        livekit_api = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
        rooms_response = await livekit_api.room.list_rooms(api.ListRoomsRequest())

        return [
            {
                "room_name": room.name,
                "room_sid": room.sid,
                "num_participants": room.num_participants,
                "creation_time": str(room.creation_time) if hasattr(room, 'creation_time') else None,
            }
            for room in rooms_response.rooms
        ]

    async def get_room(self, room_name: str) -> Optional[dict]:
        """
        Get information about a specific room.

        Args:
            room_name: Name of the room

        Returns:
            Room information dictionary or None if room doesn't exist
        """
        livekit_api = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
        rooms_response = await livekit_api.room.list_rooms(
            api.ListRoomsRequest(names=[room_name])
        )

        if rooms_response.rooms:
            r = rooms_response.rooms[0]
            return {
                "room_name": r.name,
                "room_sid": r.sid,
                "num_participants": r.num_participants,
                "creation_time": str(r.creation_time) if hasattr(r, 'creation_time') else None,
            }

        return None

    async def delete_room(self, room_name: str) -> bool:
        """
        Delete a LiveKit room.

        Args:
            room_name: Name of the room to delete

        Returns:
            True if room was deleted successfully, False otherwise
        """
        try:
            livekit_api = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
            await livekit_api.room.delete_room(api.DeleteRoomRequest(room=room_name))
            return True
        except Exception as e:
            # Room might not exist, which is fine
            print(f"Error deleting room {room_name}: {e}")
            return False

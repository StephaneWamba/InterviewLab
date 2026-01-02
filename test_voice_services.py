"""Test voice services in Docker container."""

import asyncio
from src.services.livekit_service import LiveKitService
from src.services.tts_service import TTSService


async def test_livekit():
    """Test LiveKit service."""
    print("=" * 60)
    print("Testing LiveKit Service")
    print("=" * 60)
    
    service = LiveKitService()
    print(f"✅ Service initialized")
    print(f"   URL: {service.url}")
    print(f"   API Key: {service.api_key[:10]}...")
    
    # Test token creation
    token = service.create_access_token(
        room_name="test-room",
        participant_name="test-user",
        participant_identity="test-identity"
    )
    print(f"✅ Token created: {len(token)} chars")
    print(f"   Token preview: {token[:50]}...")
    
    print("\n✅ All LiveKit tests passed!")


async def test_tts():
    """Test TTS service."""
    print("\n" + "=" * 60)
    print("Testing TTS Service")
    print("=" * 60)
    
    service = TTSService()
    print("✅ TTS Service initialized")
    
    # Test TTS
    test_text = "Hello, this is a test of the text to speech service."
    audio_bytes = await service.text_to_speech(test_text)
    print(f"✅ TTS generated: {len(audio_bytes)} bytes")
    print(f"   Text: {test_text}")
    
    print("\n✅ All TTS tests passed!")


async def main():
    """Run all tests."""
    try:
        await test_livekit()
        await test_tts()
        print("\n" + "=" * 60)
        print("✅ All voice service tests completed successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())






# LiveKit Transcription Setup Guide

## Overview

Transcription in LiveKit Agents is **automatically enabled** when you use `AgentSession` with an STT (Speech-to-Text) provider. No additional server configuration is required.

## How It Works

1. **Agent Side**: When your agent uses `openai.STT()`, all audio is automatically transcribed
2. **Transmission**: Transcriptions are automatically published to the `lk.transcription` text stream
3. **Frontend**: Your frontend receives transcriptions via `RoomEvent.TranscriptionReceived`

## Current Setup

✅ **Already Configured:**
- Agent uses `openai.STT()` → Transcription enabled automatically
- Frontend component listens for `RoomEvent.TranscriptionReceived`
- Transcription display component is ready to receive and show transcriptions

## Verification Steps

### 1. Check Agent Logs
When the agent processes audio, you should see STT activity in the agent logs:
```
INFO: Processing user message: ...
```

### 2. Check Browser Console
Open browser DevTools console and look for:
```
Transcription received: { text: "...", isFinal: true, participant: "..." }
```

### 3. Test Transcription
1. Start an interview session
2. Speak into your microphone
3. Check the "Conversation" panel on the left side
4. You should see your transcribed speech appear in real-time

## Troubleshooting

### If transcription is not appearing:

1. **Check STT is working**: Verify the agent is receiving and processing audio
   - Check agent logs for STT activity
   - Ensure microphone is enabled and working

2. **Check frontend connection**: Ensure the room is connected
   - Look for "Room connected" in browser console
   - Verify `room.state === 'connected'`

3. **Check transcription events**: Enable debug logging in transcription component
   - Already added: `console.log('Transcription received:', ...)`
   - Check browser console for these logs

4. **Verify LiveKit Cloud**: 
   - Transcription should work automatically on LiveKit Cloud
   - No special configuration needed in dashboard

## LiveKit Cloud Dashboard

If you're using **LiveKit Cloud** (which you are, based on your URL pattern):
- Transcription is **already enabled** and requires no configuration
- No additional settings needed in the dashboard
- Works automatically with agents that have STT configured

## Code Reference

### Agent (Already Configured)
```python
session = AgentSession(
    vad=silero.VAD.load(),
    stt=openai.STT(),  # ← This enables transcription automatically
    llm=orchestrator_llm,
    tts=tts_instance,
)
```

### Frontend (Already Configured)
```typescript
room.on(RoomEvent.TranscriptionReceived, handleTranscription);
```

## Advanced: Disabling Transcription

If you ever need to disable transcription output (not recommended for your use case):

```python
await session.start(
    agent=agent,
    room=ctx.room,
    room_options=room_io.RoomOptions(
        text_output=False,  # Disables transcription output
    )
)
```

## Summary

**No server configuration needed!** Transcription works automatically because:
1. Your agent uses `openai.STT()` ✓
2. AgentSession automatically publishes transcriptions ✓
3. Frontend is listening for transcription events ✓

If transcriptions aren't appearing, check:
- Agent logs for STT activity
- Browser console for transcription events
- Microphone permissions and audio input


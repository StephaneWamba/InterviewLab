# ChatGPT Debug Prompt: LiveKit Transcription and Video Issues

Copy and paste this prompt to ChatGPT:

---

I'm building a real-time interview application using LiveKit Agents (Python) and a React/Next.js frontend. I have two critical issues:

## Issue 1: Real-time Transcription Not Working

**Setup:**

- Backend: Python LiveKit Agent using `AgentSession` with `openai.STT()` and `openai.TTS()`
- Frontend: React component listening for `RoomEvent.TranscriptionReceived`
- Agent code explicitly sets `text_output=True` in `RoomOptions`

**What I see in logs:**

- Room connects successfully: `✅ LiveKit connected`
- Transcription listeners are set up: `Setting up transcription listeners for room: interview-9`
- Microphone enabled: `Microphone enabled successfully`
- Agent is speaking (audio visualizer shows activity)

**What's NOT working:**

- No transcription events are received in the frontend
- The "Conversation" panel remains empty
- No `Transcription received:` logs in console

**Frontend code (simplified):**

```typescript
useEffect(() => {
  if (!room) return;

  const handleTranscription = (segment: TranscriptionSegment) => {
    console.log("Transcription received:", {
      text: segment.text,
      isFinal: segment.isFinal,
      participant: segment.participant?.identity,
    });
    // ... update state
  };

  room.on(RoomEvent.TranscriptionReceived, handleTranscription);

  return () => {
    room.off(RoomEvent.TranscriptionReceived, handleTranscription);
  };
}, [room]);
```

**Agent code (simplified):**

```python
session = AgentSession(
    vad=silero.VAD.load(),
    stt=openai.STT(),
    llm=orchestrator_llm,
    tts=openai.TTS(voice="alloy", model="tts-1-hd"),
)

await session.start(
    agent=agent,
    room=ctx.room,
    room_options=room_io.RoomOptions(
        audio_output=True,
        text_output=True,  # Explicitly enabled
    )
)
```

**Important Note:**
LiveKit documentation mentions transcriptions are sent via **text streams** using topic `lk.transcription`, but I'm currently using `RoomEvent.TranscriptionReceived`. Should I use `registerTextStreamHandler` instead?

**Questions:**

1. Do I need to explicitly enable transcription in the LiveKit Cloud dashboard, or should it work automatically with `AgentSession` + STT?
2. **Are transcriptions sent via `RoomEvent.TranscriptionReceived` OR via text streams (`registerTextStreamHandler('lk.transcription', ...)`)?** The docs mention text streams but the SDK also has TranscriptionReceived event - which should I use?
3. What could prevent transcription events from reaching the frontend even though the room is connected and agent is speaking?
4. Should I use BOTH methods (event listener AND text stream handler) as a fallback?
5. Does transcription only start AFTER the first user speech, or should it also transcribe the agent's speech?

## Issue 2: Local Video Not Displaying

**Setup:**

- Using `Room.localParticipant` to get camera track
- Listening for `RoomEvent.TrackPublished`, `RoomEvent.LocalTrackPublished`, `RoomEvent.TrackSubscribed`
- Room state is `connected`

**What I see in logs:**

- Room connected: `✅ LiveKit connected`
- Camera enabled: `Camera enabled successfully`
- Track publishing: `publishing track {room: 'interview-9', ...}`

**What's NOT working:**

- Video element shows "No video" placeholder
- `hasVideo` state remains `false`
- Video track is not attached to the `<video>` element

**Frontend code (simplified):**

```typescript
const attachLocalVideo = () => {
  let videoTrack = null;

  // Try multiple methods to get track
  const publication = room.localParticipant.getTrackPublication(
    Track.Source.Camera
  );
  if (publication?.track) {
    videoTrack = publication.track;
  }

  if (!videoTrack) {
    for (const pub of room.localParticipant.videoTrackPublications.values()) {
      if (pub.source === Track.Source.Camera && pub.track) {
        videoTrack = pub.track;
        break;
      }
    }
  }

  if (videoTrack && localVideoRef.current) {
    videoTrack.attach(localVideoRef.current);
    setHasVideo(true);
  }
};

// Listeners set up for: Connected, TrackPublished, LocalTrackPublished, TrackSubscribed
```

**Questions:**

1. What's the correct way to access local participant's camera track in LiveKit client SDK?
2. Should I wait for a specific event before trying to attach the track?
3. Could the track be published but not yet subscribed? Should I subscribe to my own local tracks?
4. Is there a delay I should wait for after enabling the camera before the track is available?

## Additional Context

**LiveKit Setup:**

- Using LiveKit Cloud (not self-hosted)
- URL pattern: `wss://*.livekit.cloud`
- Agent connects successfully and can speak (audio works)

**Development Environment:**

- Next.js with Fast Refresh enabled
- Room disconnects on Fast Refresh (expected, but might be causing issues)
- Using `useLiveKitRoom` custom hook that manages room lifecycle

**Logs show:**

- Fast Refresh triggers room disconnect: `🧹 Disconnecting LiveKit room (unmount)`
- Room reconnects automatically
- But transcription and video never work even after reconnection

**Specific Questions:**

1. Should transcription work immediately when `AgentSession` with STT starts, or does it only transcribe after the first user speech? Should I see transcriptions of the agent's own speech (TTS output)?
2. For local video, should the track be available immediately after `setCameraEnabled(true)` succeeds, or is there an async delay? Should I subscribe to my own local tracks?
3. Are there any LiveKit Cloud-specific settings or permissions needed for transcription or video?
4. Could the `AutoSubscribe.AUDIO_ONLY` in the agent connection (`await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)`) be affecting video or transcription on the client side? Does this only affect what the agent subscribes to, or does it affect the entire room?
5. For local video, should I wait for `TrackSubscribed` event for my own local video track, or is `TrackPublished` enough? The track seems to be published (logs show it) but not attached to the video element.

Please help me debug both issues with specific code fixes or configuration steps.

---

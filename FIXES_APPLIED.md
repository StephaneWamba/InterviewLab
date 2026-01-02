# Fixes Applied: Transcription & Video Issues

## Summary

Fixed both critical issues based on ChatGPT's diagnosis:
1. **Transcription**: Changed from `RoomEvent.TranscriptionReceived` to text streams (`registerTextStreamHandler`)
2. **Video**: Fixed local video attachment to use `LocalTrackPublished` event correctly

## Issue 1: Transcription Fixed ✅

### Root Cause
- `RoomEvent.TranscriptionReceived` only works for LiveKit Cloud Transcription service
- AgentSession STT (like `openai.STT()`) outputs transcriptions via **text streams**, not events
- Topic: `lk.transcription`

### Solution Applied
- ✅ Removed: `room.on(RoomEvent.TranscriptionReceived, ...)`
- ✅ Added: `room.registerTextStreamHandler('lk.transcription', handler)`
- ✅ Handler reads text data using `reader.readAll()`
- ✅ Checks `lk.transcription_final` attribute for final vs interim
- ✅ Extracts participant info from handler parameters

### Files Changed
- `frontend/components/interview/transcription-display.tsx`

### Key Code Changes
```typescript
// OLD (didn't work):
room.on(RoomEvent.TranscriptionReceived, handleTranscription);

// NEW (correct):
room.registerTextStreamHandler('lk.transcription', async (reader, participantInfo) => {
  const textData = await reader.readAll();
  const isFinal = reader.info?.attributes?.['lk.transcription_final'] === 'true';
  // ... process transcription
});
```

## Issue 2: Local Video Fixed ✅

### Root Cause
- Local tracks don't fire `TrackSubscribed` events (only remote tracks do)
- Local tracks are published asynchronously after `setCameraEnabled(true)`
- Need to wait for `LocalTrackPublished` event
- Track must be attached directly from the publication

### Solution Applied
- ✅ Removed: Multiple track access methods and `TrackSubscribed` handler
- ✅ Simplified: Use ONLY `LocalTrackPublished` event
- ✅ Direct attachment: Attach track from publication in the event handler
- ✅ Fallback: Check for already-published tracks when component mounts
- ✅ Cleanup: Properly handle `LocalTrackUnpublished` event

### Files Changed
- `frontend/components/interview/participant-video.tsx`

### Key Code Changes
```typescript
// OLD (didn't work reliably):
const attachLocalVideo = () => {
  // Try multiple methods, use TrackSubscribed, etc.
};

// NEW (correct):
const handleLocalTrackPublished = (publication: any) => {
  if (publication?.source === Track.Source.Camera && publication?.track) {
    publication.track.attach(localVideoRef.current);
    setHasVideo(true);
  }
};
room.on(RoomEvent.LocalTrackPublished, handleLocalTrackPublished);
```

## Testing Checklist

### Transcription
- [ ] Start an interview session
- [ ] Speak into microphone
- [ ] Check browser console for: `📝 Transcription received:`
- [ ] Verify transcriptions appear in "Conversation" panel
- [ ] Check that both interim and final transcriptions work

### Video
- [ ] Start an interview session
- [ ] Enable camera (should happen automatically)
- [ ] Check browser console for: `🎥 Local camera track published`
- [ ] Verify video appears in left panel
- [ ] Toggle camera off/on and verify it updates correctly

## Expected Console Logs

### Transcription Working
```
Setting up transcription text stream handler for room: interview-X
✅ Transcription text stream handler registered for topic: lk.transcription
📝 Transcription received: { text: "...", isFinal: true, ... }
```

### Video Working
```
🎥 Local camera track published, attaching...
✅ Video track attached successfully
```

## Notes

- **Transcription timing**: Only starts after user speaks (no speech = no STT = no events)
- **Video timing**: Track is published asynchronously after camera is enabled
- **AutoSubscribe.AUDIO_ONLY**: Does NOT affect local video or transcription (only affects what agent subscribes to)
- Both fixes are backward compatible and don't require agent-side changes


# LiveKit Room Connection Issues - Detailed Analysis Prompt for ChatGPT

## Context
I'm building a React/Next.js application using LiveKit for real-time voice/video communication. The app connects users to LiveKit rooms, but the room keeps disconnecting immediately after connection, and the UI shows "Room is disconnected" even when the user expects it to be connected.

## Technical Stack
- **Frontend**: Next.js 16.1.1 with React (Turbopack)
- **LiveKit Client**: `livekit-client` library
- **State Management**: React hooks (`useState`, `useEffect`)
- **Development Mode**: Fast Refresh/HMR enabled (causing component re-renders)

## Current Implementation Issues

### Issue 1: useEffect Dependency Loop
```typescript
// In frontend/app/dashboard/interviews/[id]/page.tsx
useEffect(() => {
  if (!voiceToken || roomInstance) return;  // Guard clause
  
  const connectToRoom = async () => {
    // ... connection logic ...
    setRoomInstance(room);  // Sets roomInstance
  };
  
  connectToRoom();
  
  return () => {
    // Cleanup disconnects room
    if (room) {
      room.disconnect();
    }
  };
}, [voiceToken, roomInstance]);  // ⚠️ PROBLEM: roomInstance is a dependency
```

**Problem**: The useEffect has `roomInstance` in its dependency array, but it also sets `roomInstance` inside the effect. This creates a cycle:
1. Effect runs → connects → sets `roomInstance`
2. `roomInstance` changes → effect runs again
3. Cleanup runs → disconnects room
4. New connection attempt → repeats

### Issue 2: Fast Refresh / HMR Disconnections
During development, Next.js Fast Refresh causes component re-renders. Every re-render triggers the cleanup function, which disconnects the room.

**Console Evidence**:
```
[Fast Refresh] rebuilding
disconnect from room
[Fast Refresh] done
Room not ready for track publishing
```

### Issue 3: Missing Disconnected Event Handler
The room can disconnect for reasons outside our control (network issues, server-side disconnects, token expiry), but there's no listener for `RoomEvent.Disconnected` to update the UI state.

### Issue 4: Room State Not Monitored
After connection, there's no ongoing monitoring of room state. If the room disconnects, the UI state (`roomInstance`) still holds a reference to a disconnected room object, leading to:
- Buttons showing as enabled but not working
- `room.state === 'disconnected'` when checked
- User sees "disconnected" banner but can't reconnect

### Issue 5: Multiple Room Instances
The cleanup function checks `if (room)` where `room` is a local variable in the effect scope. During Fast Refresh or re-renders, new effect instances can create multiple room objects, leading to orphaned connections.

## Current Behavior
1. User clicks "Enable Video" → Gets voice token → useEffect runs
2. Room connects successfully → `Connected` event fires
3. `setRoomInstance(room)` is called
4. **IMMEDIATELY AFTER**: Because `roomInstance` changed, useEffect re-runs
5. Cleanup function disconnects the room
6. UI shows "Room is disconnected" banner
7. Buttons don't work because `room.state === 'disconnected'`
8. User can't reconnect without refreshing the page

## Console Logs Observed
```
[Fast Refresh] rebuilding
disconnect from room Object
Room not ready for track publishing
testAudio called {roomInstance: true, state: 'disconnected'}
toggleVideo called {room: true, roomState: 'disconnected'}
toggleMute called {room: true, roomState: 'disconnected'}
```

## Questions for ChatGPT

1. **How should I structure the useEffect dependency array to prevent the reconnect loop?**
   - Should `roomInstance` be in dependencies?
   - Should I use a ref instead of state for the room instance?
   - Should I track connection state separately from the room instance?

2. **How to handle Fast Refresh / HMR without disconnecting the room?**
   - Should I check if the room is already connected before creating a new one?
   - Should I use a global/singleton pattern to persist room across re-renders?
   - Should I disable Fast Refresh for this specific component?

3. **What's the correct pattern for managing LiveKit Room lifecycle in React?**
   - When should I create the Room instance?
   - When should I disconnect (only on component unmount or also on token change)?
   - How to handle reconnection after unexpected disconnects?

4. **How to properly monitor room state and handle disconnections?**
   - Should I add a `RoomEvent.Disconnected` listener?
   - How to distinguish between intentional and unintentional disconnections?
   - How to provide a "Reconnect" button when room disconnects?

5. **Is there a better pattern than useEffect for managing persistent WebSocket connections in React?**
   - Should I use a custom hook?
   - Should I use a context provider?
   - Should I use a state management library (Zustand, Redux)?

6. **How to prevent multiple room instances from being created?**
   - Should I check `roomInstance` state before creating a new room?
   - Should I use a ref to track if connection is in progress?
   - Should I debounce the connection attempt?

## Specific Code Pattern I Need Help With

I need a pattern that:
- Connects to LiveKit room when `voiceToken` is available
- Preserves connection across Fast Refresh / component re-renders
- Handles unexpected disconnections gracefully
- Allows manual reconnection
- Cleans up properly only on actual component unmount
- Doesn't create multiple room instances
- Updates UI state when room connects/disconnects

## Additional Context

- The room connection takes ~2-3 seconds to establish
- We wait for `Connected` event before enabling tracks
- We use retry logic for track publishing (3 attempts with exponential backoff)
- The room token has a specific format: `interview-{interviewId}`
- Multiple users can be in the same room (user + AI agent)

Please provide a complete, working implementation pattern for managing LiveKit room connections in a React component that handles all these edge cases.


# LiveKit Agent Initialization Timeout Configuration

## Understanding the Timeout Issue

The initialization timeout happens when LiveKit's process supervisor waits for the agent process to respond to an initialization handshake. If the process doesn't respond within the timeout period (~1-2 seconds by default), it's killed.

## Can Increasing Timeout Solve the Issue?

**Short answer**: Yes, but it's a **temporary workaround**, not a permanent solution.

### Why It Helps:
- Gives more time for heavy imports (VAD, database, orchestrator)
- Allows agent to complete initialization even with slower operations
- Reduces false timeouts during agent startup

### Why It's Not Ideal:
- Doesn't fix the root cause (heavy operations during initialization)
- Still has a timeout limit (can't be infinite)
- Doesn't improve actual initialization speed
- Masks underlying performance issues

### Recommendation:
- **Use increased timeout as a temporary measure** while optimizing initialization
- **Show UI feedback** to inform users during initialization
- **Continue optimizing** the code to reduce initialization time

## How to Increase Timeout

The timeout is controlled by **LiveKit Server configuration**, not the agent code itself.

### Option 1: LiveKit Server Config (If Self-Hosted)

If you're running LiveKit server yourself, you can configure the timeout in the server config:

```yaml
# livekit.yaml or environment variables
agent:
  process_pool:
    init_timeout: 5s  # Default is usually 1-2s
    shutdown_timeout: 5s
```

Or via environment variable:
```bash
LIVEKIT_AGENT_PROCESS_POOL_INIT_TIMEOUT=5s
```

### Option 2: LiveKit Cloud

If using LiveKit Cloud, you may need to:
1. Contact LiveKit support to increase the timeout
2. Use their dashboard/config to adjust agent settings
3. Check their documentation for timeout configuration

### Option 3: AgentServer Configuration (Limited)

The `AgentServer` in your code doesn't directly control the timeout, but you can configure process pool settings:

```python
server = AgentServer(
    num_idle_processes=2,  # Prewarm processes
    shutdown_timeout=5,    # Cleanup timeout
)
```

**Note**: The initialization timeout is controlled by the LiveKit server, not the agent code.

## UI Feedback Solution (Recommended)

Since the timeout is server-side, the best approach is:

1. **Show "Interviewer is preparing..." message** in the UI
2. **Keep the timeout reasonable** (don't make it too long)
3. **Optimize agent initialization** to be fast

The UI feedback ensures users know what's happening, even if initialization takes a few seconds.

## Implementation Status

✅ **UI Feedback**: Implemented
- Shows "Connecting to room..." when connecting
- Shows "Interviewer is preparing..." when waiting for agent

⏳ **Timeout Increase**: Server-side configuration required
- Need to configure LiveKit server (self-hosted) or contact LiveKit Cloud support
- Agent code cannot directly control this timeout

✅ **Agent Optimization**: In progress
- Deferred VAD loading
- Two-phase orchestrator initialization
- Bootstrap resources pattern

## Testing the Timeout

To test if timeout increase helps:

1. **Check current timeout** in LiveKit server logs
2. **Increase timeout** to 5-10 seconds
3. **Monitor initialization times** in agent logs
4. **Verify** agent processes no longer timeout

## Best Practice Approach

**Recommended Strategy**:
1. ✅ **Fix the root cause**: Optimize agent initialization (fast handshake)
2. ✅ **Add UI feedback**: Show "Interviewer is preparing..." message
3. ⚠️ **Increase timeout slightly**: As a safety net (3-5 seconds max)
4. ✅ **Monitor and measure**: Track initialization times

This gives you:
- Fast initialization (user experience)
- User feedback (transparency)
- Safety margin (reliability)
- Measurable improvement (monitoring)


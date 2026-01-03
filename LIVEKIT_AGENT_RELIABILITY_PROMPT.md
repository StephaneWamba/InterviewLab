# LiveKit Agent Reliability Issues - Comprehensive Analysis & Solution Request

## Context

I'm building a production-grade voice interview platform using LiveKit Agents SDK (Python). The agent connects to LiveKit rooms to conduct AI-powered technical interviews with real-time voice interaction, transcription, and code sandbox integration.

**Tech Stack:**
- **Framework**: LiveKit Agents SDK (Python) v0.7.0+
- **Python**: 3.11+
- **Database**: PostgreSQL (async via SQLAlchemy)
- **LLM**: Custom orchestrator using OpenAI GPT-4o
- **TTS/STT**: OpenAI TTS/STT plugins
- **VAD**: Silero VAD for voice activity detection
- **Deployment**: Docker containers, LiveKit Cloud/Server

**Architecture:**
- `AgentServer` with `@server.rtc_session()` entrypoint
- Custom `OrchestratorLLM` that integrates with interview orchestrator
- Database sessions for state management
- Background checkpointing and logging

---

## Symptoms & Issues Encountered

### 1. **Initialization Timeout Errors**

**Symptom:**
```
{"message": "killing process", "level": "INFO", "name": "livekit.agents", "pid": 394, "timestamp": "2026-01-02T23:58:59.860618+00:00"}
{"message": "sending SIGUSR1 signal to process", "level": "INFO", "name": "livekit.agents", "pid": 394, "timestamp": "2026-01-02T23:58:59.861152+00:00"}
{"message": "process exited with non-zero exit code -10", "level": "ERROR", "name": "livekit.agents", "pid": 394, "timestamp": "2026-01-02T23:58:59.901094+00:00"}
{"message": "error initializing process", "level": "ERROR", "name": "livekit.agents", "exc_info": "Traceback (most recent call last):\n  File \"/usr/local/lib/python3.11/asyncio/tasks.py\", line 500, in wait_for\n    return fut.result()\n           ^^^^^^^^^^^^\n  File \"/usr/local/lib/python3.11/site-packages/livekit/agents/ipc/channel.py\", line 47, in arecv_message\n    return _read_message(await dplx.recv_bytes(), messages)\n                         ^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/usr/local/lib/python3.11/site-packages/livekit/agents/utils/aio/duplex_unix.py\", line 35, in recv_bytes\n    len_bytes = await self._reader.readexactly(4)\n                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/usr/local/lib/python3.11/asyncio/streams.py\", line 750, in readexactly\n    await self._wait_for_data('readexactly')\n  File \"/usr/local/lib/python3.11/asyncio/streams.py\", line 543, in _wait_for_data\n    await self._waiter\nasyncio.exceptions.CancelledError\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File \"/usr/local/lib/python3.11/site-packages/livekit/agents/ipc/supervised_proc.py\", line 210, in initialize\n    init_res = await asyncio.wait_for(\n               ^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/usr/local/lib/python3.11/asyncio/tasks.py\", line 502, in wait_for\n    raise exceptions.TimeoutError() from exc\nTimeoutError"}
```

**Analysis:**
- LiveKit's process supervisor expects agent process to respond to initialization handshake quickly
- If process doesn't respond within timeout window, supervisor kills it with SIGUSR1
- Exit code -10 indicates process was killed by signal
- The `TimeoutError` occurs in `supervised_proc.py` when waiting for initialization message

**Root Causes Identified:**
1. **VAD Model Loading**: Silero VAD model loading is synchronous and can take 2-5 seconds, blocking initialization
2. **Database Connection Pool**: Creating async database engine/session factory at module import time
3. **Settings Loading**: Pydantic settings validation during import
4. **Heavy Imports**: Importing orchestrator, models, and other heavy dependencies at module level

### 2. **Race Conditions in Process Initialization**

**Symptom:**
- Agent process starts but fails to complete initialization handshake
- Process is killed before it can establish IPC channel with supervisor
- Intermittent failures - works sometimes, fails other times (suggests race condition)

**Possible Causes:**
- Multiple blocking operations competing for event loop time
- Database pool creation happening synchronously
- ML model loading blocking the async event loop

### 3. **Cleanup Errors After Timeout**

**Symptom:**
```
ValueError: process object is closed
```
This occurs in `supervised_proc.py` when trying to kill an already-closed process during cleanup after timeout.

**Analysis:**
- Cleanup logic attempts to kill process that has already exited
- Indicates timing issues in the supervisor's process lifecycle management

### 4. **Partial Workarounds Applied (Current State)**

**Current Mitigations:**
1. **VAD Loading Deferred**: VAD now loads asynchronously after session starts
   - ✅ Prevents blocking during initialization
   - ⚠️ Agent starts without VAD (less accurate turn detection)
   - ⚠️ Not ideal for production - want VAD available immediately

2. **No Prewarming**: Disabled agent prewarming to avoid initialization overhead
   - ⚠️ Increases cold start latency for first request
   - ⚠️ Each new agent job has to initialize from scratch

---

## Current Implementation Details

### Entrypoint Structure:
```python
@server.rtc_session()
async def entrypoint(ctx: JobContext):
    """Entry point for the LiveKit agent job."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    # Extract interview_id from room name
    interview_id = int(ctx.room.name.replace("interview-", ""))
    
    # Create database session and orchestrator
    db = AsyncSessionLocal()
    orchestrator = InterviewOrchestrator()
    
    # Create custom LLM
    orchestrator_llm = OrchestratorLLM(interview_id, db, orchestrator)
    
    # Create TTS instance
    tts_instance = openai.TTS(voice=settings.OPENAI_TTS_VOICE, model=settings.OPENAI_TTS_MODEL)
    
    # VAD loading deferred (currently None during init)
    vad_instance = None
    
    # Create agent session
    session = AgentSession(
        vad=vad_instance,
        stt=openai.STT(),
        llm=orchestrator_llm,
        tts=tts_instance,
    )
    
    # Start session
    await session.start(agent=agent, room=ctx.room, ...)
    
    # Load VAD in background (current workaround)
    asyncio.create_task(load_vad_async())
```

### Module-Level Initialization:
- `AgentServer()` created at module level
- Database engine created at module import time
- Settings loaded via Pydantic (synchronous validation)
- Heavy imports (orchestrator, models, etc.) at module level

---

## Questions & Solution Requests

### 1. **Optimal Initialization Pattern**
- What is the **best practice pattern** for LiveKit agent initialization to avoid timeouts?
- Should heavy operations (VAD, DB connections, orchestrator) be:
  - Deferred until after `ctx.connect()`?
  - Pre-warmed at server startup (not process startup)?
  - Loaded lazily on first use?
  - Loaded in a separate initialization phase?

### 2. **VAD Loading Strategy**
- How can I **preload VAD model** without blocking process initialization?
- Is there a way to:
  - Pre-warm VAD at server level (shared across processes)?
  - Load VAD asynchronously before agent session starts?
  - Use a VAD instance pool/cache?
- What's the recommended approach for production systems?

### 3. **Database Connection Strategy**
- Should database engine/pool be created:
  - At module import time (current)?
  - In a startup hook/lifespan?
  - Lazily on first use?
- How to handle connection pool initialization in multiprocess agent architecture?

### 4. **Error Handling & Resilience**
- How to **robustly handle initialization failures**?
- What retry/backoff strategy is recommended?
- How to gracefully degrade (e.g., continue without VAD if loading fails)?
- What monitoring/alerting should be in place?

### 5. **Process Pool & Prewarming**
- How does LiveKit's process pool work?
- Can/should I prewarm processes?
- What's the balance between prewarming (faster starts) and resource usage?
- How to handle process lifecycle (creation, reuse, cleanup)?

### 6. **Performance Optimization**
- What are the **critical path** operations during initialization?
- Which operations can be safely deferred?
- How to minimize initialization time while maintaining functionality?
- What's a reasonable initialization timeout target for production?

### 7. **Testing & Debugging**
- How to test initialization reliability locally?
- What logging should be added to diagnose initialization issues?
- How to simulate the supervisor's initialization handshake?
- Tools/techniques for profiling initialization time?

### 8. **Production Hardening**
- What configuration values are critical for reliability (timeouts, pool sizes, etc.)?
- How to handle resource constraints (memory, CPU limits in containers)?
- What health checks should be implemented?
- How to monitor agent process health and auto-recovery?

---

## Specific Code Questions

1. **Should `AgentServer()` be created at module level or in a startup hook?**

2. **Is this pattern safe for async database connections?**
   ```python
   # At module level
   engine = create_async_engine(database_url, ...)
   AsyncSessionLocal = async_sessionmaker(engine, ...)
   
   # In entrypoint
   db = AsyncSessionLocal()  # Is this async-safe across processes?
   ```

3. **Can VAD be shared across agent processes?**
   ```python
   # Global VAD instance?
   _global_vad = None
   
   async def get_vad():
       global _global_vad
       if _global_vad is None:
           _global_vad = await load_vad_async()
       return _global_vad
   ```

4. **What's the correct pattern for cleanup in entrypoint?**
   ```python
   try:
       # initialization
       await session.start(...)
       # ... run agent
   finally:
       await db.close()  # Is this sufficient?
   ```

---

## Desired Outcome

I need a **production-ready, robust initialization pattern** that:

✅ **Guarantees** agent processes initialize successfully (99.9%+ reliability)
✅ **Minimizes** initialization time (< 1 second ideally)
✅ **Loads** all required components (VAD, DB, orchestrator) before first interaction
✅ **Handles** failures gracefully with proper error handling
✅ **Scales** well in containerized/multiprocess environments
✅ **Provides** clear monitoring and observability

**Please provide:**
1. **Recommended initialization pattern** (pseudocode or actual code)
2. **Best practices** for each component (VAD, DB, orchestrator)
3. **Error handling strategy** with concrete examples
4. **Configuration recommendations** (timeouts, pool sizes, etc.)
5. **Testing approach** for reliability
6. **Production monitoring strategy**

Thank you for your expertise in helping make this system production-ready!


# Interview Agent Refactoring Plan

## Current Issues

1. **Timeout Errors**: Bootstrap happens AFTER `ctx.connect()`, but LiveKit docs recommend heavy operations BEFORE connection
2. **File Length**: 827 lines - difficult to maintain and understand
3. **Import Time**: Must remain <100ms (currently optimized with lazy loading)

## LiveKit Best Practices (from docs)

According to `/agents/logic/external-data.md`:

> **Load time optimizations**
>
> If your agent requires external data in order to start, the following tips can help minimize the impact to the user experience:
>
> 1. For static data (not user-specific) load it in the **prewarm function**
> 2. Send user specific data in the **job metadata**, **room metadata**, or **participant attributes** rather than loading it in the entrypoint.
> 3. **If you must make a network call in the entrypoint, do so BEFORE `ctx.connect()`**. This ensures your frontend doesn't show the agent participant before it is listening to incoming audio.

## Key Architectural Change Needed

### Current Pattern (WRONG):

```python
@server.rtc_session()
async def entrypoint(ctx: JobContext):
    await ctx.connect()  # Handshake completes
    # Bootstrap AFTER connection
    resources = await bootstrap_resources(ctx, interview_id)
    session = AgentSession(...)
    await session.start(...)
```

### Recommended Pattern (CORRECT):

```python
@server.rtc_session()
async def entrypoint(ctx: JobContext):
    # Extract interview_id from room name BEFORE connection
    interview_id = int(ctx.room.name.replace("interview-", ""))

    # Bootstrap BEFORE connection (frontend won't show agent until ready)
    resources = await bootstrap_resources(ctx, interview_id)

    # Now connect (handshake happens here, agent is ready)
    await ctx.connect()

    # Create and start session
    session = AgentSession(...)
    await session.start(...)
```

## Refactoring Structure

### Proposed Module Structure:

```
src/agents/
├── __init__.py
├── interview_agent.py          # Main entrypoint (simplified, ~200 lines)
├── tts_utils.py                # TTS text processing utilities
├── orchestrator_llm.py         # OrchestratorLLM and OrchestratorLLMStream classes
├── resources.py                # AgentResources, bootstrap_resources, VAD handling
└── checkpoint_utils.py         # Checkpoint background tasks
```

### Module Responsibilities:

#### `interview_agent.py` (~200 lines)

- Main entrypoint function
- AgentSession setup
- Agent instructions
- Greeting logic (if needed)
- Minimal imports (stdlib + LiveKit core only)

#### `tts_utils.py` (~100 lines)

- `prepare_text_for_tts()`
- `normalize_numbers_and_symbols()`
- `split_into_sentences()`
- No heavy imports

#### `orchestrator_llm.py` (~300 lines)

- `OrchestratorLLM` class
- `OrchestratorLLMStream` class
- Lazy imports inside methods (after handshake)

#### `resources.py` (~200 lines)

- `AgentResources` class
- `bootstrap_resources()` function
- `get_vad()` function
- All heavy imports happen here (after handshake)

#### `checkpoint_utils.py` (~50 lines)

- `_checkpoint_greeting_in_background()`
- `_checkpoint_in_background()` (from OrchestratorLLMStream)
- Lazy imports

## Import Time Safety

**CRITICAL**: All modules must follow lazy loading pattern:

1. **Module-level imports** (in `interview_agent.py` only):

   - stdlib only (asyncio, logging, pathlib, typing)
   - LiveKit core only (Agent, AgentServer, etc.)
   - TYPE_CHECKING imports for type hints

2. **Lazy imports** (in all other modules):

   - All `src.*` imports inside functions
   - All `sqlalchemy` imports inside functions
   - All plugin imports (openai, silero) inside functions

3. **Import chain**:
   ```
   interview_agent.py (main entrypoint)
   ├── Imports tts_utils (fast, no heavy deps)
   ├── Imports orchestrator_llm (only TYPE_CHECKING at module level)
   ├── Imports resources (only TYPE_CHECKING at module level)
   └── Imports checkpoint_utils (only TYPE_CHECKING at module level)
   ```

## Implementation Steps

1. ✅ Create refactoring plan
2. ⬜ Create `tts_utils.py` module
3. ⬜ Create `orchestrator_llm.py` module
4. ⬜ Create `resources.py` module
5. ⬜ Create `checkpoint_utils.py` module
6. ⬜ Refactor `interview_agent.py` to use new modules
7. ⬜ **Move bootstrap_resources() call BEFORE ctx.connect()**
8. ⬜ Test import time (<100ms)
9. ⬜ Test agent initialization
10. ⬜ Verify no timeout errors

## Benefits

1. **Better timing**: Bootstrap before connection prevents timeout issues
2. **Maintainability**: Smaller, focused modules easier to understand
3. **Testability**: Each module can be tested independently
4. **Reusability**: TTS utils and resources can be reused
5. **Performance**: Still maintains <100ms import time with proper lazy loading

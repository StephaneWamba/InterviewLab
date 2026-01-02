# Interview Agent Stuck in Greeting Loop - Debug Prompt

## Problem Description

The interview agent is stuck in an infinite loop, repeatedly sending the greeting message every time the user responds. The conversation flow looks like this:

```
User: "Hi."
Agent: "Hi there! It's great to meet you..." (greeting)
User: "Thank you."
Agent: "Hi there! It's great to meet you..." (SAME greeting again)
User: "I've been working in product engineering..."
Agent: "Hi there! It's great to meet you..." (SAME greeting again)
```

The agent never progresses past the greeting, no matter how the user responds.

## System Architecture

This is a LiveKit voice agent application using:

- **Backend**: Python FastAPI with LiveKit Agents SDK
- **Agent File**: `src/agents/interview_agent.py`
- **Orchestrator**: `src/services/interview_orchestrator.py`
- **State Management**: LangGraph-style state with PostgreSQL checkpointing
- **Flow**: User speaks → STT → OrchestratorLLMStream → Orchestrator.execute_step → Response → TTS

## Key Code Sections

### 1. Agent Entrypoint (src/agents/interview_agent.py, lines 417-497)

The entrypoint function sends an initial greeting:

```python
# Send initial greeting after session starts
if interview and interview.status == "in_progress":
    checkpoint_service = get_checkpoint_service()
    existing_state = await checkpoint_service.restore(interview_id, db)

    has_any_messages = interview.conversation_history and len(interview.conversation_history) > 0

    if not has_any_messages and not existing_state:
        # Generate and send greeting
        state = interview_to_state(interview)
        state = await orchestrator.execute_step(state)  # <-- This generates greeting
        greeting = state.get("next_message")
        await session.say(greeting)
        # Checkpoint is saved after greeting
```

### 2. OrchestratorLLMStream.\_run (src/agents/interview_agent.py, lines 155-282)

This processes user messages:

```python
async def _run(self) -> None:
    # Get user's last message
    user_message = ""
    if self._chat_ctx.items:
        for item in reversed(self._chat_ctx.items):
            if item.type == "message" and item.role == "user":
                user_message = item.text_content or ""
                break

    # Load interview from database
    interview = await db.execute(select(Interview).where(Interview.id == interview_id))

    # Attempt to restore state from checkpoint
    checkpoint_service = get_checkpoint_service()
    state = await checkpoint_service.restore(interview_id, db)
    if state:
        logger.info("Restored state from checkpoint")
    else:
        # If no checkpoint, initialize from interview data
        state = interview_to_state(interview)  # <-- POTENTIAL ISSUE HERE

    # Execute orchestrator step with user response
    state = await self._llm_instance.orchestrator.execute_step(state, user_response=user_message)

    # Get response
    response = state.get("next_message", "...")

    # Update interview from state
    state_to_interview(state, interview)
    await db.commit()

    # Checkpoint state after each step
    await checkpoint_service.checkpoint(state, db)

    # Push response to stream
    self._event_ch.send_nowait(llm.ChatChunk(...))
```

### 3. Orchestrator.execute_step (src/services/interview_orchestrator.py, lines 1299-1411)

The main execution flow:

```python
async def execute_step(self, state: InterviewState, user_response: str = "") -> InterviewState:
    """Execute one step of the interview workflow."""

    # Initialize state if needed
    state = await self._initialize_state(state)

    # Store user response
    if user_response:
        state["last_response"] = user_response
        state["turn_count"] = state.get("turn_count", 0) + 1
        state["conversation_history"].append({
            "role": "user",
            "content": user_response,
            "timestamp": datetime.utcnow().isoformat()
        })

    # Monitor sandbox
    state = await self._monitor_sandbox_node(state)

    # Detect user intent
    state = await self._detect_user_intent_node(state)

    # Decide next action
    state = await self._decide_next_action(state)

    # Execute action node based on _next_action
    next_action = state.get("_next_action", "question")

    if next_action == "greeting":
        state = await self._greeting_node(state)  # <-- ISSUE: Might be routing here repeatedly
    elif next_action == "question":
        state = await self._question_node(state)
    # ... other actions

    return state
```

### 4. Decision Node (\_decide_next_action)

This determines which node to execute next. If it keeps routing to "greeting", that would explain the loop.

## Potential Root Causes

1. **State Restoration Issue**: When restoring state from checkpoint, the `turn_count` or `conversation_history` might not be properly loaded, causing the orchestrator to think it's still at the start.

2. **Decision Logic Bug**: The `_decide_next_action` function might always route to "greeting" if certain conditions aren't met.

3. **Checkpoint Not Saving Conversation**: The checkpoint might not be saving the conversation history properly, so each user message resets the state.

4. **Greeting Node Always Executing**: The greeting node might be executing even when `turn_count > 0` or conversation history exists.

5. **State Initialization Issue**: `interview_to_state()` might be resetting the state incorrectly when no checkpoint exists.

6. **Checkpoint Restoration Returning Empty State**: If checkpoint restoration returns a state without conversation history, it might trigger greeting again.

## Questions to Investigate

1. **Is the checkpoint being saved correctly after the greeting?**

   - Check if `checkpoint_service.checkpoint()` is actually persisting the state with conversation_history.

2. **Is the checkpoint being restored correctly?**

   - When a user sends a message, does `checkpoint_service.restore()` return the state with the greeting already in conversation_history?

3. **What does `_decide_next_action` return after the first greeting?**

   - After the greeting is sent and checkpointed, when user responds, what action does the decision node choose?

4. **Is `interview_to_state()` being called incorrectly?**

   - In `OrchestratorLLMStream._run`, if no checkpoint exists, it calls `interview_to_state(interview)`. But if the interview already has conversation_history from the greeting, this might create a conflicting state.

5. **Is the conversation_history being saved to the database?**
   - After the greeting, `state_to_interview(state, interview)` should save the greeting to `interview.conversation_history`. Is this happening?

## Debugging Steps

1. **Check Logs**: Look for these log statements:

   - `"Restored state from checkpoint"` vs `"Initialized new state from interview data"`
   - `"Executing orchestrator step..."`
   - `"Checkpointed state: {checkpoint_id}"`
   - What `last_node` and `_next_action` values are in the state

2. **Verify Database State**: After greeting is sent, check the database:

   - Does `interview.conversation_history` contain the greeting message?
   - Does the `interview_graph_checkpoints` table have a checkpoint with the greeting in the state?

3. **Verify Checkpoint Restoration**: When user responds:

   - What state is returned by `checkpoint_service.restore()`?
   - Does it include the greeting in `conversation_history`?
   - What is the `turn_count`?

4. **Check Decision Logic**: What does `_decide_next_action` return after:
   - First greeting is sent
   - User responds with "Thank you"
   - Should it return "question" or "greeting"?

## Expected Behavior

1. **First Connection**: Agent sends greeting → saves to DB → checkpoints state
2. **User Responds**: Restore checkpoint → detect intent → decide action → should route to "question" node (NOT "greeting")
3. **Subsequent Turns**: Should continue with questions, followups, etc. Never return to greeting

## Files to Review

- `src/agents/interview_agent.py` (lines 417-497 for greeting logic, lines 155-282 for message processing)
- `src/services/interview_orchestrator.py` (lines 1299-1411 for execute_step, \_decide_next_action method)
- `src/services/checkpoint_service.py` (checkpoint save/restore logic)
- `src/services/state_manager.py` (interview_to_state, state_to_interview conversions)

## Expected Fix

The most likely fix is one of these:

1. **Ensure conversation_history is saved before checkpointing** in the greeting flow
2. **Fix decision logic** to never route to "greeting" if conversation_history has entries
3. **Fix state restoration** to properly load conversation_history from checkpoint
4. **Add guard in greeting node** to check if greeting was already sent (check turn_count > 0 or conversation_history exists)

Please analyze the code flow, identify the root cause, and provide a fix that ensures:

- Greeting is only sent once at the very beginning
- State is properly checkpointed with conversation_history
- State restoration properly loads conversation_history
- Decision logic never routes back to greeting after the first turn

# Conversation Issues Analysis

## Transcript Analysis

### Critical Issues Identified

#### 1. **Agent Not Listening to Explicit User Requests** 🔴 CRITICAL
**Problem**: User explicitly asks multiple times:
- "can you please walk me through the code on my resume?"
- "Please, can you allow me to write code on a standard so that you see how I did?"
- "Yeah, can you please walk me through the code on my resume?"

**Agent Response**: Completely ignores these requests and asks unrelated questions instead.

**Root Cause**: 
- The `_detect_user_intent_node` only detects generic intent types (`technical_assessment`, `change_topic`, etc.)
- There's NO specific intent detection for:
  - "write code in sandbox"
  - "review code on resume"
  - "show code"
  - "walk through code"

#### 2. **Agent Restarting/Repeating Greetings** 🔴 CRITICAL
**Problem**: Agent says "Hi Stéphane! It's great to meet you today..." multiple times:
- After user explains overfitting problem
- After user asks to write code
- Multiple times throughout conversation

**Root Cause**: 
- State might be getting reset between turns
- Checkpointing might not be working properly
- Agent might not be maintaining conversation context

#### 3. **No Sandbox/Code Integration** 🔴 CRITICAL
**Problem**: User asks to write code in sandbox, but agent doesn't:
- Acknowledge the sandbox feature
- Guide user to use sandbox
- React to sandbox activity (if user writes code)

**Root Cause**: 
- `_detect_user_intent_node` doesn't detect sandbox/code requests
- `_decide_next_action` doesn't have a "sandbox" or "code_review" action when user requests it
- Agent doesn't proactively encourage sandbox usage

#### 4. **Poor Conversation Continuity** 🟠 HIGH
**Problem**: 
- After user explains overfitting, agent asks a completely new question
- Agent doesn't follow up on technical details (87% F1 score, neural networks)
- Agent doesn't acknowledge user's answers before asking new questions

**Root Cause**:
- `_decide_next_action` might be choosing wrong actions
- No proper follow-up question generation after technical answers
- Decision logic might not consider conversation flow properly

#### 5. **No Code Sandbox Awareness** 🟠 HIGH
**Problem**: Agent seems completely unaware of:
- The sandbox feature that exists
- How to guide users to write code
- How to react when users write code

**Root Cause**:
- Agent instructions don't mention sandbox
- No system prompts about sandbox capabilities
- `_code_review_node` exists but is never triggered by user requests

#### 6. **Repetitive Questions** 🟡 MEDIUM
**Problem**: Agent asks similar questions without building on previous answers.

**Root Cause**:
- Question deduplication might not be working
- Not tracking what questions were already asked effectively

## Technical Issues

### Intent Detection Problems

**Current Intent Types** (from `_detect_user_intent_node`):
```python
1. technical_assessment
2. change_topic
3. clarify
4. stop
5. continue
6. no_intent
```

**Missing Intent Types**:
- `write_code` / `use_sandbox` - User wants to write code
- `review_code` / `walk_through_code` - User wants code reviewed
- `show_code_from_resume` - User wants to discuss code from resume

### Decision Logic Problems

**In `_decide_next_action`**:
- When user intent is `technical_assessment`, it routes to `"question"` instead of potentially `"code_review"` or `"sandbox"`
- No routing to `_code_review_node` when user explicitly asks for code review
- Sandbox state is monitored but never acted upon proactively

### Agent Instructions Missing

Agent doesn't know:
- That a sandbox exists
- How to encourage users to write code
- What to do when users ask to write code
- How to respond to sandbox activity

## Recommended Fixes

### 1. Enhance Intent Detection
```python
# Add new intent types:
- "write_code" / "use_sandbox"
- "review_code" / "code_walkthrough"
- "show_resume_code"

# Update detection prompt to look for:
- "write code", "sandbox", "code editor"
- "review code", "walk through code", "show code"
- "code from resume", "project code"
```

### 2. Add Sandbox-Aware Routing
```python
# In _decide_next_action:
if intent_type == "write_code" or intent_type == "use_sandbox":
    state["_next_action"] = "sandbox_guidance"
    state["next_message"] = "Great! I can see you want to write code. Please use the code sandbox on the right side of your screen. You can write Python code there and I'll review it when you submit it."
    return state

if intent_type == "review_code" or intent_type == "code_walkthrough":
    # Check if code exists in sandbox or request it
    if state.get("current_code"):
        state["_next_action"] = "code_review"
    else:
        state["_next_action"] = "request_code"
    return state
```

### 3. Add Sandbox Guidance Node
```python
async def _sandbox_guidance_node(self, state: InterviewState) -> InterviewState:
    """Guide user to use sandbox."""
    state["last_node"] = "sandbox_guidance"
    state["next_message"] = (
        "Perfect! I see you'd like to write code. "
        "Please use the code sandbox on the right side of your screen. "
        "You can write Python code there, and when you submit it, I'll review it for you. "
        "Feel free to write code related to any project on your resume or any technical problem you'd like to discuss."
    )
    return state
```

### 4. Update Agent Instructions
```python
instructions = (
    "You are a professional interviewer conducting a technical interview. "
    "IMPORTANT: The user has access to a code sandbox where they can write and submit code. "
    "If the user asks to write code, show code, or review code, guide them to use the sandbox. "
    "When they submit code in the sandbox, you will receive it automatically for review. "
    "Always acknowledge user requests, especially requests to write code or review code. "
    "All your responses will be SPOKEN ALOUD. "
    "Therefore, use short, clear sentences and natural, conversational language. "
)
```

### 5. Fix Conversation Continuity
- Don't reset greeting state
- Always acknowledge previous answer before asking new question
- Follow up on technical details mentioned by user
- Maintain context across turns

### 6. Improve State Persistence
- Ensure checkpointing saves conversation state properly
- Don't reset state between turns
- Maintain conversation history correctly

## Priority Fixes

### Immediate (Critical):
1. ✅ Add "write_code" / "use_sandbox" intent detection
2. ✅ Add "review_code" / "code_walkthrough" intent detection  
3. ✅ Route to sandbox_guidance when user requests code
4. ✅ Update agent instructions about sandbox
5. ✅ Fix conversation state persistence (prevent greeting resets)

### High Priority:
6. ✅ Improve conversation continuity (acknowledge answers)
7. ✅ Add sandbox_guidance node
8. ✅ Proactively monitor sandbox activity

### Medium Priority:
9. ✅ Better follow-up on technical details
10. ✅ Improve question deduplication


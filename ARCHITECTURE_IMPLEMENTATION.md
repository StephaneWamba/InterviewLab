# Robust LangGraph Architecture Implementation

## Overview

This document describes the complete implementation of a robust LangGraph-based interview orchestrator with explicit state semantics, checkpointing, and resume-driven question generation.

## Key Architectural Principles

1. **LangGraph ≠ Chat loop**: LangGraph is a stateful workflow engine. Concepts that matter for decisions must exist explicitly in state.
2. **Nodes don't decide**: Only the `decide` node decides. All other nodes read state, act, and update their slice of state.
3. **Decisions are data-driven**: Decision logic uses structured signals, not raw conversation text inference.

## Implementation Components

### 1. Robust State Structure (`InterviewState`)

#### New Nested Structures:

- **`QuestionRecord`**: Tracks every question asked with metadata:
  - `id`, `text`, `source`, `resume_anchor`, `aspect`, `asked_at_turn`
- **`UserIntent`**: First-class user intent tracking:
  - `type` (technical_assessment, change_topic, clarify, stop, continue, no_intent)
  - `confidence`, `extracted_from`, `turn`, `metadata`
- **`ResumeExploration`**: Structured resume anchor tracking:
  - `anchor_id`, `anchor_type` (project, skill, experience, education)
  - `aspects_covered` (set), `depth_score`, `last_explored_turn`
- **`SandboxState`**: Code activity tracking:
  - `is_active`, `last_activity_ts`, `submissions`, `signals`

#### State Fields:

```python
{
    # Core
    "interview_id", "user_id", "resume_id",

    # Conversation
    "turn_count", "conversation_history",

    # Questions (EXPLICIT tracking)
    "questions_asked": list[QuestionRecord],
    "current_question": str | None,

    # Resume (STRUCTURED)
    "resume_structured": dict,
    "resume_exploration": dict[str, ResumeExploration],

    # User Intent (FIRST-CLASS)
    "detected_intents": list[UserIntent],
    "active_user_request": UserIntent | None,

    # Sandbox
    "sandbox": SandboxState,

    # Flow control
    "phase": str,  # intro | exploration | technical | closing
    "last_node": str,
    "next_node": str | None,

    # System
    "checkpoints": list[str],
}
```

### 2. Checkpointing Strategy (`CheckpointService`)

**When**: After every node execution

**What**:

- Entire `InterviewState` (JSONB)
- `last_node`, `turn_count`, timestamp

**How**:

- Stored in `Interview.conversation_history` as system messages with metadata
- Checkpoint ID: ISO timestamp
- Can restore from latest or specific checkpoint

**Recovery**:

- Load latest checkpoint → Restore state → Resume from `last_node` → `decide`
- Never replay LLM outputs, resume from state

**Files**:

- `src/services/checkpoint_service.py`
- Integrated in `src/agents/interview_agent.py` after each `execute_step`

### 3. Context Injection Architecture

**Pattern**: Context builders per node (read-only)

**Examples**:

- `_build_decision_context()`: Structured signals for decision node
- `_build_resume_context()`: Resume data for prompts
- `_build_conversation_context()`: Recent conversation history

**Rule**: Context builders are read-only. State updates happen after node logic.

### 4. User Intent Detection Node (`_detect_user_intent_node`)

**Position**: Runs immediately after user input, BEFORE decide

**Flow**: `user_input → detect_intent → decide`

**What it does**:

1. Analyzes user's last response with LLM
2. Classifies intent: technical_assessment, change_topic, clarify, stop, continue, no_intent
3. Stores in `detected_intents` list
4. Sets `active_user_request` if confidence > 0.7

**Decision Node Priority**:

- IF `active_user_request` exists → Route accordingly (highest priority)
- ELSE → Default flow

**This fixes**: User requests being ignored (e.g., "can we do technical assessment")

### 5. Resume-Driven Exploration (No Fixed Taxonomy)

**Principle**: Adapt to each resume dynamically, don't impose fixed categories

**Implementation**:

1. **Normalize resume into anchors**:

   - Extract projects → `project_1`, `project_2`, ...
   - Extract skills → `skill_python`, `skill_machine_learning`, ...
   - Extract experiences → `experience_1`, `experience_2`, ...

2. **Track exploration per anchor**:

   - `aspects_covered`: set of aspects explored (challenges, impact, design, tools, team, results, tradeoffs, implementation)
   - `depth_score`: 0-10, how deeply explored
   - `last_explored_turn`: when last explored

3. **Question generation**:
   - Pick anchor with unexplored aspects
   - Generate question about specific aspect
   - Update anchor tracking after asking

**This guarantees**:

- ✅ Coverage across resume
- ✅ No repetition (same anchor + aspect = blocked)
- ✅ Natural deep dives (multiple aspects per anchor)

### 6. Question Deduplication (Layered Strategy)

**Layer 1**: Exact match (normalized text)

**Layer 2**: Aspect gating

- Same `resume_anchor` + same `aspect` = block

**Layer 3**: Semantic similarity (word overlap > 80%)

- In production: use embeddings, similarity > 0.85

**When**: Before asking, not after

**This fixes**: Repeated questions with different wording

### 7. Sandbox Code Monitoring Integration

**Pattern**: Sandbox is signal, not interruption

**State Tracking**:

- `sandbox.is_active`: User is coding
- `sandbox.signals`: struggling, confident, refactoring, idle, syntax_errors, rapid_iterations
- `sandbox.submissions`: Code submissions with results

**Decision Logic**:

- IF `sandbox.active` AND `signal == struggling` → Ask clarification
- ELSE continue normal flow

**No new node needed**: Just state awareness in decision logic

### 8. Decision Node (Data-Driven)

**Before**: Rules-based, inferring from raw conversation

**After**: Structured signals:

- Turn, phase, questions asked, resume coverage, sandbox signals
- Active user request (highest priority)
- Answer quality, conversation length

**Priority Order**:

1. Active user request (if confidence > 0.7)
2. Sufficient coverage → evaluation → closing
3. Last node rules (question → transition, transition → question)
4. Answer quality → followup
5. Default → transition

### 9. Interview Evaluation Node (`_evaluation_node`)

**When**: Before closing (triggered by decision node)

**What**:

- Comprehensive feedback generation using `FeedbackGenerator`
- Scores: overall, communication, technical, problem-solving, code quality
- Strengths, weaknesses, recommendations
- Topics covered, code submissions analysis

**Integration**:

- `action == "evaluation"` or `should_evaluate == True`
- Always followed by `closing` node

### 10. Graph Flow

```
START
 ↓
initialize
 ↓
[user_input] → detect_user_intent
 ↓
decide
 ├─ greeting
 ├─ question
 ├─ followup
 ├─ transition → question
 ├─ evaluation → closing
 └─ closing
 ↓
[checkpoint]
```

**Key Points**:

- Only `decide` has conditional routing
- All other nodes return → `decide`
- `detect_intent` runs before `decide` when user responds

## File Structure

```
src/
├── services/
│   ├── interview_orchestrator.py    # Main orchestrator with all nodes
│   ├── checkpoint_service.py         # Checkpointing implementation
│   └── state_manager.py              # State conversion (DB ↔ LangGraph)
├── agents/
│   └── interview_agent.py            # LiveKit agent with checkpointing integration
└── models/
    └── interview.py                  # Database model (checkpoints in conversation_history)
```

## Migration Notes

### Backward Compatibility

- Legacy fields preserved: `topics_covered`, `resume_context`, etc.
- Old state structures still work
- New fields initialized with defaults

### State Conversion

- `interview_to_state()`: Converts DB model → LangGraph state
- `state_to_interview()`: Converts LangGraph state → DB model
- Checkpoints stored in `conversation_history` metadata

### Resume Exploration Initialization

- Called in `_initialize_node()`
- Extracts anchors from `resume_context` or `resume_structured`
- Creates `ResumeExploration` entries for each anchor

## Benefits

### Before (Problems Fixed):

- ❌ Repeated questions (no tracking)
- ❌ User requests ignored (no intent detection)
- ❌ Shallow exploration (no anchor tracking)
- ❌ State lost on errors (no checkpointing)
- ❌ Decisions based on inference (no structured signals)

### After (Solutions):

- ✅ Never repeat questions (explicit tracking + deduplication)
- ✅ User requests honored (first-class intent detection)
- ✅ Deep resume exploration (anchor-based tracking)
- ✅ Resilient to failures (checkpointing)
- ✅ Predictable decisions (data-driven with structured signals)

## Testing Recommendations

1. **Checkpoint Recovery**:

   - Start interview → Kill agent → Restart → Should resume from last checkpoint

2. **Intent Detection**:

   - User says "can we do technical assessment" → Should route accordingly

3. **Question Deduplication**:

   - Ask question → Try to ask similar question → Should be blocked

4. **Resume Exploration**:

   - Resume with 3 projects → Should explore different aspects of each

5. **Evaluation**:
   - Complete interview → Should generate comprehensive feedback

## Future Enhancements

1. **Semantic Similarity**: Use OpenAI embeddings for better deduplication
2. **Separate Checkpoint Table**: Store checkpoints in dedicated table (not conversation_history)
3. **State Compression**: Compress state snapshots for storage efficiency
4. **Parallel Node Execution**: Design parallel paths for certain operations
5. **State Validation**: Validate state structure before/after node execution

## Conclusion

This implementation transforms the interview orchestrator from a chat loop into a robust, stateful workflow engine. By making implicit concepts explicit in state and using structured signals for decisions, the system becomes predictable, debuggable, and maintainable.

The architecture follows LangGraph best practices:

- Explicit state semantics
- Checkpointing for resilience
- Context injection at right moments
- Data-driven decision making
- Resume-driven (not taxonomy-driven) exploration

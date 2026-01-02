# ChatGPT Prompt: Robust LangGraph Architecture for Interview Orchestrator

Copy and paste this prompt to ChatGPT:

---

I'm building an interview orchestrator using **LangGraph** and need help designing a robust architecture with proper state management, context injection, and checkpointing.

## Current Problems

**Evidence from conversation log:**

The agent repeatedly asks the same or very similar questions:

- "What was the most interesting project you worked on during your internship at ITGStore?" → asked **3+ times**
- "What inspired you to focus on machine learning?" → variations asked **multiple times**

**User requests are ignored:**

- User says: _"Can we do a technical assessment please?"_
- Agent completely ignores this and continues asking similar questions

**Root Architectural Issues:**

1. ❌ **Poor state management** - not tracking what questions were asked
2. ❌ **No checkpointing** - state can be lost or inconsistent
3. ❌ **Context not injected at right moments** - decision logic doesn't have full picture
4. ❌ **No deduplication** - questions repeat because state isn't properly queried
5. ❌ **User requests not detected** - no mechanism to analyze user intent and inject into decision flow

## Current Architecture

**LangGraph-based orchestrator** with nodes:

- `greeting` → Initial greeting
- `question` → Generate new question
- `followup` → Follow-up on last answer
- `transition` → Transition to new topic
- `closing` → End interview
- `decide` → Decision node (routes to other nodes)

**Current State Structure:**

```python
class InterviewState(TypedDict):
    interview_id: int
    resume_context: dict  # Resume extracted_data
    conversation_history: list[dict]
    topics_covered: list[str]  # Too high-level
    current_node: str
    current_question: str | None
    last_response: str | None
    next_message: str | None
    turn_count: int
    code_submissions: list[dict]
    # Missing: questions_asked, question types, user intent, etc.
```

**Current Decision Node:**

- Uses LLM to decide next action
- Simple rules-based routing
- Doesn't have full context (missing questions asked, user requests, etc.)

## What I Need: Robust LangGraph Architecture

### 1. Effective Checkpointing Strategy

**Questions:**

- How should I structure checkpointing in LangGraph for interview conversations?
- Should I checkpoint after each node execution, or at specific points?
- How do I handle state persistence (database, Redis, etc.)?
- What's the best way to recover from failures and resume conversations?
- How do I ensure state consistency when multiple operations happen?

### 2. Context Injection at Right Moments

**Questions:**

- How should I structure state to include all necessary context (questions asked, user requests, code activity, etc.)?
- What's the best way to inject resume context into question generation without making prompts too long?
- How do I ensure decision nodes have access to:
  - Full conversation history
  - Questions already asked (for deduplication)
  - User's last response (for request detection)
  - Current coding activity in sandbox
  - Topics and aspects covered (granular tracking)
- When should context be updated vs. just read?
- How do I structure context builders that extract the right information at the right time?

### 3. Dynamic Resume-Driven Question Generation

**Critical Requirement:**

- The agent should **adapt to each resume dynamically** - don't impose fixed taxonomies
- Generate questions based on what's actually in the candidate's resume
- Explore different aspects of their experience, projects, skills, education
- NOT use fixed categories like "behavioral vs technical" - instead explore what makes sense for THIS candidate

**Questions:**

- How do I structure question generation to be resume-driven, not taxonomy-driven?
- How do I track what's been explored from the resume (projects, skills, experiences)?
- How do I ensure questions explore different aspects (project details, challenges, technologies used, impact, etc.)?
- How do I avoid repetition while still allowing deep dives into interesting topics?

### 4. User Intent Detection & Request Handling

**Questions:**

- Where in the LangGraph flow should I detect user requests ("can we do technical assessment", "change topic", etc.)?
- Should this be a separate node, or part of decision logic?
- How do I prioritize user requests over default decision flow?
- What's the best pattern for extracting user intent from responses?

### 5. State Tracking Best Practices

**Questions:**

- How should I structure state to track:
  - Questions asked (for deduplication)
  - Aspects explored (not just topics, but what about each topic)
  - User requests detected
  - Code activity in sandbox
  - Conversation quality signals
- Should I use nested structures, separate lists, or different patterns?
- How do I query state efficiently for decision-making?

### 6. Sandbox Code Monitoring Integration

**Requirement:**

- When user writes code in sandbox, agent should monitor it (like real interviewer watching)
- Agent should detect coding activity and adapt conversation

**Questions:**

- How do I integrate sandbox state (`code_submissions`) into the decision flow?
- Should code monitoring affect decision logic? How?
- What's the best pattern to make agent aware of coding activity without interrupting flow?

### 7. Robust Orchestration Patterns

**Questions:**

- What are LangGraph best practices for:
  - Conditional routing between nodes?
  - State validation before node execution?
  - Error handling and recovery?
  - Parallel vs sequential node execution?
- How do I ensure nodes receive the right state at the right time?
- What's the best way to structure edges/transitions in LangGraph for interview flows?

## Specific Architecture Questions

1. **State Structure:**

   - How should I expand `InterviewState` to support all these requirements?
   - Should I use nested TypedDicts, separate fields, or different patterns?
   - How do I balance state completeness vs. performance?

2. **Node Design:**

   - Should each node be responsible for updating its own state section?
   - How do I ensure state updates are atomic and consistent?
   - What's the pattern for nodes that need to read and write state?

3. **Decision Logic:**

   - How do I structure the decision node to have full context?
   - Should I build context summaries, or pass full state?
   - How do I make decisions deterministic enough while staying flexible?

4. **Question Deduplication:**

   - Should I use semantic similarity (embeddings) or simpler pattern matching?
   - Where should deduplication happen - before generation or after?
   - How do I balance preventing repetition vs. allowing natural follow-ups?

5. **Resume-Driven Exploration:**
   - How do I track what parts of the resume have been explored?
   - Should I structure resume data in a way that makes exploration tracking easier?
   - How do I ensure balanced exploration without imposing fixed categories?

## Code Patterns I Need

**Example: Robust State Management**

```python
# How should I structure this?
class InterviewState(TypedDict):
    # What fields? How nested? How to track everything?
    pass

# How do I update state safely?
# How do I query state efficiently?
```

**Example: Context Injection**

```python
# How should I build context for decision node?
async def _decision_node(self, state: InterviewState):
    # What context should I extract?
    # When should I extract it?
    # How do I structure it?
    pass
```

**Example: Checkpointing**

```python
# How do I checkpoint state?
# Where do I checkpoint?
# How do I recover?
```

## Constraints

- Using OpenAI GPT-4o-mini for all LLM calls
- LangGraph-based state machine
- Python/AsyncIO
- State persisted in PostgreSQL (SQLAlchemy models)
- Must maintain real-time conversation flow
- Must be resilient to failures

## Expected Outcomes

Please provide:

1. **Robust state structure** - Complete TypedDict design with all necessary fields
2. **Checkpointing strategy** - When, where, and how to checkpoint
3. **Context injection patterns** - How to build and inject context at right moments
4. **Node design patterns** - Best practices for each node type
5. **Orchestration patterns** - How to structure edges, routing, error handling
6. **Resume-driven question generation** - Architecture for dynamic, adaptive questions
7. **User intent detection** - Integration into decision flow
8. **Sandbox monitoring** - Integration pattern for code activity

Focus on **architecture and patterns**, not just fixing specific bugs. I want a robust, scalable design.

---

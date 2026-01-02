# Sandbox Orchestration - How the Agent Sees Sandbox Code

## Overview

The sandbox orchestration system allows users to write and submit code during interviews, which the agent then executes, analyzes, and provides feedback on. This document explains the complete flow from user intent to agent response.

## Architecture Flow

```
User Intent → Intent Detection → Sandbox Guidance → Code Submission → Code Execution → Code Analysis → Agent Feedback
```

## Detailed Flow

### 1. **User Intent Detection** (`_detect_user_intent_node`)

When a user expresses interest in writing code (e.g., "I'd like to write some code"), the holistic intent detection system identifies:

- **Intent Type**: `write_code` or `review_code`
- **Confidence**: 0.7+ (threshold for action)
- **Goal Analysis**: Understands user wants to demonstrate coding ability

**Location**: `src/services/interview_orchestrator.py:440-563`

### 2. **Intent-Based Routing** (`_decide_next_action`)

If intent is detected with high confidence (>0.7):

- `write_code` → Routes to `sandbox_guidance` action
- `review_code` → Routes to `code_review` action (if code exists) or `sandbox_guidance` (if no code yet)

**Location**: `src/services/interview_orchestrator.py:871-842`

### 3. **Sandbox Guidance Node** (`_sandbox_guidance_node`)

**Purpose**: Guide user to use the sandbox and encourage code submission

**What happens**:

1. Generates personalized, spoken-friendly message
2. Guides user to "code sandbox on the right side of your screen"
3. Encourages writing code related to projects/technical questions
4. Mentions agent will review when submitted

**Output**: Message like:

> "Absolutely! I'd love to see your code. Please use the code sandbox on the right side of your screen. You can write Python code there, and I'll review it when you submit it."

**Location**: `src/services/interview_orchestrator.py:1263-1343`

### 4. **Code Submission** (Frontend → Backend)

**API Endpoint**: `POST /api/v1/interviews/{interview_id}/code`

**Request Body**:

```json
{
  "code": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
  "language": "python"
}
```

**What happens**:

1. Frontend sends code + language to API
2. API endpoint receives submission
3. Calls `orchestrator.execute_step(state, code=data.code, language=data.language)`

**Location**: `src/api/v1/endpoints/interviews.py:290-339`

### 5. **Code Reception in Orchestrator** (`execute_step`)

**Entry Point**: `execute_step(state, code=code, language=language)`

**What happens**:

```python
# Handle code submission
if code:
    state["current_code"] = code  # Store code in state
    if language:
        state["current_language"] = language  # Store language

    # Immediately route to code review
    state = await self._code_review_node(state)
    return state
```

**Key Point**: Code is stored in `state["current_code"]` and immediately triggers `_code_review_node`

**Location**: `src/services/interview_orchestrator.py:1502-1520`

### 6. **Code Review Node** (`_code_review_node`)

**Purpose**: Execute code, analyze it, and generate feedback

**Step-by-step process**:

#### 6.1. **Code Execution**

```python
sandbox_service = self._get_sandbox_service()
execution_result = await sandbox_service.execute_code(
    code=code,
    language=sandbox_language,  # Python, JavaScript, etc.
)
```

**SandboxService** (`src/services/sandbox_service.py`):

- Creates isolated Docker container
- Executes code with resource limits (memory, CPU, timeout)
- Captures stdout, stderr, exit code, execution time
- Returns `ExecutionResult` object

**Location**: `src/services/interview_orchestrator.py:1370-1379`

#### 6.2. **Code Quality Analysis**

```python
code_quality = await self._code_analyzer.analyze_code(
    code=code,
    language=language_str,
    execution_result=exec_result_dict,
    context={
        "question": state.get("current_question", ""),
        "conversation_summary": conversation_summary,
    },
)
```

**What's analyzed**:

- **Correctness**: Does it work? Are there errors?
- **Efficiency**: Time/space complexity, performance
- **Readability**: Code clarity, naming, structure
- **Best Practices**: Patterns, conventions, style
- **Overall Quality Score**: 0.0-1.0

**Output**: Structured `CodeQuality` object with:

- Scores for each dimension
- Strengths list
- Weaknesses list
- Feedback text
- Suggestions for improvement

**Location**: `src/services/interview_orchestrator.py:1381-1403`

#### 6.3. **Feedback Generation**

```python
# Generate spoken feedback message
feedback_message = await self._code_analyzer.generate_code_feedback_message(
    code_quality=code_quality,
    execution_result=exec_result_dict,
)

# Generate adaptive follow-up question
followup_question = await self._code_analyzer.generate_adaptive_question(
    code_quality=code_quality,
    execution_result=exec_result_dict,
    conversation_context=conversation_summary,
)

combined_message = f"{feedback_message}\n\n{followup_question}"
state["next_message"] = combined_message
```

**What the agent sees**:

- The **actual code** (`state["current_code"]`)
- **Execution results** (stdout, stderr, exit code, timing)
- **Code quality analysis** (scores, strengths, weaknesses)
- **Conversation context** (what was discussed before)

**Location**: `src/services/interview_orchestrator.py:1405-1419`

#### 6.4. **State Storage**

```python
# Store submission in state
submission = {
    "code": code,
    "language": language_str,
    "execution_result": exec_result_dict,
    "code_quality": state["code_quality"],
    "timestamp": datetime.utcnow().isoformat(),
}
state["code_submissions"].append(submission)
state["sandbox"]["submissions"].append(submission)
```

**Location**: `src/services/interview_orchestrator.py:1432-1441`

### 7. **Agent Response**

The agent's response includes:

1. **Feedback Message**: Analysis of the code (what worked, what didn't, suggestions)
2. **Follow-up Question**: Adaptive question based on code quality and conversation context

**Example Response**:

> "Great work! Your code correctly implements the Fibonacci function using recursion. The logic is sound and handles the base cases well. However, the recursive approach has exponential time complexity O(2^n). For better efficiency, consider using memoization or an iterative approach.
>
> Can you explain how you would optimize this for larger inputs?"

## Key State Variables

The agent tracks code-related information in the `InterviewState`:

```python
{
    "current_code": str | None,           # The actual code submitted
    "current_language": str | None,       # Language (python, javascript, etc.)
    "code_execution_result": dict | None, # Execution output (stdout, stderr, etc.)
    "code_quality": dict | None,          # Quality analysis scores and feedback
    "code_submissions": list[dict],       # History of all code submissions
    "sandbox": {
        "is_active": bool,                # Is sandbox being used?
        "last_activity_ts": float,        # Last activity timestamp
        "submissions": list[dict],        # Code submissions
        "signals": list[str],             # Behavioral signals
    }
}
```

## How the Agent "Sees" the Code

The agent doesn't directly "see" the code in the traditional sense. Instead:

1. **Code is stored in state**: `state["current_code"]` contains the full code string
2. **Code is analyzed**: `CodeAnalyzer` processes the code and creates structured analysis
3. **Code is executed**: `SandboxService` runs it and captures results
4. **Context is provided**: The agent receives:

   - The code itself (as text)
   - Execution results (what happened when it ran)
   - Quality analysis (structured feedback)
   - Conversation context (what was discussed)

5. **LLM processes everything**: The `CodeAnalyzer` uses GPT-4o mini to:
   - Analyze code structure and logic
   - Evaluate correctness and efficiency
   - Generate natural language feedback
   - Create adaptive follow-up questions

## Code Execution Details

**SandboxService** (`src/services/sandbox_service.py`):

- Uses Docker containers for isolation
- Supports Python and JavaScript
- Resource limits: memory, CPU, timeout
- Captures all output (stdout, stderr)
- Returns structured `ExecutionResult`

**Execution Flow**:

1. Create temporary Docker container
2. Write code to file in container
3. Execute code with language-specific command
4. Capture output and errors
5. Measure execution time
6. Clean up container
7. Return results

## Integration Points

### Frontend → Backend

- **Endpoint**: `POST /api/v1/interviews/{interview_id}/code`
- **Schema**: `CodeSubmissionRequest` (code, language)
- **Authentication**: JWT token required

### Backend → Agent

- **Method**: `orchestrator.execute_step(state, code=code, language=language)`
- **State Update**: Code stored in `state["current_code"]`
- **Immediate Action**: Routes to `_code_review_node`

### Agent → Analysis

- **Service**: `CodeAnalyzer.analyze_code()`
- **Input**: Code string, execution results, conversation context
- **Output**: Structured quality analysis

### Analysis → Response

- **Service**: `CodeAnalyzer.generate_code_feedback_message()`
- **Service**: `CodeAnalyzer.generate_adaptive_question()`
- **Output**: Natural language feedback + follow-up question

## Example Complete Flow

1. **User**: "I'd like to write some code to demonstrate my approach"
2. **Intent Detection**: Detects `write_code` intent (confidence: 0.9)
3. **Routing**: Routes to `sandbox_guidance` action
4. **Agent Response**: "Absolutely! I'd love to see your code. Please use the code sandbox..."
5. **User**: Submits code via frontend
6. **API**: Receives code, calls `execute_step(state, code=code)`
7. **Orchestrator**: Stores code in `state["current_code"]`, calls `_code_review_node`
8. **SandboxService**: Executes code in Docker container
9. **CodeAnalyzer**: Analyzes code quality, generates feedback
10. **Agent Response**: "Great work! Your code correctly implements... However, consider optimizing..."

## Key Files

- **Orchestration**: `src/services/interview_orchestrator.py`

  - `_detect_user_intent_node()`: Intent detection
  - `_sandbox_guidance_node()`: Guides user to sandbox
  - `_code_review_node()`: Executes and analyzes code
  - `execute_step()`: Main entry point

- **API Endpoints**: `src/api/v1/endpoints/interviews.py`

  - `POST /{interview_id}/code`: Code submission endpoint

- **Sandbox Service**: `src/services/sandbox_service.py`

  - `execute_code()`: Executes code in Docker container

- **Code Analysis**: `src/services/code_analyzer.py`
  - `analyze_code()`: Analyzes code quality
  - `generate_code_feedback_message()`: Creates feedback
  - `generate_adaptive_question()`: Creates follow-up questions

## Summary

The agent "sees" code through a multi-layered process:

1. **Code is submitted** via API endpoint
2. **Code is stored** in interview state
3. **Code is executed** in isolated sandbox
4. **Code is analyzed** by LLM-powered analyzer
5. **Results are synthesized** into natural language feedback
6. **Agent responds** with feedback and adaptive questions

The agent has full access to:

- The code text itself
- Execution results (output, errors, timing)
- Quality analysis (scores, strengths, weaknesses)
- Conversation context (previous discussion)

This allows the agent to provide intelligent, context-aware feedback on the user's code.

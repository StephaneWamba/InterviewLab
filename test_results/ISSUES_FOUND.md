# Agent Behavior Test - Issues Found

## Test Date: 2026-01-02

### ✅ **FIXED ISSUES**

1. **Greeting Loop Bug** - FIXED ✅
   - Agent no longer sends greeting multiple times
   - Properly routes to questions after first user response

2. **Code Request Intent Detection** - FIXED ✅
   - "I'd like to write some code" → correctly routes to `sandbox_guidance`
   - "Can I use the sandbox?" → correctly routes to `sandbox_guidance`
   - Intent detection schema now includes `write_code` and `review_code`

### ⚠️ **REMAINING ISSUES**

#### 1. **Topic Change Not Detected**
**Scenario**: `topic_change`, `mixed_intents`

**Problem**: When user says "Actually, let's talk about my team leadership instead" or "Can we change topics?", the agent:
- Does NOT detect `change_topic` intent
- Continues with questions instead of transitioning
- Ignores the user's explicit request to change topic

**Expected**: Should detect `change_topic` intent and route to `transition` node

**Example from test**:
```
Turn 5: User: "Actually, let's talk about my team leadership instead"
Agent: "What impact did your leadership have on the project's success?" (continues with question)
Expected: Should transition to leadership topic
```

**Root Cause**: Intent detection prompt may not be recognizing topic change language in context, or confidence threshold too high.

---

#### 2. **Code Review Intent - Ambiguous Behavior**
**Scenario**: `code_request`

**Problem**: When user says "Here's my code implementation...", the agent:
- Routes to `sandbox_guidance` instead of `code_review`
- This is technically correct (no actual code in state), but intent should still be detected as `review_code`

**Expected**: 
- Intent should be detected as `review_code` (even if code doesn't exist yet)
- Agent should acknowledge intent but guide user to submit code

**Example from test**:
```
Turn 5: User: "Here's my code implementation..."
Agent: "Absolutely! Go ahead and use the code sandbox..." (sandbox_guidance)
Expected: Should detect review_code intent, acknowledge, then guide to sandbox
```

---

#### 3. **Clarification Requests - Not Fully Handled**
**Scenario**: `clarification_request`

**Problem**: When user asks for clarification multiple times:
- Intent is correctly detected as `clarify` ✅
- But agent continues asking followup questions instead of actually clarifying the previous question

**Example from test**:
```
Turn 3: User: "What do you mean by that?"
Agent: "Can you share a specific example of that challenge?" (followup question)
Expected: Should rephrase or clarify the previous question

Turn 4: User: "Can you clarify the question?"
Agent: "What part of the challenge would you like to explore further?" (another followup)
Expected: Should actually clarify/rephrase the original question
```

**Root Cause**: `clarify` intent is detected but there's no dedicated clarification handling node - it just routes to followup.

---

#### 4. **Sandbox Guidance Repetition**
**Scenario**: `code_request`

**Problem**: When user asks about sandbox multiple times:
- Agent keeps giving the same sandbox guidance message
- No variation or acknowledgment that guidance was already given

**Example from test**:
```
Turn 3: "I'd like to write some code" → sandbox_guidance
Turn 4: "Can I use the sandbox?" → same sandbox_guidance message
Turn 5: "Here's my code..." → same sandbox_guidance message
```

**Expected**: Should acknowledge previous guidance, or vary the response

---

#### 5. **Intent Detection Confidence Issues**
**Observation**: Some intents are detected but with confidence < 0.7, so they're ignored:
- `change_topic` might be detected but with low confidence
- System requires confidence > 0.7 to act on intent

**Potential Fix**: Lower threshold or improve prompt to increase confidence for clear intents

---

## Summary Statistics

From latest test run:
- **Total Scenarios Tested**: 7
- **Scenarios Working Well**: 4 (basic_conversation, code_request detection, short_responses, long_detailed_response)
- **Scenarios with Issues**: 3 (topic_change, clarification_request, mixed_intents)

## Recommended Fixes

1. **Improve Topic Change Detection**:
   - Add more examples to intent detection prompt
   - Lower confidence threshold for explicit topic change requests
   - Add explicit check for "Actually", "Let's talk about", "Can we change" patterns

2. **Add Clarification Node**:
   - Create `_clarification_node` that rephrases the last question
   - Route `clarify` intent to this node instead of followup

3. **Improve Sandbox Guidance**:
   - Track if sandbox guidance was already given
   - Vary responses or acknowledge previous guidance

4. **Review Intent Detection Confidence**:
   - Consider lowering threshold to 0.6 for explicit requests
   - Or improve prompt to increase confidence scores


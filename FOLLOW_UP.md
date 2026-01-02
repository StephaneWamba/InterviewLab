# Follow-Up Prompt for InterviewLab Project

## Context Summary

We've been working on enhancing the InterviewLab interview agent system with job description integration, exercise generation, code polling, and exercise validation features. The system is a voice-based AI interview platform using LiveKit Agents, FastAPI backend, and Next.js frontend.

## What We've Accomplished

### 1. Job Description Integration ✅

- Added `job_description` field to Interview model (database migration completed)
- Updated schemas, state management, and API endpoints
- Job description is now used in question generation, code review, exercise generation, and feedback

### 2. Exercise Generation ✅

- Agent generates coding exercises based on job description
- Exercises include description, starter code, difficulty, hints
- Provided when user requests to code

### 3. Code Polling ✅

- Frontend polls code changes every 10 seconds
- Backend tracks code snapshots for real-time monitoring

### 4. Exercise Validation ✅

- Agent validates submitted code matches the provided exercise
- Strict matching: candidate must solve EXACT exercise (e.g., "task management API" ≠ "book management API")

## Key Files Modified

**Backend:**

- `src/models/interview.py` - Added `job_description` field
- `src/services/interview_orchestrator.py` - Major updates for exercises, validation, polling
- `src/api/v1/endpoints/interviews.py` - Added `PUT /sandbox/code` endpoint
- `alembic/versions/add_job_description_to_interviews.py` - Migration

**Frontend:**

- `frontend/app/dashboard/interviews/page.tsx` - Job description field
- `frontend/components/interview/sandbox.tsx` - Exercise support, polling
- `frontend/lib/api/interviews.ts` - Updated interfaces

## Test Results

✅ Exercise mismatch detection: WORKING
✅ Multiple submissions: WORKING  
✅ Partial solutions: WORKING
✅ Code polling: WORKING
⚠️ Test 1 needs fix: Test code should match exact exercise domain

## Current State

**Working:**

- Job description integration
- Exercise generation
- Code validation
- Code polling infrastructure
- Feedback with job context

**Needs Attention:**

- Test script should match exact exercise domain
- Frontend exercise initialization verification
- Code polling real-time feedback enhancement

## Real-World Test Scenarios to Implement

### Core Interview Flow Tests

1. **Complete Interview Journey**

   - User creates interview with job description
   - Agent greets and asks job-relevant question
   - User responds with experience
   - User requests to code → Agent provides exercise
   - User works on code (polling detects changes)
   - User submits code → Agent reviews with job context
   - User asks follow-up question
   - User submits improved code
   - Interview ends → Feedback generated with job context

2. **Exercise Request Scenarios**

   - User explicitly says "I'd like to write code" → Exercise provided
   - User says "Can I show you my coding skills?" → Exercise provided
   - User says "Let me code something" → Exercise provided
   - User just starts coding without asking → Should agent provide exercise or wait?

3. **Code Submission Scenarios**

   - User submits code matching exercise exactly → Positive feedback
   - User submits code for different domain (books vs tasks) → Mismatch detected
   - User submits incomplete code (has TODOs) → Agent recognizes and guides
   - User submits code with syntax errors → Agent helps debug
   - User submits code that runs but doesn't meet requirements → Agent points out gaps

4. **Multiple Submissions Flow**

   - User submits incomplete code → Agent provides feedback
   - User asks "How can I improve this?" → Agent gives specific suggestions
   - User submits improved version → Agent recognizes improvement
   - User submits 3rd version → Agent tracks progression

5. **Code Polling During Work**
   - User starts typing code → Polling detects changes
   - User makes significant progress → Agent could provide subtle encouragement
   - User seems stuck (no changes for 30s) → Agent could offer hint
   - User deletes all code → Agent could ask if they need help

### Edge Cases & Error Handling

6. **Exercise Understanding**

   - User asks "What does this exercise mean?" → Agent clarifies
   - User says "I don't understand the requirements" → Agent explains
   - User asks "Can you give me a hint?" → Agent provides hint from exercise_hints
   - User says "This is too hard" → Agent could adjust or provide simpler version

7. **Topic Changes During Coding**

   - User is coding → User says "Actually, can we talk about something else?" → Agent handles gracefully
   - User submits code → User immediately asks different question → Agent responds appropriately
   - User requests new exercise mid-interview → Agent provides new exercise

8. **Code Quality Scenarios**

   - User submits code that works but is inefficient → Agent mentions job requirement (efficiency)
   - User submits code without error handling → Agent mentions job requirement (robustness)
   - User submits code that's hard to read → Agent mentions job requirement (maintainability)
   - User submits perfect code → Agent praises and asks deeper question

9. **Job Description Integration**

   - Interview with detailed job description → Questions should reference job requirements
   - Interview with vague job description → Agent should still generate relevant exercise
   - Interview without job description → Agent should work from resume/context
   - Job description mentions specific tech → Exercise should use that tech

10. **Real-Time Interaction**
    - User types code → Agent sees changes via polling → Agent could comment on approach
    - User makes good progress → Agent provides encouragement
    - User seems confused → Agent offers help
    - User completes exercise quickly → Agent provides harder follow-up

### User Experience Scenarios

11. **Clarification Requests**

    - User: "I'm not sure what you mean" → Agent rephrases question
    - User: "Can you repeat that?" → Agent repeats last question
    - User: "What was the exercise again?" → Agent restates exercise

12. **Help Requests**

    - User: "I'm stuck" → Agent provides hint
    - User: "Can you help me?" → Agent gives guidance without solving
    - User: "Show me how" → Agent explains approach, doesn't give full solution

13. **Confidence & Encouragement**

    - User submits good code → Agent praises and builds confidence
    - User seems nervous → Agent provides reassurance
    - User makes mistake → Agent is supportive, helps learn

14. **Interview Completion**
    - User says "I'm done" → Agent evaluates and provides feedback
    - User says "That's all I have" → Agent wraps up gracefully
    - Interview time limit → Agent transitions to feedback

### Technical Edge Cases

15. **Code Execution Issues**

    - Code has syntax error → Agent helps identify and fix
    - Code runs but produces wrong output → Agent points out logic error
    - Code times out → Agent suggests optimization
    - Code uses wrong language → Agent corrects

16. **State Management**

    - User refreshes page → State should persist
    - Multiple code submissions → All should be tracked
    - Exercise changes mid-interview → State should update correctly

17. **Frontend-Backend Sync**
    - Code typed in editor → Should sync to backend via polling
    - Exercise provided → Should appear in editor
    - Agent feedback → Should appear in conversation

## Next Steps

1. **Implement Real-World Test Scenarios** - Create tests for scenarios above
2. **Fix Test 1** - Test code should match exact exercise domain
3. **Test End-to-End in UI** - Verify complete flow works
4. **Enhance Code Polling** - Add real-time feedback during coding
5. **Add Hint System** - Implement hint provision when user stuck

## Key Concepts

- **Exercise Matching is Strict**: Exact domain/requirements required
- **Job Description is Central**: Used throughout the system
- **Sandbox State**: Contains exercise code, description, hints, polling data

## Important Notes

- Database migration already run
- API endpoint: `PUT /api/v1/interviews/{id}/sandbox/code`
- All prompts include job context when available

**Status**: Core features implemented. Ready for UI testing.

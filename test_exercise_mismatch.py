"""Test script to verify agent detects when candidate submits code that doesn't match the exercise."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import AsyncSessionLocal
from src.models.user import User
from src.models.resume import Resume
from src.models.interview import Interview
from src.services.interview_orchestrator import InterviewOrchestrator
from src.services.state_manager import interview_to_state, state_to_interview
from sqlalchemy import select

Path("test_results").mkdir(exist_ok=True)


async def setup_test_data():
    """Set up test user and resume."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email == "test@interviewlab.com")
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print("ERROR: Test user not found. Please create test user first.")
            return None, None
        
        result = await db.execute(
            select(Resume).where(Resume.user_id == user.id).limit(1)
        )
        resume = result.scalar_one_or_none()
        
        return user, resume


async def test_exercise_mismatch():
    """Test: Agent detects when candidate submits code that doesn't match the exercise."""
    print("\n" + "=" * 80)
    print("TEST: Exercise Mismatch Detection")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        job_description = """
        Senior Python Backend Engineer
        - Design and implement RESTful APIs
        - Build microservices architecture
        """
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Exercise Mismatch",
            status="pending",
            resume_context=resume.extracted_data if resume else {},
            job_description=job_description.strip(),
            conversation_history=[],
            turn_count=0,
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)
        
        print(f"\n[SETUP] Created interview {interview.id}")
        
        orchestrator = InterviewOrchestrator()
        state = interview_to_state(interview)
        
        # Turn 1: Initial greeting
        print("\n--- Turn 1: Greeting ---")
        state = await orchestrator.execute_step(state)
        print(f"[AGENT] {state.get('next_message', '')[:200]}...")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: User requests to code
        print("\n--- Turn 2: User requests to code ---")
        print("[USER] I'd like to write some code to demonstrate my skills")
        state = await orchestrator.execute_step(state, user_response="I'd like to write some code to demonstrate my skills")
        print(f"[AGENT] {state.get('next_message', '')[:300]}...")
        
        # Check exercise was generated
        sandbox = state.get('sandbox', {})
        exercise_code = sandbox.get('initial_code', '')
        exercise_desc = sandbox.get('exercise_description', '')
        
        print(f"\n[EXERCISE GENERATED]")
        print(f"Description: {exercise_desc[:200]}...")
        print(f"Starter Code: {exercise_code[:200]}...")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 3: User submits WRONG code (Fibonacci instead of RESTful API)
        print("\n--- Turn 3: User submits MISMATCHED code ---")
        wrong_code = """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))"""
        
        print(f"[USER] Submitting code (WRONG - doesn't match exercise):\n{wrong_code}")
        state = await orchestrator.execute_step(state, code=wrong_code, language="python")
        
        feedback = state.get('next_message', '')
        print(f"\n[AGENT FEEDBACK]")
        print(feedback)
        
        # Check if agent detected mismatch
        detected_mismatch = (
            "doesn't match" in feedback.lower() or
            "exercise" in feedback.lower() and ("different" in feedback.lower() or "original" in feedback.lower()) or
            "note:" in feedback.lower()
        )
        
        print(f"\n[CHECK] Agent detected mismatch: {detected_mismatch}")
        if detected_mismatch:
            print("[OK] SUCCESS: Agent detected that code doesn't match exercise!")
        else:
            print("[WARN] WARNING: Agent did not detect code mismatch")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "exercise_mismatch_detection",
            "interview_id": interview.id,
            "exercise_description": exercise_desc,
            "exercise_code": exercise_code[:500],
            "submitted_code": wrong_code,
            "agent_feedback": feedback,
            "detected_mismatch": detected_mismatch,
            "conversation_history": state.get("conversation_history", []),
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/exercise_mismatch_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


if __name__ == "__main__":
    asyncio.run(test_exercise_mismatch())


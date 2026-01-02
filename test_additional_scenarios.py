"""Additional test scenarios for job description and exercise features.

Tests:
1. Multiple code submissions in one interview
2. Exercise generation without job description
3. Agent providing hints during coding
4. Code review with partial/incomplete solution
"""

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
            print("ERROR: Test user not found.")
            return None, None
        
        result = await db.execute(
            select(Resume).where(Resume.user_id == user.id).limit(1)
        )
        resume = result.scalar_one_or_none()
        
        return user, resume


async def test_scenario_1_multiple_submissions():
    """Test 1: Multiple code submissions in one interview."""
    print("\n" + "=" * 80)
    print("TEST 1: Multiple Code Submissions")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        job_description = "Senior Python Developer - Write clean, efficient code"
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Multiple Submissions",
            status="pending",
            resume_context=resume.extracted_data if resume else {},
            job_description=job_description,
            conversation_history=[],
            turn_count=0,
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)
        
        orchestrator = InterviewOrchestrator()
        state = interview_to_state(interview)
        
        # Turn 1: Greeting
        state = await orchestrator.execute_step(state)
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: Request to code
        state = await orchestrator.execute_step(state, user_response="I'd like to write some code")
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 3: First submission (incomplete)
        print("\n--- Submission 1: Incomplete code ---")
        code1 = """def fibonacci(n):
    if n <= 1:
        return n
    # TODO: optimize this"""
        
        state = await orchestrator.execute_step(state, code=code1, language="python")
        feedback1 = state.get('next_message', '')
        print(f"[FEEDBACK 1] {feedback1[:200]}...")
        
        submissions_count_1 = len(state.get('code_submissions', []))
        print(f"[SUBMISSIONS] Count after first: {submissions_count_1}")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 4: Second submission (improved)
        print("\n--- Submission 2: Improved code ---")
        code2 = """def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

print(fibonacci(10))"""
        
        state = await orchestrator.execute_step(state, code=code2, language="python")
        feedback2 = state.get('next_message', '')
        print(f"[FEEDBACK 2] {feedback2[:200]}...")
        
        submissions_count_2 = len(state.get('code_submissions', []))
        print(f"[SUBMISSIONS] Count after second: {submissions_count_2}")
        
        # Check if agent recognizes improvement
        recognizes_improvement = (
            "improve" in feedback2.lower() or
            "better" in feedback2.lower() or
            "enhance" in feedback2.lower() or
            submissions_count_2 > submissions_count_1
        )
        
        print(f"\n[CHECK] Agent tracked multiple submissions: {submissions_count_2 > 1}")
        print(f"[CHECK] Agent recognizes improvement: {recognizes_improvement}")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "multiple_submissions",
            "interview_id": interview.id,
            "submission_1": code1,
            "submission_2": code2,
            "feedback_1": feedback1,
            "feedback_2": feedback2,
            "submissions_count": submissions_count_2,
            "recognizes_improvement": recognizes_improvement,
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/multiple_submissions_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def test_scenario_2_exercise_no_job_description():
    """Test 2: Exercise generation when no job description provided."""
    print("\n" + "=" * 80)
    print("TEST 2: Exercise Generation (No Job Description)")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Exercise No Job Desc",
            status="pending",
            resume_context=resume.extracted_data if resume else {},
            job_description=None,  # No job description
            conversation_history=[],
            turn_count=0,
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)
        
        orchestrator = InterviewOrchestrator()
        state = interview_to_state(interview)
        
        # Turn 1: Greeting
        state = await orchestrator.execute_step(state)
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: Request to code
        print("\n--- Request to code (no job description) ---")
        state = await orchestrator.execute_step(state, user_response="I'd like to write some code")
        
        sandbox = state.get('sandbox', {})
        exercise_generated = bool(sandbox.get('initial_code'))
        exercise_desc = sandbox.get('exercise_description', '')
        
        print(f"[EXERCISE GENERATED] {exercise_generated}")
        if exercise_generated:
            print(f"[EXERCISE] {exercise_desc[:200]}...")
            print("[OK] SUCCESS: Agent generated exercise without job description!")
        else:
            print("[WARN] WARNING: No exercise generated without job description")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "exercise_no_job_description",
            "interview_id": interview.id,
            "exercise_generated": exercise_generated,
            "exercise_description": exercise_desc,
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/exercise_no_job_desc_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def test_scenario_3_partial_solution():
    """Test 3: Code review with partial/incomplete solution."""
    print("\n" + "=" * 80)
    print("TEST 3: Partial/Incomplete Solution Review")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        job_description = "Backend Engineer - Complete implementations required"
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Partial Solution",
            status="pending",
            resume_context=resume.extracted_data if resume else {},
            job_description=job_description,
            conversation_history=[],
            turn_count=0,
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)
        
        orchestrator = InterviewOrchestrator()
        state = interview_to_state(interview)
        
        # Turn 1: Greeting
        state = await orchestrator.execute_step(state)
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: Request to code
        state = await orchestrator.execute_step(state, user_response="I'd like to write some code")
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 3: Submit partial solution
        print("\n--- Submit partial solution ---")
        partial_code = """from flask import Flask, jsonify, request

app = Flask(__name__)
books = []

@app.route('/books', methods=['POST'])
def create_book():
    # TODO: implement this
    pass

@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(books)"""
        
        state = await orchestrator.execute_step(state, code=partial_code, language="python")
        feedback = state.get('next_message', '')
        print(f"[FEEDBACK] {feedback[:400]}...")
        
        # Check if agent recognizes incomplete solution
        recognizes_incomplete = (
            "incomplete" in feedback.lower() or
            "todo" in feedback.lower() or
            "implement" in feedback.lower() or
            "missing" in feedback.lower() or
            "finish" in feedback.lower()
        )
        
        print(f"\n[CHECK] Agent recognizes incomplete solution: {recognizes_incomplete}")
        if recognizes_incomplete:
            print("[OK] SUCCESS: Agent correctly identified incomplete solution!")
        else:
            print("[WARN] WARNING: Agent may not have recognized incomplete solution")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "partial_solution",
            "interview_id": interview.id,
            "partial_code": partial_code,
            "agent_feedback": feedback,
            "recognizes_incomplete": recognizes_incomplete,
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/partial_solution_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def main():
    """Run all additional scenario tests."""
    print("=" * 80)
    print("ADDITIONAL SCENARIO TESTS")
    print("=" * 80)
    
    results = []
    
    # Test 1: Multiple submissions
    try:
        result = await test_scenario_1_multiple_submissions()
        if result:
            results.append(result)
    except Exception as e:
        print(f"Test 1 failed: {e}")
    
    # Test 2: Exercise without job description
    try:
        result = await test_scenario_2_exercise_no_job_description()
        if result:
            results.append(result)
    except Exception as e:
        print(f"Test 2 failed: {e}")
    
    # Test 3: Partial solution
    try:
        result = await test_scenario_3_partial_solution()
        if result:
            results.append(result)
    except Exception as e:
        print(f"Test 3 failed: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total scenarios tested: {len(results)}")
    for i, result in enumerate(results, 1):
        scenario = result.get('scenario', 'unknown')
        print(f"  {i}. {scenario}: COMPLETED")
    
    print("\n[DONE] All tests complete!")
    print("Please review the individual test result files in test_results/ for detailed analysis.")


if __name__ == "__main__":
    asyncio.run(main())


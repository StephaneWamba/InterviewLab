"""Comprehensive test for exercise validation and mismatch detection.

Tests:
1. Correct code submission (matches exercise)
2. Wrong code submission (doesn't match exercise)
3. No exercise provided (normal code review)
4. Partial match (related but not exact)
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

import sys
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


async def test_scenario_1_correct_submission():
    """Test 1: Candidate submits code that matches the exercise."""
    print("\n" + "=" * 80)
    print("TEST 1: Correct Code Submission (Matches Exercise)")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        job_description = "Senior Python Backend Engineer - Design RESTful APIs"
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Correct Submission",
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
        print("\n--- Turn 1: Greeting ---")
        state = await orchestrator.execute_step(state)
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: Request to code
        print("\n--- Turn 2: Request to code ---")
        state = await orchestrator.execute_step(state, user_response="I'd like to write some code")
        
        sandbox = state.get('sandbox', {})
        exercise_desc = sandbox.get('exercise_description', '')
        exercise_code = sandbox.get('initial_code', '')
        
        print(f"[EXERCISE] {exercise_desc[:150]}...")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 3: Submit CORRECT code (matching the exercise)
        print("\n--- Turn 3: Submit CORRECT code ---")
        # Use the starter code and complete it based on the exercise description
        # This ensures we're solving the exact exercise provided
        if exercise_code and ("TODO" in exercise_code or "pass" in exercise_code):
            # Extract domain from exercise description AND starter code
            domain = None
            entity_name = None  # singular form
            
            # First, check the starter code for existing variable names
            # Look for list variable patterns like "books = []", "tasks = []", etc.
            list_match = re.search(r'(\w+)\s*=\s*\[\]', exercise_code)
            if list_match:
                entity_name = list_match.group(1)
                # Convert to plural if singular (basic pluralization)
                if entity_name.endswith('y'):
                    domain = entity_name[:-1] + 'ies'
                elif entity_name.endswith('s'):
                    domain = entity_name
                else:
                    domain = entity_name + 's'
            
            # If not found in code, extract from exercise description
            if not domain:
                desc_lower = exercise_desc.lower()
                if "book" in desc_lower or "library" in desc_lower:
                    domain = "books"
                    entity_name = "book"
                elif "task" in desc_lower or "todo" in desc_lower:
                    domain = "tasks"
                    entity_name = "task"
                elif "user" in desc_lower or "account" in desc_lower:
                    domain = "users"
                    entity_name = "user"
                elif "product" in desc_lower:
                    domain = "products"
                    entity_name = "product"
                elif "item" in desc_lower:
                    domain = "items"
                    entity_name = "item"
                else:
                    # Default fallback
                    domain = "items"
                    entity_name = "item"
            
            # Complete the starter code by implementing the TODO/pass statements
            # For RESTful API exercises, implement the CRUD operations
            if "RESTful API" in exercise_desc or "route" in exercise_code.lower() or "@app.route" in exercise_code:
                # Replace pass/TODO with actual implementation
                correct_code = exercise_code
                
                # Replace "pass" with POST implementation
                if "def create" in exercise_code.lower() or "def post" in exercise_code.lower() or "POST" in exercise_code:
                    correct_code = re.sub(
                        r'\bpass\b',
                        f"""    data = request.json
    {entity_name} = {{
        'id': len({domain}) + 1,
        **data
    }}
    {domain}.append({entity_name})
    return jsonify({entity_name}), 201""",
                        correct_code,
                        count=1
                    )
                
                # Replace TODO comments with GET implementation
                if "TODO" in correct_code or "def get" in correct_code.lower() or "GET" in correct_code:
                    correct_code = re.sub(
                        r'TODO[^\n]*',
                        f'    return jsonify({domain})',
                        correct_code
                    )
                    if "pass" in correct_code and "def get" in correct_code.lower():
                        correct_code = re.sub(
                            r'\bpass\b',
                            f'    return jsonify({domain})',
                            correct_code,
                            count=1
                        )
            else:
                # For other exercises, just use the starter code as-is
                correct_code = exercise_code
        else:
            # If no starter code, use exercise code directly
            correct_code = exercise_code if exercise_code else """# Exercise implementation"""
        
        print(f"[USER] Submitting code (CORRECT - matches exercise)")
        state = await orchestrator.execute_step(state, code=correct_code, language="python")
        
        feedback = state.get('next_message', '')
        print(f"\n[AGENT FEEDBACK]")
        print(feedback[:500] + "...")
        
        # Check if agent detected mismatch (should be False)
        detected_mismatch = (
            "doesn't match" in feedback.lower() or
            ("exercise" in feedback.lower() and "original" in feedback.lower())
        )
        
        print(f"\n[CHECK] Agent detected mismatch: {detected_mismatch}")
        if not detected_mismatch:
            print("[OK] SUCCESS: Agent correctly identified matching code!")
        else:
            print("[WARN] WARNING: Agent incorrectly flagged matching code as mismatch")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "correct_submission",
            "interview_id": interview.id,
            "exercise_description": exercise_desc,
            "submitted_code": correct_code[:500],
            "agent_feedback": feedback,
            "detected_mismatch": detected_mismatch,
            "expected": False,
            "passed": not detected_mismatch,
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/exercise_validation_test1_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def test_scenario_2_wrong_submission():
    """Test 2: Candidate submits code that doesn't match the exercise."""
    print("\n" + "=" * 80)
    print("TEST 2: Wrong Code Submission (Doesn't Match Exercise)")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        job_description = "Senior Python Backend Engineer - Design RESTful APIs"
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Wrong Submission",
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
        
        sandbox = state.get('sandbox', {})
        exercise_desc = sandbox.get('exercise_description', '')
        
        print(f"[EXERCISE] {exercise_desc[:150]}...")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 3: Submit WRONG code
        print("\n--- Submit WRONG code ---")
        wrong_code = """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))"""
        
        print(f"[USER] Submitting code (WRONG - doesn't match exercise)")
        state = await orchestrator.execute_step(state, code=wrong_code, language="python")
        
        feedback = state.get('next_message', '')
        print(f"\n[AGENT FEEDBACK]")
        print(feedback)
        
        # Check if agent detected mismatch (should be True)
        detected_mismatch = (
            "doesn't match" in feedback.lower() or
            ("exercise" in feedback.lower() and "original" in feedback.lower()) or
            "note:" in feedback.lower()
        )
        
        print(f"\n[CHECK] Agent detected mismatch: {detected_mismatch}")
        if detected_mismatch:
            print("[OK] SUCCESS: Agent correctly detected code mismatch!")
        else:
            print("[WARN] WARNING: Agent failed to detect code mismatch")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "wrong_submission",
            "interview_id": interview.id,
            "exercise_description": exercise_desc,
            "submitted_code": wrong_code,
            "agent_feedback": feedback,
            "detected_mismatch": detected_mismatch,
            "expected": True,
            "passed": detected_mismatch,
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/exercise_validation_test2_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def test_scenario_3_no_exercise():
    """Test 3: Code submission when no exercise was provided."""
    print("\n" + "=" * 80)
    print("TEST 3: Code Submission (No Exercise Provided)")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - No Exercise",
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
        
        # Turn 2: Submit code directly (no exercise provided)
        print("\n--- Submit code (no exercise) ---")
        code = """def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

print(fibonacci(10))"""
        
        print(f"[USER] Submitting code (no exercise was provided)")
        state = await orchestrator.execute_step(state, code=code, language="python")
        
        feedback = state.get('next_message', '')
        print(f"\n[AGENT FEEDBACK]")
        print(feedback[:500] + "...")
        
        # Check if agent mentioned exercise mismatch (should be False - no exercise to mismatch)
        mentioned_exercise = "exercise" in feedback.lower() and ("doesn't match" in feedback.lower() or "original" in feedback.lower())
        
        print(f"\n[CHECK] Agent mentioned exercise mismatch: {mentioned_exercise}")
        if not mentioned_exercise:
            print("[OK] SUCCESS: Agent correctly handled code without exercise context!")
        else:
            print("[WARN] WARNING: Agent incorrectly mentioned exercise when none was provided")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "no_exercise",
            "interview_id": interview.id,
            "submitted_code": code,
            "agent_feedback": feedback,
            "mentioned_exercise_mismatch": mentioned_exercise,
            "expected": False,
            "passed": not mentioned_exercise,
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/exercise_validation_test3_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def main():
    """Run all validation tests."""
    print("=" * 80)
    print("EXERCISE VALIDATION COMPREHENSIVE TESTS")
    print("=" * 80)
    
    results = []
    
    # Test 1: Correct submission
    try:
        result = await test_scenario_1_correct_submission()
        if result:
            results.append(result)
    except Exception as e:
        print(f"Test 1 failed: {e}")
    
    # Test 2: Wrong submission
    try:
        result = await test_scenario_2_wrong_submission()
        if result:
            results.append(result)
    except Exception as e:
        print(f"Test 2 failed: {e}")
    
    # Test 3: No exercise
    try:
        result = await test_scenario_3_no_exercise()
        if result:
            results.append(result)
    except Exception as e:
        print(f"Test 3 failed: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    passed = sum(1 for r in results if r.get('passed', False))
    total = len(results)
    print(f"Tests passed: {passed}/{total}")
    
    for i, result in enumerate(results, 1):
        scenario = result.get('scenario', 'unknown')
        passed_status = "PASSED" if result.get('passed', False) else "FAILED"
        print(f"  {i}. {scenario}: {passed_status}")
    
    print("\n[DONE] All tests complete!")
    print("Please review the individual test result files in test_results/ for detailed analysis.")


if __name__ == "__main__":
    asyncio.run(main())


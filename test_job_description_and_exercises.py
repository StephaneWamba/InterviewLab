"""Test script for job description and exercise generation features.

Tests:
1. Interview creation with job description
2. Exercise generation based on job description
3. Code submission with job context
4. Feedback generation with job description
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create test results directory
Path("test_results").mkdir(exist_ok=True)


async def setup_test_data():
    """Set up test user and resume."""
    async with AsyncSessionLocal() as db:
        # Get or create test user
        result = await db.execute(
            select(User).where(User.email == "test@interviewlab.com")
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error("Test user not found. Please create test user first.")
            return None, None
        
        # Get a resume
        result = await db.execute(
            select(Resume).where(Resume.user_id == user.id).limit(1)
        )
        resume = result.scalar_one_or_none()
        
        return user, resume


async def test_scenario_1_job_description_questions():
    """Test 1: Agent uses job description to ask relevant questions."""
    print("\n" + "=" * 80)
    print("SCENARIO 1: Job Description - Relevant Questions")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        # Create interview with job description
        job_description = """
        We are looking for a Senior Backend Engineer with:
        - 5+ years experience in Python and microservices
        - Strong knowledge of distributed systems
        - Experience with AWS, Docker, and Kubernetes
        - Ability to design scalable APIs
        - Leadership experience preferred
        """
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Job Description Questions",
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
        print(f"[JOB DESCRIPTION] {job_description[:100]}...")
        
        orchestrator = InterviewOrchestrator()
        state = interview_to_state(interview)
        
        # Turn 1: Initial greeting
        print("\n--- Turn 1 ---")
        print("[USER] (no input - initial greeting)")
        state = await orchestrator.execute_step(state)
        print(f"[AGENT] {state.get('next_message', '')[:200]}...")
        print(f"[STATE] Turn: {state.get('turn_count')}, Node: {state.get('last_node')}, Phase: {state.get('phase')}")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: User responds
        print("\n--- Turn 2 ---")
        print("[USER] Hi, thank you")
        state = await orchestrator.execute_step(state, user_response="Hi, thank you")
        print(f"[AGENT] {state.get('next_message', '')[:200]}...")
        print(f"[STATE] Turn: {state.get('turn_count')}, Node: {state.get('last_node')}, Phase: {state.get('phase')}")
        
        # Check if question is relevant to job description
        question = state.get('next_message', '')
        job_keywords = ['backend', 'python', 'microservices', 'distributed', 'aws', 'docker', 'kubernetes', 'api', 'scalable', 'leadership']
        relevant = any(keyword.lower() in question.lower() for keyword in job_keywords)
        print(f"[CHECK] Question relevant to job: {relevant}")
        if relevant:
            print(f"[OK] SUCCESS: Agent asked job-relevant question")
        else:
            print(f"[WARN] WARNING: Question may not be job-relevant")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "job_description_questions",
            "interview_id": interview.id,
            "job_description": job_description,
            "question_asked": question,
            "is_relevant": relevant,
            "conversation_history": state.get("conversation_history", []),
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/job_desc_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def test_scenario_2_exercise_generation():
    """Test 2: Agent generates coding exercise based on job description."""
    print("\n" + "=" * 80)
    print("SCENARIO 2: Exercise Generation")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        # Create interview with technical job description
        job_description = """
        Senior Python Backend Engineer
        - Design and implement RESTful APIs
        - Build microservices architecture
        - Optimize database queries
        - Write clean, maintainable code
        """
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Exercise Generation",
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
        print("\n--- Turn 1 ---")
        print("[USER] (no input - initial greeting)")
        state = await orchestrator.execute_step(state)
        print(f"[AGENT] {state.get('next_message', '')[:200]}...")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: User requests to code
        print("\n--- Turn 2 ---")
        print("[USER] I'd like to write some code to demonstrate my skills")
        state = await orchestrator.execute_step(state, user_response="I'd like to write some code to demonstrate my skills")
        print(f"[AGENT] {state.get('next_message', '')[:200]}...")
        print(f"[STATE] Turn: {state.get('turn_count')}, Node: {state.get('last_node')}, Phase: {state.get('phase')}")
        
        # Check if exercise was generated
        sandbox = state.get('sandbox', {})
        has_exercise = bool(sandbox.get('initial_code'))
        exercise_code = sandbox.get('initial_code', '')
        exercise_desc = sandbox.get('exercise_description', '')
        
        print(f"\n[CHECK] Exercise generated: {has_exercise}")
        if has_exercise:
            print(f"[EXERCISE CODE] {exercise_code[:200]}...")
            print(f"[EXERCISE DESCRIPTION] {exercise_desc}")
            print(f"[OK] SUCCESS: Agent generated exercise")
        else:
            print(f"[WARN] WARNING: No exercise generated")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "exercise_generation",
            "interview_id": interview.id,
            "job_description": job_description,
            "exercise_generated": has_exercise,
            "exercise_code": exercise_code,
            "exercise_description": exercise_desc,
            "sandbox_state": sandbox,
            "conversation_history": state.get("conversation_history", []),
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/exercise_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def test_scenario_3_code_review_with_job_context():
    """Test 3: Agent reviews code considering job requirements."""
    print("\n" + "=" * 80)
    print("SCENARIO 3: Code Review with Job Context")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        # Create interview with job description
        job_description = """
        Backend Engineer - Python
        - Write efficient, scalable code
        - Follow best practices
        - Design clean APIs
        - Optimize performance
        """
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Code Review with Job Context",
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
        print("\n--- Turn 1 ---")
        print("[USER] (no input - initial greeting)")
        state = await orchestrator.execute_step(state)
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Turn 2: User submits code
        print("\n--- Turn 2 ---")
        test_code = """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))"""
        
        print(f"[USER] Submitting code:\n{test_code}")
        state = await orchestrator.execute_step(state, code=test_code, language="python")
        print(f"[AGENT] {state.get('next_message', '')[:300]}...")
        print(f"[STATE] Turn: {state.get('turn_count')}, Node: {state.get('last_node')}, Phase: {state.get('phase')}")
        
        # Check code quality analysis
        code_quality = state.get('code_quality', {})
        execution_result = state.get('code_execution_result', {})
        
        print(f"\n[CODE QUALITY]")
        print(f"  Overall Score: {code_quality.get('quality_score', 0):.2f}")
        print(f"  Correctness: {code_quality.get('correctness_score', 0):.2f}")
        print(f"  Efficiency: {code_quality.get('efficiency_score', 0):.2f}")
        print(f"  Readability: {code_quality.get('readability_score', 0):.2f}")
        print(f"  Best Practices: {code_quality.get('best_practices_score', 0):.2f}")
        
        # Check if feedback mentions job-relevant aspects
        feedback_message = state.get('next_message', '')
        job_keywords = ['efficient', 'scalable', 'performance', 'optimize', 'best practice', 'clean']
        mentions_job = any(keyword.lower() in feedback_message.lower() for keyword in job_keywords)
        print(f"\n[CHECK] Feedback mentions job requirements: {mentions_job}")
        if mentions_job:
            print(f"[OK] SUCCESS: Agent considered job requirements in feedback")
        else:
            print(f"[WARN] WARNING: Feedback may not reference job requirements")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "code_review_with_job_context",
            "interview_id": interview.id,
            "job_description": job_description,
            "code_submitted": test_code,
            "code_quality": code_quality,
            "execution_result": execution_result,
            "feedback_message": feedback_message,
            "mentions_job_requirements": mentions_job,
            "conversation_history": state.get("conversation_history", []),
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/code_review_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def test_scenario_4_feedback_with_job_description():
    """Test 4: Feedback generation includes job description context."""
    print("\n" + "=" * 80)
    print("SCENARIO 4: Feedback with Job Description")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        # Create interview with job description
        job_description = """
        Full Stack Developer
        - React and Python experience required
        - Strong problem-solving skills
        - Good communication
        - Code quality and testing
        """
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Feedback with Job Description",
            status="pending",
            resume_context=resume.extracted_data if resume else {},
            job_description=job_description.strip(),
            conversation_history=[
                {"role": "assistant", "content": "Hi! Let's start the interview.", "timestamp": datetime.utcnow().isoformat()},
                {"role": "user", "content": "Hello", "timestamp": datetime.utcnow().isoformat()},
                {"role": "assistant", "content": "Tell me about your React experience.", "timestamp": datetime.utcnow().isoformat()},
                {"role": "user", "content": "I've worked with React for 3 years, building complex UIs.", "timestamp": datetime.utcnow().isoformat()},
            ],
            turn_count=4,
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)
        
        print(f"\n[SETUP] Created interview {interview.id} with conversation history")
        
        orchestrator = InterviewOrchestrator()
        state = interview_to_state(interview)
        
        # Generate feedback
        print("\n--- Generating Feedback ---")
        state = await orchestrator.execute_step(state)
        
        # Try to trigger evaluation
        state["phase"] = "closing"
        state = await orchestrator._evaluation_node(state)
        
        feedback = state.get('feedback', {})
        
        print(f"\n[FEEDBACK GENERATED]")
        print(f"  Overall Score: {feedback.get('overall_score', 0):.2f}")
        print(f"  Communication: {feedback.get('communication_score', 0):.2f}")
        print(f"  Technical: {feedback.get('technical_score', 0):.2f}")
        print(f"  Problem Solving: {feedback.get('problem_solving_score', 0):.2f}")
        print(f"  Code Quality: {feedback.get('code_quality_score', 0):.2f}")
        
        summary = feedback.get('summary', '')
        print(f"\n[SUMMARY] {summary[:300]}...")
        
        # Check if feedback references job requirements
        job_keywords = ['react', 'python', 'problem-solving', 'communication', 'code quality', 'testing']
        mentions_job = any(keyword.lower() in summary.lower() for keyword in job_keywords)
        print(f"\n[CHECK] Feedback references job requirements: {mentions_job}")
        if mentions_job:
            print(f"[OK] SUCCESS: Feedback includes job-relevant context")
        else:
            print(f"[WARN] WARNING: Feedback may not reference job requirements")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "feedback_with_job_description",
            "interview_id": interview.id,
            "job_description": job_description,
            "feedback": feedback,
            "mentions_job_requirements": mentions_job,
            "conversation_history": state.get("conversation_history", []),
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/feedback_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


async def main():
    """Run all test scenarios one at a time."""
    print("=" * 80)
    print("JOB DESCRIPTION AND EXERCISE GENERATION TESTS")
    print("=" * 80)
    
    results = []
    
    # Test 1: Job description questions
    try:
        result = await test_scenario_1_job_description_questions()
        if result:
            results.append(result)
    except Exception as e:
        logger.error(f"Test 1 failed: {e}", exc_info=True)
    
    # Test 2: Exercise generation
    try:
        result = await test_scenario_2_exercise_generation()
        if result:
            results.append(result)
    except Exception as e:
        logger.error(f"Test 2 failed: {e}", exc_info=True)
    
    # Test 3: Code review with job context
    try:
        result = await test_scenario_3_code_review_with_job_context()
        if result:
            results.append(result)
    except Exception as e:
        logger.error(f"Test 3 failed: {e}", exc_info=True)
    
    # Test 4: Feedback with job description
    try:
        result = await test_scenario_4_feedback_with_job_description()
        if result:
            results.append(result)
    except Exception as e:
        logger.error(f"Test 4 failed: {e}", exc_info=True)
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total scenarios tested: {len(results)}")
    for i, result in enumerate(results, 1):
        scenario = result.get('scenario', 'unknown')
        print(f"  {i}. {scenario}: {'PASSED' if result.get('is_relevant') or result.get('exercise_generated') or result.get('mentions_job_requirements') else 'NEEDS REVIEW'}")
    
    print("\n[DONE] All tests complete!")
    print("Please review the individual test result files in test_results/ for detailed analysis.")


if __name__ == "__main__":
    asyncio.run(main())


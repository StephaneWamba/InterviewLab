"""Test code polling functionality - agent monitoring code changes in real-time."""

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


async def test_code_polling():
    """Test: Agent polls code changes and provides real-time feedback."""
    print("\n" + "=" * 80)
    print("TEST: Code Polling - Real-time Code Monitoring")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        user, resume = await setup_test_data()
        if not user:
            return
        
        job_description = "Senior Python Backend Engineer - Design RESTful APIs"
        
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id if resume else None,
            title="Test - Code Polling",
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
        exercise_code = sandbox.get('initial_code', '')
        exercise_desc = sandbox.get('exercise_description', '')
        
        print(f"[EXERCISE] {exercise_desc[:150]}...")
        print(f"[STARTER CODE] {exercise_code[:200]}...")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Simulate code polling: Update code multiple times
        print("\n--- Simulating Code Polling ---")
        
        # Initial code (starter code)
        initial_code = exercise_code
        state["current_code"] = initial_code
        state["sandbox"]["last_code_snapshot"] = initial_code
        state["sandbox"]["last_poll_time"] = datetime.utcnow().timestamp()
        
        # Simulate user making changes
        code_versions = [
            initial_code,
            initial_code.replace("pass", "# Working on it..."),
            initial_code.replace("pass", """    data = request.json
    return jsonify({"message": "In progress"}), 200"""),
        ]
        
        polling_results = []
        
        for i, code_version in enumerate(code_versions[1:], 1):  # Skip first (initial)
            print(f"\n[POLL {i}] Code updated by user")
            state["current_code"] = code_version
            state["sandbox"]["is_active"] = True
            
            # Simulate polling check (what happens in execute_step)
            # In real scenario, this would be called periodically
            current_time = datetime.utcnow().timestamp()
            last_poll = state["sandbox"].get("last_poll_time", 0)
            time_since_poll = current_time - last_poll
            
            # Check if enough time has passed (in real scenario, this is 10 seconds)
            # For testing, we'll trigger it manually
            if time_since_poll > 5 or i == 1:  # First poll or 5+ seconds
                print(f"  [CHECK] Polling code changes...")
                
                # The polling logic would check for changes and potentially provide guidance
                last_snapshot = state["sandbox"].get("last_code_snapshot", "")
                if code_version != last_snapshot:
                    print(f"  [DETECTED] Code has changed")
                    state["sandbox"]["last_code_snapshot"] = code_version
                    state["sandbox"]["last_poll_time"] = current_time
                    
                    # In real scenario, agent might provide subtle encouragement
                    # For now, we just track the change
                    polling_results.append({
                        "poll_number": i,
                        "code_changed": True,
                        "code_length": len(code_version),
                        "timestamp": current_time,
                    })
                else:
                    print(f"  [NO CHANGE] Code unchanged")
        
        print(f"\n[POLLING SUMMARY]")
        print(f"  Total polls: {len(polling_results)}")
        print(f"  Code changes detected: {sum(1 for r in polling_results if r['code_changed'])}")
        
        # Final submission
        print("\n--- Final Code Submission ---")
        final_code = code_versions[-1]
        state = await orchestrator.execute_step(state, code=final_code, language="python")
        
        feedback = state.get('next_message', '')
        print(f"\n[AGENT FEEDBACK]")
        print(feedback[:500] + "...")
        
        state_to_interview(state, interview)
        await db.commit()
        
        # Save results
        results = {
            "scenario": "code_polling",
            "interview_id": interview.id,
            "exercise_description": exercise_desc,
            "polling_results": polling_results,
            "final_code": final_code[:500],
            "agent_feedback": feedback,
            "conversation_history": state.get("conversation_history", []),
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results/code_polling_test_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Results saved to: {results_file}")
        
        return results


if __name__ == "__main__":
    asyncio.run(test_code_polling())


"""
Test script to simulate interview agent conversations.

This script tests the orchestrator directly (bypassing LiveKit voice layer)
to identify issues like the greeting loop bug.

Results are saved to files for manual review - no automated pass/fail.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import AsyncSessionLocal
from src.models.interview import Interview
from src.models.user import User
from src.models.resume import Resume
from src.services.interview_orchestrator import InterviewOrchestrator
from src.services.state_manager import interview_to_state, state_to_interview
from src.services.checkpoint_service import CheckpointService


# Test conversation turns - simulate the bug scenario
TEST_CONVERSATION = [
    None,  # Turn 1: No user input (should trigger greeting)
    "Hi, thank you",  # Turn 2: User responds to greeting
    "I've been working in product engineering for about 7 years now",  # Turn 3
    "I led the team that built and stabilized the core communication platform",  # Turn 4
    "We were handling very high volumes of communication",  # Turn 5
]


async def create_test_user(db: AsyncSession) -> User:
    """Create or get test user."""
    result = await db.execute(
        select(User).where(User.email == "test@interviewlab.com")
    )
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            email="test@interviewlab.com",
            full_name="Test User",
            hashed_password="test_hash",  # Not used for this test
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"[OK] Created test user: {user.id}")
    else:
        print(f"[OK] Using existing test user: {user.id}")
    
    return user


async def create_test_resume(db: AsyncSession, user_id: int) -> Resume:
    """Create test resume with sample data."""
    result = await db.execute(
        select(Resume).where(Resume.user_id == user_id).limit(1)
    )
    resume = result.scalar_one_or_none()
    
    if not resume:
        resume = Resume(
            user_id=user_id,
            file_name="test_resume.pdf",
            file_path="assets/CV_StephaneWamba.pdf",  # Use existing resume if available
            file_size=1000,
            file_type="pdf",
            analysis_status="completed",
            extracted_data={
                "profile": "Senior Developer Consultant with 7+ years in product engineering",
                "experience": "Led core communication platform team at Simpl. Built distributed systems using Golang, AWS, Kafka.",
                "education": "Computer Science degree",
                "projects": "Built Simpl Checkout, billbox payment system",
                "hobbies": None,
            }
        )
        db.add(resume)
        await db.commit()
        await db.refresh(resume)
        print(f"[OK] Created test resume: {resume.id}")
    else:
        print(f"[OK] Using existing test resume: {resume.id}")
    
    return resume


async def create_test_interview(
    db: AsyncSession,
    user_id: int,
    resume_id: int
) -> Interview:
    """Create test interview."""
    interview = Interview(
        user_id=user_id,
        resume_id=resume_id,
        title="Test Interview - Greeting Loop Debug",
        status="in_progress",
        conversation_history=[],
        resume_context={
            "profile": "Senior Developer Consultant",
            "experience": "7+ years in product engineering",
        },
        turn_count=0,
        started_at=datetime.utcnow(),
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)
    print(f"[OK] Created test interview: {interview.id}")
    return interview


def extract_state_summary(state: dict) -> dict:
    """Extract key state fields for summary."""
    return {
        "turn_count": state.get("turn_count", 0),
        "last_node": state.get("last_node", ""),
        "next_node": state.get("next_node"),
        "phase": state.get("phase", ""),
        "_next_action": state.get("_next_action"),
        "_should_evaluate": state.get("_should_evaluate", False),
        "conversation_history_length": len(state.get("conversation_history", [])),
        "questions_asked_count": len(state.get("questions_asked", [])),
        "last_response": state.get("last_response"),
        "next_message_preview": (state.get("next_message", "")[:100] + "...") 
            if state.get("next_message") and len(state.get("next_message", "")) > 100 
            else state.get("next_message"),
    }


async def simulate_conversation():
    """Simulate a full interview conversation."""
    print("=" * 80)
    print("INTERVIEW AGENT CONVERSATION SIMULATION")
    print("=" * 80)
    print()
    
    # Get database session
    db = AsyncSessionLocal()
    
    try:
        # Setup: Create test data
        print("[SETUP] Setting up test data...")
        user = await create_test_user(db)
        resume = await create_test_resume(db, user.id)
        interview = await create_test_interview(db, user.id, resume.id)
        print()
        
        # Initialize orchestrator
        orchestrator = InterviewOrchestrator()
        checkpoint_service = CheckpointService()
        
        # Initialize state
        state = interview_to_state(interview)
        print(f"[STATE] Initial state summary:")
        print(f"   Turn count: {state.get('turn_count', 0)}")
        print(f"   Conversation history: {len(state.get('conversation_history', []))} messages")
        print()
        
        # Store results for each turn
        results = {
            "interview_id": interview.id,
            "test_started_at": datetime.utcnow().isoformat(),
            "turns": [],
        }
        
        # Simulate conversation turns
        print("=" * 80)
        print("CONVERSATION SIMULATION")
        print("=" * 80)
        print()
        
        for turn_num, user_input in enumerate(TEST_CONVERSATION, start=1):
            print(f"\n{'=' * 80}")
            print(f"TURN {turn_num}")
            print(f"{'=' * 80}")
            
            turn_result = {
                "turn_number": turn_num,
                "user_input": user_input,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            # Show user input
            if user_input:
                print(f"[USER] {user_input}")
                turn_result["user_input"] = user_input
            else:
                print(f"[USER] (no input - initial greeting)")
                turn_result["user_input"] = None
            
            # Restore state from checkpoint (simulate what agent does)
            restored_state = await checkpoint_service.restore(interview.id, db)
            if restored_state:
                print(f"[CHECKPOINT] State restored from checkpoint")
                state = restored_state
                turn_result["state_restored"] = True
                turn_result["restored_state_summary"] = extract_state_summary(state)
            else:
                print(f"[CHECKPOINT] No checkpoint found, using current state")
                turn_result["state_restored"] = False
            
            # Show state before execution
            print(f"\n[STATE] State BEFORE execution:")
            state_before = extract_state_summary(state)
            for key, value in state_before.items():
                print(f"   {key}: {value}")
            turn_result["state_before"] = state_before
            
            # Execute orchestrator step
            print(f"\n[EXEC] Executing orchestrator step...")
            try:
                state = await orchestrator.execute_step(
                    state,
                    user_response=user_input if user_input else None
                )
                turn_result["execution_success"] = True
            except Exception as e:
                print(f"[ERROR] ERROR during execution: {e}")
                turn_result["execution_success"] = False
                turn_result["execution_error"] = str(e)
                import traceback
                turn_result["execution_traceback"] = traceback.format_exc()
                continue
            
            # Show state after execution
            print(f"\n[STATE] State AFTER execution:")
            state_after = extract_state_summary(state)
            for key, value in state_after.items():
                print(f"   {key}: {value}")
            turn_result["state_after"] = state_after
            
            # Show agent response
            agent_response = state.get("next_message", "")
            if agent_response:
                print(f"\n[AGENT] {agent_response[:200]}{'...' if len(agent_response) > 200 else ''}")
                turn_result["agent_response"] = agent_response
            else:
                print(f"\n[AGENT] (no response generated)")
                turn_result["agent_response"] = None
            
            # Check for potential bugs
            print(f"\n[BUG CHECK] Bug Detection:")
            bugs_found = []
            
            # Check 1: Greeting loop bug
            if turn_num > 1 and state.get("_next_action") == "greeting":
                bug_msg = f"[WARNING] GREETING LOOP: Turn {turn_num} routes to 'greeting' after user has responded"
                print(bug_msg)
                bugs_found.append({
                    "type": "greeting_loop",
                    "message": bug_msg,
                    "turn_count": state.get("turn_count", 0),
                    "conversation_history_length": len(state.get("conversation_history", [])),
                })
            
            # Check 2: State not persisting
            if turn_num > 1 and state.get("turn_count", 0) == 0:
                bug_msg = f"[WARNING] STATE RESET: Turn count is 0 after multiple turns"
                print(bug_msg)
                bugs_found.append({
                    "type": "state_reset",
                    "message": bug_msg,
                })
            
            # Check 3: Conversation history not growing
            if turn_num > 1 and len(state.get("conversation_history", [])) < turn_num:
                bug_msg = f"[WARNING] HISTORY NOT GROWING: Expected at least {turn_num} messages, got {len(state.get('conversation_history', []))}"
                print(bug_msg)
                bugs_found.append({
                    "type": "history_not_growing",
                    "message": bug_msg,
                    "expected_min": turn_num,
                    "actual": len(state.get("conversation_history", [])),
                })
            
            if not bugs_found:
                print("   [OK] No obvious bugs detected")
            
            turn_result["bugs_detected"] = bugs_found
            
            # Update interview from state
            state_to_interview(state, interview)
            await db.commit()
            
            # Save checkpoint
            try:
                checkpoint_id = await checkpoint_service.checkpoint(state, db)
                print(f"\n[CHECKPOINT] Checkpoint saved: {checkpoint_id}")
                turn_result["checkpoint_id"] = checkpoint_id
                turn_result["checkpoint_saved"] = True
            except Exception as e:
                print(f"\n[ERROR] Failed to save checkpoint: {e}")
                turn_result["checkpoint_saved"] = False
                turn_result["checkpoint_error"] = str(e)
            
            # Store full state (for deep analysis)
            turn_result["full_state"] = {
                k: v for k, v in state.items() 
                if k not in ["resume_context", "resume_structured"]  # Too large
            }
            
            results["turns"].append(turn_result)
            
            print()
        
        # Final summary
        print("=" * 80)
        print("SIMULATION COMPLETE")
        print("=" * 80)
        print()
        
        # Final state check
        final_state = await checkpoint_service.restore(interview.id, db)
        if final_state:
            print("[STATE] Final State Summary:")
            final_summary = extract_state_summary(final_state)
            for key, value in final_summary.items():
                print(f"   {key}: {value}")
        else:
            print("[WARNING] No checkpoint found for final state")
        
        print()
        print(f"[SUMMARY] Total turns simulated: {len(TEST_CONVERSATION)}")
        print(f"[SUMMARY] Total bugs detected: {sum(len(turn.get('bugs_detected', [])) for turn in results['turns'])}")
        
        # Save results to files
        results["test_completed_at"] = datetime.utcnow().isoformat()
        
        # Save JSON (detailed)
        output_dir = Path("test_results")
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        json_file = output_dir / f"conversation_test_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[SAVE] Detailed results saved to: {json_file}")
        
        # Save human-readable text summary
        txt_file = output_dir / f"conversation_test_{timestamp}.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("INTERVIEW AGENT CONVERSATION TEST RESULTS\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Test Date: {results['test_started_at']}\n")
            f.write(f"Interview ID: {results['interview_id']}\n")
            f.write(f"Total Turns: {len(results['turns'])}\n\n")
            
            for turn in results["turns"]:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"TURN {turn['turn_number']}\n")
                f.write("=" * 80 + "\n\n")
                
                f.write(f"User Input: {turn.get('user_input') or '(none - initial greeting)'}\n\n")
                
                f.write("State Before Execution:\n")
                for key, value in turn.get("state_before", {}).items():
                    f.write(f"  {key}: {value}\n")
                f.write("\n")
                
                f.write("State After Execution:\n")
                for key, value in turn.get("state_after", {}).items():
                    f.write(f"  {key}: {value}\n")
                f.write("\n")
                
                agent_response = turn.get("agent_response", "")
                if agent_response:
                    f.write(f"Agent Response:\n{agent_response}\n\n")
                else:
                    f.write("Agent Response: (none)\n\n")
                
                bugs = turn.get("bugs_detected", [])
                if bugs:
                    f.write("Bugs Detected:\n")
                    for bug in bugs:
                        f.write(f"  - {bug['type']}: {bug['message']}\n")
                    f.write("\n")
                else:
                    f.write("Bugs Detected: None\n\n")
                
                if turn.get("checkpoint_saved"):
                    f.write(f"Checkpoint ID: {turn.get('checkpoint_id')}\n")
                else:
                    f.write(f"Checkpoint: FAILED - {turn.get('checkpoint_error', 'unknown error')}\n")
                f.write("\n")
            
            # Summary
            f.write("\n" + "=" * 80 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            
            total_bugs = sum(len(turn.get("bugs_detected", [])) for turn in results["turns"])
            f.write(f"Total Bugs Detected: {total_bugs}\n\n")
            
            if total_bugs > 0:
                f.write("Bug Details:\n")
                for turn in results["turns"]:
                    for bug in turn.get("bugs_detected", []):
                        f.write(f"  Turn {turn['turn_number']}: {bug['type']} - {bug['message']}\n")
        
        print(f"[SAVE] Human-readable summary saved to: {txt_file}")
        print()
        print("[DONE] Test complete! Review the files above for detailed analysis.")
        
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(simulate_conversation())


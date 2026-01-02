"""
Comprehensive test script to evaluate agent behavior across various scenarios.

Tests different conversation patterns, edge cases, and user behaviors.
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


# Test scenarios
TEST_SCENARIOS = {
    "basic_conversation": [
        None,  # Greeting
        "Hi, thank you",
        "I've been working in product engineering for about 7 years now",
        "I led the team that built and stabilized the core communication platform",
        "We were handling very high volumes of communication",
    ],
    
    "code_request": [
        None,  # Greeting
        "Hi",
        "I'd like to write some code to demonstrate my approach",
        "Can I use the sandbox?",
        "Here's my code implementation...",
    ],
    
    "topic_change": [
        None,  # Greeting
        "Hello",
        "I've worked on distributed systems",
        "Can we talk about something else?",
        "I'd like to discuss my leadership experience",
    ],
    
    "short_responses": [
        None,  # Greeting
        "Yes",
        "Sure",
        "Okay",
        "That's correct",
    ],
    
    "long_detailed_response": [
        None,  # Greeting
        "Hi there",
        """I've been working in product engineering for about 7 years now. I started as a junior developer 
        and worked my way up to senior staff engineer. I've led multiple teams, built scalable systems 
        handling millions of requests, and have experience with Golang, Python, Node.js, AWS, Kafka, Redis, 
        and Postgres. I'm particularly proud of the communication platform I built at Simpl, which reduced 
        costs by 40% while improving latency.""",
    ],
    
    "clarification_request": [
        None,  # Greeting
        "Hello",
        "What do you mean by that?",
        "Can you clarify the question?",
        "I'm not sure I understand",
    ],
    
    "mixed_intents": [
        None,  # Greeting
        "Hi",
        "I've worked on microservices",
        "Can I show you some code?",
        "Actually, let's talk about my team leadership instead",
        "I managed a team of 5 engineers",
    ],
}


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
        "active_user_request": state.get("active_user_request"),
        "next_message_preview": (state.get("next_message", "")[:100] + "...") 
            if state.get("next_message") and len(state.get("next_message", "")) > 100 
            else state.get("next_message"),
    }


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
            hashed_password="test_hash",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
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
            file_path="assets/CV_StephaneWamba.pdf",
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
    
    return resume


async def run_scenario(
    scenario_name: str,
    conversation: list,
    db: AsyncSession,
    user_id: int,
    resume_id: int
) -> dict:
    """Run a single test scenario."""
    print(f"\n{'=' * 80}")
    print(f"SCENARIO: {scenario_name.upper()}")
    print(f"{'=' * 80}\n")
    
    # Create interview for this scenario
    interview = Interview(
        user_id=user_id,
        resume_id=resume_id,
        title=f"Test - {scenario_name}",
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
    
    orchestrator = InterviewOrchestrator()
    checkpoint_service = CheckpointService()
    state = interview_to_state(interview)
    
    scenario_results = {
        "scenario_name": scenario_name,
        "interview_id": interview.id,
        "turns": [],
    }
    
    for turn_num, user_input in enumerate(conversation, start=1):
        print(f"\n--- Turn {turn_num} ---")
        
        turn_result = {
            "turn_number": turn_num,
            "user_input": user_input,
        }
        
        if user_input:
            print(f"[USER] {user_input[:150]}{'...' if len(user_input) > 150 else ''}")
        else:
            print(f"[USER] (no input - initial greeting)")
        
        # Restore state from checkpoint
        restored_state = await checkpoint_service.restore(interview.id, db)
        if restored_state:
            state = restored_state
        
        # Execute orchestrator step
        try:
            state = await orchestrator.execute_step(
                state,
                user_response=user_input if user_input else None
            )
            turn_result["execution_success"] = True
        except Exception as e:
            print(f"[ERROR] Execution failed: {e}")
            turn_result["execution_success"] = False
            turn_result["execution_error"] = str(e)
            continue
        
        # Extract state summary
        state_summary = extract_state_summary(state)
        turn_result["state"] = state_summary
        
        # Show agent response
        agent_response = state.get("next_message", "")
        if agent_response:
            print(f"[AGENT] {agent_response[:200]}{'...' if len(agent_response) > 200 else ''}")
            turn_result["agent_response"] = agent_response
        else:
            print(f"[AGENT] (no response)")
            turn_result["agent_response"] = None
        
        # Show key state info
        print(f"[STATE] Turn: {state_summary['turn_count']}, Node: {state_summary['last_node']}, "
              f"Action: {state_summary['_next_action']}, Phase: {state_summary['phase']}")
        
        if state_summary.get("active_user_request"):
            print(f"[INTENT] Detected: {state_summary['active_user_request']}")
            turn_result["detected_intent"] = state_summary["active_user_request"]
        
        # Update interview and checkpoint
        state_to_interview(state, interview)
        await db.commit()
        
        try:
            checkpoint_id = await checkpoint_service.checkpoint(state, db)
            turn_result["checkpoint_id"] = checkpoint_id
        except Exception as e:
            turn_result["checkpoint_error"] = str(e)
        
        scenario_results["turns"].append(turn_result)
    
    return scenario_results


async def run_all_tests():
    """Run all test scenarios."""
    print("=" * 80)
    print("COMPREHENSIVE AGENT BEHAVIOR TEST")
    print("=" * 80)
    
    db = AsyncSessionLocal()
    
    try:
        # Setup
        print("\n[SETUP] Creating test data...")
        user = await create_test_user(db)
        resume = await create_test_resume(db, user.id)
        print(f"[OK] User: {user.id}, Resume: {resume.id}\n")
        
        all_results = {
            "test_started_at": datetime.utcnow().isoformat(),
            "scenarios": [],
        }
        
        # Run each scenario
        for scenario_name, conversation in TEST_SCENARIOS.items():
            try:
                results = await run_scenario(
                    scenario_name,
                    conversation,
                    db,
                    user.id,
                    resume.id
                )
                all_results["scenarios"].append(results)
            except Exception as e:
                print(f"[ERROR] Scenario {scenario_name} failed: {e}")
                all_results["scenarios"].append({
                    "scenario_name": scenario_name,
                    "error": str(e),
                })
        
        # Save results
        all_results["test_completed_at"] = datetime.utcnow().isoformat()
        
        output_dir = Path("test_results")
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON
        json_file = output_dir / f"comprehensive_test_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\n[SAVE] JSON results: {json_file}")
        
        # Save human-readable summary
        txt_file = output_dir / f"comprehensive_test_{timestamp}.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("COMPREHENSIVE AGENT BEHAVIOR TEST RESULTS\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Test Date: {all_results['test_started_at']}\n")
            f.write(f"Total Scenarios: {len(all_results['scenarios'])}\n\n")
            
            for scenario in all_results["scenarios"]:
                if "error" in scenario:
                    f.write(f"\n{'=' * 80}\n")
                    f.write(f"SCENARIO: {scenario['scenario_name']} - ERROR\n")
                    f.write(f"{'=' * 80}\n")
                    f.write(f"Error: {scenario['error']}\n")
                    continue
                
                f.write(f"\n{'=' * 80}\n")
                f.write(f"SCENARIO: {scenario['scenario_name'].upper()}\n")
                f.write(f"{'=' * 80}\n\n")
                
                for turn in scenario.get("turns", []):
                    f.write(f"\n--- Turn {turn['turn_number']} ---\n")
                    f.write(f"User: {turn.get('user_input') or '(no input)'}\n")
                    f.write(f"Agent: {turn.get('agent_response') or '(no response)'}\n")
                    
                    state = turn.get("state", {})
                    f.write(f"\nState:\n")
                    f.write(f"  Turn Count: {state.get('turn_count', 0)}\n")
                    f.write(f"  Last Node: {state.get('last_node', '')}\n")
                    f.write(f"  Next Action: {state.get('_next_action', '')}\n")
                    f.write(f"  Phase: {state.get('phase', '')}\n")
                    f.write(f"  Conversation History: {state.get('conversation_history_length', 0)} messages\n")
                    f.write(f"  Questions Asked: {state.get('questions_asked_count', 0)}\n")
                    
                    if turn.get("detected_intent"):
                        f.write(f"  Detected Intent: {turn['detected_intent']}\n")
                    
                    f.write("\n")
                
                # Scenario summary
                f.write(f"\nScenario Summary:\n")
                f.write(f"  Total Turns: {len(scenario.get('turns', []))}\n")
                f.write(f"  Final Turn Count: {scenario.get('turns', [{}])[-1].get('state', {}).get('turn_count', 0)}\n")
                f.write(f"  Final Phase: {scenario.get('turns', [{}])[-1].get('state', {}).get('phase', '')}\n")
                f.write(f"  Total Questions: {scenario.get('turns', [{}])[-1].get('state', {}).get('questions_asked_count', 0)}\n")
        
        print(f"[SAVE] Text summary: {txt_file}")
        print("\n[DONE] All tests complete!")
        
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run_all_tests())


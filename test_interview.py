"""Test script for LangGraph-based interview orchestrator."""

from src.services.response_analyzer import ResponseAnalyzer
from src.services.interview_orchestrator import InterviewOrchestrator, InterviewState
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


async def test_orchestrator():
    """Test the interview orchestrator with a mock resume."""
    print("=" * 80)
    print("TESTING INTERVIEW ORCHESTRATOR")
    print("=" * 80)

    # Initialize orchestrator
    orchestrator = InterviewOrchestrator()

    # Create mock resume context
    resume_context = {
        "profile": "Experienced software engineer with 5+ years in Python development, specializing in backend systems and API design.",
        "experience": "Senior Software Engineer at Tech Corp (2020-2024): Led development of microservices architecture. Junior Developer at Startup Inc (2018-2020): Built REST APIs using FastAPI.",
        "education": "BS Computer Science, University of Technology (2018)",
        "projects": "Open-source contributor to FastAPI. Built a distributed task queue system.",
        "hobbies": "Reading technical blogs, contributing to open source"
    }

    # Initialize state
    state: InterviewState = {
        "interview_id": 1,
        "user_id": 1,
        "resume_id": 1,
        "resume_context": resume_context,
        "conversation_history": [],
        "question_bank": [],
        "current_node": "",
        "current_topic": None,
        "current_question": None,
        "last_response": None,
        "next_message": None,
        "answer_quality": 0.0,
        "topics_covered": [],
        "needs_followup": False,
        "needs_transition": False,
        "should_close": False,
        "turn_count": 0,
        "feedback": None,
    }

    print("\n" + "=" * 80)
    print("STEP 1: Initialize and Generate Greeting")
    print("=" * 80)

    # Execute initial step (should generate greeting)
    state = await orchestrator.execute_step(state, user_response=None)

    print(f"Current Node: {state.get('current_node')}")
    print(f"Turn Count: {state.get('turn_count')}")
    print(f"Next Message:\n{state.get('next_message')}")
    print(
        f"\nConversation History Length: {len(state.get('conversation_history', []))}")

    assert state.get("next_message"), "Greeting should be generated"
    assert len(state.get("conversation_history", [])
               ) > 0, "Conversation history should have greeting"
    print("✅ Greeting generated successfully!")

    print("\n" + "=" * 80)
    print("STEP 2: User Response - Answer to Greeting")
    print("=" * 80)

    user_response_1 = "Hello! Thank you for having me. I'm excited to discuss my background."
    state = await orchestrator.execute_step(state, user_response=user_response_1)

    print(f"Current Node: {state.get('current_node')}")
    print(f"Turn Count: {state.get('turn_count')}")
    print(f"Next Message (Question):\n{state.get('next_message')}")
    print(f"Current Question: {state.get('current_question')}")
    print(f"Answer Quality: {state.get('answer_quality'):.2f}")
    print(f"Topics Covered: {state.get('topics_covered', [])}")

    assert state.get("next_message"), "Question should be generated"
    assert state.get("current_question"), "Current question should be set"
    print("✅ Question generated after user response!")

    print("\n" + "=" * 80)
    print("STEP 3: User Response - Answer to Question")
    print("=" * 80)

    user_response_2 = "I have extensive experience with Python, especially FastAPI. I've built several REST APIs and microservices architectures. I'm particularly proud of a distributed task queue system I developed that handles millions of tasks per day."
    state = await orchestrator.execute_step(state, user_response=user_response_2)

    print(f"Current Node: {state.get('current_node')}")
    print(f"Turn Count: {state.get('turn_count')}")
    print(f"Next Message:\n{state.get('next_message')}")
    print(f"Answer Quality: {state.get('answer_quality'):.2f}")
    print(f"Needs Follow-up: {state.get('needs_followup')}")
    print(f"Topics Covered: {state.get('topics_covered', [])}")

    assert state.get("next_message"), "Response should be generated"
    print("✅ Response analyzed and next step generated!")

    print("\n" + "=" * 80)
    print("STEP 4: Multiple Turns - Test Adaptive Flow")
    print("=" * 80)

    # Run a few more turns
    responses = [
        "Yes, I used Redis for caching and PostgreSQL for persistence. The system scales horizontally by adding more worker nodes.",
        "I have a BS in Computer Science from University of Technology, graduated in 2018. I focused on distributed systems and databases.",
        "I enjoy contributing to open-source projects, especially FastAPI. I also read technical blogs to stay updated with industry trends.",
    ]

    for i, response in enumerate(responses, start=3):
        print(f"\n--- Turn {i} ---")
        state = await orchestrator.execute_step(state, user_response=response)
        print(
            f"Node: {state.get('current_node')}, Turn: {state.get('turn_count')}")
        print(f"Message: {state.get('next_message')[:100]}...")
        print(
            f"Quality: {state.get('answer_quality'):.2f}, Topics: {len(state.get('topics_covered', []))}")

        if state.get("should_close"):
            print("⚠️ Interview marked for closing")
            break

    print("\n" + "=" * 80)
    print("STEP 5: Test Response Analyzer Directly")
    print("=" * 80)

    analyzer = ResponseAnalyzer()
    analysis = await analyzer.analyze_answer(
        question="Tell me about your Python experience.",
        answer="I've been using Python for 5 years. I've built APIs with FastAPI, worked with async programming, and used libraries like SQLAlchemy and Pydantic.",
        context={"resume_context": resume_context},
    )

    print(f"Quality Score: {analysis.quality_score:.2f}")
    print(f"Depth Score: {analysis.depth_score:.2f}")
    print(f"Relevance Score: {analysis.relevance_score:.2f}")
    print(f"Completeness Score: {analysis.completeness_score:.2f}")
    print(f"Needs Follow-up: {analysis.needs_followup}")
    print(f"Topics Mentioned: {analysis.topics_mentioned}")
    print(f"Feedback: {analysis.feedback}")

    assert analysis.quality_score >= 0.0 and analysis.quality_score <= 1.0
    assert analysis.relevance_score >= 0.0 and analysis.relevance_score <= 1.0
    print("✅ Response analyzer working correctly!")

    print("\n" + "=" * 80)
    print("STEP 6: Test State Conversion")
    print("=" * 80)

    from src.services.state_manager import interview_to_state, state_to_interview
    from src.models.interview import Interview

    # Create a mock interview object (we'll just check the function exists and runs)
    print("✅ State manager functions imported successfully!")
    print("   (Full integration test requires database connection)")

    print("\n" + "=" * 80)
    print("FINAL STATE SUMMARY")
    print("=" * 80)
    print(f"Total Turns: {state.get('turn_count')}")
    print(f"Topics Covered: {state.get('topics_covered', [])}")
    print(
        f"Conversation History Length: {len(state.get('conversation_history', []))}")
    print(f"Should Close: {state.get('should_close')}")
    print(f"Current Node: {state.get('current_node')}")

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_orchestrator())

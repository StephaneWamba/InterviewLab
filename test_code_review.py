"""Test code review integration with interview orchestrator."""

import asyncio
from src.services.code_analyzer import CodeAnalyzer
from src.services.interview_orchestrator import InterviewOrchestrator, InterviewState
from src.services.sandbox_service import SandboxService, Language


async def test_code_analyzer():
    """Test code analyzer service."""
    print("=" * 60)
    print("Test 1: Code Analyzer Service")
    print("=" * 60)

    analyzer = CodeAnalyzer()

    # Test with good code
    good_code = """
def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

print(fibonacci(10))
"""

    print("\nAnalyzing good code...")
    quality = await analyzer.analyze_code(
        code=good_code,
        language="python",
        execution_result={"success": True, "stdout": "55\n", "stderr": "", "exit_code": 0},
    )

    print(f"✅ Quality Score: {quality.quality_score:.2f}/1.0")
    print(f"   Correctness: {quality.correctness_score:.2f}")
    print(f"   Efficiency: {quality.efficiency_score:.2f}")
    print(f"   Readability: {quality.readability_score:.2f}")
    print(f"   Best Practices: {quality.best_practices_score:.2f}")
    print(f"   Strengths: {', '.join(quality.strengths[:3]) if quality.strengths else 'None'}")
    print(f"   Weaknesses: {', '.join(quality.weaknesses[:3]) if quality.weaknesses else 'None'}")

    # Test feedback message generation
    print("\nGenerating feedback message...")
    feedback = await analyzer.generate_code_feedback_message(
        code_quality=quality,
        execution_result={"success": True, "stdout": "55\n", "stderr": "", "exit_code": 0},
    )
    print(f"✅ Feedback: {feedback}")


async def test_code_review_node():
    """Test code review node in interview orchestrator."""
    print("\n" + "=" * 60)
    print("Test 2: Code Review Node Integration")
    print("=" * 60)

    orchestrator = InterviewOrchestrator()

    # Create initial state
    state: InterviewState = {
        "interview_id": 1,
        "user_id": 1,
        "resume_id": 1,
        "resume_context": {
            "profile": "Software engineer with Python experience",
            "experience": "5 years of Python development",
        },
        "conversation_history": [
            {
                "role": "assistant",
                "content": "Can you write a function to calculate the factorial of a number?",
                "timestamp": "2024-01-01T00:00:00",
            }
        ],
        "question_bank": [],
        "current_node": "question",
        "current_topic": None,
        "current_question": "Can you write a function to calculate the factorial of a number?",
        "last_response": None,
        "next_message": None,
        "answer_quality": 0.0,
        "topics_covered": [],
        "turn_count": 1,
        "feedback": None,
        "code_submissions": [],
        "current_code": None,
        "code_execution_result": None,
        "code_quality": None,
    }

    # Test code submission
    test_code = """
def factorial(n):
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)

print(factorial(5))
"""

    print("\nSubmitting code for review...")
    print(f"Code:\n{test_code}")

    # Execute code review
    state = await orchestrator.execute_step(
        state=state,
        code=test_code,
        language="python",
    )

    print(f"\n✅ Code Review Complete")
    print(f"   Current Node: {state.get('current_node')}")
    print(f"   Next Message: {state.get('next_message', '')[:200]}...")
    
    if state.get("code_execution_result"):
        exec_result = state["code_execution_result"]
        print(f"   Execution Success: {exec_result.get('success', False)}")
        print(f"   Exit Code: {exec_result.get('exit_code', -1)}")
        if exec_result.get("stdout"):
            print(f"   Output: {exec_result.get('stdout', '')[:100]}")
    
    if state.get("code_quality"):
        quality = state["code_quality"]
        print(f"   Quality Score: {quality.get('quality_score', 0):.2f}/1.0")
        print(f"   Correctness: {quality.get('correctness_score', 0):.2f}")
        print(f"   Strengths: {len(quality.get('strengths', []))} identified")
        print(f"   Weaknesses: {len(quality.get('weaknesses', []))} identified")
    
    if state.get("code_submissions"):
        print(f"   Code Submissions: {len(state['code_submissions'])} stored")


async def test_full_flow():
    """Test full flow: sandbox execution + code analysis."""
    print("\n" + "=" * 60)
    print("Test 3: Full Flow (Sandbox + Analysis)")
    print("=" * 60)

    # Test with actual sandbox execution
    sandbox = SandboxService()
    analyzer = CodeAnalyzer()

    test_code = """
def reverse_string(s):
    return s[::-1]

result = reverse_string("hello")
print(f"Reversed: {result}")
"""

    print("\nExecuting code in sandbox...")
    print(f"Code:\n{test_code}")

    # Execute in sandbox
    execution_result = await sandbox.execute_code(
        code=test_code,
        language=Language.PYTHON,
    )

    print(f"\n✅ Sandbox Execution Complete")
    print(f"   Success: {execution_result.success}")
    print(f"   Exit Code: {execution_result.exit_code}")
    print(f"   Stdout: {execution_result.stdout}")
    if execution_result.stderr:
        print(f"   Stderr: {execution_result.stderr}")

    # Analyze code
    print("\nAnalyzing code quality...")
    quality = await analyzer.analyze_code(
        code=test_code,
        language="python",
        execution_result=execution_result.to_dict(),
    )

    print(f"\n✅ Code Analysis Complete")
    print(f"   Quality Score: {quality.quality_score:.2f}/1.0")
    print(f"   Feedback: {quality.feedback[:200]}...")

    # Generate feedback message
    feedback_msg = await analyzer.generate_code_feedback_message(
        code_quality=quality,
        execution_result=execution_result.to_dict(),
    )
    print(f"\n✅ Feedback Message Generated")
    print(f"   Message: {feedback_msg}")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Code Review Integration Tests")
    print("=" * 60)

    try:
        # Test 1: Code Analyzer
        await test_code_analyzer()

        # Test 2: Code Review Node
        await test_code_review_node()

        # Test 3: Full Flow
        await test_full_flow()

        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())





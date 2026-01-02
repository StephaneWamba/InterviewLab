"""Test sandbox service in Docker container."""

import asyncio
from src.services.sandbox_service import SandboxService, Language


async def test_sandbox():
    """Test sandbox service."""
    print("=" * 60)
    print("Testing Sandbox Service")
    print("=" * 60)

    service = SandboxService()
    print(f"✅ Service initialized")

    # Test health check
    is_healthy = await service.health_check()
    print(f"✅ Health check: {'Healthy' if is_healthy else 'Degraded (Docker not available)'}")

    # Test Python execution
    print("\n" + "-" * 60)
    print("Test 1: Python Code Execution")
    print("-" * 60)
    python_code = """
print("Hello from Python!")
result = 2 + 2
print(f"2 + 2 = {result}")
"""
    result = await service.execute_code(python_code, Language.PYTHON)
    print(f"✅ Execution successful: {result.success}")
    print(f"   Exit code: {result.exit_code}")
    print(f"   Execution time: {result.execution_time_ms:.2f}ms")
    print(f"   Stdout:\n{result.stdout}")
    if result.stderr:
        print(f"   Stderr: {result.stderr}")
    if result.error:
        print(f"   Error: {result.error}")

    # Test JavaScript execution
    print("\n" + "-" * 60)
    print("Test 2: JavaScript Code Execution")
    print("-" * 60)
    js_code = """
console.log("Hello from JavaScript!");
const result = 3 * 4;
console.log(`3 * 4 = ${result}`);
"""
    result = await service.execute_code(js_code, Language.JAVASCRIPT)
    print(f"✅ Execution successful: {result.success}")
    print(f"   Exit code: {result.exit_code}")
    print(f"   Execution time: {result.execution_time_ms:.2f}ms")
    print(f"   Stdout:\n{result.stdout}")
    if result.stderr:
        print(f"   Stderr: {result.stderr}")
    if result.error:
        print(f"   Error: {result.error}")

    # Test error handling
    print("\n" + "-" * 60)
    print("Test 3: Error Handling")
    print("-" * 60)
    error_code = """
print("This will cause an error")
raise ValueError("Test error")
"""
    result = await service.execute_code(error_code, Language.PYTHON)
    print(f"✅ Error handled correctly: {not result.success}")
    print(f"   Exit code: {result.exit_code}")
    print(f"   Stderr:\n{result.stderr}")

    print("\n" + "=" * 60)
    print("✅ All sandbox tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_sandbox())






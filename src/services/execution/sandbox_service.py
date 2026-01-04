"""Sandbox service for secure code execution in isolated containers."""

import asyncio
import logging
import tarfile
import io
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logging.warning(
        "Docker SDK not available. Sandbox service will be limited.")

from src.core.config import settings

logger = logging.getLogger(__name__)


class Language(str, Enum):
    """Supported programming languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"


class ExecutionResult:
    """Result of code execution."""

    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        execution_time_ms: float = 0.0,
        error: Optional[str] = None,
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.execution_time_ms = execution_time_ms
        self.error = error
        self.success = exit_code == 0 and error is None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time_ms": self.execution_time_ms,
            "success": self.success,
            "error": self.error,
        }


class SandboxService:
    """Service for executing code in isolated Docker containers."""

    def __init__(self):
        """Initialize sandbox service."""
        self.docker_client = None
        self.timeout_seconds = settings.SANDBOX_TIMEOUT_SECONDS
        self.memory_limit = settings.SANDBOX_MEMORY_LIMIT
        self.cpu_limit = settings.SANDBOX_CPU_LIMIT

        if DOCKER_AVAILABLE:
            try:
                self.docker_client = docker.from_env()
                self.docker_client.ping()
            except Exception as e:
                logger.warning(f"Failed to initialize Docker client: {e}")
                logger.warning(
                    "Sandbox service will use fallback execution (less secure)")
                self.docker_client = None
        else:
            logger.warning(
                "Docker SDK not installed. Install with: pip install docker")

    def _get_language_image(self, language: Language) -> str:
        """Get Docker image for language."""
        images = {
            Language.PYTHON: "python:3.11-slim",
            Language.JAVASCRIPT: "node:20-slim",
        }
        return images.get(language, "python:3.11-slim")

    def _prepare_code_files(
        self, code: str, language: Language, files: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Prepare code files for execution."""
        files_dict = files or {}

        if language == Language.PYTHON:
            main_file = "main.py"
        elif language == Language.JAVASCRIPT:
            main_file = "main.js"
        else:
            main_file = "main.py"

        if main_file not in files_dict:
            files_dict[main_file] = code

        return files_dict

    async def execute_code(
        self,
        code: str,
        language: Language = Language.PYTHON,
        files: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[int] = None,
        memory_limit: Optional[str] = None,
        cpu_limit: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute code in isolated container.

        Args:
            code: Code to execute
            language: Programming language
            files: Additional files (filename -> content)
            timeout_seconds: Execution timeout
            memory_limit: Memory limit (e.g., "128m")
            cpu_limit: CPU limit (e.g., "0.5")

        Returns:
            ExecutionResult with stdout, stderr, exit_code, etc.
        """
        timeout = timeout_seconds or self.timeout_seconds
        memory = memory_limit or self.memory_limit
        cpu = cpu_limit or self.cpu_limit

        if self.docker_client is None:
            logger.warning("Using fallback execution (Docker not available)")
            return await self._execute_fallback(code, language, timeout)

        code_files = self._prepare_code_files(code, language, files)
        image = self._get_language_image(language)

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._execute_in_container,
                code_files,
                language,
                image,
                timeout,
                memory,
                cpu,
            )
            return result
        except Exception as e:
            logger.error(f"Error executing code: {e}", exc_info=True)
            return ExecutionResult(
                error=f"Execution failed: {str(e)}", exit_code=1
            )

    def _execute_in_container(
        self,
        files: Dict[str, str],
        language: Language,
        image: str,
        timeout: int,
        memory: str,
        cpu: str,
    ) -> ExecutionResult:
        """Execute code in Docker container (synchronous)."""
        import time

        start_time = time.time()
        container = None

        try:
            if language == Language.PYTHON:
                command = ["python", "/workspace/main.py"]
            elif language == Language.JAVASCRIPT:
                command = ["node", "/workspace/main.js"]
            else:
                command = ["python", "/workspace/main.py"]

            container_name = f"sandbox-{uuid.uuid4().hex[:12]}"
            
            container = self.docker_client.containers.create(
                image,
                command=command,
                name=container_name,
                working_dir="/workspace",
                mem_limit=memory,
                cpu_quota=int(float(cpu) * 100000),
                cpu_period=100000,
                network_disabled=True,
                auto_remove=False,
            )

            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                for filename, content in files.items():
                    tarinfo = tarfile.TarInfo(name=filename)
                    content_bytes = content.encode('utf-8')
                    tarinfo.size = len(content_bytes)
                    tarinfo.mode = 0o644
                    tar.addfile(tarinfo, io.BytesIO(content_bytes))

            tar_stream.seek(0)
            container.put_archive("/workspace", tar_stream)

            container.start()

            # Wait for container with timeout
            try:
                container.wait(timeout=timeout)
            except Exception as e:
                # Container timed out or error
                container.kill()
                raise

            # Get logs
            logs = container.logs(stdout=True, stderr=True)
            stdout_logs = container.logs(stdout=True, stderr=False)
            stderr_logs = container.logs(stdout=False, stderr=True)

            # Decode logs
            stdout = stdout_logs.decode(
                "utf-8", errors="replace") if stdout_logs else ""
            stderr = stderr_logs.decode(
                "utf-8", errors="replace") if stderr_logs else ""

            # Get exit code
            container.reload()
            exit_code = container.attrs["State"]["ExitCode"] or 0

            execution_time = (time.time() - start_time) * \
                1000  # Convert to ms

            return ExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                error_msg = f"Execution timed out after {timeout} seconds"
            return ExecutionResult(
                error=error_msg,
                exit_code=1,
                execution_time_ms=execution_time,
            )
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    async def _execute_fallback(
        self, code: str, language: Language, timeout: int
    ) -> ExecutionResult:
        """Fallback execution when Docker is not available (development only)."""
        import time
        import subprocess

        start_time = time.time()

        try:
            if language == Language.PYTHON:
                process = await asyncio.create_subprocess_exec(
                    "python",
                    "-c",
                    code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            elif language == Language.JAVASCRIPT:
                process = await asyncio.create_subprocess_exec(
                    "node",
                    "-e",
                    code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                return ExecutionResult(
                    error=f"Unsupported language: {language}", exit_code=1
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult(
                    error=f"Execution timed out after {timeout} seconds",
                    exit_code=1,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            execution_time = (time.time() - start_time) * 1000

            return ExecutionResult(
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            return ExecutionResult(
                error=f"Execution failed: {str(e)}",
                exit_code=1,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    async def health_check(self) -> bool:
        """Check if sandbox service is healthy."""
        if self.docker_client is None:
            return False
        try:
            self.docker_client.ping()
            return True
        except Exception:
            return False

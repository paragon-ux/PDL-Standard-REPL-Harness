from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# Windows Win32 Job Object Constants and Structures
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_PRIORITY_CLASS = 0x00000020
NORMAL_PRIORITY_CLASS = 0x00000020
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
IDLE_PRIORITY_CLASS = 0x00000040
JobObjectExtendedLimitInformation = 9

_IS_WINDOWS = sys.platform == "win32" or os.name == "nt"

if _IS_WINDOWS:
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]


_NETWORK_BLOCK_PRELUDE = """
# Deterministic Sandbox Isolation Prelude
import socket as _socket
def _disabled_network(*args, **kwargs):
    raise PermissionError("Network access is strictly disabled inside ExecutionSandbox")
_socket.socket = _disabled_network
_socket.create_connection = _disabled_network
_socket.getaddrinfo = _disabled_network
"""


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of sandboxed script execution."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool = False
    oom_killed: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.oom_killed and self.error is None


class ExecutionSandbox:
    """OS-native deterministic execution sandbox (P1).

    Conformant to ADR-0013:
    - Zero-dependency local process isolation (Windows Job Objects on Windows,
      setrlimit on POSIX).
    - Ephemeral scratchpad filesystem containment.
    - Deterministic wall-clock timeout and memory ceilings.
    - Zero outbound network access.
    """

    DEFAULT_TIMEOUT_SECONDS: float = 5.0
    DEFAULT_MEMORY_LIMIT_BYTES: int = 256 * 1024 * 1024  # 256 MB

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
        allow_network: bool = False,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.memory_limit_bytes = int(memory_limit_bytes)
        self.allow_network = allow_network

    def _create_windows_job(self, memory_limit_bytes: int) -> int | None:
        """Create and configure a Windows Job Object with memory and process lifecycle limits."""
        if not _IS_WINDOWS:
            return None
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return None

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_JOB_MEMORY
            | JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | JOB_OBJECT_LIMIT_PRIORITY_CLASS
        )
        info.BasicLimitInformation.PriorityClass = BELOW_NORMAL_PRIORITY_CLASS
        info.JobMemoryLimit = memory_limit_bytes
        info.ProcessMemoryLimit = memory_limit_bytes

        success = kernel32.SetInformationJobObject(
            h_job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not success:
            kernel32.CloseHandle(h_job)
            return None
        return h_job

    def run_code(
        self,
        code: str,
        *,
        timeout: float | None = None,
        memory_limit: int | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Execute a Python snippet in an isolated ephemeral scratchpad with OS-native limits."""
        effective_timeout = timeout if timeout is not None else self.timeout_seconds
        effective_memory = memory_limit if memory_limit is not None else self.memory_limit_bytes

        with tempfile.TemporaryDirectory(prefix="pdl_sandbox_") as scratchpad:
            scratchpad_path = Path(scratchpad).resolve()
            entry_file = scratchpad_path / "_entry.py"

            content_parts: list[str] = []
            if not self.allow_network:
                content_parts.append(_NETWORK_BLOCK_PRELUDE)
            content_parts.append(code)
            entry_file.write_text("\n".join(content_parts), encoding="utf-8")

            return self._execute_process(
                [sys.executable, "-I", "-s", str(entry_file)],
                cwd=scratchpad_path,
                timeout=effective_timeout,
                memory_limit_bytes=effective_memory,
                env=env,
            )

    def run_script(
        self,
        script_path: str | Path,
        args: list[str] | None = None,
        *,
        timeout: float | None = None,
        memory_limit: int | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Execute an existing script within the sandboxed environment."""
        effective_timeout = timeout if timeout is not None else self.timeout_seconds
        effective_memory = memory_limit if memory_limit is not None else self.memory_limit_bytes
        resolved_script = Path(script_path).resolve()

        with tempfile.TemporaryDirectory(prefix="pdl_sandbox_") as scratchpad:
            scratchpad_path = Path(scratchpad).resolve()
            cmd = [sys.executable, "-I", "-s", str(resolved_script)]
            if args:
                cmd.extend(args)

            return self._execute_process(
                cmd,
                cwd=scratchpad_path,
                timeout=effective_timeout,
                memory_limit_bytes=effective_memory,
                env=env,
            )

    def _execute_process(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        timeout: float,
        memory_limit_bytes: int,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        base_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        if env:
            base_env.update(env)

        h_job = None
        kernel32 = None
        if _IS_WINDOWS:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            h_job = self._create_windows_job(memory_limit_bytes)

        preexec = None
        if not _IS_WINDOWS:
            def _preexec_posix():
                import resource
                os.setsid()
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
                except (ValueError, OSError):
                    pass
            preexec = _preexec_posix

        start_time = time.perf_counter()
        proc = None
        timed_out = False
        stdout_text = ""
        stderr_text = ""
        exit_code = -1

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=base_env,
                preexec_fn=preexec,
            )

            if _IS_WINDOWS and h_job and kernel32:
                # Assign process to Job Object immediately
                assign_ok = kernel32.AssignProcessToJobObject(h_job, proc._handle)
                if not assign_ok and proc.poll() is None:
                    # Process is still running but could not be assigned
                    err_code = ctypes.get_last_error()
                    kernel32.TerminateJobObject(h_job, 1)
                    proc.kill()
                    return SandboxResult(
                        stdout="",
                        stderr=f"Failed to assign process to JobObject (err={err_code})",
                        exit_code=-1,
                        duration_ms=(time.perf_counter() - start_time) * 1000.0,
                        error=f"job_assign_failed_{err_code}",
                    )

            raw_out, raw_err = proc.communicate(timeout=timeout)
            stdout_text = raw_out.decode("utf-8", errors="replace")
            stderr_text = raw_err.decode("utf-8", errors="replace")
            exit_code = proc.returncode

        except subprocess.TimeoutExpired:
            timed_out = True
            if _IS_WINDOWS and h_job and kernel32:
                kernel32.TerminateJobObject(h_job, 124)
            if proc is not None:
                try:
                    if not _IS_WINDOWS:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    else:
                        proc.kill()
                    raw_out, raw_err = proc.communicate()
                    stdout_text = raw_out.decode("utf-8", errors="replace")
                    stderr_text = raw_err.decode("utf-8", errors="replace")
                except Exception:
                    pass
            exit_code = 124

        except Exception as exc:
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            return SandboxResult(
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                duration_ms=(time.perf_counter() - start_time) * 1000.0,
                error=f"execution_exception: {exc}",
            )

        finally:
            if _IS_WINDOWS and h_job and kernel32:
                kernel32.CloseHandle(h_job)

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Memory limit exhaustion detection
        oom_killed = False
        if "MemoryError" in stderr_text:
            oom_killed = True
        elif exit_code in (-1073741545, 3221225751, -1073741801, 3221225495):  # Win32 STATUS_NO_MEMORY / STATUS_PAGEFILE_QUOTA
            oom_killed = True
        elif not _IS_WINDOWS and exit_code in (-9, 137) and not timed_out:
            oom_killed = True

        return SandboxResult(
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            oom_killed=oom_killed,
        )

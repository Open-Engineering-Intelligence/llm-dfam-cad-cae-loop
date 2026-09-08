"""Strict, path-contained evidence I/O and bounded owned subprocesses."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    # Also catches overflow from otherwise legal literals such as 1e999.
    json.dumps(value, allow_nan=False)
    return value


def write_json(path: Path, value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path, root: Path) -> dict:
    path, root = Path(path).resolve(), Path(root).resolve()
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}


def verify_ref(ref, root: Path) -> Path:
    if hasattr(ref, "model_dump"):
        ref = ref.model_dump()
    name = ref["path"]
    if (
        not name
        or "\\" in name
        or PureWindowsPath(name).drive
        or PurePosixPath(name).is_absolute()
        or ".." in PurePosixPath(name).parts
    ):
        raise ValueError("artifact path must remain relative to the run")
    path, root = (Path(root) / name).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError("artifact path escapes the run")
    if sha256(path) != ref["sha256"]:
        raise ValueError(f"artifact hash mismatch: {name}")
    return path


class _WindowsJob:
    """Keep descendants reachable even after their parent process exits."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("minimum_working_set", ctypes.c_size_t),
                ("maximum_working_set", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling_class", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io_counters", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t),
                ("peak_job_memory", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.get_last_error()
            kernel.CloseHandle(self.handle)
            raise ctypes.WinError(error)

    def assign(self, process):
        import ctypes

        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self):
        self.kernel.TerminateJobObject(self.handle, 1)

    def resume(self, process):
        """Resume the initial suspended thread only after job ownership is established."""
        import ctypes
        from ctypes import wintypes

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("usage", wintypes.DWORD),
                ("thread_id", wintypes.DWORD),
                ("owner_pid", wintypes.DWORD),
                ("base_priority", wintypes.LONG),
                ("delta_priority", wintypes.LONG),
                ("flags", wintypes.DWORD),
            ]

        kernel = self.kernel
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        snapshot = kernel.CreateToolhelp32Snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            present = kernel.Thread32First(snapshot, ctypes.byref(entry))
            while present:
                if entry.owner_pid == process.pid:
                    thread = kernel.OpenThread(0x2, False, entry.thread_id)
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if kernel.ResumeThread(thread) != 1:
                            raise RuntimeError(
                                "worker initial thread was not suspended exactly once"
                            )
                        return
                    finally:
                        kernel.CloseHandle(thread)
                present = kernel.Thread32Next(snapshot, ctypes.byref(entry))
            raise RuntimeError("worker initial thread was not found")
        finally:
            kernel.CloseHandle(snapshot)

    def close(self):
        self.terminate()
        self.kernel.CloseHandle(self.handle)


def run_process(args, cwd: Path, label: str, timeout: float, *, env=None, new_group=True):
    """Stream logs to disk, kill the owned process tree on timeout, never retry."""
    cwd = Path(cwd)
    options = {}
    if os.name == "nt":
        # https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | 0x4  # CREATE_SUSPENDED
    else:
        options["start_new_session"] = new_group
    with (
        (cwd / f"{label}.stdout.log").open("wb") as stdout,
        (cwd / f"{label}.stderr.log").open("wb") as stderr,
    ):
        process = subprocess.Popen(
            args, cwd=cwd, env=env, stdout=stdout, stderr=stderr, shell=False, **options
        )
        job = None
        try:
            if os.name == "nt":
                job = _WindowsJob()
                job.assign(process)
                job.resume(process)
            return process.wait(timeout=timeout)
        except BaseException as exc:
            if job is not None:
                job.terminate()
            if os.name == "nt" and process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            elif os.name != "nt" and new_group:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            process.wait(timeout=15)
            if isinstance(exc, subprocess.TimeoutExpired):
                raise TimeoutError(f"{label} timed out after {timeout} seconds") from exc
            raise
        finally:
            if job is not None:
                job.close()
            elif os.name != "nt" and new_group:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

"""Processes: start a server that outlives its starter, check a pid exactly, stop a process and its children.

Windows termination is forceful (taskkill /T /F): Windows has no portable polite stop for a console-less process.
POSIX stop sends SIGTERM to the process group that spawnDetached created.
"""
import os
import signal
import subprocess

from .env import IS_WINDOWS

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


def spawnDetached(cmd, logFile, belowNormal=True):
    """Start cmd with output to logFile, detached from this process: on Windows its own process group with no console
    (and below-normal priority unless belowNormal is False, so the desktop stays responsive); elsewhere its own session.
    Returns the Popen."""
    flags = 0
    if IS_WINDOWS:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        if belowNormal:
            flags |= BELOW_NORMAL_PRIORITY_CLASS
    with open(logFile, "w", encoding="utf-8") as lf:
        return subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags,
                                start_new_session=not IS_WINDOWS)


HIGH_PRIORITY_CLASS = 0x00000080


def launch(cmd, timeout=None, cpu=None, highPriority=True):
    """Run cmd to completion with its output discarded, for a measurement: at raised priority (HIGH_PRIORITY_CLASS on Windows;
    POSIX priority is left alone) and, when `cpu` is given, pinned to that one logical CPU, so the scheduler cannot move it
    mid-run. A process still running after `timeout` seconds is killed and subprocess.TimeoutExpired is raised; a non-zero exit
    raises subprocess.CalledProcessError."""
    quiet = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if IS_WINDOWS:
        p = subprocess.Popen(cmd, creationflags=HIGH_PRIORITY_CLASS if highPriority else 0, **quiet)
        if cpu is not None:
            import ctypes
            ctypes.windll.kernel32.SetProcessAffinityMask(int(p._handle), ctypes.c_size_t(1 << cpu))
        try:
            code = p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            raise
    else:
        def pin():
            if cpu is not None and hasattr(os, "sched_setaffinity"):
                os.sched_setaffinity(0, {cpu})
        code = subprocess.run(cmd, preexec_fn=pin, timeout=timeout, **quiet).returncode
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd)


def alive(pid):
    """Whether a process with exactly this pid exists (no subprocess, no text matching)."""
    if IS_WINDOWS:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # access denied: exists; invalid parameter: does not
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.GetExitCodeProcess.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        try:
            code = wintypes.DWORD()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def terminate(pid):
    """Stop a process and its children: taskkill /T /F on Windows; SIGTERM to its process group elsewhere, falling back to
    the process alone when it leads no group."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        os.kill(pid, signal.SIGTERM)


def cpuSeconds(pid):
    """User plus kernel CPU seconds a process has used, or None when it cannot be read."""
    try:
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.restype = wintypes.HANDLE
            k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
            h = k.OpenProcess(0x1000, False, pid)
            if not h:
                return None
            try:
                t = [wintypes.FILETIME() for _ in range(4)]
                if not k.GetProcessTimes(h, *[ctypes.byref(x) for x in t]):
                    return None
                ticks = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime  # noqa: E731  (100 ns units)
                return (ticks(t[2]) + ticks(t[3])) / 1e7
            finally:
                k.CloseHandle(h)
        with open("/proc/%d/stat" % pid) as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None

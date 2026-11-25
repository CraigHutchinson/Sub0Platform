"""Shared and exclusive machine leases on the native Platform file lock."""
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4
from weakref import finalize

from . import dirs, fs, proc
from ._file_lock import tryLock


@dataclass(frozen=True)
class LeaseOwner:
    """A holder's diagnostic record. Resources are descriptive strings."""

    pid: int
    time: float
    what: str
    tool: str
    mode: str = "exclusive"
    cores: str = ""
    memory_bandwidth: str = ""
    gpu: str = ""
    power_state: str = ""

    def describe(self):
        """Name this holder and the action that frees its lease."""
        start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.time))
        resources = ", ".join(f"{label}: {value}" for label, value in (
            ("cores", self.cores), ("memory bandwidth", self.memory_bandwidth),
            ("GPU", self.gpu), ("power state", self.power_state)) if value)
        detail = f", {resources}" if resources else ""
        message = (f"held by {self.tool or 'another tool'} ({self.what}), pid {self.pid}, "
                f"since {start}, {self.mode}{detail}.")
        clean = "".join(" " if ord(char) < 32 else char for char in message)
        return clean + " Wait for it to finish or stop it to release the lease."


def defaultLockFile():
    """The per-user machine lock path, without creating any files."""
    return Path(dirs.state("sub0")) / "machine.lock"


def _sidecar(path, suffix):
    return path.with_name(path.name + suffix)


def _readRecord(path):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        pid = record["pid"]
        start = record["time"]
        if type(pid) is not int or not 0 < pid < 2**31:
            return None
        if type(start) not in (int, float) or not 0 <= start < 32535216000 or not math.isfinite(start):
            return None
        fields = {key: record.get(key, fallback) for key, fallback in (
            ("what", ""), ("tool", ""), ("mode", "exclusive"), ("cores", ""),
            ("memory_bandwidth", ""), ("gpu", ""), ("power_state", ""))}
        if any(not isinstance(value, str) for value in fields.values()) or fields["mode"] not in ("shared", "exclusive"):
            return None
        return LeaseOwner(pid, start, **fields)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return None


def readOwners(lockFile=None):
    """Return live owner records in stable order. These are diagnostic snapshots."""
    path = Path(lockFile) if lockFile is not None else defaultLockFile()
    shared = _sidecar(path, ".owners")
    records = [_sidecar(path, ".owner"), *sorted(shared.glob("*.json"))]
    found = []
    for record in records:
        holder = _readRecord(record)
        if holder is not None and proc.alive(holder.pid):
            found.append(holder)
    if found:
        return found
    waiting = _readRecord(_sidecar(path, ".writer.owner"))
    return [waiting] if waiting is not None and proc.alive(waiting.pid) else []


def _writeRecord(path, owner):
    if not fs.atomicWrite(path, json.dumps(asdict(owner), ensure_ascii=False) + "\n", attempts=1, wait=0):
        raise OSError(f"cannot publish lease owner record at {path}")


def _removeRecord(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass  # The OS lock remains authoritative when a reader or crash leaves a sidecar behind.


def _releaseRecord(release, record):
    try:
        _removeRecord(record)
    finally:
        release()


class MachineLease:
    """A held native lock. Use as a context manager or call close()."""

    def __init__(self, release, record):
        self._finalize = finalize(self, _releaseRecord, release, record)

    def close(self):
        """Release the lock and remove this holder's record. Repeated calls are harmless."""
        self._finalize()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def acquire(mode, tool, what, *, lockFile=None, timeout=0, onWait=None,
            cores="", memory_bandwidth="", gpu="", power_state=""):
    """Take a lease or return None after timeout seconds. Errors opening or publishing it propagate.

    onWait receives the current owner records before each retry. Zero timeout tries once.
    """
    if mode not in ("shared", "exclusive"):
        raise ValueError("lease mode must be shared or exclusive")
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("lease timeout must be finite and nonnegative")

    path = Path(lockFile) if lockFile is not None else defaultLockFile()
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = mode == "exclusive"
    intent = _sidecar(path, ".writer")
    intent_record = _sidecar(path, ".writer.owner")
    deadline = time.monotonic() + timeout
    release_intent = None
    published_intent = False
    try:
        while True:
            if release_intent is None:
                release_intent = tryLock(intent, writer)
            if release_intent is not None:
                release = tryLock(path, writer)
                if release is not None:
                    try:
                        owner = LeaseOwner(os.getpid(), time.time(), what, tool, mode,
                                           cores, memory_bandwidth, gpu, power_state)
                        if writer:
                            record = _sidecar(path, ".owner")
                        else:
                            directory = _sidecar(path, ".owners")
                            directory.mkdir(exist_ok=True)
                            record = directory / (f"{owner.pid}-{uuid4().hex}.json")
                        _writeRecord(record, owner)
                        return MachineLease(release, record)
                    except BaseException:
                        release()
                        raise
                if not writer:
                    release_intent()
                    release_intent = None

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            if writer and release_intent is not None and not published_intent:
                owner = LeaseOwner(os.getpid(), time.time(), what, tool, mode,
                                   cores, memory_bandwidth, gpu, power_state)
                _writeRecord(intent_record, owner)
                published_intent = True
            if onWait is not None:
                onWait(readOwners(path))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(0.1, remaining))
            if time.monotonic() >= deadline:
                return None
    finally:
        if release_intent is not None:
            if published_intent:
                _removeRecord(intent_record)
            release_intent()

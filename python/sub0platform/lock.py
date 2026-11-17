"""An exclusive lock file across processes, for jobs that must not overlap (one GPU bench at a time, one writer).

The file is created exclusively and holds the owner's pid. A lock whose owner no longer exists (a crash) is set aside as
<path>.stale-<pid> and taken; a live owner is waited for, never stolen on age alone (a legitimate job can run for hours).
A pid reused by an unrelated process reads as alive: the safe side.
"""
import os
import time

from . import proc


def owner(path):
    """The pid text in the lock when a live process holds it, else None."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip() or "unknown"
    except OSError:
        return None
    return None if text.isdigit() and not proc.alive(int(text)) else text


class ExclusiveLock:
    """with ExclusiveLock(path, onWait=callback): ... ; onWait(ownerText) is called each time it has to wait."""

    def __init__(self, path, poll=2.0, onWait=None, timeout=None):
        self.path, self.poll, self.onWait, self.timeout = path, poll, onWait, timeout

    def __enter__(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        start = time.monotonic()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    with open(self.path, encoding="utf-8") as f:
                        text = f.read().strip()
                except OSError:
                    continue  # released between our attempts
                if text.isdigit() and not proc.alive(int(text)):
                    try:
                        os.replace(self.path, self.path + ".stale-" + text)
                    except OSError:
                        pass
                    continue
                if self.timeout is not None and time.monotonic() - start > self.timeout:
                    raise TimeoutError("lock %s held by %s" % (self.path, text))
                if self.onWait:
                    self.onWait(text)
                time.sleep(self.poll)

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass

"""Files: an atomic replace that survives readers on Windows.

On Windows os.replace fails with PermissionError while another process has the target open (a poller, an indexer, an
antivirus scan). atomicWrite retries briefly with growing waits and then gives up, leaving the old file intact.
"""
import os
import time


def atomicWrite(path, data, attempts=10, wait=0.05):
    """Write data (str or bytes) to path atomically: a temporary file beside it, then a replace. Returns True when the
    new content is in place, False when every attempt found the target held open (the old file stays)."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    mode, kw = ("wb", {}) if isinstance(data, bytes) else ("w", {"encoding": "utf-8", "newline": "\n"})
    with open(tmp, mode, **kw) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(attempts):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(wait * (attempt + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False

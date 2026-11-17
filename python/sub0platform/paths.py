"""Windows drive paths and WSL's mounts of them (/mnt/<drive>/...), both ways.

The rules are pinned by conformance/paths.json, which the C++ library's tests read too.
"""
import re

from . import env

_DRIVE = re.compile(r"^([A-Za-z]):[\\/]")
_MOUNT = re.compile(r"^/mnt/([a-z])(?:/|$)")


def toPosix(p):
    """D:/x or D:\\x -> /mnt/d/x; anything else unchanged (POSIX and relative paths, UNC paths)."""
    m = _DRIVE.match(p or "")
    if not m:
        return p
    return "/mnt/" + m.group(1).lower() + "/" + p[3:].replace("\\", "/")


def toWindows(p):
    """/mnt/d/x -> D:/x (forward slashes, which Windows accepts); anything else unchanged."""
    m = _MOUNT.match(p or "")
    if not m:
        return p
    rest = p[len("/mnt/x"):].lstrip("/")
    return m.group(1).upper() + ":/" + rest


def local(p, isWindows=None):
    """A path as this platform reads it: a Windows drive path off Windows becomes its WSL mount; on Windows a WSL mount
    becomes its drive path; anything else is unchanged."""
    win = env.IS_WINDOWS if isWindows is None else isWindows
    return toWindows(p) if win else toPosix(p)


def isDrivePath(p):
    return bool(_DRIVE.match(p or ""))

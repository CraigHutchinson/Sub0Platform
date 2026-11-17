"""Which platform this is."""
import os

IS_WINDOWS = os.name == "nt"


def _isWsl():
    if IS_WINDOWS:
        return False
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


IS_WSL = _isWsl()
# Platform names, most general first (for per-platform config layers such as app.local.<name>.json).
NAMES = ["windows"] if IS_WINDOWS else (["linux", "wsl"] if IS_WSL else ["linux"])
EXE = ".exe" if IS_WINDOWS else ""

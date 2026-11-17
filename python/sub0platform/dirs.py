"""Per-user directories, following each platform's convention.

  config  settings a user edits or keeps (roaming on Windows): %APPDATA%, $XDG_CONFIG_HOME or ~/.config
  cache   data that can be rebuilt (local): %LOCALAPPDATA%, $XDG_CACHE_HOME or ~/.cache
  state   logs, histories, locks (local): %LOCALAPPDATA%, $XDG_STATE_HOME or ~/.local/state

Each takes the application's name and returns <base>/<app>; nothing is created.
"""
import os

from . import env


def _base(winVar, xdgVar, fallback, environ=None, isWindows=None):
    e = os.environ if environ is None else environ
    win = env.IS_WINDOWS if isWindows is None else isWindows
    if win:
        return e.get(winVar) or os.path.join(os.path.expanduser("~"), "AppData", "Roaming" if winVar == "APPDATA" else "Local")
    return e.get(xdgVar) or os.path.join(os.path.expanduser("~"), fallback)


def config(app, environ=None, isWindows=None):
    return os.path.join(_base("APPDATA", "XDG_CONFIG_HOME", ".config", environ, isWindows), app)


def cache(app, environ=None, isWindows=None):
    return os.path.join(_base("LOCALAPPDATA", "XDG_CACHE_HOME", ".cache", environ, isWindows), app)


def state(app, environ=None, isWindows=None):
    return os.path.join(_base("LOCALAPPDATA", "XDG_STATE_HOME", os.path.join(".local", "state"), environ, isWindows), app)

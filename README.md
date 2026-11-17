# Sub0Platform

The operating-system layer shared by the Sub0 projects, so each one stops solving the same Windows, Linux and WSL
problems on its own: paths and WSL mounts, per-user directories, processes, atomic files and locks, and later host
facts, CPU topology, sockets, local IPC and memory mapping.

* **Python package** `sub0platform` (`python/`): standard library only, Python 3.10+. Seeded from Sub0LlmEngine's
  platform module (2026-11-17).
* **C++ library** (`cpp/`): Sub0Squad's platform layer, to be moved here (see `cpp/README.md`).
* **Conformance vectors** (`conformance/*.json`): behaviour both languages must match, read by both test suites.

| Python module | What it does |
|---|---|
| `env` | `IS_WINDOWS`, `IS_WSL`, platform `NAMES` (for per-platform config layers), `EXE` |
| `paths` | `toPosix("D:/x")` = `/mnt/d/x`, `toWindows("/mnt/d/x")` = `D:/x`, `local(p)` for this platform |
| `dirs` | `config(app)` (roaming on Windows: `%APPDATA%`; `$XDG_CONFIG_HOME`), `cache(app)` and `state(app)` (local: `%LOCALAPPDATA%`; XDG) |
| `proc` | `spawnDetached` (outlives its starter; no console, below-normal priority on Windows), `alive(pid)` (exact), `terminate(pid)` (the process tree), `cpuSeconds(pid)` |
| `fs` | `atomicWrite(path, data)`: temporary file, fsync, replace, retried while a Windows reader holds the target |
| `lock` | `ExclusiveLock(path)`: one holder across processes; a crashed owner's lock is set aside, a live owner waited for |

```sh
python -m unittest discover -s python/tests      # Windows and Linux (CI runs both, Python 3.10 and 3.12)
pip install -e .                                  # or add python/ to sys.path
```

The plan, what moves from which repository and the decisions still open: Sub0Squad
`docs/sessions/platform-unification.md`.

## Licence

MIT, see [LICENSE](LICENSE).

# Sub0Platform

The operating-system layer shared by the Sub0 projects, so each one stops solving the same Windows, Linux and WSL
problems on its own: paths and WSL mounts, per-user directories, processes, atomic files and locks, and later host
facts, CPU topology, sockets, local IPC and memory mapping.

* **Python package** `sub0platform` (`python/`): standard library only, Python 3.10+. Seeded from Sub0LlmEngine's
  platform module (2026-11-17).
* **C++ library** (`cpp/`): Sub0Squad's platform layer, to be moved here (see `cpp/README.md`).
* **Conformance vectors** ([`conformance/`](conformance/)): behaviour both languages must match, read by both test suites.

| Python module | What it does |
|---|---|
| `env` | `IS_WINDOWS`, `IS_WSL`, platform `NAMES` (for per-platform config layers), `EXE` |
| `paths` | `toPosix("D:/x")` = `/mnt/d/x`, `toWindows("/mnt/d/x")` = `D:/x`, `local(p)` for this platform |
| `dirs` | `config(app)` (roaming on Windows: `%APPDATA%`; `$XDG_CONFIG_HOME`), `cache(app)` and `state(app)` (local: `%LOCALAPPDATA%`; XDG) |
| `proc` | `spawnDetached` (outlives its starter; no console, below-normal priority on Windows), `launch(cmd, timeout, cpu)` (a pinned, raised-priority measurement run that is killed at the timeout), `alive(pid)` (exact), `terminate(pid)` (the process tree), `cpuSeconds(pid)` |
| `topology.readTopology()` | Physical-core sibling groups visible to the current affinity mask. Includes OS performance classes where available. Returns `None` when topology is unavailable. |
| `fs` | `atomicWrite(path, data)`: temporary file, fsync, replace, retried while a Windows reader holds the target |
| `lock` | `ExclusiveLock(path)`: one holder across processes; a crashed owner's lock is set aside, a live owner waited for |

```sh
python -m unittest discover -s python/tests      # Windows and Linux (CI runs both, Python 3.10 and 3.12)
pip install -e .                                  # or add python/ to sys.path
```

The plan, what moves from which repository and the decisions still open: Sub0Squad
`docs/sessions/platform-unification.md`.

## Machine leases

[ADR 0005](https://github.com/CraigHutchinson/.github/blob/main/docs/decisions/0005-machine-scheduling.md) defines the
rollout. Use Python `lease.acquire` or C++ `MachineLease::acquire`. A lease is shared or exclusive. A caller
supplies its wait budget and can receive owner snapshots while waiting. The default is one attempt. The
operating system releases the lock on process exit. Use a separate lock path for tests.

Both implementations lock `<state directory>/sub0/machine.lock`. They use `flock` on POSIX and lock the first
byte with `LockFileEx` on Windows. A companion `.writer` lock allows a waiting exclusive caller to prevent
new shared holders from entering while active readers finish. Keep lock files in place so all holders use
the same file identity.

The exclusive holder writes `machine.lock.owner`. Each shared holder publishes its own JSON file in
`machine.lock.owners/`. A waiting exclusive caller can publish `machine.lock.writer.owner`. These records
carry `pid`, `time` (UTC seconds since the Unix epoch), `what`, `tool`, `mode` and optional reporting strings
`cores`, `memory_bandwidth`, `gpu` and `power_state`. A legacy record without `mode` is exclusive. Owner
records are diagnostic snapshots and can lag the native lock during acquisition, release or process exit.
Both languages read the same [owner examples](conformance/lease_owner.jsonl).

## Licence

MIT, see [LICENSE](LICENSE).

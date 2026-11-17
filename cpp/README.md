# Sub0Platform C++ library (not yet moved)

The C++ library will be Sub0Squad's layer 0 (`include/sub0squad/platform_*.hpp` with its `_posix` and `_win32`
backends, tests and layering check), lifted here once the platform work in progress in Sub0Squad has landed, then
consumed by Sub0Squad through CPM. Module names match the Python package: `process`, `proc`, `host`, `topology`, `file`,
`mapping`, `net`, `ipc`, `wait`, `dirs`, plus Sub0Log's Windows argument quoting with its round-trip tests.

Its tests must read the shared vectors in `../conformance/` (today: `paths.json`) so both languages behave the same.
Open decisions (C++ standard floor, Windows toolchains, whether Sub0Log depends on it) are in Sub0Squad
`docs/sessions/platform-unification.md`.

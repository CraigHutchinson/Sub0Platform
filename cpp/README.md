# Sub0Platform C++ library

The operating-system layer of the C++ Sub0 projects: child processes, the process tree, host facts, whole and atomic files, sockets, the
local control socket, and waiting on several things at once. It is Sub0Squad's layer 0, lifted here. The library is one static library,
`sub0platform`, in the namespace `sub0platform`; the Windows and POSIX backends are chosen at build time. It needs C++23 and `<expected>`.

| Module (header) | What it does |
|---|---|
| `error` | `PlatformError`: the one error type, with the operation, the native code and a sentence for a person |
| `process` | `spawn` and `runCaptured`: the one launcher for child processes (argument vectors, captured or piped output, timeouts, process groups) |
| `proc` | this process's id, program and command line; `isAlive`, `descendants`, `terminateProcess`; `setEnvironment`, `unsetEnvironment`, `getEnvironment` |
| `host` | `memory`, `cpuTimes`, `loadAverage`, `freeDiskMiB` and `gpu` |
| `file` | `readFile`, `writeFile`, `writeFileAtomic`, `appendToFile`, `removeTree` and `FileLock` (one holder across processes) |
| `net` | `SocketStream` and `SocketListener` over TCP, with deadlines |
| `ipc` | the local control socket: a stream socket named by a path (AF_UNIX on both systems) |
| `wait` | `Waiter`: sockets, child exits, wake-ups and stop requests in one wait |

`getEnvironment` returns `nullopt` for an unset variable and `""` for a variable set to nothing. Use it in place of `std::getenv`. On Windows
it reads the system's copy as UTF-8, the encoding `setEnvironment` writes; the C runtime's copy drops an empty value.

Not in this library yet: the path mapping and per-user directories of the Python package, Sub0Log's Windows argument quoting, and the
conformance vectors in `../conformance/` that they read. The vectors apply once those modules land.

## Layout

```
cpp/
  CMakeLists.txt                      the library; as the top-level project, also the tests and the layering check
  cmake/Modules.cmake                 the module list: the one source for the build and for the include check
  cmake/CheckLayers.cmake             the include check, run as the `layering` test
  cmake/Sub0PlatformConfig.cmake.in   the package config that `cmake --install` installs
  include/sub0platform/               public headers, one per module, and testing/check.hpp (the shared test helper)
  src/                                <module>.cpp and <module>_posix.cpp or <module>_win32.cpp; util.hpp, posix_util.hpp, win32_util.hpp (private)
  tests/                              test_platform_<module>.cpp, and platform_child.cpp, the program the process and proc tests start
```

## Rules

* The library is one layer and uses nothing else of ours. The `layering` test fails on a quoted include that is neither a module nor a
  private header, on an operating-system header in a public header, and on a file that belongs to no module.
* Operating-system headers stay in `src/`. Public headers name the standard library and each other.
* Strings cross the interface as UTF-8; paths are `std::filesystem::path`.
* A failed operation returns `std::expected<..., PlatformError>`, or `std::optional` where absence is the answer; no caller reads errno.

## Consuming it

With CPM. The tests stay off unless the library is the top-level project:

```cmake
CPMAddPackage(
  NAME Sub0Platform
  GITHUB_REPOSITORY CraigHutchinson/Sub0Platform
  GIT_TAG <a tag or commit that contains cpp/>
  SOURCE_SUBDIR cpp
)
target_link_libraries(my_app PRIVATE Sub0Platform::sub0platform)
```

The test helper is `#include "sub0platform/testing/check.hpp"`: `CHECK`, `CHECK_EQ`, `CHECK_GE`, `makeTempDir`, `removeTree` and `finish`. It
needs the library linked.

Standalone, from this directory:

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build
ctest --test-dir build --output-on-failure
```

Requirements: CMake 3.24, a C++23 compiler with `<expected>` (GCC 13.2 on MinGW-w64 and GCC 15 on Linux were built here), and Windows with
MinGW-w64 (UCRT) or POSIX. CI runs `cpp-linux` on the runner's GCC and `cpp-windows` on MSYS2's UCRT64 GCC.

## Tests

Six test programs, registered with CTest, and the helper program `platform_child`. They need only the standard library and the platform.

* `SUB0PLATFORM_TEST_TMP` names the root of the tests' temporary directories. Default: `test-tmp` in the build directory.
* On Windows keep that root short and outside `AppData`. `test_platform_net` makes a path longer than 107 bytes, which must fit in
  `MAX_PATH`, and AF_UNIX connect fails under the user's AppData directories on the build host. Long socket paths fall back to
  `%USERPROFILE%\.sub0platform\sockets`, which the tests create.
* On WSL keep the root off `/mnt/`: DrvFs has neither POSIX file modes nor Unix sockets, and two tests need both.

Open decisions: whether the library keeps C++23 as its floor, which MSVC toolchains to support (only MinGW is built here), and whether
Sub0Log depends on it. The plan and its status: Sub0Squad `docs/sessions/platform-unification.md`.

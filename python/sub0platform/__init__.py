"""Sub0Platform for Python: the operating-system layer shared by the Sub0 projects (standard library only, 3.10+).

Modules (the C++ library under cpp/ uses the same names):
  env    which platform this is: IS_WINDOWS, IS_WSL, NAMES, EXE
  paths  Windows drive paths and WSL mounts, both ways
  dirs   per-user config, cache and state directories
  proc   detached servers, a pinned measurement launch with a timeout, exact liveness, stopping a process tree
  fs     atomic replace that survives Windows readers
  lock   an exclusive lock file that recovers from a crashed owner
  lease  shared and exclusive machine leases interoperable with the C++ library

Behaviour shared with the C++ library is pinned by the JSON vectors in conformance/.
"""
__version__ = "0.2.0"

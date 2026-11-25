"""Native file locks compatible with C++ FileLock."""
import errno
import os

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ("internal", ctypes.c_size_t),
            ("internal_high", ctypes.c_size_t),
            ("offset", wintypes.DWORD),
            ("offset_high", wintypes.DWORD),
            ("event", wintypes.HANDLE),
        ]

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _open = _kernel.CreateFileW
    _open.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _open.restype = wintypes.HANDLE
    _lock = _kernel.LockFileEx
    _lock.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                      wintypes.DWORD, ctypes.POINTER(_Overlapped))
    _lock.restype = wintypes.BOOL
    _close = _kernel.CloseHandle
    _close.argtypes = (wintypes.HANDLE,)
    _close.restype = wintypes.BOOL

    _invalid_handle = ctypes.c_void_p(-1).value
    _read_write = 0xC0000000
    _share_read_write_delete = 7
    _open_always = 4
    _normal = 0x80
    _fail_immediately = 1
    _exclusive_lock = 2
    _lock_violation = 33

    def tryLock(path, exclusive):
        """Return a close callback for a held lock, or None if the lock is busy."""
        handle = _open(os.fspath(path), _read_write, _share_read_write_delete,
                       None, _open_always, _normal, None)
        if handle == _invalid_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        flags = _fail_immediately | (_exclusive_lock if exclusive else 0)
        if _lock(handle, flags, 0, 1, 0, ctypes.byref(_Overlapped())):
            return lambda: _close(handle)
        error = ctypes.get_last_error()
        _close(handle)
        if error == _lock_violation:
            return None
        raise ctypes.WinError(error)
else:
    import fcntl

    def tryLock(path, exclusive):
        """Return a close callback for a held lock, or None if the lock is busy."""
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        lock = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(fd, lock | fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                return None
            raise
        return lambda: os.close(fd)

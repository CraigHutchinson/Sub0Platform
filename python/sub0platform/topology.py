"""Physical cores visible to the current affinity domain."""

import ctypes
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhysicalCore:
    """Allowed logical CPU indices sharing a core, with optional OS class evidence."""

    logicalCpus: tuple[int, ...]
    performanceClass: int | None


def readTopology() -> tuple[PhysicalCore, ...] | None:
    """Return cores sorted by their first logical CPU, or None when unavailable.

    Compare classes only within one snapshot when all classes are known. Higher
    values indicate higher performance. Windows indices are affinity-mask bits
    on a single-group system. Linux indices are from the calling thread's mask.
    """
    try:
        if sys.platform == "win32":
            return _windows_topology()
        if sys.platform == "linux":
            return _linux_topology(Path("/sys/devices/system/cpu"), os.sched_getaffinity(0))
    except (OSError, ValueError):
        return None
    return None


def _allowed_cpu_list(value, allowed):
    """Read kernel CPU ranges without expanding indices outside the allowed mask."""
    result = set()
    for part in value.strip().split(","):
        first, sep, last = part.partition("-")
        lo = int(first)
        hi = int(last) if sep else lo
        if lo < 0 or hi < lo:
            raise ValueError("invalid CPU range")
        result.update(cpu for cpu in allowed if lo <= cpu <= hi)
    return tuple(sorted(result))


def _linux_topology(root, allowed):
    by_cpu = {}
    for cpu in sorted(allowed):
        path = root / f"cpu{cpu}"
        topology = path / "topology"
        if int((topology / "physical_package_id").read_text()) < 0:
            return None  # The kernel can supply a default singleton mask without real topology.
        try:
            siblings = (topology / "core_cpus_list").read_text()
        except FileNotFoundError:
            siblings = (topology / "thread_siblings_list").read_text()
        group = _allowed_cpu_list(siblings, allowed)
        if cpu not in group:
            return None
        by_cpu[cpu] = group

    if not by_cpu or any(by_cpu[sibling] != group for group in by_cpu.values() for sibling in group):
        return None

    def read_capacity(cpu):
        try:
            capacity = int((root / f"cpu{cpu}" / "cpu_capacity").read_text())
            return capacity if capacity > 0 else None
        except (OSError, ValueError):
            return None

    result = []
    for group in sorted(set(by_cpu.values())):
        capacities = {read_capacity(cpu) for cpu in group}
        performance_class = next(iter(capacities)) if len(capacities) == 1 else None
        result.append(PhysicalCore(group, performance_class))
    return tuple(result)


# SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX header, PROCESSOR_RELATIONSHIP through
# GroupCount, and its one 64-bit GROUP_AFFINITY for RelationProcessorCore.
_PROCESSOR_CORE = struct.Struct("<IIBB20xHQH6x")
_RELATION_PROCESSOR_CORE = 0
_ERROR_INSUFFICIENT_BUFFER = 122


def _windows_core_records(records, allowed):
    result = []
    seen = 0
    offset = 0
    while len(records) - offset >= _PROCESSOR_CORE.size:
        relation, size, _, efficiency_class, group_count, mask, group = _PROCESSOR_CORE.unpack_from(records, offset)
        if (relation != _RELATION_PROCESSOR_CORE or not _PROCESSOR_CORE.size <= size <= len(records) - offset
                or group_count != 1 or group != 0 or not mask or mask & seen):
            return None
        seen |= mask
        cpus = tuple(cpu for cpu in range(64) if (mask & allowed) & (1 << cpu))
        if cpus:
            result.append(PhysicalCore(cpus, efficiency_class))
        offset += size
    if offset != len(records) or not result or allowed & ~seen:
        return None
    return tuple(sorted(result, key=lambda core: core.logicalCpus))


def _windows_topology():
    # SetProcessAffinityMask uses one processor group. WOW64 can fold upper mask bits.
    if ctypes.sizeof(ctypes.c_size_t) != 8:
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetActiveProcessorGroupCount.restype = ctypes.c_uint16
    if kernel.GetActiveProcessorGroupCount() != 1:
        return None

    mask_pointer = ctypes.POINTER(ctypes.c_size_t)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, mask_pointer, mask_pointer]
    kernel.GetProcessAffinityMask.restype = ctypes.c_int
    allowed = ctypes.c_size_t()
    system = ctypes.c_size_t()
    if not kernel.GetProcessAffinityMask(kernel.GetCurrentProcess(), ctypes.byref(allowed), ctypes.byref(system)):
        return None

    query = kernel.GetLogicalProcessorInformationEx
    query.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    query.restype = ctypes.c_int
    size = ctypes.c_uint32()
    if query(_RELATION_PROCESSOR_CORE, None, ctypes.byref(size)):
        return None
    if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER or size.value < _PROCESSOR_CORE.size:
        return None
    records = ctypes.create_string_buffer(size.value)
    if not query(_RELATION_PROCESSOR_CORE, records, ctypes.byref(size)):
        return None
    return _windows_core_records(records.raw[:size.value], allowed.value)

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sub0platform import topology
from sub0platform.topology import PhysicalCore


def windows_core(cpus, efficiency=0, *, group=0, size=48, group_count=1):
    record = bytearray(48)
    struct.pack_into("<II", record, 0, 0, size)
    record[9] = efficiency
    struct.pack_into("<H", record, 30, group_count)
    struct.pack_into("<QH", record, 32, sum(1 << cpu for cpu in cpus), group)
    return record


class TopologyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def linux_cpu(self, cpu, siblings, *, capacity=None, package=0, legacy=False):
        path = self.root / f"cpu{cpu}"
        cpu_topology = path / "topology"
        cpu_topology.mkdir(parents=True, exist_ok=True)
        (cpu_topology / "physical_package_id").write_text(str(package))
        sibling_file = "thread_siblings_list" if legacy else "core_cpus_list"
        (cpu_topology / sibling_file).write_text(siblings)
        if capacity is not None:
            (path / "cpu_capacity").write_text(str(capacity))

    def test_linux_sparse_affinity_and_same_core_siblings(self):
        self.linux_cpu(2, "2,8,20", capacity=1024)
        self.linux_cpu(8, "2,8,20", capacity=1024, legacy=True)
        self.linux_cpu(41, "40-42", capacity=512)
        self.linux_cpu(76, "76")
        self.assertEqual(topology._linux_topology(self.root, {76, 41, 8, 2}),
                         (PhysicalCore((2, 8), 1024), PhysicalCore((41,), 512), PhysicalCore((76,), None)))

    def test_linux_rejects_inconsistent_or_default_siblings(self):
        self.linux_cpu(1, "1,4")
        self.linux_cpu(4, "4")
        self.assertIsNone(topology._linux_topology(self.root, {1, 4}))
        self.linux_cpu(4, "1,4", package=-1)
        self.assertIsNone(topology._linux_topology(self.root, {1, 4}))
        self.linux_cpu(4, "1")
        self.assertIsNone(topology._linux_topology(self.root, {1, 4}))

    def test_linux_unreadable_or_invalid_records_are_unavailable(self):
        with patch.object(topology.sys, "platform", "linux"), \
                patch.object(topology.os, "sched_getaffinity", return_value={6}, create=True), \
                patch.object(topology, "Path", return_value=self.root):
            self.assertIsNone(topology.readTopology())
            self.linux_cpu(6, "6-3")
            self.assertIsNone(topology.readTopology())

    def test_windows_sibling_masks_and_classes(self):
        records = windows_core([63], 0) + windows_core([2, 34], 1) + windows_core([9, 37], 2)
        allowed = (1 << 2) | (1 << 34) | (1 << 37) | (1 << 63)
        self.assertEqual(topology._windows_core_records(records, allowed),
                         (PhysicalCore((2, 34), 1), PhysicalCore((37,), 2), PhysicalCore((63,), 0)))

    def test_windows_rejects_incomplete_or_ambiguous_records(self):
        for records in (windows_core([0], group=1), windows_core([0], group_count=2),
                        windows_core([0], size=0), windows_core([0], size=49), windows_core([0])[:-1],
                        windows_core([0]) + windows_core([0]), windows_core([1])):
            with self.subTest(records=records):
                self.assertIsNone(topology._windows_core_records(records, 1))

    def test_unsupported_platform(self):
        with patch.object(topology.sys, "platform", "darwin"):
            self.assertIsNone(topology.readTopology())

    def test_live_snapshot_when_available(self):
        cores = topology.readTopology()
        if cores is None:
            self.skipTest("the current affinity domain provides no topology")
        cpus = [cpu for core in cores for cpu in core.logicalCpus]
        self.assertEqual(len(cpus), len(set(cpus)))
        self.assertEqual(list(cores), sorted(cores, key=lambda core: core.logicalCpus))

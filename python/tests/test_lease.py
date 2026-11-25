"""Lease owner records and process-level lock interoperability."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sub0platform import lease


class MachineLeaseTests(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "machine.lock"

    def test_owner_conformance(self):
        vectors = Path(__file__).resolve().parents[2] / "conformance" / "lease_owner.jsonl"
        lines = vectors.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        sidecar = self.path.with_suffix(".lock.owner")
        for line in lines:
            record = line.replace("123456789", str(os.getpid()))
            sidecar.write_text(record, encoding="utf-8")
            holders = lease.readOwners(self.path)
            if '"legacy"' in record:
                self.assertEqual(holders, [lease.LeaseOwner(os.getpid(), 0, 'measure "vectors" \\ path', "legacy")])
            elif '"shared"' in record:
                self.assertEqual(holders, [lease.LeaseOwner(os.getpid(), 1.25, "serve\nqueries", "engine 🚲",
                                                           "shared", "P0–P3", "high", "GPU 0", "AC")])
                self.assertIn("1970-01-01T00:00:01Z, shared", holders[0].describe())
                self.assertIn("serve queries", holders[0].describe())
            else:
                self.assertEqual(holders, [])

    def test_shared_readers_are_distinct_and_waiting_writer_blocks_new_readers(self):
        first = lease.acquire("shared", "test", "reader A", lockFile=self.path)
        second = lease.acquire("shared", "test", "reader B", lockFile=self.path)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        self.assertCountEqual([owner.what for owner in lease.readOwners(self.path)], ["reader A", "reader B"])

        waiting = threading.Event()
        finished = []
        def writer():
            try:
                def announce(owners):
                    finished.append([owner.what for owner in owners])
                    waiting.set()
                finished.append(lease.acquire("exclusive", "test", "writer", lockFile=self.path,
                                              onWait=announce, timeout=5))
            except BaseException as error:
                finished.append(error)
                waiting.set()

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            self.assertTrue(waiting.wait(5))
            self.assertIsNone(lease.acquire("shared", "test", "late reader", lockFile=self.path))
            self.assertIsNone(lease.acquire("exclusive", "test", "late writer", lockFile=self.path))
        finally:
            first.close()
            second.close()
            thread.join(6)
        self.assertFalse(thread.is_alive())
        held = finished[-1]
        self.assertIsInstance(held, lease.MachineLease)
        self.assertCountEqual(finished[0], ["reader A", "reader B"])
        with held:
            self.assertEqual(lease.readOwners(self.path)[0].what, "writer")
            self.assertIsNone(lease.acquire("shared", "test", "reader", lockFile=self.path))
        self.assertEqual(lease.readOwners(self.path), [])

    @unittest.skipUnless(os.environ.get("SUB0PLATFORM_LEASE_CPP"), "C++ test program not built")
    def test_cpp_and_python_contend_and_read_reciprocal_owner_records(self):
        executable = os.environ["SUB0PLATFORM_LEASE_CPP"]

        def probe(action, mode):
            return subprocess.run([executable, action, mode, str(self.path)], check=False, timeout=5).returncode

        with lease.acquire("shared", "python", 'serve "examples"\\\n', lockFile=self.path, power_state="AC"):
            self.assertEqual(probe("read", "shared"), 0)
            self.assertEqual(probe("probe", "shared"), 0)
            self.assertEqual(probe("probe", "exclusive"), 75)

        child = subprocess.Popen([executable, "hold", "exclusive", str(self.path)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            self.assertEqual(child.stdout.readline().strip(), b"ready")
            self.assertIsNone(lease.acquire("shared", "python", "serve", lockFile=self.path))
            [owner] = lease.readOwners(self.path)
            self.assertEqual((owner.tool, owner.what, owner.gpu, owner.mode),
                             ("C++", "test holder", "GPU 0", "exclusive"))
        finally:
            child.kill()
            child.communicate(timeout=5)
        self.assertEqual(lease.readOwners(self.path), [])
        with lease.acquire("exclusive", "python", "after crash", lockFile=self.path):
            self.assertEqual(lease.readOwners(self.path)[0].what, "after crash")


if __name__ == "__main__":
    unittest.main()

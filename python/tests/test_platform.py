"""Sub0Platform Python tests: conformance vectors plus real processes, files and locks on whichever OS runs them."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sub0platform import dirs, env, fs, lock, paths, proc  # noqa: E402

CONFORMANCE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "conformance")


def vectors(name):
    with open(os.path.join(CONFORMANCE, name), encoding="utf-8") as f:
        return json.load(f)


def deadPid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)


class TestPaths(unittest.TestCase):
    def test_conformance(self):
        v = vectors("paths.json")
        for given, want in v["toPosix"]:
            self.assertEqual(paths.toPosix(given), want, given)
        for given, want in v["toWindows"]:
            self.assertEqual(paths.toWindows(given), want, given)

    def test_local_follows_the_platform(self):
        self.assertEqual(paths.local("D:/x", isWindows=False), "/mnt/d/x")
        self.assertEqual(paths.local("/mnt/d/x", isWindows=True), "D:/x")
        self.assertTrue(paths.isDrivePath("C:\\x"))
        self.assertFalse(paths.isDrivePath("/mnt/c/x"))


class TestEnvAndDirs(unittest.TestCase):
    def test_env(self):
        self.assertEqual(env.NAMES[0], "windows" if os.name == "nt" else "linux")
        self.assertEqual(env.EXE, ".exe" if os.name == "nt" else "")

    def test_dirs_windows_split_roaming_config_local_cache(self):
        e = {"APPDATA": "R", "LOCALAPPDATA": "L"}
        self.assertEqual(dirs.config("app", e, True), os.path.join("R", "app"))
        self.assertEqual(dirs.cache("app", e, True), os.path.join("L", "app"))
        self.assertEqual(dirs.state("app", e, True), os.path.join("L", "app"))

    def test_dirs_xdg(self):
        e = {"XDG_CONFIG_HOME": "/c", "XDG_CACHE_HOME": "/k", "XDG_STATE_HOME": "/s"}
        self.assertEqual(dirs.config("app", e, False), os.path.join("/c", "app"))
        self.assertEqual(dirs.cache("app", e, False), os.path.join("/k", "app"))
        self.assertEqual(dirs.state("app", e, False), os.path.join("/s", "app"))
        self.assertTrue(dirs.config("app", {}, False).endswith(os.path.join(".config", "app")))


class TestProc(Tmp):
    def test_spawn_detached_alive_cpu_terminate(self):
        p = proc.spawnDetached([sys.executable, "-c", "import time\nwhile True: sum(range(10000)); time.sleep(0.01)"],
                               os.path.join(self.dir, "log.txt"))
        try:
            self.assertTrue(proc.alive(p.pid))
            time.sleep(0.5)
            self.assertIsNotNone(proc.cpuSeconds(p.pid))
            proc.terminate(p.pid)
            p.wait(timeout=20)
            self.assertFalse(proc.alive(p.pid))
        finally:
            if p.poll() is None:
                p.kill()

    def test_launch_runs_to_completion_and_raises_on_failure_and_timeout(self):
        proc.launch([sys.executable, "-c", "pass"])
        proc.launch([sys.executable, "-c", "pass"], timeout=30, cpu=0)
        with self.assertRaises(subprocess.CalledProcessError):
            proc.launch([sys.executable, "-c", "raise SystemExit(3)"])
        began = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            proc.launch([sys.executable, "-c", "import time; time.sleep(60)"], timeout=1)
        self.assertLess(time.monotonic() - began, 20)

    def test_dead_pid(self):
        self.assertFalse(proc.alive(deadPid()))
        self.assertIsNone(proc.cpuSeconds(deadPid()))


class TestFs(Tmp):
    def test_atomic_write_text_and_bytes(self):
        p = os.path.join(self.dir, "a.json")
        self.assertTrue(fs.atomicWrite(p, "one\n"))
        self.assertTrue(fs.atomicWrite(p, b"two"))
        with open(p, "rb") as f:
            self.assertEqual(f.read(), b"two")
        self.assertEqual(sorted(os.listdir(self.dir)), ["a.json"])


class TestLock(Tmp):
    def test_exclusive_then_released(self):
        p = os.path.join(self.dir, "job.lock")
        with lock.ExclusiveLock(p):
            self.assertEqual(lock.owner(p), str(os.getpid()))
            with self.assertRaises(TimeoutError):
                with lock.ExclusiveLock(p, poll=0.05, timeout=0.2):
                    pass
        self.assertIsNone(lock.owner(p))

    def test_crashed_owner_is_set_aside(self):
        p = os.path.join(self.dir, "job.lock")
        dead = deadPid()
        with open(p, "w") as f:
            f.write(str(dead))
        self.assertIsNone(lock.owner(p))
        with lock.ExclusiveLock(p, poll=0.05, timeout=5):
            self.assertTrue(os.path.exists(p + ".stale-%d" % dead))

    def test_waiter_gets_it_after_release(self):
        p = os.path.join(self.dir, "job.lock")
        waits = []
        first = lock.ExclusiveLock(p)
        first.__enter__()
        threading.Timer(0.3, first.__exit__, args=(None, None, None)).start()
        with lock.ExclusiveLock(p, poll=0.05, timeout=5, onWait=waits.append):
            self.assertTrue(waits)


if __name__ == "__main__":
    unittest.main()

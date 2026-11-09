import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import unittest
from pathlib import Path

from data_agent.exchange import export_index
from test_scanner import ScanCase


class CliTests(ScanCase):
    def command(self, *arguments):
        return subprocess.run([sys.executable, "-m", "data_agent", arguments[0],
                               "--state-dir", str(self.store.directory), *arguments[1:]],
                              capture_output=True, text=True, timeout=15)

    def test_real_permission_failure_and_preservation(self):
        if os.name != "posix" or os.geteuid() == 0:
            self.skipTest("需要普通 POSIX 用户验证 chmod 拒绝")
        denied = self.root / "denied"
        denied.mkdir()
        (denied / "keep.txt").write_text("keep")
        self.run_scan()
        denied.chmod(0)
        try:
            result = self.command("scan", "--source", "demo", "--root", str(self.root))
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "partial")
            self.assertTrue(json.loads(result.stdout)["errors"])
            history = self.command("search", "--query", "keep.txt")
            self.assertEqual(json.loads(history.stdout)[0]["status"], "unknown")
        finally:
            denied.chmod(0o700)
        self.assertEqual(self.command("scan", "--source", "demo", "--root", str(self.root)).returncode, 0)

    def slow_worker(self):
        program = '''
import sys, time
from data_agent import scanner
from data_agent.cli import main
original = scanner.walk

def slow(*args):
    for item in original(*args):
        yield item
        print("READY", file=sys.stderr, flush=True)
        time.sleep(60)

scanner.walk = slow
raise SystemExit(main(sys.argv[1:]))
'''
        worker = subprocess.Popen([sys.executable, "-c", program, "scan", "--source", "demo",
                                   "--root", str(self.root), "--state-dir", str(self.store.directory)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: worker.poll() is None and worker.kill())
        ready, _, _ = select.select([worker.stderr], [], [], 10)
        self.assertTrue(ready, "worker 未在10秒内就绪")
        self.assertEqual(worker.stderr.readline().strip(), "READY")
        return worker

    @unittest.skipUnless(os.name == "posix", "POSIX 信号集成测试")
    def test_signals_concurrent_writer_and_read_query(self):
        self.run_scan()
        before = export_index(self.store)
        worker = self.slow_worker()
        # Read queries continue while the scan holds its write transaction.
        self.assertEqual(self.command("search", "--query", "中文").returncode, 0)
        second = self.command("scan", "--source", "other", "--root", str(self.root))
        self.assertEqual(second.returncode, 1, second.stdout)
        self.assertIn("写入任务", json.loads(second.stderr)["error"])
        worker.send_signal(signal.SIGTERM)
        stdout, stderr = worker.communicate(timeout=10)
        self.assertEqual(worker.returncode, 130, stderr)
        self.assertEqual(json.loads(stdout)["status"], "interrupted")
        worker = self.slow_worker()
        worker.kill()
        worker.communicate(timeout=10)
        self.assertEqual(len(self.store.entries()), len(before["entries"]))
        self.assertEqual(self.run_scan()["status"], "complete")
        self.assertFalse(any(scan["status"] == "running" for scan in self.store.scans()))
        self.assertGreaterEqual(sum(scan["status"] == "interrupted" for scan in self.store.scans()), 2)

    def test_cli_exit_codes_outputs_and_source_protection(self):
        self.run_scan()
        self.assertEqual(self.command("search", "--query", "absent").returncode, 4)
        self.assertEqual(self.command("search", "--source", "absent").returncode, 1)
        path = self.root / "forbidden.json"
        self.assertEqual(self.command("export", "--output", str(path)).returncode, 1)
        self.assertFalse(path.exists())
        path = self.root.parent / "report.json"
        self.assertEqual(self.command("export", "--output", str(path)).returncode, 0)
        original = path.read_bytes()
        self.assertEqual(self.command("export", "--output", str(path)).returncode, 1)
        self.assertEqual(path.read_bytes(), original)
        nested = self.root / "nested-state"
        self.assertEqual(self.command("scan", "--source", "demo", "--root", str(self.root),
                                      "--state-dir", str(nested)).returncode, 1)
        self.assertFalse(nested.exists())

    def test_batch_and_sparse_source_snapshot(self):
        for number in range(500):
            (self.root / f"small-{number}.txt").write_text(str(number))
        with (self.root / "large.bin").open("wb") as stream:
            stream.truncate(16 * 1024 * 1024)

        def snapshot():
            return {str(path.relative_to(self.root)): (path.stat().st_size, path.stat().st_mtime_ns,
                                                       hashlib.sha256(path.read_bytes()).hexdigest())
                    for path in self.root.iterdir()}

        before = snapshot()
        self.assertEqual(self.run_scan()["status"], "complete")
        self.assertEqual(self.run_scan()["status"], "complete")
        self.assertEqual(len(self.store.entries()), 502)
        self.assertEqual(snapshot(), before)

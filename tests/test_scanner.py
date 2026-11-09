import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data_agent.scanner import scan, walk
from data_agent.store import Store


class ScanCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "source"
        self.root.mkdir()
        (self.root / "中文 space.txt").write_text("hello")
        self.store = Store(base / "state")
        self.addCleanup(self.store.close)

    def run_scan(self, **kwargs):
        return scan(self.store, "demo", self.root, **kwargs)


class ScanTests(ScanCase):
    def test_repeat_update_delete_and_readonly(self):
        before = (self.root / "中文 space.txt").stat()
        self.assertEqual(self.run_scan()["status"], "complete")
        self.assertEqual(self.run_scan()["status"], "complete")
        self.assertEqual(len(self.store.entries()), 1)
        self.assertEqual((self.root / "中文 space.txt").stat().st_mtime_ns, before.st_mtime_ns)
        (self.root / "中文 space.txt").write_text("new content")
        (self.root / "new").write_text("new")
        self.run_scan()
        self.assertEqual(self.store.entries()[1]["size"], len("new content"))
        (self.root / "new").unlink()
        self.run_scan()
        self.assertEqual(self.store.entries()[0]["status"], "missing")

    def test_partial_offline_interrupted_recovery(self):
        self.run_scan()

        def denied(root, patterns, error):
            error(".", "permission denied (injected)")
            return iter(())

        with patch("data_agent.scanner.walk", denied):
            self.assertEqual(self.run_scan()["status"], "partial")
        self.assertEqual(self.store.entries()[0]["status"], "unknown")
        with patch("data_agent.scanner.walk", side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_scan()["status"], "interrupted")
        self.root.rename(self.root.with_name("offline"))
        self.assertEqual(self.run_scan()["status"], "unavailable")
        self.assertEqual(len(self.store.entries()), 1)
        self.root.with_name("offline").rename(self.root)
        self.assertEqual(self.run_scan()["status"], "complete")
        self.assertEqual(self.store.entries()[0]["status"], "observed")

    def test_links_and_exclusion(self):
        (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        (self.root / "escape").symlink_to(self.root.parent, target_is_directory=True)
        self.run_scan(patterns=["*.txt"])
        self.assertEqual([e["kind"] for e in self.store.entries()], ["symlink", "symlink"])

    def test_changed_during_scan(self):
        original = os.stat
        calls = 0

        def changing(path, *args, **kwargs):
            nonlocal calls
            if path == "中文 space.txt":
                calls += 1
                if calls == 2:
                    (self.root / path).write_text("changed during scan")
            return original(path, *args, **kwargs)

        with patch("data_agent.scanner.os.stat", changing):
            self.assertEqual(self.run_scan()["status"], "partial")
        self.assertEqual(self.store.entries()[0]["status"], "unstable")

    def test_persistent_and_source_identity(self):
        self.run_scan()
        scan(self.store, "other", self.root)
        self.assertEqual(len(self.store.entries()), 2)
        second = Store(self.store.directory)
        self.addCleanup(second.close)
        self.assertEqual(len(second.entries()), 2)

    def test_state_inside_source_rejected(self):
        nested = Store(self.root / "state")
        self.addCleanup(nested.close)
        with self.assertRaises(ValueError):
            scan(nested, "bad", self.root)

    def test_nested_mount_identity_change_preserves_history(self):
        from types import SimpleNamespace

        directory = self.root / "mounted"
        directory.mkdir()
        (directory / "research.txt").write_text("research")
        self.run_scan()
        original = walk

        def changed_device(root, patterns, error):
            for path, info, kind, unstable in original(root, patterns, error):
                if path == "mounted":
                    fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                    fields["st_dev"] += 1
                    info = SimpleNamespace(**fields)
                yield path, info, kind, unstable

        with patch("data_agent.scanner.walk", changed_device):
            self.assertEqual(self.run_scan()["status"], "partial")
        historical = next(entry for entry in self.store.entries() if entry["path"] == "mounted/research.txt")
        self.assertEqual(historical["status"], "unknown")

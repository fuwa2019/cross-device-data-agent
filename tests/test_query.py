import os

from data_agent.query import search, stats
from data_agent.scanner import scan
from test_scanner import ScanCase


class QueryTests(ScanCase):
    def test_chinese_space_special_year_source(self):
        (self.root / "示例券商 月结单 2025.pdf").write_text("fake")
        (self.root / "$(touch NEVER);100%.txt").write_text("data")
        self.run_scan()
        scan(self.store, "other", self.root)
        self.assertEqual(len(search(self.store, "月结单", category="statement", year=2025)), 2)
        self.assertEqual(len(search(self.store, "100%", source_id="demo")), 1)
        self.assertEqual(search(self.store, "不存在"), [])
        with self.assertRaises(ValueError):
            search(self.store, source_id="absent")
        row = search(self.store, "中文 space", source_id="demo")[0]
        self.assertEqual(row["availability"], "unknown_now")
        self.assertEqual(search(self.store, "中文", check=True)[0]["availability"], "accessible_now_metadata_only")

    def test_logical_hardlinks_overlap(self):
        os.link(self.root / "中文 space.txt", self.root / "hardlink.txt")
        self.run_scan()
        scan(self.store, "overlap", self.root)
        report = stats(self.store)
        self.assertEqual(report["logical_bytes_by_path"], 20)
        self.assertEqual(report["logical_bytes_unique_local_identity"], 5)
        self.assertEqual(len(report["hardlink_or_overlap_repeated_paths"]), 3)
        self.assertEqual(len(report["overlapping_sources"]), 1)
        self.assertEqual(stats(self.store, group_by="extension")["groups"][0]["files"], 4)

    def test_offline_query_historical(self):
        self.run_scan()
        self.root.rename(self.root.with_name("offline"))
        self.run_scan()
        row = search(self.store, "中文")[0]
        self.assertEqual(row["availability"], "unavailable_at_last_attempt")
        self.assertEqual(row["status"], "unknown")

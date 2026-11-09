import json
from unittest.mock import patch

from data_agent.experiments import experiments, markdown_overview, parse_entry, policy_for
from data_agent.scanner import scan
from data_agent.exchange import export_index, import_index
from data_agent.store import Store
from test_scanner import ScanCase

POLICY = {"enabled": True, "paths": ["QER/*"], "extensions": [".json", ".toml", ".log"], "max_bytes": 1024}


class ExperimentTests(ScanCase):
    def make_run(self, directory="a", extra=False):
        run = self.root / "QER" / directory
        run.mkdir(parents=True)
        (run / "config.json").write_text(json.dumps({"run_id": "demo", "result": "result.json", "weight": "model.pt"}))
        (run / "model.pt").write_text("DO NOT LOAD")
        (run / "train.log").write_text("run_id=demo\n")
        if extra:
            (run / "config2.toml").write_text('run_id="other"\n')
            (run / "epoch-2.pt").write_text("DO NOT LOAD EITHER")
        else:
            (run / "result.json").write_text('{"score":1}')
        return run

    def test_evidence_ambiguities_missing_duplicate(self):
        self.make_run()
        self.make_run("b", extra=True)
        self.assertEqual(self.run_scan(parse=POLICY)["status"], "complete")
        runs = experiments(self.store)
        rendered = markdown_overview(runs)
        self.assertIn("# 实验关联概览", rendered)
        self.assertIn("### 歧义与缺失", rendered)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["missing_roles"], [])
        self.assertIn("result", runs[1]["missing_roles"])
        self.assertTrue(any("重复 run_id" in item for item in runs[0]["ambiguities"]))
        self.assertTrue(any("多个 weight" in item for item in runs[1]["ambiguities"]))
        self.assertTrue(any(link.get("state") == "not_indexed_or_missing" for link in runs[1]["explicit_links"]))

    def test_bounded_cached_no_weight_read(self):
        self.make_run()
        self.run_scan(parse=POLICY)
        from data_agent.experiments import read_bounded
        with patch("data_agent.experiments.read_bounded", wraps=read_bounded) as read:
            self.run_scan(parse=POLICY)
            self.assertEqual(read.call_count, 0)
        entry = next(e for e in self.store.entries() if e["path"].endswith("model.pt"))
        self.assertEqual(entry["parsed"]["state"], "outside_policy")
        with self.assertRaises(ValueError):
            policy_for({**POLICY, "extensions": [".pt"]})

    def test_malformed_oversize_unsafe_reference_and_disabled(self):
        run = self.make_run()
        (run / "config.json").write_text('{"run_id":"demo","result":"../../../../secret"}')
        (run / "huge.log").write_text("x" * 2048)
        self.run_scan(parse=POLICY)
        self.assertEqual(next(e for e in self.store.entries() if e["path"].endswith("huge.log"))["parsed"]["state"], "too_large")
        self.assertTrue(any(link.get("state") == "outside_source_rejected" for link in experiments(self.store)[0]["explicit_links"]))
        (run / "config.json").write_text("{bad json")
        self.assertEqual(self.run_scan(parse=POLICY)["status"], "partial")
        self.run_scan()
        self.assertEqual(experiments(self.store)[0]["run_ids"], [])

    def test_safe_open_rejects_symlink_parent(self):
        run = self.make_run()
        self.run_scan(parse=POLICY)
        entry = next(e for e in self.store.entries() if e["path"].endswith("config.json"))
        moved = run.with_name("moved")
        run.rename(moved)
        run.symlink_to(moved, target_is_directory=True)
        parsed = parse_entry(self.root, entry, None, policy_for(POLICY))
        self.assertEqual(parsed["state"], "error")

    def test_imported_parse_cache_is_not_reused_for_local_scan(self):
        self.make_run()
        self.run_scan(parse=POLICY)
        target = Store(self.root.parent / "imported-state")
        self.addCleanup(target.close)
        import_index(target, export_index(self.store))
        from data_agent.experiments import read_bounded
        with patch("data_agent.experiments.read_bounded", wraps=read_bounded) as read:
            scan(target, "demo", self.root, parse=POLICY)
            self.assertGreater(read.call_count, 0)

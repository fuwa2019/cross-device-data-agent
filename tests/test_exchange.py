import copy

from data_agent.exchange import decode_manifest, encode_jsonl, export_index, import_index
from data_agent.query import search
from data_agent.scanner import scan
from data_agent.store import Store
from test_scanner import ScanCase


class ExchangeTests(ScanCase):
    def target(self):
        target = Store(self.root.parent / "imported")
        self.addCleanup(target.close)
        return target

    def test_two_sources_idempotence_jsonl_offline(self):
        self.run_scan()
        scan(self.store, "second", self.root)
        manifest = export_index(self.store)
        target = self.target()
        self.assertEqual(len(import_index(target, manifest)["imported"]), 2)
        decoded = decode_manifest(encode_jsonl(manifest), True)
        self.assertEqual(len(import_index(target, decoded)["unchanged"]), 2)
        self.assertEqual(len(target.entries()), 2)
        self.assertTrue(all(row["availability"] == "unknown_remote" for row in search(target, check=True)))
        self.assertEqual(len(import_index(target, export_index(target))["unchanged"]), 2)

    def test_old_conflict_bad_version_atomic(self):
        self.run_scan()
        old = export_index(self.store)
        target = self.target()
        import_index(target, old)
        (self.root / "new").write_text("new")
        self.run_scan()
        newer = export_index(self.store)
        import_index(target, newer)
        with self.assertRaises(ValueError):
            import_index(target, old)
        broken = copy.deepcopy(newer)
        broken["entries"][0]["size"] += 1
        with self.assertRaises(ValueError):
            import_index(target, broken)
        broken["version"] = 999
        with self.assertRaises(ValueError):
            import_index(target, broken)
        self.assertEqual(len(target.entries()), 2)

    def test_malformed_batch_does_not_damage_existing(self):
        self.run_scan()
        manifest = export_index(self.store)
        target = self.target()
        import_index(target, manifest)
        variants = []
        for field, value in (("path", "../escape"), ("size", "oops"), ("kind", "execute"),
                             ("indexed_at", "bad"), ("parsed", {"state":"parsed", "run_ids": [], "references": [42]})):
            broken = copy.deepcopy(manifest)
            broken["entries"][0][field] = value
            variants.append(broken)
        for broken in variants:
            with self.assertRaises(ValueError):
                import_index(target, broken)
        self.assertEqual(len(target.entries()), 1)
        for text in ("{bad", "[]", '{"record":"header","data":{}}\n{"record":"evil"}'):
            with self.assertRaises(ValueError):
                import_index(target, decode_manifest(text, text.startswith('{"record"')))

    def test_partial_snapshot_omission_preserves_history(self):
        self.run_scan()
        target = self.target()
        import_index(target, export_index(self.store))
        (self.root / "new").write_text("new")
        self.run_scan()
        partial = export_index(self.store)
        partial["sources"][0]["status"] = "partial"
        partial["entries"] = [entry for entry in partial["entries"] if entry["path"] == "new"]
        import_index(target, partial)
        self.assertEqual(len(target.entries()), 2)
        historical = next(entry for entry in target.entries() if entry["path"] != "new")
        self.assertEqual(historical["status"], "unknown")
        self.assertEqual(import_index(target, partial)["unchanged"], ["demo"])

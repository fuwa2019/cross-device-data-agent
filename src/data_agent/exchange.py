"""Versioned snapshots. Validate everything before taking a write transaction."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import PurePosixPath

from .store import encode, now

FORMAT = "data-agent-index"
VERSION = 1
SOURCE_STATES = {"complete", "partial", "interrupted", "unavailable", "running"}
ENTRY_STATES = {"observed", "unstable", "unknown", "missing", "excluded"}


def instant(value):
    if not isinstance(value, str):
        raise ValueError("清单时间必须为带时区 ISO 字符串")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("清单时间缺少时区")
    return parsed


def require(condition, message):
    if not condition:
        raise ValueError(message)


def string(value, label):
    require(isinstance(value, str) and len(value) <= 32768 and "\0" not in value, f"无效 {label}")


def digest(source, entries):
    portable = {key: value for key, value in source.items()
                if key not in {"origin", "host_id", "root_fingerprint", "import_digest", "imported_at"}}
    return hashlib.sha256(encode([portable, sorted(entries, key=lambda e: e["path"])]).encode()).hexdigest()


def export_index(store, source_id=None):
    store.conn.execute("BEGIN")
    try:
        sources = [source for source in store.sources() if source_id is None or source["source_id"] == source_id]
        if not sources:
            raise ValueError("没有可导出的来源")
        data = {"format": FORMAT, "version": VERSION, "exported_at": now(), "sources": sources,
                "entries": store.entries(source_id)}
        # A read transaction gives a consistent source/entries view even with another writer.
        validate(data)
        return data
    finally:
        store.conn.rollback()


def validate(data):
    require(isinstance(data, dict), "清单必须为 JSON 对象")
    require(data.get("format") == FORMAT and type(data.get("version")) is int and data["version"] == VERSION,
            "不支持的清单格式或版本")
    instant(data.get("exported_at"))
    require(isinstance(data.get("sources"), list) and bool(data["sources"]), "缺少 sources")
    require(isinstance(data.get("entries"), list), "缺少 entries")
    sources = {}
    for source in data["sources"]:
        require(isinstance(source, dict), "无效来源记录")
        sid = source.get("source_id")
        require(isinstance(sid, str) and bool(re.fullmatch(r"[\w.-]{1,128}", sid)), "无效 source_id")
        require(sid not in sources, "重复来源记录")
        require(source.get("status") in SOURCE_STATES, "无效来源状态")
        instant(source.get("updated_at"))
        instant(source.get("last_attempt"))
        if source.get("last_success") is not None:
            instant(source["last_success"])
        for key in ("root", "device"):
            string(source.get(key), key)
        for key in ("tags", "exclude"):
            require(isinstance(source.get(key), list) and all(isinstance(v, str) for v in source[key]), f"无效 {key}")
        sources[sid] = source
    seen = set()
    for entry in data["entries"]:
        require(isinstance(entry, dict), "无效条目记录")
        sid = entry.get("source_id")
        require(isinstance(sid, str) and sid in sources, "条目来源不存在")
        path = entry.get("path")
        string(path, "path")
        require(bool(path) and not path.startswith("/") and str(PurePosixPath(path)) == path and
                ".." not in PurePosixPath(path).parts and path != ".", "条目路径必须为规范相对路径")
        require((sid, path) not in seen, "重复条目")
        seen.add((sid, path))
        require(entry.get("kind") in {"file", "directory", "symlink", "special"}, "无效文件类型")
        require(entry.get("status") in ENTRY_STATES, "无效条目状态")
        for key in ("size", "mtime_ns", "ctime_ns", "dev", "ino", "nlink"):
            require(type(entry.get(key)) is int, f"无效数值 {key}")
        require(entry["size"] >= 0 and entry["ino"] >= 0 and entry["nlink"] >= 0, "无效负数")
        require(entry.get("allocated") is None or (type(entry["allocated"]) is int and entry["allocated"] >= 0), "无效 allocated")
        require(isinstance(entry.get("signature"), list) and len(entry["signature"]) == 5 and
                all(type(v) is int for v in entry["signature"]), "无效 signature")
        instant(entry.get("indexed_at"))
        parsed = entry.get("parsed", {"state": "disabled"})
        require(isinstance(parsed, dict) and parsed.get("state") in
                {"disabled", "outside_policy", "too_large", "parsed", "error"}, "无效 parsed")
        if parsed.get("state") == "parsed":
            require(isinstance(parsed.get("run_ids"), list) and
                    all(isinstance(v, str) and bool(re.fullmatch(r"[\w.:-]{1,128}", v)) for v in parsed["run_ids"]), "无效 run_ids")
            require(isinstance(parsed.get("references"), list), "无效 references")
            for reference in parsed["references"]:
                require(isinstance(reference, dict), "无效 reference")
                string(reference.get("key"), "reference key")
                string(reference.get("value"), "reference value")
    return sources


def import_index(store, data):
    sources = validate(data)
    grouped = {sid: [] for sid in sources}
    for entry in data["entries"]:
        grouped[entry["source_id"]].append(entry)
    result = {"imported": [], "unchanged": []}
    with store.writer_lock():
        store.conn.execute("BEGIN IMMEDIATE")
        try:
            # Validate conflicts across the entire batch before touching any source.
            pending = []
            for sid, source in sources.items():
                existing = store.source(sid)
                incoming_digest = digest(source, grouped[sid])
                if existing:
                    incoming_time = instant(source["updated_at"])
                    existing_time = instant(existing["updated_at"])
                    if incoming_time < existing_time:
                        raise ValueError(f"拒绝旧索引覆盖较新来源 {sid}")
                    if incoming_time == existing_time:
                        if incoming_digest not in {existing.get("import_digest"), digest(existing, store.entries(sid))}:
                            raise ValueError(f"同时间不同内容的来源冲突 {sid}")
                        result["unchanged"].append(sid)
                        continue
                pending.append((sid, source, incoming_digest))
            for sid, source, incoming_digest in pending:
                imported = dict(source)
                imported.pop("root_fingerprint", None)
                imported.pop("host_id", None)
                imported.update(origin="imported", import_digest=incoming_digest, imported_at=now())
                store.put_source(imported)
                incoming_paths = {entry["path"] for entry in grouped[sid]}
                for previous in store.entries(sid):
                    if previous["path"] not in incoming_paths:
                        if imported["status"] == "complete":
                            previous["status"] = "missing"
                        elif previous["status"] not in {"missing", "excluded"}:
                            previous["status"] = "unknown"
                        store.put_entry(previous)
                for entry in grouped[sid]:
                    store.put_entry(entry)
                result["imported"].append(sid)
            store.conn.commit()
        except BaseException:
            store.conn.rollback()
            raise
    return result


def encode_jsonl(manifest):
    header = {key: value for key, value in manifest.items() if key not in {"sources", "entries"}}
    rows = [{"record": "header", "data": header}]
    rows.extend({"record": "source", "data": source} for source in manifest["sources"])
    rows.extend({"record": "entry", "data": entry} for entry in manifest["entries"])
    return "\n".join(encode(row) for row in rows) + "\n"


def decode_manifest(text, jsonl=False):
    try:
        if not jsonl:
            return json.loads(text)
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        require(bool(rows) and isinstance(rows[0], dict) and rows[0].get("record") == "header", "JSONL 缺少首行 header")
        require(isinstance(rows[0].get("data"), dict), "JSONL header 数据无效")
        data = {**rows[0]["data"], "sources": [], "entries": []}
        for row in rows[1:]:
            require(isinstance(row, dict) and row.get("record") in {"source", "entry"} and "data" in row, "无效 JSONL 记录")
            data["sources" if row["record"] == "source" else "entries"].append(row["data"])
        return data
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"清单 JSON 解码失败 {exc}") from None

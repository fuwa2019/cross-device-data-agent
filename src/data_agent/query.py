import re
import unicodedata
from collections import defaultdict
from pathlib import Path, PurePosixPath

from .scanner import kind_of
from .store import now


def normalized(text):
    return unicodedata.normalize("NFC", text).casefold()


def classify(entry, source):
    path = normalized(entry["path"])
    extension = PurePosixPath(path).suffix
    tags = source.get("tags", [])
    if "statement" in tags or any(word in path for word in ("月结单", "月結單", "statement")):
        return "statement", "显式标签或路径/月结单命名规则"
    groups = {
        "weight": {".pt", ".pth", ".ckpt", ".safetensors"},
        "config": {".json", ".toml", ".yaml", ".yml", ".ini"},
        "log": {".log"},
        "image": {".jpg", ".jpeg", ".png", ".heic"},
        "document": {".pdf", ".md", ".txt", ".docx"},
        "code": {".py", ".rs", ".js", ".ts", ".sh"},
        "archive": {".zip", ".tar", ".gz", ".7z"},
    }
    for category, extensions in groups.items():
        if extension in extensions:
            return category, f"扩展名 {extension}"
    return "unknown", "命名证据不足，未读正文"


def accessibility(source, entry, check=False):
    if source.get("origin") == "imported":
        return "unknown_remote"
    if source.get("status") == "unavailable":
        return "unavailable_at_last_attempt"
    if not check:
        return "unknown_now"
    try:
        root = Path(source["root"])
        info = root.lstat()
        if kind_of(info) != "directory" or [info.st_dev, info.st_ino] != source.get("root_fingerprint"):
            return "unknown_root_changed"
        path = root
        for part in PurePosixPath(entry["path"]).parts:
            path /= part
            info = path.lstat()
            if kind_of(info) == "symlink":
                return "symlink_not_followed"
        return "accessible_now_metadata_only"
    except FileNotFoundError:
        return "not_found_now"
    except OSError:
        return "unavailable_now"


def search(store, query="", source_id=None, category=None, year=None, tag=None,
           min_size=0, max_size=None, check=False, include_missing=False):
    sources = {s["source_id"]: s for s in store.sources()}
    if source_id and source_id not in sources:
        raise ValueError(f"未知来源 {source_id}")
    terms = [normalized(term) for term in query.split()]
    result = []
    for entry in store.entries(source_id):
        if entry["status"] == "excluded" or (entry["status"] == "missing" and not include_missing):
            continue
        source = sources[entry["source_id"]]
        entry_category, basis = classify(entry, source)
        years = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", entry["path"])
        haystack = normalized(entry["path"])
        if not all(term in haystack for term in terms):
            continue
        if category and entry_category != category:
            continue
        if year and str(year) not in years:
            continue
        if tag and tag not in source.get("tags", []):
            continue
        if entry["size"] < min_size or (max_size is not None and entry["size"] > max_size):
            continue
        result.append({**entry, "device": source.get("device", source["source_id"]),
                       "root": source.get("root"), "category": entry_category,
                       "category_evidence": basis, "year_evidence": years,
                       "match_evidence": {"path_terms": terms, "category": category,
                                          "year_from_path": year, "tag": tag},
                       "availability": accessibility(source, entry, check),
                       "source_status": source["status"], "last_scan": source.get("last_attempt"),
                       "last_success": source.get("last_success"), "queried_at": now()})
    return result


def stats(store, source_id=None, group_by="category", limit=20):
    sources = {s["source_id"]: s for s in store.sources()}
    rows = [e for e in search(store, source_id=source_id) if e["kind"] == "file"]
    groups = defaultdict(list)
    for entry in rows:
        if group_by == "directory":
            key = f'{entry["source_id"]}/{PurePosixPath(entry["path"]).parent}'
        elif group_by == "extension":
            key = PurePosixPath(entry["path"]).suffix.lower() or "<none>"
        elif group_by == "source":
            key = entry["source_id"]
        elif group_by == "size":
            if entry["size"] < 1024**2:
                key = "<1MiB"
            elif entry["size"] < 1024**3:
                key = "1MiB–1GiB"
            else:
                key = ">=1GiB"
        else:
            key = entry["category"]
        groups[key].append(entry)
    identities = set()
    unique_logical = 0
    unique_allocated = 0
    unknown_allocated = 0
    repeated = []
    sizes = defaultdict(list)
    for entry in rows:
        source = sources[entry["source_id"]]
        # Never compare inode numbers between independently imported sources.
        scope = source["source_id"] if source.get("origin") == "imported" else source.get("host_id")
        identity = (scope, entry["dev"], entry["ino"])
        if not entry["ino"]:
            identity = (entry["source_id"], entry["path"])
        if identity in identities:
            repeated.append({"source_id": entry["source_id"], "path": entry["path"]})
        else:
            identities.add(identity)
            unique_logical += entry["size"]
            if entry["allocated"] is None:
                unknown_allocated += 1
            else:
                unique_allocated += entry["allocated"]
        sizes[entry["size"]].append({"source_id": entry["source_id"], "path": entry["path"]})
    overlaps = []
    local_sources = [s for s in sources.values() if s.get("origin") == "local" and s.get("root")]
    for position, first in enumerate(local_sources):
        for second in local_sources[position + 1:]:
            a, b = Path(first["root"]), Path(second["root"])
            if a.is_relative_to(b) or b.is_relative_to(a):
                overlaps.append([first["source_id"], second["source_id"]])
    return {"file_count": len(rows), "logical_bytes_by_path": sum(e["size"] for e in rows),
            "logical_bytes_unique_local_identity": unique_logical,
            "allocated_bytes_known_unique_identity": unique_allocated,
            "allocated_unknown_files": unknown_allocated,
            "hardlink_or_overlap_repeated_paths": repeated, "overlapping_sources": overlaps,
            "groups": [{"key": key, "files": len(entries), "logical_bytes_by_path": sum(e["size"] for e in entries)}
                       for key, entries in sorted(groups.items())],
            "large_files": sorted(rows, key=lambda e: (-e["size"], e["path"]))[:limit],
            "same_size_candidates": [{"size": size, "files": files, "evidence": "仅同大小，内容未确认"}
                                     for size, files in sorted(sizes.items()) if len(files) > 1],
            "warnings": ["路径逻辑字节可重复计数，各组不能直接作为可释放容量。",
                         "st_blocks 是文件系统报告的已分配字节，未处理克隆、压缩、快照或独立导入来源重叠。",
                         "统计基于最后已知索引，含 unknown/unstable，完整性见来源状态。"],
            "sources": list(sources.values())}

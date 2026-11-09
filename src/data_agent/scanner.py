import fnmatch
import os
import re
import stat
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .store import now


def excluded(path, patterns):
    parts = PurePosixPath(path).parts
    return any(fnmatch.fnmatchcase(path, pattern) or
               any(fnmatch.fnmatchcase(part, pattern) for part in parts)
               for pattern in patterns)


def signature(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def kind_of(info):
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0):
        return "symlink"
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    if stat.S_ISREG(info.st_mode):
        return "file"
    return "special"


def walk(root, patterns, on_error):
    """Yield no-follow metadata. POSIX fwalk anchors stats to directory FDs."""
    def error(exc):
        on_error(str(getattr(exc, "filename", root)), str(exc))

    if hasattr(os, "fwalk"):
        iterator = os.fwalk(root, topdown=True, onerror=error, follow_symlinks=False)
    else:
        iterator = ((base, dirs, files, None) for base, dirs, files in
                    os.walk(root, topdown=True, onerror=error, followlinks=False))
    for base, dirs, files, descriptor in iterator:
        relative_base = Path(base).relative_to(root)
        before = os.fstat(descriptor) if descriptor is not None else os.lstat(base)
        for name in sorted(dirs + files):
            relative = (relative_base / name).as_posix()
            if excluded(relative, patterns):
                if name in dirs:
                    dirs.remove(name)
                continue
            try:
                if descriptor is None:
                    first = os.lstat(Path(base) / name)
                    second = os.lstat(Path(base) / name)
                else:
                    first = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    second = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                kind = kind_of(first)
                if kind != "directory" and name in dirs:
                    dirs.remove(name)
                unstable = signature(first) != signature(second)
                if unstable:
                    on_error(relative, "元数据读取期间发生变化")
                yield relative, first, kind, unstable
            except OSError as exc:
                on_error(relative, str(exc))
                if name in dirs:
                    dirs.remove(name)
        after = os.fstat(descriptor) if descriptor is not None else os.lstat(base)
        if signature(before) != signature(after):
            on_error(relative_base.as_posix(), "目录遍历期间发生变化")


def scan(store, source_id, root, patterns=(), device=None, tags=(), rebind=False, parse=None):
    if not isinstance(source_id, str) or not re.fullmatch(r"[\w.-]{1,128}", source_id):
        raise ValueError("source_id 只能包含字母、数字、下划线、点和连字符，最多128字符")
    if not all(isinstance(pattern, str) for pattern in patterns):
        raise ValueError("排除规则必须为字符串")
    from .experiments import policy_for
    policy = policy_for(parse)
    with store.writer_lock():
        return _scan(store, source_id, root, patterns, device, tags, rebind, policy)


def _scan(store, source_id, root, patterns, device, tags, rebind, parse):
    from .experiments import parse_entry

    root = Path(os.path.abspath(Path(root).expanduser()))
    if root == Path(root.anchor):
        raise ValueError("拒绝全盘根目录扫描，请指定资料子目录")
    if store.directory.is_relative_to(root.resolve()):
        raise ValueError("状态目录必须位于来源目录之外")
    store.conn.execute("BEGIN IMMEDIATE")
    # The writer lock proves that any persisted running scan has lost its writer.
    for previous in store.scans():
        if previous["status"] == "running":
            previous.update(status="interrupted", finished_at=now())
            store.put_scan(previous)
            stale = store.source(previous["source_id"])
            if stale:
                stale.update(status="interrupted", last_attempt=previous["started_at"])
                store.put_source(stale)
    source = store.source(source_id) or {"source_id": source_id, "last_success": None}
    started = now()
    report = {"id": str(uuid4()), "source_id": source_id, "started_at": started,
              "finished_at": None, "status": "running", "errors": [], "seen": 0}
    source.update(status="running", last_attempt=started, updated_at=started)
    source.setdefault("root", str(root))
    source.setdefault("device", device or source_id)
    source.setdefault("exclude", list(patterns))
    source.setdefault("tags", list(tags))
    source.setdefault("origin", "local")
    store.put_source(source)
    store.put_scan(report)
    # Keep the OS writer lock while committing the durable recovery marker.
    store.conn.commit()
    store.conn.execute("BEGIN IMMEDIATE")
    source = store.source(source_id)
    old = {entry["path"]: entry for entry in store.entries(source_id)}
    seen = set()
    changed_subtrees = []
    status = "complete"

    def error(path, message):
        report["errors"].append({"path": path, "error": message})

    try:
        root_stat = root.lstat()
        if kind_of(root_stat) != "directory":
            raise OSError("根目录必须为真实目录，不能为符号链接")
        fingerprint = [root_stat.st_dev, root_stat.st_ino]
        if source.get("root_fingerprint") not in (None, fingerprint) and not rebind:
            raise OSError("根目录身份变化，核对挂载后使用 --rebind-root")
        can_reuse_parse = source.get("origin") == "local" and source.get("root_fingerprint") == fingerprint and not rebind
        source.update(root=str(root), device=device or source.get("device", source_id),
                      host_id=store.host_id, origin="local", root_fingerprint=fingerprint,
                      exclude=list(patterns), tags=list(tags))
        for path, info, kind, unstable in walk(root, patterns, error):
            if any(path.startswith(prefix + "/") for prefix in changed_subtrees):
                continue
            previous = old.get(path)
            if (not rebind and previous and kind == "directory" and
                    previous["dev"] != info.st_dev):
                changed_subtrees.append(path)
                error(path, "子目录文件系统身份变化，可能为挂载失联；核实后可显式 rebind")
                continue
            seen.add(path)
            entry = {"source_id": source_id, "path": path, "kind": kind,
                     "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                     "ctime_ns": info.st_ctime_ns, "dev": info.st_dev, "ino": info.st_ino,
                     "nlink": info.st_nlink, "allocated": getattr(info, "st_blocks", None),
                     "indexed_at": now(), "status": "unstable" if unstable else "observed",
                     "signature": signature(info)}
            if entry["allocated"] is not None:
                entry["allocated"] *= 512
            entry["parsed"] = parse_entry(root, entry, old.get(path) if can_reuse_parse else None, parse)
            if entry["parsed"]["state"] == "error":
                error(path, entry["parsed"]["error"])
            store.put_entry(entry)
            report["seen"] += 1
        # Recheck root identity and directory metadata after the traversal.
        ending = root.lstat()
        if signature(root_stat) != signature(ending):
            error(".", "根目录在扫描期间变化")
        if report["errors"]:
            status = "partial"
    except KeyboardInterrupt:
        status = "interrupted"
        error(".", "扫描被中断")
    except OSError as exc:
        status = "unavailable" if not seen else "partial"
        error(".", str(exc))
    except BaseException:
        store.conn.rollback()
        raise
    for path, entry in old.items():
        if path in seen:
            continue
        if excluded(path, patterns):
            entry["status"] = "excluded"
        elif status == "complete":
            entry["status"] = "missing"
        elif entry["status"] not in ("missing", "excluded"):
            entry["status"] = "unknown"
        store.put_entry(entry)
    report.update(status=status, finished_at=now())
    source.update(status=status, last_attempt=started, updated_at=report["finished_at"],
                  last_errors=report["errors"])
    if status == "complete":
        source["last_success"] = report["finished_at"]
    store.put_source(source)
    store.put_scan(report)
    store.conn.commit()
    return report

"""Bounded metadata extraction, never import or execute scanned projects."""
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import stat
import tomllib
from collections import defaultdict
from pathlib import Path, PurePosixPath

from .scanner import signature
from .store import encode

PARSER_VERSION = 1
ALLOWED_EXTENSIONS = {".json", ".toml", ".log", ".txt"}
REFERENCE_KEYS = {"config", "config_path", "result", "result_path", "results", "weight", "weights",
                  "checkpoint", "checkpoint_path", "log", "log_path", "artifact", "artifacts"}


def policy_for(config):
    config = config or {}
    if not config.get("enabled", False):
        return None
    paths = config.get("paths", [])
    extensions = config.get("extensions", [])
    limit = config.get("max_bytes", 65536)
    if not paths or not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ValueError("parse.paths 必须显式指定路径 glob 列表")
    if not extensions or not isinstance(extensions, list) or not set(extensions) <= ALLOWED_EXTENSIONS:
        raise ValueError("parse.extensions 只支持 .json/.toml/.log/.txt")
    if type(limit) is not int or not 0 < limit <= 1024 * 1024:
        raise ValueError("parse.max_bytes 必须为 1 至 1048576")
    return {"paths": paths, "extensions": extensions, "max_bytes": limit, "parser": PARSER_VERSION}


def read_bounded(root, relative, expected, limit):
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise OSError("此平台尚无经验证的 no-follow 正文读取，保留元数据索引")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(file_descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or signature(info) != expected:
                raise OSError("正文读取前文件已变化")
            content = stream.read(limit + 1)
            if len(content) > limit:
                raise OSError("正文超出上限")
            if signature(os.fstat(stream.fileno())) != expected:
                raise OSError("正文读取期间文件已变化")
            return content.decode("utf-8")
    finally:
        os.close(descriptor)


def extract(text, extension):
    fields = []
    if extension in {".json", ".toml"}:
        data = json.loads(text) if extension == ".json" else tomllib.loads(text)

        def visit(value, depth=0):
            if depth > 8 or len(fields) >= 256:
                return
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in REFERENCE_KEYS | {"run_id"}:
                        values = item if isinstance(item, list) else [item]
                        for scalar in values[:64]:
                            if isinstance(scalar, (str, int)) and not isinstance(scalar, bool):
                                fields.append((key, str(scalar)))
                    if isinstance(item, (dict, list)):
                        visit(item, depth + 1)
            elif isinstance(value, list):
                for item in value[:256]:
                    visit(item, depth + 1)
        visit(data)
    else:
        for line in text.splitlines():
            match = re.fullmatch(r"\s*(run_id|config|result|weight|checkpoint|log_path)\s*[:=]\s*([^\s]+)\s*", line)
            if match:
                fields.append(match.groups())
    run_ids = sorted({value for key, value in fields if key == "run_id" and
                      re.fullmatch(r"[\w.:-]{1,128}", value)})
    references = [{"key": key, "value": value} for key, value in fields
                  if key in REFERENCE_KEYS and len(value) <= 2048][:256]
    return {"run_ids": run_ids, "references": references}


def parse_entry(root, entry, old, policy):
    if policy is None:
        return {"state": "disabled"}
    extension = PurePosixPath(entry["path"]).suffix.lower()
    if entry["kind"] != "file" or extension not in policy["extensions"] or not any(
            fnmatch.fnmatchcase(entry["path"], pattern) for pattern in policy["paths"]):
        return {"state": "outside_policy"}
    if entry["size"] > policy["max_bytes"]:
        return {"state": "too_large"}
    key = hashlib.sha256(encode(policy).encode()).hexdigest()
    cached = old.get("parsed", {}) if old else {}
    if old and old["signature"] == entry["signature"] and cached.get("policy_key") == key and cached.get("state") == "parsed":
        return cached
    try:
        text = read_bounded(root, entry["path"], entry["signature"], policy["max_bytes"])
        return {"state": "parsed", "policy_key": key, **extract(text, extension)}
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return {"state": "error", "error": str(exc), "policy_key": key}


def role(entry):
    path = PurePosixPath(entry["path"])
    name = path.name.casefold()
    if path.suffix.lower() in {".pt", ".pth", ".ckpt", ".safetensors"}:
        return "weight"
    if any(word in name for word in ("result", "metric", "结果")):
        return "result"
    if path.suffix.lower() == ".log" or "log" in name:
        return "log"
    if path.suffix.lower() in {".json", ".toml", ".yaml", ".yml", ".ini"}:
        return "config"
    return None


def experiments(store, source_id=None):
    sources = {source["source_id"]: source for source in store.sources()}
    if source_id and source_id not in sources:
        raise ValueError(f"未知来源 {source_id}")
    entries = [entry for entry in store.entries(source_id) if entry["kind"] == "file" and
               entry["status"] not in {"missing", "excluded"}]
    index = {(entry["source_id"], entry["path"]): entry for entry in entries}
    anchors = {(entry["source_id"], str(PurePosixPath(entry["path"]).parent)) for entry in entries
               if role(entry) == "config" or entry.get("parsed", {}).get("run_ids")}
    grouped = defaultdict(list)
    for entry in entries:
        parent = PurePosixPath(entry["path"]).parent
        candidates = [str(p) for p in (parent, *parent.parents) if (entry["source_id"], str(p)) in anchors]
        if candidates and role(entry):
            grouped[(entry["source_id"], candidates[0])].append(entry)
    run_locations = defaultdict(set)
    result = []
    for (sid, directory), members in sorted(grouped.items()):
        source = sources[sid]
        roles = {name: [] for name in ("config", "log", "result", "weight")}
        run_ids = set()
        links = []
        issues = []
        for entry in members:
            roles[role(entry)].append(entry["path"])
            parsed = entry.get("parsed", {})
            run_ids.update(parsed.get("run_ids", []))
            for run_id in parsed.get("run_ids", []):
                links.append({"from": entry["path"], "run_id": run_id, "evidence": "受限文本显式 run_id"})
                run_locations[run_id].add((sid, directory))
            for reference in parsed.get("references", []):
                value = reference["value"]
                target = posixpath.normpath(posixpath.join(str(PurePosixPath(entry["path"]).parent), value))
                invalid = value.startswith(("/", "\\")) or "\\" in value or bool(re.match(r"^[A-Za-z]:", value)) or target == ".." or target.startswith("../")
                target_entry = index.get((sid, target)) if not invalid else None
                state = "outside_source_rejected" if invalid else "indexed" if target_entry else "not_indexed_or_missing"
                links.append({"from": entry["path"], "to": target, "key": reference["key"],
                              "evidence": "受限文本相对路径引用", "state": state,
                              "target_status": target_entry["status"] if target_entry else "unknown"})
                if state != "indexed":
                    issues.append(f"引用未确认 {entry['path']} → {target} ({state})")
            if parsed.get("state") in {"error", "too_large"}:
                issues.append(f"解析 {parsed['state']} {entry['path']}")
        if len(run_ids) > 1:
            issues.append("同目录多个 run_id，保持歧义")
        for name in ("config", "weight"):
            if len(roles[name]) > 1:
                issues.append(f"多个 {name} 候选，未强行配对")
        missing = [name for name, paths in roles.items() if not paths]
        result.append({"source_id": sid, "device": source.get("device", sid), "root": source.get("root"),
                       "directory": directory, "run_ids": sorted(run_ids), "roles": roles,
                       "evidence": [{"path": entry["path"], "basis": "同目录或其子目录的命名角色候选",
                                     "role": role(entry), "indexed_at": entry["indexed_at"],
                                     "status": entry["status"], "parse_state": entry.get("parsed", {}).get("state", "disabled")}
                                    for entry in members],
                       "explicit_links": links, "ambiguities": issues, "missing_roles": missing,
                       "source_status": source["status"], "last_scan": source.get("last_attempt"),
                       "availability": "unknown_remote" if source.get("origin") == "imported" else "unknown_now",
                       "note": "目录候选与显式引用分开列示；权重保留价值待人工判断"})
    for run in result:
        for run_id in run["run_ids"]:
            if len(run_locations[run_id]) > 1:
                run["ambiguities"].append(f"重复 run_id {run_id} 出现在多个来源/目录")
    return result


def markdown_overview(runs):
    from html import escape

    def code(value):
        return "<code>" + escape(json.dumps(value, ensure_ascii=False)) + "</code>"

    labels = {"config": "配置", "log": "日志", "result": "结果", "weight": "权重"}
    lines = ["# 实验关联概览", "", "依据为目录候选和显式文本引用。权重保留价值待判断。", ""]
    for number, run in enumerate(runs, 1):
        lines.extend([f"## 实验 {number}", "",
                      f"- 来源为 {code(run['source_id'])}，设备为 {code(run['device'])}",
                      f"- 根目录为 {code(run['root'])}",
                      f"- 相对目录为 {code(run['directory'])}",
                      f"- 扫描时间为 {code(run['last_scan'])}，来源状态为 {code(run['source_status'])}",
                      f"- 当前可用性为 {code(run['availability'])}",
                      f"- 显式 run ID 为 {code(run['run_ids'])}", ""])
        for role_name, paths in run["roles"].items():
            lines.extend([f"### {labels[role_name]}候选", ""])
            lines.extend([f"- {code(path)}" for path in paths] or ["尚未在索引中发现。"])
            lines.append("")
        lines.extend(["### 关联证据", ""])
        for evidence in run["evidence"]:
            lines.append(f"- {code(evidence['path'])}，依据为 {evidence['basis']}，索引时间为 {code(evidence['indexed_at'])}，条目状态为 {code(evidence['status'])}")
        lines.extend(["", "### 显式引用", ""])
        lines.extend([f"- {code(link)}" for link in run["explicit_links"]] or ["尚无受限解析证据。"])
        lines.extend(["", "### 歧义与缺失", ""])
        lines.extend([f"- {code(issue)}" for issue in run["ambiguities"]] or ["当前规则未发现额外歧义。"])
        lines.extend([f"- 未找到的角色为 {code(run['missing_roles'])}", ""])
    return "\n".join(lines) + "\n"

import argparse
import json
import os
import signal
import sqlite3
import sys
import tempfile
import tomllib
from pathlib import Path

from .exchange import decode_manifest, encode_jsonl, export_index, import_index
from .experiments import experiments, markdown_overview
from .query import search, stats
from .scanner import scan
from .store import Store


def parser():
    result = argparse.ArgumentParser(description="只读盘点与离线检索 CLI")
    result.add_argument("--version", action="version", version="0.1.0")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("scan", "sources", "scans", "search", "stats", "experiments", "export", "import"):
        command = commands.add_parser(name)
        command.add_argument("--state-dir", default="~/.local/state/data-agent")
        command.add_argument("--format", choices=("json", "jsonl", "markdown"), default="json")
        command.add_argument("--source", required=name == "scan")
        command.add_argument("--output", help="写入新的报告文件，拒绝覆盖与源目录写入")
        if name == "import":
            command.add_argument("--input", required=True)
            command.add_argument("--input-format", choices=("json", "jsonl"), default="json")
        if name == "search":
            command.add_argument("--query", default="")
            command.add_argument("--category")
            command.add_argument("--year", type=int)
            command.add_argument("--tag")
            command.add_argument("--min-size", type=int, default=0)
            command.add_argument("--max-size", type=int)
            command.add_argument("--check-access", action="store_true")
            command.add_argument("--include-missing", action="store_true")
        if name == "stats":
            command.add_argument("--group-by", choices=("source", "directory", "extension", "size", "category"), default="category")
            command.add_argument("--limit", type=int, default=20)
        if name == "scan":
            command.add_argument("--root")
            command.add_argument("--config")
            command.add_argument("--exclude", action="append", default=[])
            command.add_argument("--device")
            command.add_argument("--tag", action="append", default=[])
            command.add_argument("--rebind-root", action="store_true")
    return result


def output(data, format):
    if format == "jsonl":
        rows = data if isinstance(data, list) else [data]
        return "\n".join(json.dumps(row, ensure_ascii=True) for row in rows) + "\n"
    if format == "markdown":
        return "# 数据目录报告\n\n```json\n" + json.dumps(data, ensure_ascii=True, indent=2) + "\n```\n"
    return json.dumps(data, ensure_ascii=True, indent=2) + "\n"


def scan_options(args):
    config = {}
    options = {}
    if args.config:
        config_path = Path(args.config).resolve()
        with config_path.open("rb") as stream:
            config = tomllib.load(stream)
        options = config.get("sources", {}).get(args.source, {})
        if not args.root and options.get("root"):
            args.root = str(config_path.parent / options["root"])
    if not args.root:
        raise ValueError("scan 必须通过 --root 或配置显式指定根目录")
    root = Path(args.root).expanduser().resolve()
    state = Path(args.state_dir).expanduser().resolve()
    if state.is_relative_to(root):
        raise ValueError("状态目录必须位于来源目录之外")
    return options, config.get("parse", {})


def write_report(store, destination, rendered):
    target = Path(destination).expanduser().resolve()
    if target.is_relative_to(store.directory) and target.name in {"index.sqlite", "writer.lock"}:
        raise ValueError("不能覆盖内部状态文件")
    for source in store.sources():
        if source.get("origin") == "local" and source.get("root") and target.is_relative_to(Path(source["root"]).resolve()):
            raise ValueError("报告必须位于所有本地来源目录之外")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".data-agent-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def interrupt_handler(*_):
    raise KeyboardInterrupt


def main(argv=None):
    args = parser().parse_args(argv)
    store = None
    original_handler = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, interrupt_handler)
    try:
        options, parse = scan_options(args) if args.command == "scan" else ({}, {})
        store = Store(args.state_dir)
        if args.command not in {"scan", "import", "export"}:
            store.conn.execute("BEGIN")
        code = 0
        if args.command == "scan":
            data = scan(store, args.source, args.root,
                        options.get("exclude", []) + args.exclude,
                        args.device or options.get("device"),
                        options.get("tags", []) + args.tag, args.rebind_root, parse)
            code = {"complete": 0, "partial": 3, "interrupted": 130, "unavailable": 1}[data["status"]]
        elif args.command == "search":
            data = search(store, args.query, args.source, args.category, args.year, args.tag,
                          args.min_size, args.max_size, args.check_access, args.include_missing)
            code = 0 if data else 4
        elif args.command == "export":
            data = export_index(store, args.source)
        elif args.command == "import":
            with Path(args.input).open("rb") as stream:
                content = stream.read(128 * 1024 * 1024 + 1)
            if len(content) > 128 * 1024 * 1024:
                raise ValueError("清单超过 MVP 128 MiB 上限，请按来源拆分")
            data = import_index(store, decode_manifest(content.decode("utf-8"), args.input_format == "jsonl"))
        elif args.command == "experiments":
            data = experiments(store, args.source)
            code = 0 if data else 4
        elif args.command == "stats":
            data = stats(store, args.source, args.group_by, args.limit)
        elif args.command == "sources":
            data = store.sources()
        else:
            data = store.scans(args.source)
        rendered = encode_jsonl(data) if args.command == "export" and args.format == "jsonl" else output(data, args.format)
        if args.command == "experiments" and args.format == "markdown":
            rendered = markdown_overview(data)
        if args.output:
            write_report(store, args.output, rendered)
        else:
            sys.stdout.write(rendered)
        return code
    except (OSError, ValueError, sqlite3.Error, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('{"error":"interrupted"}', file=sys.stderr)
        return 130
    finally:
        if store:
            store.close()
        signal.signal(signal.SIGTERM, original_handler)


if __name__ == "__main__":
    raise SystemExit(main())

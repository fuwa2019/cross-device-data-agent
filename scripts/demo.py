"""Reproducible synthetic CLI demonstration. Destination must not exist."""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from make_fixture import generate


def demo(destination):
    started = time.perf_counter()
    base = Path(destination).resolve()
    base.mkdir(parents=True, exist_ok=False)
    mac = generate(base / "mac")
    gpu = generate(base / "gpu")
    config = base / "parse.toml"
    config.write_text('''[parse]
enabled = true
paths = ["QER/*"]
extensions = [".json", ".toml", ".log"]
max_bytes = 65536
''', encoding="utf-8")
    commands = []

    def run(state, *arguments, expected=0):
        command = [sys.executable, "-m", "data_agent", arguments[0],
                   "--state-dir", str(base / state), *map(str, arguments[1:])]
        beginning = time.perf_counter()
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        commands.append({"arguments": command[3:], "exit_code": result.returncode,
                         "seconds": round(time.perf_counter() - beginning, 6)})
        if result.returncode != expected:
            raise RuntimeError(f"CLI unexpected exit {result.returncode}: {result.stderr} {result.stdout}")
        if result.stderr:
            raise RuntimeError(f"unexpected diagnostics: {result.stderr}")
        return json.loads(result.stdout) if result.stdout.strip() else None

    for sid, root, state in (("mac-demo", mac, "local-state"), ("gpu025-demo", gpu, "remote-state")):
        first = run(state, "scan", "--source", sid, "--root", root, "--exclude", "excluded", "--config", config)
        second = run(state, "scan", "--source", sid, "--root", root, "--exclude", "excluded", "--config", config)
        assert first["seen"] == second["seen"]
        run(state, "export", "--source", sid, "--format", "json", "--output", base / f"{sid}.json")
    run("remote-state", "export", "--source", "gpu025-demo", "--format", "jsonl", "--output", base / "gpu.jsonl")
    imported = run("local-state", "import", "--input", base / "gpu.jsonl", "--input-format", "jsonl")
    assert imported["imported"] == ["gpu025-demo"]
    again = run("local-state", "import", "--input", base / "gpu025-demo.json")
    assert again["unchanged"] == ["gpu025-demo"]
    statements = run("local-state", "search", "--category", "statement", "--year", "2025")
    assert len(statements) == 2
    run("local-state", "search", "--query", "QER", "--source", "gpu025-demo")
    report = run("local-state", "stats", "--group-by", "source")
    assert report["file_count"] == 26
    run("local-state", "search", "--query", "not-present", expected=4)
    run("local-state", "experiments", "--source", "gpu025-demo", "--format", "markdown",
        "--output", base / "experiments.md")
    experiments = run("local-state", "experiments", "--source", "gpu025-demo")
    (base / "experiments.json").write_text(json.dumps(experiments, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert len(experiments) == 2
    assert "result" in experiments[1]["missing_roles"]
    mac.rename(base / "mac-offline")
    offline = run("local-state", "scan", "--source", "mac-demo", "--root", mac, expected=1)
    assert offline["status"] == "unavailable"
    history = run("local-state", "search", "--source", "mac-demo", "--query", "月结单")
    assert history[0]["availability"] == "unavailable_at_last_attempt"
    remote_history = run("local-state", "search", "--source", "gpu025-demo", "--check-access")
    assert all(row["availability"] == "unknown_remote" for row in remote_history)
    run("local-state", "export", "--format", "json", "--output", base / "combined.json")
    run("fresh-state", "import", "--input", base / "combined.json")
    assert len(run("fresh-state", "search", "--query", "月结单")) == 2
    # The executable demo may rename synthetic roots solely to simulate offline status.
    summary = {"environment": {"system": platform.system(), "release": platform.release(),
                               "machine": platform.machine(), "python": platform.python_version()},
               "synthetic_sources": 2, "regular_files_per_source": 13,
               "indexed_file_paths_total": report["file_count"],
               "experiment_directories": len(experiments), "commands": commands,
               "total_seconds": round(time.perf_counter() - started, 6),
               "real_device_validation": "未进行"}
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2).replace(str(base), "DEMO_ROOT")
    (base / "demo-summary.json").write_text(summary_text + "\n", encoding="utf-8")
    print(summary_text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    demo(parser.parse_args().destination)

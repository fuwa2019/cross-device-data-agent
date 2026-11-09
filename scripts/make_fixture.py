"""Create synthetic data only, refusing any existing destination."""
import argparse
import json
import os
from pathlib import Path


def generate(destination):
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    files = {
        "QER/run-a/config.json": json.dumps({"run_id": "qer-001", "result": "result.json", "weight": "model.pt"}),
        "QER/run-a/result.json": '{"run_id":"qer-001","score":0.91}',
        "QER/run-a/train.log": "run_id=qer-001\n",
        "QER/run-a/model.pt": "SYNTHETIC WEIGHT DO NOT LOAD",
        "QER/run-b/config.json": '{"run_id":"qer-001","result":"missing.json"}',
        "QER/run-b/config-extra.toml": 'run_id = "qer-alt"\n',
        "QER/run-b/model.pt": "SYNTHETIC SECOND WEIGHT",
        "QER/run-b/epoch-2.pt": "SYNTHETIC THIRD WEIGHT",
        "券商/2025/示例证券 月结单 2025-12.pdf": "SYNTHETIC STATEMENT",
        "券商/未确定.pdf": "SYNTHETIC UNKNOWN",
        "中文 空格/$(echo NEVER_EXECUTE);'文档.txt": "SYNTHETIC DATA",
        "excluded/secret.txt": "SYNTHETIC EXCLUSION",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    with (root / "large.bin").open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    try:
        os.link(root / "large.bin", root / "large-hardlink.bin")
        (root / "loop").symlink_to(root, target_is_directory=True)
    except OSError:
        pass
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    generate(parser.parse_args().destination)

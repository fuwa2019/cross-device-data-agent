# 跨设备只读数据目录

M0–M4 本地 MVP。指定目录扫描、SQLite 持久目录、离线检索、空间统计、实验证据及版本化索引交换。Python 3.11+，零运行时第三方依赖，构建使用 setuptools。

## 安装与完整演示

以下命令在仓库根目录执行。演示目标必须为新目录。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/data-agent --help
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/demo.py .demo/first-run
```

演示生成两个隔离来源，每个包含 13 个被索引的普通文件、中文/特殊字符路径、硬链接、稀疏大文件及符号链接。运行扫描、重扫、检索、统计、远端清单导入、离线查询与新状态目录恢复。演示脚本会重命名自己生成的合成目录以模拟离线。命令和耗时保存在目标的 `demo-summary.json`。

开发时可用 `PYTHONPATH=src python3 -m unittest discover -s tests -v`。安装后修改代码需重新安装。macOS 实测情况见 [验收记录](docs/ACCEPTANCE.md)。

## 扫描与来源

```sh
python3 scripts/make_fixture.py .demo/manual
.venv/bin/data-agent scan --source mac-demo --root .demo/manual --state-dir .state --exclude excluded --exclude '*.tmp' --device mac-demo --tag demo
.venv/bin/data-agent sources --state-dir .state
.venv/bin/data-agent scans --source mac-demo --state-dir .state
```

`source_id` 是稳定来源身份，由使用者指定，与盘符/挂载路径分离。相同目录用于两个 source_id 时会分别索引。来源根目录变动时检查文件系统身份，确需重新绑定可增加 `--rebind-root`。每个 source_id 应有单一权威扫描端。

默认不跟随符号链接。必须显式指定资料子目录，拒绝全盘根目录及以符号链接作为根目录。源目录内不创建状态，`--state-dir` 必须在源目录之外。默认状态为 `~/.local/state/data-agent`，请确认它位于本地磁盘，尤其是集群 home 可能位于 NFS。共享目录可作为扫描来源，活动数据库禁止放 SMB/NFS 或由多台机器共同写入。

可选 `--config examples/config.toml`，根目录相对于配置文件解析。命令行 `--root` 优先，排除规则和标签与配置列表合并。排除规则采用区分大小写的 fnmatch，匹配完整 POSIX 相对路径或任一目录/文件组件。`excluded` 排除整棵同名子树，`*.tmp` 匹配任意组件，`QER/*` 可跨多级目录。每次扫描使用本次提供的配置与参数。

扫描状态为 complete、partial、interrupted、unavailable。只有 complete 会将遍历未见的旧条目标为 missing，其他状态保留历史并标 unknown。改变排除规则时旧条目标 excluded。已索引子目录的文件系统设备身份改变时保留历史 unknown，核实挂载后再决定是否显式 rebind。底层文件系统静默返回陈旧或空目录且身份未变化的情况仍需现场排查。错误可在 scans 中追踪，并随来源 last_errors 导出。中断可直接重跑。SIGKILL 后事务回滚，持久 running 标记在下次扫描获得独占锁后转为 interrupted。

每次完整遍历元数据，按来源/相对路径更新索引。正文可按签名和策略复用解析缓存。文件系统持续变化时没有一致快照保证，已观察到的变化标 unstable 或 partial。读取可能改变 atime。

## 检索与统计

```sh
.venv/bin/data-agent search --query 'QER config' --source mac-demo --state-dir .state
.venv/bin/data-agent search --category statement --year 2025 --state-dir .state
.venv/bin/data-agent search --query '中文 空格' --state-dir .state --format jsonl
.venv/bin/data-agent search --query '月结单' --state-dir .state --check-access
.venv/bin/data-agent stats --source mac-demo --group-by directory --state-dir .state
```

关键词按空白分词，全部字面子串匹配路径，使用 Unicode NFC/casefold。支持 `--source`、`--category`、`--year`、`--tag`、`--min-size`、`--max-size`。分类包括 statement、weight、config、log、image、document、code、archive、unknown。来源标签 `statement` 可显式指定月结单类别。年份取自路径证据，不用 mtime 冒充账单年份。难以判定的文件保留为 unknown，可用路径查询交给 Agent 继续判断。

结果包括 device、root、相对 path、匹配/分类/年份证据、indexed_at、last_scan、last_success、source_status 和 availability。默认当前状态为 unknown_now。`--check-access` 只探测本机元数据，历史离线状态会保留提示。远端导入始终为 unknown_remote。可用 `--include-missing` 查历史缺失项。

stats 的 `--group-by` 支持 source、directory、extension、size、category，`--limit` 控制大文件列表。directory 为直属父目录分组。

- `logical_bytes_by_path` 为所有路径的逻辑字节之和。
- `logical_bytes_unique_local_identity` 以本机 host/dev/inode 去重，独立导入来源的身份仅在该来源内去重。
- `allocated_bytes_known_unique_identity` 来自 st_blocks，未提供该值的文件另计数。
- 硬链接/重叠来源路径另列，分组数值不能直接作为可释放空间相加。克隆、压缩、快照等会进一步影响实际可释放量。
- `same_size_candidates` 只有大小证据。

## 实验关联与正文范围

```sh
.venv/bin/data-agent experiments --source mac-demo --state-dir .state --format json
.venv/bin/data-agent experiments --source mac-demo --state-dir .state --format markdown --output .demo/experiment-report.md
```

默认仅用目录与文件名给出配置、日志、结果和权重候选。候选目录来自配置文件或已解析的显式 run ID 文件，产物归入最近的候选父目录。共享父目录、多层配置的真实布局需用授权样本核实，结果始终保留证据与歧义。

按需在配置中打开受限解析，再重新扫描。

```toml
[parse]
enabled = true
paths = ["QER/*"]
extensions = [".json", ".toml", ".log"]
max_bytes = 65536
```

须同时指定路径、类型和大小，最高 1 MiB。支持 JSON、TOML 和限定键日志/文本行，提取 run_id 及 config/result/weight/checkpoint 等已列出的路径引用。仅保留这些字段的证据，JSON/TOML 不支持配置执行。权重只读元数据。POSIX 通过 no-follow 目录描述符逐级读取文本并比对前后签名。Windows 受限正文读取尚未实测，缺少该能力时返回解析错误及 partial。

多配置、多权重、重复 run ID、缺失结果、失效或越界引用会明确列出。目录同处只形成候选关系。权重价值由后续人工或选定 Agent 判断。概览输出到单独报告目录。

[合成实验概览](examples/experiments.md)和[结构化清单](examples/experiments.json)可直接阅读。示例中的根目录已替换为 `/synthetic/demo`。

## 导出、导入与远端

```sh
.venv/bin/data-agent export --source mac-demo --state-dir .state --format json --output .demo/mac-index.json
.venv/bin/data-agent export --source mac-demo --state-dir .state --format jsonl --output .demo/mac-index.jsonl
.venv/bin/data-agent import --state-dir .demo/import-state --input .demo/mac-index.jsonl --input-format jsonl
.venv/bin/data-agent search --state-dir .demo/import-state --query QER
```

JSON 清单 format 为 data-agent-index，version 为 1。JSONL 首行为 header，后续为 source/entry 记录。导出在读事务中取得一致状态。JSON/JSONL 可导入，Markdown 用于阅读。导入先校验再执行整批事务，复合键为 source_id/path，重复导入幂等，旧结果拒绝覆盖新索引，同时间不同内容报冲突。来源 updated_at 使用带时区 UTC 时间，需保证设备时钟正确。

较新清单遗漏的历史项在 complete 时标 missing，在 partial/interrupted/unavailable 时保留 unknown。清单格式不受支持时不更新已有索引。MVP 导入上限 128 MiB，扫描、检索和交换使用内存收集，较大数据需按来源拆分并实测。

所有命令支持 `--format json|jsonl|markdown` 与 `--output`。机器结果在 stdout，诊断在 stderr。输出到文件会拒绝覆盖现有文件及写入已登记的本机来源，使用临时文件完成写入后原子发布。请将报告始终放在独立目录。

GPU025 路线为远端本机运行 scan/export，通过已有 SSH 配置只传元数据，再本地 import。具体模板见 [远端验证](docs/REMOTE.md)，真实连接尚待验证。

## 退出码与故障处理

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 运行失败、来源不可访问、坏清单、并发写入或输出冲突 |
| 2 | CLI 参数错误 |
| 3 | 部分完成，检查 errors 和 scans |
| 4 | 查询完成且无匹配 |
| 130 | SIGINT/SIGTERM 中断 |

权限失败时使用相同来源重跑可恢复。来源离线时继续 search，不将历史记录当作当前位置存在的证明。根目录身份变化时先核对挂载，再决定是否 rebind。清单冲突时保留双方清单，检查来源身份与时钟。写锁冲突时等待当前扫描或导入完成后重试。

## 范围与交接

当前完成 M0–M4 只读目录 MVP。现场覆盖、限制及复现证据见 [ACCEPTANCE](docs/ACCEPTANCE.md)，接手说明见 [HANDOFF](docs/HANDOFF.md)，每步研究见 [M0](docs/research/M0.md)、[M1](docs/research/M1.md)、[M2](docs/research/M2.md)、[M3](docs/research/M3.md)、[M4](docs/research/M4.md)。M5 的 DS/最小 Web UI 为后续迭代，M6 云盘归档与受控整理、M7 更多设备按任务书顺序推进。

public 仓库仅含实现、合成示例和交付记录。原始个人需求文档、本机索引、合成运行目录留在本地并由 .gitignore 排除。第三方研究项目的许可证与采用方式记录在研究文档中，本实现使用 Python 标准库。

# 接手说明

## 已交付

本轮完成任务书 M0–M4 的本地只读 MVP，需求依据为用户确认的产品基线 v0.2。public 仓库为 fuwa2019/cross-device-data-agent。原始个人任务书、需求基线与历史访谈仅留用户本机；本文件、README、research 与 ACCEPTANCE 足够在新环境复现首轮范围。

M0 提供 Python 包、data-agent 入口、配置和合成生成器。M1 提供稳定来源、无跟随链接扫描、SQLite、状态及失败保留。M2 提供空间计量、分类和路径/结构化检索。M3 提供带证据和歧义的实验清单，受限解析可选。M4 提供版本化 JSON/JSONL 导入导出、两端模拟、远端模板和验收记录。

## 运行入口

按 README 创建 .venv 并 pip install .，运行 `data-agent --help`。测试为 `python -m unittest discover -s tests -v`。完整合成演示为 `python scripts/demo.py <全新目录>`，必须从安装了包的 Python 环境调用。

## 代码结构

| 文件 | 责任 |
| --- | --- |
| src/data_agent/cli.py | 参数、退出码、配置、输出保护 |
| src/data_agent/store.py | schema v1、持久化、OS writer 锁 |
| src/data_agent/scanner.py | 只读遍历、状态、历史保留 |
| src/data_agent/query.py | 字面检索、分类、空间汇总 |
| src/data_agent/experiments.py | 受限解析、缓存、实验候选/显式证据 |
| src/data_agent/exchange.py | 清单 v1、校验、时序冲突、事务导入 |
| scripts/make_fixture.py | 全合成文件树 |
| scripts/demo.py | 正常 CLI 入口端到端验证 |

## 状态与一致性

(source_id, relative POSIX path) 为索引键。状态目录在来源之外、本地文件系统上。使用 SQLite rollback journal 和 OS writer 锁，独占覆盖运行标记提交与主更新事务。SIGKILL 后保留上次已提交条目，下一次扫描获得锁后恢复 running 状态。原始数据始终由设备上的文件系统保管。

扫描完整遍历元数据，重用按 signature + policy + parser-version 键的解析结果。解析只保存 run_id/有限路径引用，文件内容作为数据。上下文中的指令、脚本与 checkpoint 不进入执行路径。输出证据区分目录同处和文本显式引用。

清单时序依赖源端带时区时间，单 source_id 应只有一个权威写入端。重复导入跳过，旧版本拒绝，同时间不同内容报冲突。部分清单遗漏项保留 unknown。导入来源不会用本机同路径冒充远端在线。跨设备并发同步、时钟冲突自动解决超出本轮。

## 已知限制与下一步

macOS arm64 完成合成与故障验证。GPU025、Windows、fnOS/NAS、真实 QER 和真实大规模数据尚待现场测试，具体清单在 ACCEPTANCE。Windows 元数据回退路径尚未实机验证，安全正文读取暂仅 POSIX no-follow 能力可用。扫描/检索在内存中组织条目，导入有 128 MiB 上限。

先完成 GPU025 少量授权样本和真实实验布局验证，按 REMOTE 模板操作。后续按 M5 开始 DS 与最小 fnOS Web UI，每步继续 GitHub 方案研究、论坛避坑、最小实现和验证。M6 为 115 归档/受控整理，M7 为更多设备与恢复演练。需要对应访问与具体操作授权，保留本轮只读边界。

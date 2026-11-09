# M0–M4 验收记录

日期为 2026-11-09，北京时间。研究与开发在 macOS 上完成。原始需求依据为产品需求基线 v0.2 与 Agent 任务书 1.0。

## 环境与执行

环境为 Darwin 25.5.0、arm64、Python 3.13.18。运行时仅 Python 标准库及其 SQLite。测试全部使用临时合成文件或项目内合成演示目录。

实际执行过的主要命令如下。

```sh
# M0 初始安装。首次沙箱网络失败，授权网络重跑后成功。
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir .
.venv/bin/data-agent --help
python3 scripts/make_fixture.py .demo/mac

# 开发回归与语法检查。
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src scripts tests

# 最终包隔离安装与正常入口验证。
python3 -m venv .demo/clean-env
.demo/clean-env/bin/python -m pip install --no-cache-dir .
.demo/clean-env/bin/data-agent --help
.demo/clean-env/bin/python -m unittest discover -s tests -v
.demo/clean-env/bin/python scripts/demo.py .demo/installed-run

# 源码更新后的完整演示。
PYTHONPATH=src python3 scripts/demo.py .demo/final-source-run
```

最终验证结果见末节。上述目录均为当次验证目录，重新运行时请使用全新目标。

## 分步结果

| 步骤 | 交付与验证 |
| --- | --- |
| M0 | 干净 venv 安装成功、--help 可运行、合成夹具可创建。构建曾受沙箱 DNS 阻塞，授权网络重跑解决。 |
| M1 | 幂等扫描、新增/变动更新、持久化、链接循环/越界不跟随、离线/失败保留、中断重跑。 |
| M2 | 中文/空格/特殊字符字面检索、同名多来源、分类与年份、硬链接/重叠来源、逻辑与分配字节分列。 |
| M3 | 已知关系、显式 run ID/相对引用、重复 ID、多配置多权重、缺失结果、越界/失效引用、安全受限解析与缓存。 |
| M4 | JSON/JSONL 往返、多来源、幂等、旧时间拒绝、同时间冲突、坏格式和整批保护、部分清单遗漏历史保留。 |

## 故障与边界证据

- `test_real_permission_failure_and_preservation` 在普通 macOS 用户下真正 chmod(0)，扫描返回 3/partial，旧子树条目为 unknown，恢复权限后重跑成功。
- `test_signals_concurrent_writer_and_read_query` 启动通过 main 入口的真实子进程，用测试包装器暂停遍历。扫描期间 search 成功，第二个 writer 返回 1。真实发送 SIGTERM 后返回 130/interrupted，SIGKILL 后下一次扫描将 running 转为 interrupted，条目保持一致。
- `test_nested_mount_identity_change_preserves_history` 注入子树设备身份变化，扫描返回 partial 并保留旧子树 unknown。真实挂载失联尚待设备现场验证。
- `test_changed_during_scan` 在两次 stat 间真实改写合成文件，触发 unstable/partial。文件系统全程一致快照仍未保证。
- `test_batch_and_sparse_source_snapshot` 生成 500 个小文件、原有样本和一个 16 MiB 稀疏文件，共 502 个普通文件。两次扫描后逐项大小、mtime、内容 SHA-256 和文件名/结构保持一致。哈希由测试执行，扫描器没有默认哈希或读取大文件正文。
- `test_cli_exit_codes_outputs_and_source_protection` 验证退出码 1/4、机器 stdout、报告拒绝覆盖、源目录输出拒绝和源内状态目录预检。
- `test_safe_open_rejects_symlink_parent` 在元数据采集后将目录替换为符号链接，受限正文读取拒绝跟随。
- 解析缓存测试确认同策略未变化文件不重读，导入来源转换为本地扫描时重新读取授权文本，权重始终位于解析范围之外。
- JSON/JSONL 坏格式、不兼容版本、旧清单和同时间不同内容均拒绝，现有条目数量保持不变。partial 清单遗漏历史条目时保留 unknown。

测试曾有一项断言失败，原因是测试命令助手在参数末尾附加默认 state-dir，覆盖了被测参数。修正测试参数顺序后重跑通过。验收结果未以失败运行替代。

## 完整演示

脚本创建 mac-demo 与 gpu025-demo 两个隔离来源及两个独立状态目录。每来源索引 13 个普通文件，包含两条大文件路径指向同一合成 inode，另有目录与符号链接。最终按路径共 26 个普通文件，按年份和类别查询到 2 条合成月结单，GPU 模拟来源输出 2 个实验目录。

21 个正常 CLI 命令包含生成后的扫描/重扫、元数据导出、跨状态导入/幂等导入、QER/账单查询、空间统计、Markdown/JSON 实验概览、Mac 模拟离线、离线历史查询、远端 unknown 查询、整体清单在第三个状态目录恢复。

首次源码演示耗时 0.768232 秒，干净安装版本首次演示耗时 0.747778 秒。记录为此合成树和本机环境的墙钟耗时，含 Python CLI 进程启动。最新一次结果及逐命令耗时在 [合成演示记录](../examples/demo-summary.json)。以上不能外推 16 TB 或真实 GPU025 性能。

## 现场验证项

| 项目 | 当前证据 | 待现场验证 |
| --- | --- | --- |
| macOS | 本机合成数据、实际权限/信号/并发测试 | 用户授权资料根目录、真实容量、排除规则、敏感文件命名与账单样本 |
| GPU025/SSH | 两个隔离目录与独立状态库模拟、远端命令模板 | 已有 SSH Host、Python、当前任务、真实 QER 布局、目录权限、网络/本地状态磁盘、清单传回、时钟与性能 |
| Windows | 平台无关业务逻辑测试，代码含元数据遍历回退 | Windows 实机、盘符变动、长路径、junction/reparse、硬链接、权限、锁与退出码。受限正文读取需验证并补足平台能力 |
| fnOS/NAS | 离线清单语义本地验证 | NAS 本地目录、SMB/NFS 作为来源的失败行为、状态数据库必须本地；部署属于后续 |
| 大规模与恢复 | 合成清单恢复和 502 文件回归 | 真实文件数、内存、索引大小、扫描中持续训练变化、关键资料恢复演练 |

云盘、DeepSeek、Web UI、iPhone 和原文件管理进入后续任务书迭代。恢复时间与恢复点目标尚待实测，当前验收只覆盖元数据目录恢复。

## 最终验证结果

最终 wheel 为 cross_device_data_agent-0.1.0-py3-none-any.whl，SHA-256 为 `f06b6fe32db2c7f6d920704255103701ee016ca33464a9581cd88b200edc3830`。从同一 wheel 重新安装到 .venv 与 .demo/clean-env 后，隔离安装环境中运行 23 个回归，全部通过（0.754 秒）。源码套件也为 23 个独立用例且全部通过。

```sh
.venv/bin/python -m pip wheel --no-cache-dir --no-deps . --wheel-dir dist
.venv/bin/python -m pip install --no-index --force-reinstall dist/cross_device_data_agent-0.1.0-py3-none-any.whl
.demo/clean-env/bin/python -m pip install --no-index --force-reinstall dist/cross_device_data_agent-0.1.0-py3-none-any.whl
.demo/clean-env/bin/python -m unittest discover -s tests -v
.demo/clean-env/bin/python scripts/demo.py .demo/release-run
```

最终已安装包演示运行 21 条 CLI 命令，共耗时 0.773078 秒；逐命令参数、返回码及耗时在 examples/demo-summary.json。另执行 16 条 README/示例配置命令全部返回 0，包含配置相对根目录解析、筛选、两种清单与 Markdown 输出。compileall 通过。

GitHub API 已核实 fuwa2019/cross-device-data-agent 的 visibility 为 PUBLIC。公开文件经过个人路径检查，实验示例根目录替换为 /synthetic/demo。源码、文档、合成示例进入仓库，原始个人需求文档与运行索引保留本地。

研究流程中先完成各步候选源码/README/许可证研究与论坛检索，dust/Sacred/sqlite-utils 的完整依赖声明在最终交付复核补读，记录已明确标注该时序。Python 3.11/3.12 尚未单独实跑，当前实测解释器为 3.13.18。

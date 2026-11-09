# GPU025 现场验证模板

此文件为待执行模板。尚未连接 GPU025，尚未验证其 Python、路径、权限、SSH、当前任务和磁盘类型。

## 访问与运行条件

使用已有 SSH Host 配置进入设备，由操作者核对 GPU025 解析到预期机器。实际执行前确认授权的 QER 子目录、目录权限、当前研究任务、Python 3.11+ 和本地状态磁盘。集群 home 常见 NFS，需要单独选择本地状态目录并检查容量。保留来源 ID gpu025-qer，避免不同设备共用同一来源身份。

本地可构建 wheel 后仅传安装包。在远端安装 wheel 的独立虚拟环境，避免修改研究项目依赖。也可在独立开发目录取得本仓库后按 README 安装。下列路径均为占位符，须先替换。

```sh
# 本机运行，使用现有 Host 配置。
ssh GPU025
```

进入远端后的命令模板如下。

```sh
python3 --version
# 替换为已授权的资料子目录、已核实的本地状态磁盘及独立报告目录。
SOURCE_ROOT='/path/to/authorized/QER'
STATE_DIR='/path/to/local-disk/data-agent-state'
REPORT_DIR='/path/to/local-disk/data-agent-reports'
# 使用独立虚拟环境中已安装的 data-agent。
data-agent scan --source gpu025-qer --device GPU025 --root "$SOURCE_ROOT" --state-dir "$STATE_DIR" --exclude .git
# 检查扫描退出码。partial/unavailable 时先检查 scans，历史仍可导出。
data-agent scans --source gpu025-qer --state-dir "$STATE_DIR"
data-agent export --source gpu025-qer --state-dir "$STATE_DIR" --format json --output "$REPORT_DIR/gpu025-index-v1.json"
```

需要正文关联时在独立配置文件中按 README 指定范围，并给 scan 增加 `--config`。先用少量授权样本验证 run_id/相对路径引用。保留 YAML 为元数据候选，当前正文解析仅支持 JSON/TOML/限定日志与文本。

回到本机只传清单。

```sh
# 替换远端报告路径，并选择尚不存在的本地文件。
scp GPU025:/path/to/local-disk/data-agent-reports/gpu025-index-v1.json .demo/gpu025-index-v1.json
.venv/bin/data-agent import --state-dir .state --input .demo/gpu025-index-v1.json
.venv/bin/data-agent search --source gpu025-qer --query QER --state-dir .state
.venv/bin/data-agent experiments --source gpu025-qer --state-dir .state --format markdown --output .demo/gpu025-overview.md
```

现场验证需记录授权范围、环境、文件数、耗时、扫描/解析错误、实验布局匹配情况及清单大小。对来源离线、部分子树失联、中断恢复和时钟一致性进行核实。上述清单只包含路径、标签、状态和有限关联证据，原文件保留在设备端。

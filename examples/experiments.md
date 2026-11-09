# 实验关联概览

依据为目录候选和显式文本引用。权重保留价值待判断。

## 实验 1

- 来源为 <code>&quot;gpu025-demo&quot;</code>，设备为 <code>&quot;gpu025-demo&quot;</code>
- 根目录为 <code>&quot;/synthetic/demo/gpu&quot;</code>
- 相对目录为 <code>&quot;QER/run-a&quot;</code>
- 扫描时间为 <code>&quot;2026-11-09T11:52:37.879119+00:00&quot;</code>，来源状态为 <code>&quot;complete&quot;</code>
- 当前可用性为 <code>&quot;unknown_remote&quot;</code>
- 显式 run ID 为 <code>[&quot;qer-001&quot;]</code>

### 配置候选

- <code>&quot;QER/run-a/config.json&quot;</code>

### 日志候选

- <code>&quot;QER/run-a/train.log&quot;</code>

### 结果候选

- <code>&quot;QER/run-a/result.json&quot;</code>

### 权重候选

- <code>&quot;QER/run-a/model.pt&quot;</code>

### 关联证据

- <code>&quot;QER/run-a/config.json&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880866+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>
- <code>&quot;QER/run-a/model.pt&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880899+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>
- <code>&quot;QER/run-a/result.json&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880923+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>
- <code>&quot;QER/run-a/train.log&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880967+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>

### 显式引用

- <code>{&quot;from&quot;: &quot;QER/run-a/config.json&quot;, &quot;run_id&quot;: &quot;qer-001&quot;, &quot;evidence&quot;: &quot;受限文本显式 run_id&quot;}</code>
- <code>{&quot;from&quot;: &quot;QER/run-a/config.json&quot;, &quot;to&quot;: &quot;QER/run-a/result.json&quot;, &quot;key&quot;: &quot;result&quot;, &quot;evidence&quot;: &quot;受限文本相对路径引用&quot;, &quot;state&quot;: &quot;indexed&quot;, &quot;target_status&quot;: &quot;observed&quot;}</code>
- <code>{&quot;from&quot;: &quot;QER/run-a/config.json&quot;, &quot;to&quot;: &quot;QER/run-a/model.pt&quot;, &quot;key&quot;: &quot;weight&quot;, &quot;evidence&quot;: &quot;受限文本相对路径引用&quot;, &quot;state&quot;: &quot;indexed&quot;, &quot;target_status&quot;: &quot;observed&quot;}</code>
- <code>{&quot;from&quot;: &quot;QER/run-a/result.json&quot;, &quot;run_id&quot;: &quot;qer-001&quot;, &quot;evidence&quot;: &quot;受限文本显式 run_id&quot;}</code>
- <code>{&quot;from&quot;: &quot;QER/run-a/train.log&quot;, &quot;run_id&quot;: &quot;qer-001&quot;, &quot;evidence&quot;: &quot;受限文本显式 run_id&quot;}</code>

### 歧义与缺失

- <code>&quot;重复 run_id qer-001 出现在多个来源/目录&quot;</code>
- 未找到的角色为 <code>[]</code>

## 实验 2

- 来源为 <code>&quot;gpu025-demo&quot;</code>，设备为 <code>&quot;gpu025-demo&quot;</code>
- 根目录为 <code>&quot;/synthetic/demo/gpu&quot;</code>
- 相对目录为 <code>&quot;QER/run-b&quot;</code>
- 扫描时间为 <code>&quot;2026-11-09T11:52:37.879119+00:00&quot;</code>，来源状态为 <code>&quot;complete&quot;</code>
- 当前可用性为 <code>&quot;unknown_remote&quot;</code>
- 显式 run ID 为 <code>[&quot;qer-001&quot;, &quot;qer-alt&quot;]</code>

### 配置候选

- <code>&quot;QER/run-b/config-extra.toml&quot;</code>
- <code>&quot;QER/run-b/config.json&quot;</code>

### 日志候选

尚未在索引中发现。

### 结果候选

尚未在索引中发现。

### 权重候选

- <code>&quot;QER/run-b/epoch-2.pt&quot;</code>
- <code>&quot;QER/run-b/model.pt&quot;</code>

### 关联证据

- <code>&quot;QER/run-b/config-extra.toml&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880649+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>
- <code>&quot;QER/run-b/config.json&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880736+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>
- <code>&quot;QER/run-b/epoch-2.pt&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880773+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>
- <code>&quot;QER/run-b/model.pt&quot;</code>，依据为 同目录或其子目录的命名角色候选，索引时间为 <code>&quot;2026-11-09T11:52:37.880798+00:00&quot;</code>，条目状态为 <code>&quot;observed&quot;</code>

### 显式引用

- <code>{&quot;from&quot;: &quot;QER/run-b/config-extra.toml&quot;, &quot;run_id&quot;: &quot;qer-alt&quot;, &quot;evidence&quot;: &quot;受限文本显式 run_id&quot;}</code>
- <code>{&quot;from&quot;: &quot;QER/run-b/config.json&quot;, &quot;run_id&quot;: &quot;qer-001&quot;, &quot;evidence&quot;: &quot;受限文本显式 run_id&quot;}</code>
- <code>{&quot;from&quot;: &quot;QER/run-b/config.json&quot;, &quot;to&quot;: &quot;QER/run-b/missing.json&quot;, &quot;key&quot;: &quot;result&quot;, &quot;evidence&quot;: &quot;受限文本相对路径引用&quot;, &quot;state&quot;: &quot;not_indexed_or_missing&quot;, &quot;target_status&quot;: &quot;unknown&quot;}</code>

### 歧义与缺失

- <code>&quot;引用未确认 QER/run-b/config.json → QER/run-b/missing.json (not_indexed_or_missing)&quot;</code>
- <code>&quot;同目录多个 run_id，保持歧义&quot;</code>
- <code>&quot;多个 config 候选，未强行配对&quot;</code>
- <code>&quot;多个 weight 候选，未强行配对&quot;</code>
- <code>&quot;重复 run_id qer-001 出现在多个来源/目录&quot;</code>
- 未找到的角色为 <code>[&quot;log&quot;, &quot;result&quot;]</code>

# 合同目录
此目录包含了 NetTwin-SOC 的 API 合同定义以及示例数据文件。
## 版本
**合同版本：1.1 版**
## 目的
- **samples/**：与 DOC C 模式相匹配的示例 JSON 文件（用于前端模拟和后端测试）
- **schemas/**：（可选）JSON 模式或 OpenAPI 定义
## 使用方法
### 前端模拟模式
前端可以在开发过程中从“samples/*.json”文件夹中加载样本数据，以模拟 API 响应。
### 后端测试
后端测试确保 API 的输出与“samples/*.json”文件中的结构相匹配。
### 基础数据
`backend/scripts/seed_samples.py` 能够根据实际的数据库记录重新生成样本。
## 模式变更流程
1. 先更新文档 C（权威来源）2. 更新“samples/*.json”文件以符合新的格式规范3. 更新后端的 Pydantic 模型定义4. 更新前端的 TypeScript 类型定义5. 执行合同合规性测试
## 示例文件
| 文件 | 描述 | DOC C 参考文献 ||------|-------------|-----------------|
| `flow.sample.json` | 流程记录示例 | C1.2 |
| `alert.sample.json` | 警报示例 | C1.3 |
| `graph.sample.json` | 拓扑图响应 | C5.1 |
| `investigation.sample.json` | 代理调查 | C1.4 |
| `recommendation.sample.json` | 代理推荐 | C1.5 |
| `actionplan.sample.json` | 双重行动计划 | C2.1 |
| `dryrun.sample.json` | 双重干运行结果 | C2.2 |
| `evidencechain.sample.json` | 证据链 | C3.1 |
| `scenario.sample.json` | 场景定义 | C4.1 |
| `scenario_run_result.sample.json` | 场景运行结果 | C4.2 |
## 验证规则
所有样本文件必须：
1. 要求字段名称与 DOC C 完全一致（区分大小写）2. 对于“id”字段，请使用有效的 UUID 格式。3. 请使用 ISO8601 标准的 UTC 格式来表示时间戳（格式为“2026-01-31T12:00:00Z”）4. 要有内部一致的引用（例如，`alert.evidence.flow_ids` 应引用有效的流 ID）
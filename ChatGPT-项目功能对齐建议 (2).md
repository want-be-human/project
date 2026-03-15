# 项目功能对齐建议

**User:** Anonymous (q15525125026@163.com)  
**Created:** 3/10/2026 20:03:56  
**Updated:** 3/15/2026 19:08:43  
**Exported:** 3/15/2026 19:39:00  

## Response:
Thought for 21s

下面是基于你给出的分析，我整理出的**应该继续优化的部分**。我按“优先级 + 问题总结 + 可直接喂给 AI 的提示词”来写，这样你可以直接分批让 AI 改。

* * *

一、优先级结论
=======

P0：最该先补齐的
---------

1.  **Agent 结果回填与告警详情页初始化展示**
2.  **Recommendation → compile-plan → Twin 的真实链路接入**
3.  **威胁增强 `threat_context` 的前端类型与渲染**
4.  **Twin / Scenario 的 WebSocket 事件消费修复**

P1：第二批优化
--------

5.  **告警详情页闭环刷新：证据链 / 建议 / dry-run 执行后自动刷新**
6.  **流水线可观测性前端补齐（pipeline stages UI）**
7.  **拓扑页 `dryRunId` 查询错误回退修复**

P2：顺手修掉的前端问题
------------

8.  **EvidenceChainView 节点类型样式修复（`investigation` → `hypothesis`）**
9.  **real 模式隐藏 mock 调试入口 `simulateWs`**

* * *

二、逐项优化总结 + 可直接喂给 AI 的提示词
========================

* * *

1）Agent 结果回填与告警详情页初始化展示
-----------------------

### 问题总结

现在 `AgentPanel` 能调用真实接口，但**页面初始进入时不会把后端已经存在的 triage / investigate / recommend 结果回填出来**。  
结果就是：

*   用户刷新页面后，看不到之前已经跑过的 Agent 结果
*   详情页更像“临时触发器”，不像“可持续查看的分析记录”
*   后端已经持久化的数据没有被前端利用起来

涉及位置：

*   `frontend/src/app/alerts/[id]/page.tsx`
*   `frontend/src/components/alerts/AlertDetailView.tsx`
*   `frontend/src/components/agent/AgentPanel.tsx`

### 可直接喂给 AI 的提示词

```
请修复前端 real 模式下“告警详情页无法回填已有 Agent 结果”的问题。

现状：
1. AgentPanel 可以调用真实 triage / investigate / recommend 接口。
2. 但 alerts/[id]/page.tsx 和 AlertDetailView.tsx 页面初始化时，只加载告警和证据链，没有把后端已存在的 Agent 结果读回来。
3. 后端已经持久化了 alert.agent.triage_summary、investigation_id、recommendation_id 等关联信息，但前端没有展示，导致刷新页面后用户看不到历史分析结果。

目标：
1. 告警详情页首次加载时，如果后端已经有 triage / investigation / recommendation 结果，前端必须自动回填并展示。
2. AgentPanel 既支持“首次触发分析”，也支持“展示已有分析结果”。
3. 页面刷新后，已有 Agent 结果不能丢失。
4. 不破坏当前 mock / real 双模式。

实现要求：
1. 检查 frontend/src/lib/api/types.ts，补齐 alert 详情和 Agent 结果关联类型。
2. 修改 frontend/src/app/alerts/[id]/page.tsx，在加载告警详情时一并拉取或解析已有 Agent 结果。
3. 修改 frontend/src/components/alerts/AlertDetailView.tsx，将已有 triage / investigation / recommendation 结果传给 AgentPanel。
4. 修改 frontend/src/components/agent/AgentPanel.tsx，支持：
   - 初始展示已有 triage / investigation / recommendation
   - 用户手动重新执行时覆盖更新
5. 若 investigation_id / recommendation_id 需要单独请求详情，请在 realApi 中新增对应获取方法，并保持类型安全。
6. UI 上要清楚区分：
   - 已有结果
   - 正在执行
   - 新执行结果

约束：
1. 不修改现有后端接口语义。
2. 不删除现有 AgentPanel 的触发能力。
3. 保持 real 模式与 mock 模式兼容。

产出：
1. 可回填的告警详情页 Agent 展示链路。
2. 补齐后的前端类型和 API 调用。
3. 页面刷新后仍可看到已存在的 Agent 分析结果。
```

* * *

2）Recommendation → compile-plan → Twin 的真实链路接入
----------------------------------------------

### 问题总结

现在前端并没有真正使用后端的 `POST /alerts/{id}/compile-plan`。  
当前做法是：

*   前端 `ActionBuilder` 根据 recommendation 标题自己猜动作类型
*   然后直接调用 `/twin/plans`

这会导致：

*   前端绕过后端 plan compiler
*   看不到后端编译出来的 `confidence / derived_from_evidence / reasoning_summary`
*   Recommendation → Twin 这条链路不是真正的“后端编排结果”

涉及位置：

*   `frontend/src/lib/api/real.ts`
*   `frontend/src/components/twin/ActionBuilder.tsx`

### 可直接喂给 AI 的提示词

```
请将前端当前“本地猜动作类型再创建 Twin Plan”的流程，改造成真正使用后端 compile-plan 的真实链路。

现状：
1. 前端没有调用 POST /alerts/{id}/compile-plan。
2. realApi 里只有 createPlan，没有 compilePlan。
3. ActionBuilder 当前是根据 recommendation 标题猜测 action_type，再直接发到 /api/v1/twin/plans。
4. 这导致前端绕过了后端 plan compiler，无法展示 confidence、derived_from_evidence、reasoning_summary 等编译结果。

目标：
1. 前端必须接入后端 compile-plan 接口。
2. 用户应能从 recommendation 一键生成结构化 plan。
3. 前端必须展示后端返回的编译结果，包括：
   - action_type
   - target
   - params
   - rollback
   - confidence
   - derived_from_evidence
   - reasoning_summary
4. 后续创建 Twin Plan 时，应优先消费 compile-plan 返回结果，而不是前端本地猜。

实现要求：
1. 在 frontend/src/lib/api/real.ts 中新增 compilePlan(alertId) 方法，调用后端真实接口。
2. 在 frontend/src/lib/api/types.ts 中新增 compile-plan 返回类型。
3. 修改 frontend/src/components/twin/ActionBuilder.tsx：
   - 新增“根据 recommendation 编译计划”入口
   - 优先展示 compile-plan 返回结果
   - 用户确认后再调用现有 createPlan / twin 相关接口
4. 在 UI 中明确区分：
   - recommendation 文本建议
   - compile-plan 结构化动作结果
5. 若 compile-plan 返回多个动作，支持列表展示与选择。
6. 保留当前 createPlan 能力作为 fallback，但默认优先使用 compile-plan。

约束：
1. 不破坏现有 Twin 页面整体结构。
2. 不删除现有 createPlan 能力。
3. mock / real 双模式都要兼容。

产出：
1. 完整的 recommendation -> compile-plan -> Twin Plan 前端真实链路。
2. 编译结果可视化展示。
3. 去除“前端自己猜动作”的主路径依赖。
```

* * *

3）威胁增强 `threat_context` 的前端类型与渲染
--------------------------------

### 问题总结

后端 schema 已经有 `threat_context`，但前端：

*   `types.ts` 没有这个字段
*   `AgentPanel` 也没有渲染 MITRE / tactics / techniques / refs / confidence

所以第五项升级在 real 模式下几乎**用户完全看不到**。

涉及位置：

*   `frontend/src/lib/api/types.ts`
*   `frontend/src/components/agent/AgentPanel.tsx`

### 可直接喂给 AI 的提示词

```
请补齐前端对后端 threat_context 的类型支持与界面渲染，让威胁增强能力在 real 模式下可见。

现状：
1. 后端 schema 已经在 investigation / recommendation 中提供了 threat_context。
2. 但 frontend/src/lib/api/types.ts 没有 threat_context 字段。
3. AgentPanel 没有渲染 MITRE tactic、technique、参考链接、enrichment_confidence 等内容。
4. 导致 real 模式下用户看不到威胁增强带来的差异。

目标：
1. 前端类型系统完整支持 threat_context。
2. Investigation 和 Recommendation 展示区都能显示 threat_context。
3. UI 要清晰展示：
   - tactics
   - techniques
   - confidence
   - rationale / rationale-like explanation
   - intel_refs
4. 如果 threat_context 不存在，界面应优雅降级，不报错。

实现要求：
1. 在 frontend/src/lib/api/types.ts 中新增 ThreatContext 及相关子类型。
2. 在 investigation / recommendation 对应类型中加入可选 threat_context 字段。
3. 修改 frontend/src/components/agent/AgentPanel.tsx：
   - 在 investigation 结果区域渲染威胁上下文卡片
   - 在 recommendation 结果区域也可渲染对应 threat_context
4. UI 建议包含：
   - MITRE tactic / technique tag
   - confidence 显示
   - 参考链接列表
   - 简要说明文字
5. threat_context 缺失时不显示空白占位块。

约束：
1. 不能破坏现有 AgentPanel 的 triage / investigate / recommend 主结构。
2. 保持 mock / real 双模式兼容。
3. 字段全部按可选处理，避免因后端未返回而报错。

产出：
1. 完整的前端 threat_context 类型定义。
2. AgentPanel 中可见的威胁增强展示区。
3. real 模式下用户可直观看到 MITRE 与 threat intel 信息。
```

* * *

4）Twin / Scenario 的 WebSocket 事件消费修复
------------------------------------

### 问题总结

当前实时事件链路不完整：

*   `DryRunPanel` 把 `twin.dryrun.created` 事件直接当成完整 `DryRunResult`
*   但后端事件实际上只发 `{ dry_run_id, alert_id, risk }`
*   `ScenarioRunPanel` 虽然订阅了事件，但没有真正消费更新 UI

所以第二项升级只做到了“有事件”，没做到“事件驱动正确刷新”。

涉及位置：

*   `frontend/src/components/twin/DryRunPanel.tsx`
*   `frontend/src/components/scenarios/ScenarioRunPanel.tsx`

### 可直接喂给 AI 的提示词

```
请修复前端对 Twin / Scenario WebSocket 事件的消费逻辑，使其与后端真实事件载荷一致，并能正确驱动 UI 刷新。

现状：
1. DryRunPanel 把 twin.dryrun.created 事件误当成完整 DryRunResult 使用。
2. 但后端 stream 事件实际上只提供 { dry_run_id, alert_id, risk } 这类轻量载荷。
3. ScenarioRunPanel 虽然订阅了事件，但没有真正将事件结果用于更新界面。
4. 结果是 Twin / Scenario 的实时刷新不可靠，事件总线链路没有真正体现在页面上。

目标：
1. WebSocket 收到轻量事件后，前端应根据 event payload 再去拉取完整详情。
2. DryRunPanel 和 ScenarioRunPanel 必须实现“事件 -> 拉取详情 -> 更新状态”的完整逻辑。
3. UI 要在实时事件到达后正确刷新，不依赖手动刷新页面。

实现要求：
1. 检查后端 stream 事件契约，严格按照真实 payload 定义前端事件类型。
2. 修改 frontend/src/components/twin/DryRunPanel.tsx：
   - 不再把事件 payload 当成完整 DryRunResult
   - 收到 dry_run_id 后调用真实 API 获取完整 dry-run 详情
   - 再更新 UI
3. 修改 frontend/src/components/scenarios/ScenarioRunPanel.tsx：
   - 对订阅到的 scenario 相关事件做真实消费
   - 必要时按 run_id 拉取完整 scenario run 详情
4. 如果相关 realApi 方法缺失，请补齐。
5. 增加 loading / refreshing 状态，避免 UI 闪烁或错误覆盖。
6. 保证事件重复到达时不会造成脏状态。

约束：
1. 不破坏现有 WSProvider 和 real mode WebSocket 连接方式。
2. 保持 mock / real 双模式兼容。
3. 所有事件处理都要按“轻事件 + 拉详情”的模式实现。

产出：
1. 修复后的 Twin / Scenario 实时刷新逻辑。
2. 与后端事件载荷一致的前端类型。
3. 更稳定的实时 UI 更新行为。
```

* * *

5）告警详情页闭环刷新：证据链 / 建议 / dry-run 自动刷新
-----------------------------------

### 问题总结

目前告警详情页中的证据链只在首次进入时加载一次。  
之后如果用户在同页执行：

*   investigate
*   recommend
*   dry-run

页面并不会自动重新拉取最新证据链和相关结果。  
这会导致“证据链 → 建议 → dry-run”的闭环**在 UI 上不连贯**。

涉及位置：

*   `frontend/src/app/alerts/[id]/page.tsx`
*   `frontend/src/components/alerts/AlertDetailView.tsx`

### 可直接喂给 AI 的提示词

```
请补齐告警详情页的闭环刷新逻辑，使 investigate / recommend / dry-run 执行后，证据链和关联结果能自动刷新到 UI。

现状：
1. 告警详情页的证据链只在进入页面时加载一次。
2. 用户在同页执行 investigate、recommend、dry-run 后，页面不会自动重新拉取最新证据链与关联结果。
3. 这导致“证据链 -> 建议 -> dry-run”闭环不能即时体现在 UI 上。

目标：
1. 在同一页面执行 investigate / recommend / dry-run 后，告警详情必须自动刷新相关数据。
2. 刷新范围至少包括：
   - evidence chain
   - alert 最新状态
   - Agent 结果
   - dry-run 关联结果（若页面展示）
3. 用户无需手动刷新页面即可看到最新闭环结果。

实现要求：
1. 修改 alerts/[id]/page.tsx 或 AlertDetailView.tsx 的数据获取结构，支持局部刷新。
2. 在 AgentPanel、DryRunPanel 等操作成功后，触发父层刷新回调。
3. 刷新逻辑应尽量局部化，避免整页闪烁重载。
4. 若已有 WS 事件可辅助刷新，可结合使用，但不能只依赖 WS。
5. 页面需要显示合理的刷新中状态。

约束：
1. 不改变现有页面路由结构。
2. 不破坏已有 mock / real 数据流。
3. 优先采用局部状态刷新，而不是粗暴整页 reload。

产出：
1. 告警详情页闭环联动刷新能力。
2. investigate / recommend / dry-run 后即时反映到证据链和结果区。
3. 更连贯的“分析 -> 建议 -> 演练”用户体验。
```

* * *

6）流水线可观测性前端补齐（pipeline stages UI）
---------------------------------

### 问题总结

第六项升级当前前端几乎没体现。  
现状只有：

*   PCAP 页显示文件级进度、flow 数、alert 数
*   Scenario 页显示 checks / metrics

但**没有 pipeline stage 级别**的可视化，例如：

*   parse
*   feature\_extract
*   detect
*   aggregate
*   investigate
*   recommend

所以用户看不到“处理是怎么一步步跑出来的”。

涉及位置：

*   `frontend/src/app/pcaps/page.tsx`
*   `frontend/src/components/scenarios/ScenarioRunPanel.tsx`
*   以及需要补 API 层

### 可直接喂给 AI 的提示词

```
请补齐前端对 pipeline 可观测性的展示，让用户在 PCAP 和 Scenario 相关页面看到阶段级处理状态，而不只是文件级进度和最终统计。

现状：
1. PCAP 页只展示上传状态、处理状态、flow 数、alert 数。
2. Scenario 页能展示 checks / metrics，但没有 pipeline stage 级别观测。
3. 前端没有接入 pipeline 相关 API，也没有 stage UI。
4. 第六项升级的大部分能力目前没有体现在前端。

目标：
1. 前端支持展示 pipeline stages，例如：
   - parse
   - feature_extract
   - detect
   - aggregate
   - investigate
   - recommend
   - compile_plan
   - dry_run
   - visualize
2. 每个 stage 至少展示：
   - 状态
   - 耗时
   - 关键结果摘要
3. 在 PCAP 页面和适合的 Scenario 页面显示这类观测。

实现要求：
1. 检查后端是否已有 pipeline 相关接口；若有，接入 realApi；若无，先预留前端类型与 UI 结构。
2. 在 frontend/src/lib/api/types.ts 中补齐 pipeline stage 类型。
3. 在 frontend/src/app/pcaps/page.tsx 中新增 pipeline 观测展示区域。
4. 根据项目结构决定是否在 ScenarioRunPanel 中复用同一套 stage timeline 组件。
5. UI 建议采用：
   - stage timeline
   - step status badge
   - duration / metrics 摘要
6. 若后端未返回完整数据，前端必须优雅降级。

约束：
1. 不破坏现有 PCAP 页面主流程。
2. 保持 mock / real 双模式兼容。
3. UI 组件应可复用，不要把 pipeline 展示硬编码在单一页面中。

产出：
1. pipeline stages 的前端类型与 API 接入。
2. 可复用的 PipelineStageTimeline 组件。
3. PCAP / Scenario 页面上的阶段级观测展示。
```

* * *

7）拓扑页 `dryRunId` 查询错误回退修复
-------------------------

### 问题总结

第四项升级总体同步最好，但这里有一个真实 bug：

*   读取 `dryRunId` 时，前端会先 `listDryRuns()` 全量拉列表再查找
*   如果没找到，会错误地回退到 `results[0]`
*   这可能把**别的 dry-run 结果**显示到当前页面

这是很危险的错误展示。

涉及位置：

*   `frontend/src/app/topology/page.tsx`

### 可直接喂给 AI 的提示词

```
请修复 topology 页面在根据 dryRunId 加载 dry-run overlay 时的错误回退逻辑，避免把其他 dry-run 结果错误显示到当前页面。

现状：
1. topology/page.tsx 会通过 listDryRuns() 全量拉取列表，再根据 dryRunId 查找目标结果。
2. 当目标 dryRunId 没找到时，当前逻辑错误地回退到 results[0]。
3. 这会导致当前页面错误显示别的 dry-run 结果，属于严重的数据展示错误。

目标：
1. 加载 dryRunId 时只能展示与当前 dryRunId 精确匹配的结果。
2. 如果找不到对应 dry-run，应显示“未找到 / 已失效 / 无权限”之类的明确状态，而不是回退到其他结果。
3. 不允许再出现错误 dry-run 结果串页显示。

实现要求：
1. 修改 frontend/src/app/topology/page.tsx 中 dryRunId 查询逻辑。
2. 去掉 results[0] 这种错误回退。
3. 若 realApi 缺少按 id 获取 dry-run 的方法，请新增 getDryRunById(dryRunId)。
4. UI 上增加：
   - loading 状态
   - not found 状态
   - 无 dry-run 状态
5. 若当前页面是通过 query param 带 dryRunId 进入，需保证 query param 变更时也能正确响应。

约束：
1. 不破坏 topology 页面现有布局、视角、heat、overlay 等功能。
2. 保持 mock / real 模式兼容。
3. 优先使用精准按 id 拉取，而不是全量列表后猜测。

产出：
1. 修复后的 dry-run 精准加载逻辑。
2. 正确的 not found / loading UI。
3. 避免串页展示错误数据。
```

* * *

8）EvidenceChainView 节点类型样式修复
----------------------------

### 问题总结

`EvidenceChainView` 里样式分支写的是 `investigation`，  
但前后端实际节点类型是 `hypothesis`。  
结果就是这类节点落入默认样式，看不出它是“调查/假设节点”。

涉及位置：

*   `frontend/src/components/evidence/EvidenceChainView.tsx`
*   `frontend/src/lib/api/types.ts`

### 可直接喂给 AI 的提示词

```
请修复 EvidenceChainView 中证据链节点类型样式不匹配的问题。

现状：
1. EvidenceChainView 的样式分支中使用的是 investigation 节点类型。
2. 但前端类型和后端实际节点类型是 hypothesis。
3. 导致 hypothesis 节点落入默认样式，无法按“调查/假设节点”正确高亮。

目标：
1. hypothesis 节点必须有明确的专属视觉样式。
2. 证据链不同节点类型在 UI 上要有清晰区分。
3. 前端类型、渲染分支、实际后端数据保持一致。

实现要求：
1. 检查 frontend/src/lib/api/types.ts 中 evidence node type 定义。
2. 修改 frontend/src/components/evidence/EvidenceChainView.tsx 中的样式分支，将错误的 investigation 逻辑修正为 hypothesis。
3. 如有必要，补充 hypothesis 的 icon / badge / color style。
4. 确保不会影响其他 evidence 节点类型的显示。

约束：
1. 不改变证据链数据结构。
2. 不影响现有布局和连线渲染。
3. 样式修复要与现有视觉体系一致。

产出：
1. 修复后的 hypothesis 节点类型渲染。
2. 更清晰的证据链视觉分层。
```

* * *

9）real 模式隐藏 mock 调试入口 `simulateWs`
----------------------------------

### 问题总结

告警列表页在 real 模式下还保留了 `simulateWs` 按钮。  
这属于 mock 调试入口泄露到真实界面，会影响产品感和使用逻辑。

涉及位置：

*   `frontend/src/app/alerts/page.tsx`

### 可直接喂给 AI 的提示词

```
请清理 real 模式下泄露出来的 mock 调试入口，确保真实界面不显示 simulateWs 之类的调试按钮。

现状：
1. alerts/page.tsx 在 real 模式下仍保留了 simulateWs 按钮。
2. 这属于 mock 调试入口泄露到真实界面，影响产品感和真实使用逻辑。

目标：
1. simulateWs 仅在 mock / dev 调试场景可见。
2. real 模式下该按钮必须隐藏。
3. 不影响开发调试体验。

实现要求：
1. 检查 frontend/src/lib/api/index.ts 或相关 mode 判断逻辑。
2. 在 frontend/src/app/alerts/page.tsx 中根据当前 API 模式或开发环境决定是否渲染 simulateWs。
3. 若项目已有统一的 isMock / isReal / isDev 判断工具，优先复用。
4. 确保按钮隐藏后，不影响其他告警列表功能。

约束：
1. 不删除该调试能力，只限制其显示条件。
2. 保持 mock 模式和本地开发环境可继续使用。

产出：
1. real 模式下无 simulateWs 按钮。
2. mock / dev 下仍可调试。
```

* * *

三、最建议你的执行顺序
===========

建议按这个顺序让 AI 改：

1.  **Agent 结果回填**
2.  **compile-plan 真实接入**
3.  **threat\_context 前端展示**
4.  **Twin / Scenario 事件消费修复**
5.  **告警详情闭环刷新**
6.  **pipeline 可观测性 UI**
7.  **topology dryRunId bug**
8.  **EvidenceChainView 样式修复**
9.  **隐藏 simulateWs**

这个顺序的好处是：

*   先补齐“六项升级”里最关键的真实前端表达
*   再修交互闭环
*   最后收尾视觉与调试问题

* * *

四、一句话总结
=======

现在最该继续优化的核心，不是再加新页面，而是：

**把后端已经做好的升级能力，真实、完整、稳定地映射到前端 real 模式中。**

如果你愿意，我下一条可以继续把这 9 项整理成一份  
**《前端 real 模式补齐实施文档》**。



---
Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)
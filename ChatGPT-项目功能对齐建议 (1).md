# 项目功能对齐建议

**User:** Anonymous (q15525125026@163.com)  
**Created:** 3/10/2026 20:03:56  
**Updated:** 3/12/2026 20:44:09  
**Exported:** 3/14/2026 22:37:36  

## Response:
我先把要升级的部分做成一张“模块清单”，再补参考仓库里对应实现的关键细节，最后把每个模块整理成可直接喂给 AI 的提示词。重点会放在“怎么嵌到你现有代码里而不破坏别的模块”。

我在补一层代码级信息：README 只能判断“有没有这个方向”，但这次你要的是“实现细节、实现逻辑、怎么升级不破坏现有项目”，所以我会把你项目和参考仓库的关键实现路径也纳进来。

Thought for 13m 18s

下面我把**应该对齐升级的部分全部统计出来**，并按你要求给出：

1.  **升级项统计与优先级**
2.  **推荐仓库对应实现的细节与实现逻辑**
3.  **如何无破坏地嵌入你现有项目**
4.  **每个部分一段可直接喂给 AI 的提示词**

先给总结：

你当前项目已经具备完整闭环：`PCAP → 特征/检测 → 告警 → 拓扑 → Agent → Twin Dry-run → 场景回归`，而且后端/前端/contract/infra 已经分层，前端也已有 `Topology3D / TimeSlider / SideInspector / DryRunOverlay`，后端已有 `alerts / topology / agent / twin / scenarios / stream` 等路由。([github.com](https://github.com/want-be-human/project?utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/want-be-human/project))

但从实现深度看，你现在的检测仍是 **IsolationForest 基线异常检测**，拓扑前端布局仍是**简化的环形确定性布局**，WebSocket 仍是**进程内内存广播**，Agent 仍是**结构化模板/规则式分析**且保持 advisory only。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/detection/service.py?utm_source=chatgpt.com) [GitHub+3GitHub+3GitHub+3](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/detection/service.py))

所以，**应对齐升级的部分共 6 个**：

**高优先级 4 个**

1.  Agent 工作流编排层
2.  内部事件总线/异步处理层
3.  推荐动作到 Twin Plan 的编译层（证据链→处置链贯通）
4.  3D 拓扑布局与交互增强层

**中优先级 2 个**  
5\. 轻量威胁情报 / MITRE 增强层  
6\. 流水线阶段化可观测性与测试回归强化

同时，**不建议现在对齐**的是：

*   AI\_SOC 那种完整 Wazuh/OpenSearch/Grafana/RAG 多服务重型栈
*   network-traffic-analysis 那种 Kafka-first 的实时数据平台  
    因为这两类会明显抬高耦合度和部署复杂度，不适合作为你当前项目的“必须升级项”。([github.com](https://github.com/zhadyz/AI_SOC?utm_source=chatgpt.com) [github.com](https://github.com/ElhoubeBrahim/network-traffic-analysis?utm_source=chatgpt.com) [GitHub+5GitHub+5GitHub+5](https://github.com/zhadyz/AI_SOC))

* * *

一、统一的无破坏升级约束
============

下面 6 个升级项都应遵守同一套约束，这样才能“完美嵌合到项目中”：

*   **不修改现有对外 API contract**
    *   保留现有 `alerts/{id}/triage|investigate|recommend`
    *   保留现有 `/topology/graph`
    *   保留现有 WebSocket 事件命名
*   **不移除现有功能，只做可插拔增强**
    *   旧逻辑继续可用
    *   新逻辑通过 feature flag / 配置开关启用
*   **不破坏前端 Mock/Real 双模式**
*   **数据库只做增量迁移，不重构已有核心表**
*   **Twin 现有动作类型保持不变**
    *   `block_ip`
    *   `isolate_host`
    *   `segment_subnet`
    *   `rate_limit_service`  
        这些动作类型当前已经在前端 real API 适配层里被标准化，不能破坏。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/frontend/src/lib/api/real.ts?utm_source=chatgpt.com) [GitHub](https://raw.githubusercontent.com/want-be-human/project/main/frontend/src/lib/api/real.ts))

* * *

二、升级项 1：Agent 工作流编排层
====================

1.1 为什么要升级
----------

你当前的 Agent 已经有 `triage / investigate / recommend` 三段能力，但本质仍是**同步调用的模板化服务**，并且明确是 advisory only，不直接执行动作。这个方向是对的，但还没有“工作流引擎化”。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/agent/service.py?utm_source=chatgpt.com) [GitHub](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/agent/service.py))

1.2 推荐仓库对应实现细节
--------------

`agentic-soc-platform` 的核心逻辑不是“多一个 LLM 接口”，而是把整条安全分析链做成：

`SIEM / Alert Source → Webhook → Redis Stream → Module Engine → SIRP → Playbooks`

并且仓库结构里明确存在 `AGENTS / MODULES / PLAYBOOKS / PLUGINS` 这类分层，说明它把能力做成了**可组合、可替换、可扩展的模块工作流**。([github.com](https://github.com/FunnyWolf/agentic-soc-platform?tab=readme-ov-file&utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/FunnyWolf/agentic-soc-platform))

它值得借鉴的实现逻辑有三点：

*   **阶段明确**：不同阶段不是一坨函数，而是“模块链”
*   **输入输出标准化**：每个模块消费标准事件，产出标准记录
*   **工作流可复用**：同一条研判链可换模块、换模型、换 playbook

1.3 你项目中应如何无破坏实现
----------------

不要改掉现有 `triage / investigate / recommend` 路由。  
正确做法是：

*   新增一个内部 `WorkflowEngine`
*   把原先 AgentService 的三段逻辑包成三个 stage：
    *   `TriageStage`
    *   `InvestigationStage`
    *   `RecommendationStage`
*   每个 stage 的输入输出**严格兼容现有 schema**
*   原有路由仍然可直接调，但内部改成：
    *   路由 → WorkflowEngine.run(stage=...)
    *   如果新工作流关闭，则 fallback 到旧逻辑
*   新增一张轻量执行轨迹表或日志模型，记录：
    *   workflow\_id
    *   stage\_name
    *   input\_snapshot
    *   output\_snapshot
    *   latency\_ms
    *   status

这样升级后：

*   前端完全不用改接口
*   旧功能不丢
*   以后可继续插入“enrichment stage / policy stage / plan compile stage”

1.4 预期产出
--------

*   `backend/app/workflows/` 新目录
*   `WorkflowEngine` 与 stage registry
*   Agent 现有三段能力的 stage 化封装
*   执行轨迹持久化或结构化日志
*   所有现有 API 响应结构保持不变

1.5 可直接喂给 AI 的提示词
-----------------

```
请在当前项目中实现“Agent 工作流编排层”升级，目标是在不破坏现有 API、数据库核心结构和前端调用方式的前提下，将当前的 triage / investigate / recommend 逻辑升级为可编排、可扩展、可回退的内部工作流。

已知约束：
1. 必须保留现有后端路由与响应契约，尤其是 alerts/{id}/triage、alerts/{id}/investigate、alerts/{id}/recommend。
2. 必须保持当前 Agent 的 advisory only 语义，不允许直接执行封禁、隔离或限流动作。
3. 必须保证前端无需修改即可继续工作。
4. 旧逻辑必须保留，并可作为 fallback。

升级内容：
1. 新增内部 WorkflowEngine，将 Agent 分为三个 stage：
   - TriageStage
   - InvestigationStage
   - RecommendationStage
2. 每个 stage 的输入输出必须兼容当前已有 schema，不得修改对外字段名。
3. 允许后续继续插入新 stage，但当前先只完成三阶段编排。
4. 新增执行轨迹记录能力，至少记录：
   - workflow_id
   - alert_id
   - stage_name
   - status
   - latency_ms
   - input_snapshot（可裁剪）
   - output_snapshot（可裁剪）
5. 路由层的调用方式改为：
   路由 -> WorkflowEngine -> 对应 Stage -> 返回当前已有响应格式
6. 通过配置开关控制是否启用新工作流；关闭时走旧逻辑。

优化逻辑与方法：
- 不直接重写现有 AgentService，而是将其能力拆为可复用 stage。
- stage 应使用统一基类或协议，便于后续增加 enrichment、plan compiler 等模块。
- 所有新增能力必须是增量式的，不允许影响 twin、topology、scenarios、stream 等现有模块。
- 代码应低耦合，工作流引擎与具体业务逻辑解耦。

期望产出：
1. 新的 workflows 目录结构与核心类。
2. Agent 三阶段的工作流封装实现。
3. 路由改造后的兼容性代码。
4. 配置开关与 fallback 逻辑。
5. 必要的单元测试，验证启用和关闭工作流时返回结果都兼容现有接口。
```

* * *

三、升级项 2：内部事件总线 / 异步处理层
======================

2.1 为什么要升级
----------

你现在已有 WebSocket 流式能力，但当前实现是一个**进程内内存连接管理器**，负责 `broadcast / send_to / ping-pong`，更像“通知层”，还不是“事件总线层”。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/api/routers/stream.py?utm_source=chatgpt.com) [GitHub](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/api/routers/stream.py))

2.2 推荐仓库对应实现细节
--------------

`agentic-soc-platform` 把事件流做成了 Redis Stream 驱动的模块处理链：  
不同模块从指定 stream 消费，再把结果投递到下游。([github.com](https://github.com/FunnyWolf/agentic-soc-platform?tab=readme-ov-file&utm_source=chatgpt.com) [GitHub+1](https://github.com/FunnyWolf/agentic-soc-platform))

它最值得借鉴的不是“必须用 Redis”，而是：

*   **先有统一事件抽象**
*   **再有不同后端实现**
*   **通知层依赖事件层，而不是反过来**

2.3 你项目中应如何无破坏实现
----------------

建议新增 `EventBus` 抽象：

*   `publish(event)`
*   `subscribe(topic, handler)`
*   `unsubscribe(...)`

第一阶段只实现：

*   `InMemoryEventBus`

第二阶段预留：

*   `RedisEventBus`（接口预留，不强制上线）

然后把这些地方改为向 EventBus 发布事件：

*   PCAP 处理进度
*   Alert 创建
*   Investigation 完成
*   Recommendation 生成
*   Twin dry-run 创建
*   Scenario 回归完成

再由 WebSocket router 订阅这些 topic，把事件广播给前端。  
这样升级后：

*   现有 WebSocket 事件名保持不变
*   以后若切 Redis，不用重写业务层
*   所有异步链条更清晰

2.4 预期产出
--------

*   `backend/app/core/events/` 或类似目录
*   `Event` schema
*   `EventBus` interface
*   `InMemoryEventBus`
*   WebSocket 与事件总线解耦
*   业务服务统一发布事件

2.5 可直接喂给 AI 的提示词
-----------------

```
请在当前项目中实现“内部事件总线 / 异步处理层”升级，目标是在不改变现有 WebSocket 对外行为和事件名称的前提下，将当前仅用于前端推送的内存广播机制升级为统一的内部事件总线抽象。

已知约束：
1. 必须保留现有 WebSocket 路由和前端订阅方式。
2. 必须保留现有事件主题和语义，不允许破坏前端实时更新。
3. 当前阶段不能强依赖 Redis、Kafka 等外部基础设施。
4. 现有 topology、agent、twin、scenarios、pcap 处理逻辑不能被重构打散。

升级内容：
1. 新增统一 EventBus 抽象层，至少包括：
   - publish(event)
   - subscribe(topic, handler)
   - unsubscribe(...)
2. 实现 InMemoryEventBus 作为默认后端。
3. 预留 RedisEventBus 扩展接口，但当前不强制实现完整 Redis 依赖。
4. 将以下事件统一通过 EventBus 发布：
   - pcap 处理进度
   - alert 创建
   - triage / investigation / recommendation 完成
   - twin dry-run 创建
   - scenario 回归执行完成
5. 让当前 WebSocket router 变为 EventBus 的订阅者，而不是业务模块直接依赖 WebSocket manager。

优化逻辑与方法：
- 事件总线只做“解耦”和“分发”，不改变业务逻辑本身。
- 业务模块只知道发布事件，不直接知道前端推送细节。
- 通过适配器模式保持现有 WebSocket 广播能力不变。
- 所有新增代码必须是可插拔的，不允许引入对外部中间件的强耦合。

期望产出：
1. 统一的事件模型和事件总线接口。
2. InMemoryEventBus 默认实现。
3. WebSocket 路由改造为事件消费者。
4. 业务模块发布事件的接入代码。
5. 兼容性测试，验证前端原有实时事件仍可正常接收。
```

* * *

四、升级项 3：推荐动作 → Twin Plan 编译层（证据链到处置链贯通）
=======================================

3.1 为什么要升级
----------

你现在已经有：

*   Agent recommendation
*   Twin dry-run
*   Evidence chain

但这几层之间还不够“自动贯通”。  
当前前端 real API 适配层里，`createPlan` 会把动作规范化成 `block_ip / isolate_host / segment_subnet / rate_limit_service` 这几种标准动作，并整理 target、params、rollback。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/frontend/src/lib/api/real.ts?utm_source=chatgpt.com) [GitHub](https://raw.githubusercontent.com/want-be-human/project/main/frontend/src/lib/api/real.ts))

这说明你其实已经有了“动作标准化”的基础，只是还缺一个正式的 **Plan Compiler**。

3.2 推荐仓库对应实现细节
--------------

`agentic-soc-platform` 的价值在于把安全处置抽成 **Playbooks**；  
AI\_SOC 也把告警分析输出结构化为 severity、confidence、mitre、recommendations，并强调验证链路。([github.com](https://github.com/FunnyWolf/agentic-soc-platform?tab=readme-ov-file&utm_source=chatgpt.com) [github.com](https://github.com/zhadyz/AI_SOC?utm_source=chatgpt.com) [GitHub+1](https://raw.githubusercontent.com/FunnyWolf/agentic-soc-platform/master/README.md))

它们共同说明一件事：  
**研判结果不该只停留在文本建议，而应可编译为结构化处置计划。**

3.3 你项目中应如何无破坏实现
----------------

新增一个独立模块：

*   `PlanCompiler`

输入：

*   alert
*   evidence
*   recommendation

输出：

*   `ActionPlan[]`

其中每个 plan action 包含：

*   `action_type`
*   `target`
*   `params`
*   `rollback`
*   `confidence`
*   `derived_from_evidence`
*   `reasoning_summary`

关键要求：

*   **只能产出你现有 Twin 支持的动作类型**
*   默认是“待审核计划”，不直接执行
*   Twin dry-run 直接消费它的输出
*   recommendation 仍然保留文本版本，便于 UI 展示

这样你就形成了：

`Evidence → Recommendation → PlanCompiler → Twin Dry-run`

这是你项目里最适合强化的“卖点闭环”。

3.4 预期产出
--------

*   独立 `PlanCompiler`
*   recommendation 到 action plan 的规则映射
*   从前端一键“由建议生成演练计划”
*   证据链字段回溯能力

3.5 可直接喂给 AI 的提示词
-----------------

```
请在当前项目中实现“推荐动作到 Twin Plan 的编译层”，目标是在不改变现有 Twin API、现有动作类型和前端总体交互模式的前提下，将 Agent 的文本建议自动编译为可用于 dry-run 的结构化处置计划。

已知约束：
1. 必须保留现有 recommendation 文本输出。
2. 必须兼容现有 Twin 动作类型，仅允许产出：
   - block_ip
   - isolate_host
   - segment_subnet
   - rate_limit_service
3. 不允许直接执行动作，只能生成待审核 / 可 dry-run 的计划。
4. 不能破坏现有前端 real API 的动作适配逻辑，应尽可能复用现有字段和结构。

升级内容：
1. 新增独立 PlanCompiler 模块。
2. 输入应包括：
   - alert
   - evidence chain
   - investigation 结果
   - recommendation 结果
3. 输出应为结构化 ActionPlan 列表，每条至少包含：
   - action_type
   - target
   - params
   - rollback
   - confidence
   - derived_from_evidence
   - reasoning_summary
4. 编译逻辑必须是确定性的、可解释的，不依赖黑盒执行。
5. Twin dry-run 应能直接消费编译结果，减少前端手工拼接动作。

优化逻辑与方法：
- recommendation 保留“自然语言建议”，PlanCompiler 负责生成“结构化处置动作”。
- 编译规则必须与当前已有 twin 动作 schema 对齐。
- 所有动作都要能追溯到 evidence chain，便于解释“为什么建议这么做”。
- 所有新增能力必须是增量式的，不能影响 topology、stream、scenario 等现有模块。

期望产出：
1. PlanCompiler 核心实现。
2. recommendation 到 action plan 的规则映射表。
3. 与 twin dry-run 的接入层。
4. 端到端测试：从 alert -> recommendation -> compile plan -> dry-run 全链可跑通。
5. 可选的 API 或服务方法，用于“由建议生成演练计划”。
```

* * *

五、升级项 4：3D 拓扑布局与交互增强层
=====================

4.1 为什么要升级
----------

你当前拓扑链路已经很好：

*   后端有 `/topology/graph`
*   支持 `start / end / mode=ip|subnet`
*   图上有 `risk / activeIntervals / alert_ids`
*   前端有 `Topology3D / TimeSlider / SideInspector / DryRunOverlay / Toolbar / Legend`

这说明你**不缺拓扑模块本身**。([github.com](https://github.com/want-be-human/project/tree/main/backend/app/api/routers?utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/want-be-human/project/tree/main/frontend/src/components/topology))

真正短板是：  
前端当前 `Topology3D` 的布局仍是**简化的 circle layout**，不是更成熟的力导向/分层布局。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/frontend/src/components/topology/Topology3D.tsx?utm_source=chatgpt.com) [GitHub](https://raw.githubusercontent.com/want-be-human/project/main/frontend/src/components/topology/Topology3D.tsx))

4.2 推荐仓库对应实现细节
--------------

Splunk 的 3D graph 组件核心是 **ThreeJS/WebGL force-directed graph**，支持：

*   节点/边的颜色、权重、标签定制
*   3D 开关
*   animation bar
*   node labels
*   link arrows
*   dagMode
*   camera controller

这说明它的优势主要在**图布局能力和交互配置能力**。([github.com](https://github.com/splunk/splunk-3D-graph-network-topology-viz?utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/splunk/splunk-3D-graph-network-topology-viz))

4.3 你项目中应如何无破坏实现
----------------

这里不要动后端主契约。  
正确做法是：

*   保持现有 `/topology/graph` 返回字段不变
*   新增可选 layout metadata 或完全前端计算
*   在前端新增布局模式：
    *   `circle`（保留旧模式）
    *   `force`
    *   `dag`
    *   `clustered-subnet`
*   新增交互配置：
    *   标签开关
    *   边箭头开关
    *   风险热度开关
    *   子网聚类开关
    *   相机预设视角
*   继续使用现有 `risk / activeIntervals / alert_ids / impacted` 等字段驱动可视化

这样做不会影响其他模块，因为：

*   API 基本不变
*   时间滑条、dry-run overlay、side inspector 都能继续复用
*   只是前端拓扑渲染层增强

4.4 预期产出
--------

*   新布局引擎
*   多布局模式
*   更强的节点/边视觉编码
*   更平滑的相机与聚焦交互
*   现有拓扑 API 零破坏

4.5 可直接喂给 AI 的提示词
-----------------

```
请在当前项目中实现“3D 拓扑布局与交互增强层”升级，目标是在不破坏现有 topology API、时间回放、dry-run overlay、side inspector 的前提下，显著提升拓扑图的布局质量、信息表达能力和交互体验。

已知约束：
1. 必须保留现有 /topology/graph 接口和主要返回字段。
2. 必须兼容现有前端 Topology3D、TimeSlider、SideInspector、DryRunOverlay 等组件协作关系。
3. 旧的 circle layout 必须保留，作为 fallback。
4. 不允许要求后端大规模改造；如需新增字段，应采用可选字段方式。

升级内容：
1. 为前端拓扑图新增多种布局模式：
   - circle（兼容旧模式）
   - force（力导向）
   - dag（分层/定向）
   - clustered-subnet（按子网聚类）
2. 新增可切换的视觉与交互配置：
   - 节点标签显示开关
   - 边箭头显示开关
   - 风险热度编码开关
   - 子网聚类开关
   - 相机预设视角 / 聚焦模式
3. 继续复用当前图数据中的 risk、activeIntervals、alert_ids、impacted 等字段。
4. 需要改进节点选择、边点击、告警高亮、dry-run 影响范围展示等交互体验。
5. 时间回放与图布局不得互相冲突。

优化逻辑与方法：
- 不改变现有图数据语义，只增强渲染与交互层。
- 布局逻辑应与渲染逻辑分离，形成独立 layout engine。
- 视觉状态与业务状态解耦，避免影响 alert、twin、stream 等其他模块。
- 新能力通过配置控制，旧布局始终可回退。

期望产出：
1. 独立的 layout engine 或布局策略模块。
2. 多布局模式切换实现。
3. 拓扑图交互增强实现。
4. 与时间回放、dry-run overlay、side inspector 的兼容集成。
5. 必要的性能与稳定性优化，避免节点较多时明显卡顿。
```

* * *

六、升级项 5：轻量威胁情报 / MITRE 增强层
==========================

5.1 为什么要升级
----------

你现在的 Agent 已经能解释“发生了什么、为什么、影响面、建议动作”，但还缺少更正式的**威胁框架映射与知识增强**。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/agent/service.py?utm_source=chatgpt.com) [GitHub](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/agent/service.py))

5.2 推荐仓库对应实现细节
--------------

AI\_SOC 的架构里明确有：

*   ML inference
*   Alert triage
*   RAG service
*   MITRE ATT&CK context retrieval
*   对高危告警做 MITRE enrichment

README 的 `/analyze` 返回里也包含 `mitre_techniques`、recommendations 等字段。([github.com](https://github.com/zhadyz/AI_SOC?utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/zhadyz/AI_SOC))

这说明它不是只做分类，而是把告警放回威胁知识框架中去解释。

5.3 你项目中应如何无破坏实现
----------------

这里我建议**轻量实现**，不要照搬完整 RAG 微服务。

正确做法是：

*   新增一个本地 `ThreatEnrichmentService`
*   输入：
    *   alert\_type
    *   ports
    *   protocol
    *   top\_features
    *   evidence tokens
*   输出：
    *   `techniques`
    *   `tactics`
    *   `intel_refs`
    *   `enrichment_confidence`

第一版可用：

*   本地 YAML/JSON 映射
*   少量静态知识库
*   规则匹配 + 关键词匹配

然后在：

*   investigate
*   recommend

两个阶段中可选调用 enrichment。  
若 enrichment 服务不可用，则静默降级，不影响主流程。

5.4 预期产出
--------

*   轻量知识增强服务
*   MITRE 映射规则
*   investigation / recommendation 的增强字段
*   无外部依赖的本地运行能力

5.5 可直接喂给 AI 的提示词
-----------------

```
请在当前项目中实现“轻量威胁情报 / MITRE 增强层”升级，目标是在不引入重型 RAG 微服务、不引入外部 SIEM 强依赖的前提下，为 investigation 和 recommendation 增加可解释的威胁知识增强能力。

已知约束：
1. 当前阶段不能要求部署向量数据库、Wazuh、OpenSearch、Grafana 等重型基础设施。
2. 必须保持主流程可离线、本地运行。
3. enrichment 失败时必须静默降级，不能影响 triage / investigate / recommend 主流程。
4. 对外返回结构只能做增量扩展，不能破坏现有字段。

升级内容：
1. 新增 ThreatEnrichmentService。
2. 输入至少包括：
   - alert_type
   - protocol
   - src/dst port
   - top_features
   - evidence chain 中提取的关键词
3. 输出至少包括：
   - techniques（MITRE ATT&CK technique IDs）
   - tactics
   - intel_refs
   - enrichment_confidence
4. 第一版使用本地静态映射与规则匹配即可，不要求完整 RAG。
5. 在 investigation 和 recommendation 阶段可选接入 enrichment。

优化逻辑与方法：
- 采用“轻量规则 + 本地知识映射”的方式，避免引入外部高耦合组件。
- enrichment 层必须与 Agent 主体解耦，作为可选增强器存在。
- 字段设计应支持未来扩展到外部 threat intel 或 RAG，但当前实现必须保持简单可靠。
- 不允许影响 topology、twin、stream、scenario 的现有功能。

期望产出：
1. ThreatEnrichmentService 实现。
2. 本地 MITRE / tactics / intel 映射文件。
3. investigation 与 recommendation 的增量增强字段。
4. 单元测试与降级测试，验证 enrichment 不可用时主流程仍正常运行。
```

* * *

七、升级项 6：流水线阶段化可观测性 + 测试回归强化
===========================

6.1 为什么要升级
----------

你当前项目其实已经有很好的“流程闭环”，README 也明确提到 scenario regression。([github.com](https://github.com/want-be-human/project?utm_source=chatgpt.com) [GitHub](https://github.com/want-be-human/project))

但目前还可以进一步强化两件事：

*   把流水线阶段显式化
*   把测试与回放体系做得更稳定

你当前检测模型是 IsolationForest 基线，说明这条流水线很适合做“阶段化可观测”和“回归对比”。([raw.githubusercontent.com](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/detection/service.py?utm_source=chatgpt.com) [GitHub](https://raw.githubusercontent.com/want-be-human/project/main/backend/app/services/detection/service.py))

6.2 推荐仓库对应实现细节
--------------

`network-traffic-analysis` 虽然整体不适合你直接照搬，但它有一个非常值得借鉴的点：  
它把数据处理链明确拆成：

`capture → transform → store → visualize`

并且 `capture.py` 负责提取包信息发消息，`transform.py` 负责消费、 enrich、落库。([github.com](https://github.com/ElhoubeBrahim/network-traffic-analysis?utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/ElhoubeBrahim/network-traffic-analysis))

AI\_SOC 则在验证层做得更完整，包含：

*   健康检查
*   unit / integration / e2e / security / load 测试
*   跨服务链路验证。([github.com](https://github.com/zhadyz/AI_SOC?utm_source=chatgpt.com) [GitHub+1](https://github.com/zhadyz/AI_SOC))

6.3 你项目中应如何无破坏实现
----------------

不需要 Kafka，也不需要微服务化。  
只需要把当前主流程显式定义为阶段：

*   `parse`
*   `feature_extract`
*   `detect`
*   `aggregate`
*   `investigate`
*   `recommend`
*   `compile_plan`
*   `dry_run`
*   `visualize`

然后对每个阶段记录：

*   status
*   start/end
*   latency
*   key metrics
*   errors
*   input/output summary

再补三类测试：

*   **fixture regression**：固定 PCAP 输出对比
*   **scenario e2e**：从 alert 到 dry-run 的链路测试
*   **schema compatibility**：确保 API contract 不被升级破坏

6.4 预期产出
--------

*   流水线阶段枚举与状态记录
*   指标与日志增强
*   PCAP 回放与回归基准
*   更稳定的 CI 测试集

6.5 可直接喂给 AI 的提示词
-----------------

```
请在当前项目中实现“流水线阶段化可观测性 + 测试回归强化”升级，目标是在不改变当前整体架构、不引入 Kafka 等重型流式基础设施的前提下，把现有 PCAP 分析闭环升级为更可观测、可验证、可回归的工程化流水线。

已知约束：
1. 必须保留当前 PCAP 上传与同步处理主流程。
2. 不允许为了可观测性重构为多服务或强依赖消息队列。
3. 不能破坏现有 alerts、topology、agent、twin、scenarios、stream 的业务行为。
4. 现有 scenario regression 应继续兼容。

升级内容：
1. 将主流程显式定义为阶段：
   - parse
   - feature_extract
   - detect
   - aggregate
   - investigate
   - recommend
   - compile_plan（如该模块已实现）
   - dry_run
   - visualize
2. 对每个阶段记录：
   - status
   - start_time / end_time
   - latency_ms
   - key_metrics
   - error_summary
   - input/output summary
3. 新增回归测试机制，至少包括：
   - 固定 PCAP fixture 回归测试
   - 从 alert 到 recommendation / dry-run 的端到端测试
   - API schema compatibility 测试
4. 日志与指标应结构化，便于后续接入可视化或监控。

优化逻辑与方法：
- 不改变当前处理逻辑，只显式标注阶段并补充观测数据。
- 可观测性层必须独立，不应侵入核心业务实现。
- 测试设计要围绕“升级不破坏现有功能”这一目标。
- 所有新增能力必须能与现有 scenario regression 和 stream 机制兼容。

期望产出：
1. 流水线阶段定义与状态记录实现。
2. 结构化日志 / 指标输出。
3. PCAP fixture 回归测试集。
4. 端到端测试与兼容性测试。
5. 可读的开发文档，说明如何使用这些回归与观测能力。
```

* * *

八、最终升级清单：建议实施顺序
===============

最建议你的实施顺序是：

**第一阶段**

1.  Agent 工作流编排层
2.  推荐动作 → Twin Plan 编译层
3.  内部事件总线 / 异步处理层

这一阶段完成后，你的“研判闭环”会明显更完整。  
因为它直接把：

`Alert → Agent → Recommendation → Plan → Twin`

连成稳定链条。  
而且这些升级几乎都属于**后端内部重构 + 增量增强**，对前端冲击最小。

**第二阶段**  
4\. 3D 拓扑布局与交互增强层

这是最适合做“演示效果拔高”的升级，且不会影响检测和 Agent 主逻辑。([github.com](https://github.com/splunk/splunk-3D-graph-network-topology-viz?utm_source=chatgpt.com) [GitHub+1](https://github.com/splunk/splunk-3D-graph-network-topology-viz))

**第三阶段**  
5\. 轻量威胁情报 / MITRE 增强层  
6\. 流水线阶段化可观测性 + 测试回归强化

这两项更偏工程与可信度建设，适合在闭环稳定后补齐。([github.com](https://github.com/zhadyz/AI_SOC?utm_source=chatgpt.com) [github.com](https://github.com/ElhoubeBrahim/network-traffic-analysis?utm_source=chatgpt.com) [GitHub+3GitHub+3GitHub+3](https://raw.githubusercontent.com/zhadyz/AI_SOC/master/README.md))

* * *

九、你现在最不该做的两件事
=============

第一，不要现在就把项目强行改造成 **Wazuh/OpenSearch/Grafana/RAG 多服务平台**。  
这会破坏你当前“PCAP-first + 数字孪生 + 可解释 dry-run”的鲜明主线。([github.com](https://github.com/zhadyz/AI_SOC?utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/zhadyz/AI_SOC))

第二，不要为了“看起来更工程化”而强行上 **Kafka-first 实时流平台**。  
你当前最有价值的是闭环表达，而不是做成通用流处理平台。([github.com](https://github.com/ElhoubeBrahim/network-traffic-analysis?utm_source=chatgpt.com) [GitHub+2GitHub+2](https://github.com/ElhoubeBrahim/network-traffic-analysis))

* * *

如果你愿意，我下一条可以继续直接给你整理成一份：

**《AI 升级实施总文档》**  
格式会是你更容易直接投喂代码模型的版本，包括：

*   总体升级目标
*   6 个模块的依赖关系
*   推荐开发顺序
*   每个模块的输入/输出/约束
*   验收标准

## Response:
我把它整理成一份可直接投喂 AI 的总文档，结构会按“目标→架构原则→模块拆分→实施顺序→每模块输入输出→验收标准”来写，这样后续你可以直接拿去分批开发。

Thought for 1m 23s

《AI 升级实施总文档》
============

0\. 文档定位
--------

本文档用于指导 AI 在**不破坏你当前项目现有闭环**的前提下，分阶段完成升级实施。  
当前仓库已经明确具备以下主线能力：`PCAP 处理 → 告警生成 → 拓扑图 → Agent 分析 → Twin Dry-run → Evidence Chain → Scenario Regression`，工程结构也已拆分为 `backend / frontend / contract / infra / reports`，并且 API 已采用统一响应 envelope。[GitHub+1](https://github.com/want-be-human/project)

本文档的目标不是把项目改造成重型 SIEM 平台，而是把你当前最有特色的主线：

**网络安全 + 可视化数字孪生 + 可解释研判 + 可演练处置**

升级为更稳定、更强表现力、更适合比赛/答辩/后续开发的工程版本。你的项目当前已经把这条主线公开写进仓库特性中，包括 PCAP Processing、Topology Graph、Agent Analysis、Twin Dry-run、Evidence Chain、Scenario Regression。[GitHub+2GitHub+2](https://github.com/want-be-human/project)

* * *

1\. 总体升级目标
----------

本次升级只做 **“增强”**，不做 **“推倒重来”**。总目标如下：

1.  保留现有 API、前端页面、Mock/Real 模式、核心数据流。
2.  将 Agent 从“规则/模板式服务”升级为“可编排工作流”。
3.  将推荐结果从“自然语言建议”升级为“可编译的演练计划”。
4.  将实时推送从“仅通知层”升级为“统一事件总线驱动”。
5.  将 3D 拓扑从“可展示”升级为“更专业的图布局与交互”。
6.  增加轻量威胁知识增强与工程化可观测/回归能力。
7.  不引入会破坏项目节奏的重型依赖。

* * *

2\. 升级边界与硬性约束
-------------

### 2.1 必须保持不变的部分

*   保留现有核心业务主线：
    *   PCAP 上传与处理
    *   Alert 生成
    *   Agent 研判
    *   Twin Dry-run
    *   Scenario Regression
*   保留现有 API 契约风格：
    *   统一 envelope
    *   原字段命名不变
*   保留现有前端功能入口与总体页面结构
*   保留现有 Twin 动作语义
*   保留现有系统“advisory only”安全边界

### 2.2 明确不做的升级

不将项目直接对齐到重型 AI-SOC/SIEM 架构。  
`AI_SOC` 的仓库明确是基于 Wazuh、TheHive、RAG、多服务编排的研究型 AI-SOC 实现；`network-traffic-analysis` 则是 Kafka + PostgreSQL + Power BI 的流式数据平台。它们适合作为思路参考，但不适合作为你当前项目的直接落地方向。[GitHub+1](https://github.com/zhadyz/AI_SOC)

* * *

3\. 推荐升级模块总览
------------

本次建议实施 6 个升级模块：

### 高优先级

1.  Agent 工作流编排层
2.  推荐动作 → Twin Plan 编译层
3.  内部事件总线 / 异步处理层
4.  3D 拓扑布局与交互增强层

### 中优先级

5.  轻量威胁情报 / MITRE 增强层
6.  流水线阶段化可观测性 + 测试回归强化

* * *

4\. 参考仓库与可借鉴点
-------------

### 4.1 Splunk 3D Graph Network Topology Visualization

该仓库的核心优势是 **基于 ThreeJS/WebGL 的 force-directed graph 可视化**，重点在图布局、图交互、视觉编码能力，而不是你的业务闭环。它适合作为你 3D 拓扑层的表现力参考。[GitHub](https://github.com/splunk/splunk-3D-graph-network-topology-viz)

### 4.2 Agentic SOC Platform

该仓库最值得借鉴的是 **Agent / Module / Playbook / SIRP 的平台化抽象**。README 明确写到它支持 AI-driven intelligence、built-in SIRP、playbook engine，以及基于 LangGraph / Dify / 本地 LLM 的可扩展能力。[GitHub](https://github.com/FunnyWolf/agentic-soc-platform)

### 4.3 AI\_SOC

该仓库体现的是 **重型 AI-SOC 平台** 路线：SIEM 基础设施、机器学习、上下文增强、多服务健康监控与自动编排。它适合借鉴“知识增强”和“验证思路”，但不适合整体照搬。[GitHub](https://github.com/zhadyz/AI_SOC)

### 4.4 network-traffic-analysis

该仓库的重点是 **capture → streaming → transform → store → visualize** 的数据流水线分阶段结构。它值得借鉴的是“阶段化”和“可观测性思路”，不值得直接引入 Kafka-first 架构。[GitHub](https://github.com/ElhoubeBrahim/network-traffic-analysis)

* * *

5\. 升级模块设计
==========

* * *

模块 A：Agent 工作流编排层
-----------------

### A.1 升级目标

将当前 `triage → investigate → recommend` 从普通服务调用升级为**内部可编排工作流**，但保持现有接口与返回格式不变。当前仓库 README 已将这三段作为现有关键能力公开列出。[GitHub](https://github.com/want-be-human/project)

### A.2 推荐仓库可借鉴逻辑

`agentic-soc-platform` 的核心价值在于将安全分析能力拆成**可组合模块**，并通过 playbook / workflow 驱动，避免单点硬编码。它的设计不是“多接一个 LLM”，而是“把流程抽象出来”。[GitHub](https://github.com/FunnyWolf/agentic-soc-platform)

### A.3 在你项目中的无破坏实现方式

新增内部目录，例如：

*   `backend/app/workflows/`
*   `backend/app/workflows/engine.py`
*   `backend/app/workflows/stages/triage.py`
*   `backend/app/workflows/stages/investigation.py`
*   `backend/app/workflows/stages/recommendation.py`

实现要求：

*   保留现有 route 不变
*   route 内部改为调用 `WorkflowEngine`
*   每个 stage 使用统一接口
*   配置开关控制：
    *   开启：走新工作流
    *   关闭：fallback 到旧逻辑
*   新增 workflow execution log，但不影响现有表

### A.4 输入 / 输出

输入：

*   alert\_id
*   alert 数据
*   证据数据
*   上一阶段产出

输出：

*   与当前 triage / investigate / recommend 完全兼容的响应对象
*   stage 执行日志

### A.5 验收标准

*   旧接口 URL 不变
*   返回 JSON 字段不变
*   前端无需修改
*   关闭 feature flag 时行为与旧系统一致
*   新增 stage 执行轨迹可追踪

### A.6 可直接投喂 AI 的实现提示词

```
请在当前项目中实现“Agent 工作流编排层”升级，目标是在不破坏现有 API、数据库核心结构和前端调用方式的前提下，将当前的 triage / investigate / recommend 逻辑升级为可编排、可扩展、可回退的内部工作流。

约束：
1. 保留现有 alerts/{id}/triage、alerts/{id}/investigate、alerts/{id}/recommend 路由与响应格式。
2. 保持 advisory only，不允许直接执行真实封禁或隔离动作。
3. 旧逻辑保留，并支持 fallback。
4. 前端不得因本次升级而修改调用方式。

实现要求：
1. 新增 WorkflowEngine。
2. 将 Agent 能力拆成 TriageStage、InvestigationStage、RecommendationStage。
3. 每个 stage 的输入输出兼容现有 schema。
4. 新增执行轨迹记录：workflow_id、stage_name、status、latency_ms、input/output snapshot。
5. 路由内部改成：route -> WorkflowEngine -> stage -> 原响应。
6. 增加 feature flag 控制启用与回退。

预期产出：
1. workflows 目录结构。
2. 工作流引擎与 stage 抽象。
3. 三阶段封装实现。
4. fallback 兼容逻辑。
5. 测试用例，验证接口不变。
```

* * *

模块 B：推荐动作 → Twin Plan 编译层
-------------------------

### B.1 升级目标

把 Agent 输出的“文本建议”进一步编译为 Twin 可直接消费的 **结构化 ActionPlan**，形成：

`Evidence → Recommendation → PlanCompiler → Twin Dry-run`

### B.2 推荐仓库可借鉴逻辑

`agentic-soc-platform` 强调 playbook；`AI_SOC` 强调将分析结果结构化为 severity、context、recommendation 等可处理对象。可借鉴的核心思想是：**研判结果不能只停留在文字层，必须可落到结构化动作层。** [GitHub+1](https://github.com/FunnyWolf/agentic-soc-platform)

### B.3 在你项目中的无破坏实现方式

新增：

*   `backend/app/services/plan_compiler/`
*   `backend/app/services/plan_compiler/compiler.py`

编译器输入：

*   alert
*   investigation
*   evidence chain
*   recommendation

编译器输出：

*   `ActionPlan[]`

每个动作对象必须只使用你当前系统已支持的动作语义，不得扩散出新的高耦合动作体系。

### B.4 输入 / 输出

输入：

*   alert
*   evidence
*   investigation result
*   recommendation result

输出：

*   `action_type`
*   `target`
*   `params`
*   `rollback`
*   `confidence`
*   `derived_from_evidence`
*   `reasoning_summary`

### B.5 验收标准

*   recommendation 文本输出仍存在
*   Twin dry-run 可直接消费 plan compiler 输出
*   每个动作都可回溯到 evidence
*   不新增真实执行能力

### B.6 可直接投喂 AI 的实现提示词

```
请在当前项目中实现“推荐动作到 Twin Plan 的编译层”，目标是在不改变现有 Twin API、现有动作类型和前端总体交互模式的前提下，将 Agent 的文本建议自动编译为可用于 dry-run 的结构化处置计划。

约束：
1. 必须保留 recommendation 的自然语言输出。
2. 仅能生成当前系统已支持的 Twin 动作类型。
3. 所有动作只能用于审核和 dry-run，不能直接执行。
4. 不能破坏现有前端和 Twin 接口语义。

实现要求：
1. 新增独立 PlanCompiler。
2. 输入包括 alert、evidence、investigation、recommendation。
3. 输出为 ActionPlan 列表，每条包含 action_type、target、params、rollback、confidence、derived_from_evidence、reasoning_summary。
4. 编译规则必须可解释、确定性、可回溯。
5. Twin dry-run 直接消费编译结果。

预期产出：
1. PlanCompiler 实现。
2. recommendation -> action plan 的映射规则。
3. 与 Twin 的集成代码。
4. 端到端测试：alert -> recommendation -> compile -> dry-run。
```

* * *

模块 C：内部事件总线 / 异步处理层
-------------------

### C.1 升级目标

把现有“WebSocket 广播层”升级为“统一内部事件总线 + WebSocket 订阅层”。  
当前仓库已有 stream 能力和整体闭环，但需要把“通知”与“业务事件”解耦。现有项目 README 也强调了完整链路与回归验证。[GitHub](https://github.com/want-be-human/project)

### C.2 推荐仓库可借鉴逻辑

`agentic-soc-platform` 的事件链路核心是：不同模块不是彼此直连，而是围绕统一事件流工作。它的实现细节可以不照搬 Redis Stream，但它的抽象方式值得采用。[GitHub](https://github.com/FunnyWolf/agentic-soc-platform)

### C.3 在你项目中的无破坏实现方式

新增：

*   `backend/app/core/events/base.py`
*   `backend/app/core/events/inmemory_bus.py`
*   `backend/app/core/events/models.py`

先实现：

*   `EventBus`
*   `InMemoryEventBus`

后续预留：

*   `RedisEventBus`

然后让这些节点发布事件：

*   PCAP 处理进度
*   Alert 创建
*   Investigation 完成
*   Recommendation 完成
*   Twin dry-run 创建
*   Scenario regression 完成

WebSocket router 不直接绑定业务服务，而是订阅 EventBus。

### C.4 输入 / 输出

输入：

*   领域事件对象

输出：

*   topic 级发布 / 订阅事件
*   前端仍接收原有实时推送

### C.5 验收标准

*   前端现有实时更新不受影响
*   WebSocket 逻辑继续工作
*   业务服务不直接依赖 WebSocket manager
*   后续可扩展 Redis 而不重写业务层

### C.6 可直接投喂 AI 的实现提示词

```
请在当前项目中实现“内部事件总线 / 异步处理层”升级，目标是在不改变现有 WebSocket 对外行为和事件名称的前提下，将当前仅用于前端推送的内存广播机制升级为统一的内部事件总线抽象。

约束：
1. 保留现有 WebSocket 路由和前端订阅方式。
2. 保留现有事件语义。
3. 当前阶段不能强依赖 Redis、Kafka。
4. 不能打散现有业务模块。

实现要求：
1. 新增 EventBus 抽象：publish、subscribe、unsubscribe。
2. 实现 InMemoryEventBus 作为默认实现。
3. 预留 RedisEventBus 接口。
4. 所有关键业务节点统一通过 EventBus 发布事件。
5. WebSocket router 改为事件消费者。

预期产出：
1. 事件模型与事件总线接口。
2. InMemoryEventBus。
3. WebSocket 适配层。
4. 业务事件接入代码。
5. 兼容性测试。
```

* * *

模块 D：3D 拓扑布局与交互增强层
------------------

### D.1 升级目标

在不改动现有 `/topology/graph` 主契约的前提下，提升 3D 拓扑在**布局质量、图表达能力、交互体验**上的专业度。你的项目当前已明确有 Topology Graph、IP/subnet 模式和时间边区间能力。[GitHub](https://github.com/want-be-human/project)

### D.2 推荐仓库可借鉴逻辑

Splunk 这个仓库的核心是 **force-directed graph based on ThreeJS/WebGL**。这说明它的真正优势是布局引擎、视觉编码和相机/图操作能力，而不是业务逻辑。[GitHub](https://github.com/splunk/splunk-3D-graph-network-topology-viz)

### D.3 在你项目中的无破坏实现方式

保留现有 topology 数据结构，仅在前端增强渲染层。

新增布局模式：

*   `circle`
*   `force`
*   `dag`
*   `clustered-subnet`

新增交互能力：

*   标签开关
*   风险热度开关
*   边箭头开关
*   子网聚类开关
*   相机预设
*   焦点追踪
*   告警高亮 / dry-run 影响范围增强

### D.4 输入 / 输出

输入：

*   现有 topology graph 数据
*   alert / impacted / activeIntervals / risk 等业务字段

输出：

*   多布局切换的 3D 图
*   更强的图交互体验
*   不影响现有 TimeSlider / SideInspector / DryRunOverlay

### D.5 验收标准

*   原 circle 模式可继续使用
*   不强制修改后端
*   时间回放与布局切换不冲突
*   dry-run 影响显示更清晰
*   中等规模节点数下不卡顿

### D.6 可直接投喂 AI 的实现提示词

```
请在当前项目中实现“3D 拓扑布局与交互增强层”升级，目标是在不破坏现有 topology API、时间回放、dry-run overlay、side inspector 的前提下，显著提升拓扑图的布局质量、信息表达能力和交互体验。

约束：
1. 保留现有 /topology/graph 接口及核心字段。
2. 保留现有 Topology3D、TimeSlider、SideInspector、DryRunOverlay 协作关系。
3. 旧的 circle 布局必须保留。
4. 不要求后端大规模改造。

实现要求：
1. 新增多布局模式：circle、force、dag、clustered-subnet。
2. 新增图交互配置：标签、箭头、风险热度、聚类、相机预设。
3. 复用现有图字段驱动可视化。
4. 优化选中、聚焦、告警高亮、dry-run 影响展示。
5. 布局逻辑与渲染逻辑分离。

预期产出：
1. 独立布局策略模块。
2. 多布局切换实现。
3. 增强交互实现。
4. 与时间回放和 dry-run overlay 的兼容集成。
5. 必要的性能优化。
```

* * *

模块 E：轻量威胁情报 / MITRE 增强层
-----------------------

### E.1 升级目标

在不引入重型 RAG / SIEM / 威胁情报平台的前提下，为 investigation 与 recommendation 增加**可解释的知识增强能力**。

### E.2 推荐仓库可借鉴逻辑

`AI_SOC` 明确是一套 AI-Augmented SOC，README 中强调 context-aware security analysis、多服务集成、研究型实现。可借鉴的是“把分析放回威胁语境中去解释”，而不是整体基础设施。[GitHub](https://github.com/zhadyz/AI_SOC)

### E.3 在你项目中的无破坏实现方式

新增：

*   `backend/app/services/threat_enrichment/`

第一版实现为：

*   本地 JSON/YAML 规则库
*   MITRE tactics/techniques 映射
*   常见端口、协议、告警类型、证据 token 规则匹配

输出为增量字段，不替换现有结果结构。

### E.4 输入 / 输出

输入：

*   alert\_type
*   protocol
*   port
*   features
*   evidence keywords

输出：

*   techniques
*   tactics
*   intel\_refs
*   enrichment\_confidence

### E.5 验收标准

*   enrichment 失败时静默降级
*   主流程正常运行
*   investigation / recommendation 的可解释性增强
*   不增加外部重依赖

### E.6 可直接投喂 AI 的实现提示词

```
请在当前项目中实现“轻量威胁情报 / MITRE 增强层”升级，目标是在不引入重型 RAG 微服务、不引入外部 SIEM 强依赖的前提下，为 investigation 和 recommendation 增加可解释的威胁知识增强能力。

约束：
1. 不能要求部署 Wazuh、OpenSearch、Grafana、向量数据库。
2. 必须支持本地运行。
3. enrichment 失败时必须静默降级。
4. 只能做增量字段扩展，不能破坏原有输出结构。

实现要求：
1. 新增 ThreatEnrichmentService。
2. 输入包括 alert_type、protocol、port、top_features、evidence keywords。
3. 输出包括 techniques、tactics、intel_refs、enrichment_confidence。
4. 第一版使用本地规则与静态映射。
5. 在 investigation 和 recommendation 中按需接入。

预期产出：
1. ThreatEnrichmentService。
2. 本地知识映射文件。
3. 增强字段集成。
4. 降级测试和单元测试。
```

* * *

模块 F：流水线阶段化可观测性 + 测试回归强化
------------------------

### F.1 升级目标

把现有闭环流程显式化为工程流水线阶段，并补足结构化观测与回归能力。你仓库已经把 Scenario Regression 列为核心特性，并且提供测试入口。[GitHub+1](https://github.com/want-be-human/project)

### F.2 推荐仓库可借鉴逻辑

`network-traffic-analysis` 明确将流程拆为 data collection、streaming、transformation、storage、visualization；`AI_SOC` 强调多服务健康监控与研究级验证。可借鉴的是“阶段化”与“验证意识”。[GitHub+1](https://github.com/ElhoubeBrahim/network-traffic-analysis)

### F.3 在你项目中的无破坏实现方式

定义内部流水线阶段：

*   parse
*   feature\_extract
*   detect
*   aggregate
*   investigate
*   recommend
*   compile\_plan
*   dry\_run
*   visualize

每个阶段记录：

*   status
*   latency
*   start / end
*   key\_metrics
*   error\_summary
*   input/output summary

测试增强：

*   fixture PCAP regression
*   alert → recommendation → plan → dry-run e2e
*   schema compatibility test

### F.4 输入 / 输出

输入：

*   每个阶段的上下文对象

输出：

*   结构化日志
*   阶段指标
*   回归基线
*   稳定的测试套件

### F.5 验收标准

*   不改业务主流程
*   能清楚看到每阶段耗时和状态
*   固定 PCAP 回归结果稳定
*   接口 contract 升级后不被破坏

### F.6 可直接投喂 AI 的实现提示词

```
请在当前项目中实现“流水线阶段化可观测性 + 测试回归强化”升级，目标是在不改变当前整体架构、不引入 Kafka 等重型流式基础设施的前提下，把现有 PCAP 分析闭环升级为更可观测、可验证、可回归的工程化流水线。

约束：
1. 保留当前 PCAP 上传与处理主流程。
2. 不引入多服务重构。
3. 不破坏 alerts、topology、agent、twin、scenario、stream 行为。
4. 保持现有 scenario regression 可用。

实现要求：
1. 显式定义阶段：parse、feature_extract、detect、aggregate、investigate、recommend、compile_plan、dry_run、visualize。
2. 每阶段记录 status、latency_ms、time range、key_metrics、error_summary、input/output summary。
3. 新增固定 PCAP fixture 回归测试。
4. 新增端到端测试和 schema compatibility 测试。
5. 输出结构化日志和指标。

预期产出：
1. 流水线阶段定义。
2. 可观测性记录实现。
3. 回归测试集。
4. 兼容性测试。
5. 开发文档。
```

* * *

6\. 推荐实施顺序
==========

第一阶段：先打通“研判闭环”
--------------

1.  Agent 工作流编排层
2.  推荐动作 → Twin Plan 编译层
3.  内部事件总线 / 异步处理层

原因：

*   这三项都主要发生在后端内部
*   对前端冲击最小
*   能最快把“告警 → 解释 → 建议 → 演练”链条真正做成平台化主线

第二阶段：再拉升“展示效果”
--------------

4.  3D 拓扑布局与交互增强层

原因：

*   这项最适合增强演示冲击力
*   与业务主逻辑耦合较低
*   对答辩展示价值极高

第三阶段：最后补“可信度与工程化”
-----------------

5.  轻量威胁情报 / MITRE 增强层
6.  流水线阶段化可观测性 + 测试回归强化

原因：

*   这两项更偏质量和解释层
*   适合在主链稳定后补齐

* * *

7\. 依赖关系
========

简化依赖如下：

*   模块 A 是模块 B 的上游
*   模块 B 与模块 C 协同最好，但可独立做
*   模块 D 几乎独立
*   模块 E 最好接入模块 A 的 investigate / recommend 阶段
*   模块 F 贯穿所有模块，建议从第一阶段开始同步补最基础能力

关系图可理解为：

`A → B`  
`A → E`  
`C` 服务于 `A/B/F`  
`D` 独立增强展示层  
`F` 贯穿全局

* * *

8\. 总体验收标准
==========

当以下条件全部满足时，可认为本轮升级完成：

1.  现有 API 路径与 JSON 主字段不变。
2.  前端现有页面和交互入口可继续工作。
3.  Agent 能以工作流方式运行，且可回退旧逻辑。
4.  recommendation 可自动编译为结构化 Twin 演练计划。
5.  关键业务节点通过统一事件总线发布。
6.  拓扑图具备多布局和更强交互能力。
7.  investigation / recommendation 支持轻量威胁知识增强。
8.  全流程具备阶段化日志、回归测试、兼容性测试。
9.  整个升级不引入必须依赖的重型外部平台。

* * *

9\. 给 AI 的总执行指令
===============

下面这段可以作为总控提示词，给 AI 作为统一实施说明：

```
你正在为一个已具备完整闭环的网络安全数字孪生项目做增量升级。该项目当前已经具备：PCAP 处理、告警生成、拓扑图、Agent 分析、Twin Dry-run、Evidence Chain、Scenario Regression。你的任务不是重构整个项目，也不是把它改造成重型 SIEM 平台，而是在不破坏现有 API、前端页面、Mock/Real 模式和核心数据流的前提下，分阶段完成以下 6 个升级模块：

1. Agent 工作流编排层
2. 推荐动作 -> Twin Plan 编译层
3. 内部事件总线 / 异步处理层
4. 3D 拓扑布局与交互增强层
5. 轻量威胁情报 / MITRE 增强层
6. 流水线阶段化可观测性 + 测试回归强化

统一约束：
- 保留现有 API 路径和主字段
- 保留现有前端功能入口
- 保留 advisory only，不允许真实执行处置动作
- 新能力必须可插拔、可回退、低耦合
- 数据库只允许增量迁移
- 所有升级必须可以自然嵌入现有 backend / frontend / contract / infra 结构
- 不引入必须部署的重型外部平台，如 Wazuh、OpenSearch、Kafka、向量数据库等

推荐开发顺序：
第一阶段：1、2、3
第二阶段：4
第三阶段：5、6

你的实现应始终遵循以下原则：
- 先兼容，再增强
- 先抽象，再扩展
- 先复用现有字段，再新增可选字段
- 先保证链路闭环，再追求复杂平台化

每完成一个模块，都要给出：
1. 改动文件清单
2. 核心类与接口
3. 与现有模块的兼容说明
4. feature flag 或 fallback 策略
5. 测试方案
6. 验收结果
```

* * *

这份就是可直接用的《AI 升级实施总文档》。  
你要的话，我下一条直接继续整理成 **“按模块拆分的 6 份开发子文档”**，每份都写成更适合代码模型逐步实现的版本。



---
Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)
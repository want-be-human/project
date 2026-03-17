# 项目功能对齐建议

**User:** Anonymous (q15525125026@163.com)  
**Created:** 3/10/2026 20:03:56  
**Updated:** 3/15/2026 19:49:24  
**Exported:** 3/16/2026 19:06:55  

## Response:
Thought for a few seconds

会，下面我按你前面那 9 个优化项，直接说清楚：

**优化后，前端会在哪个页面、哪个区域、出现什么变化。**

* * *

1\. Agent 结果回填与告警详情页初始化展示
-------------------------

### 会体现在哪

*   **页面**：`/alerts/[id]` 告警详情页
*   **区域**：`AgentPanel` 分析区、告警详情主内容区

### 你会看到什么变化

现在是进入详情页后，哪怕这个告警之前已经跑过 triage / investigate / recommend，页面也可能还是“空的”，要你重新点一次按钮。

优化后会变成：

*   进入告警详情页时，**Agent 分析结果自动显示**
*   如果这个告警之前已经做过：
    *   triage
    *   investigate
    *   recommend  
        那这三部分会直接回填出来
*   页面上会更像“历史分析记录”，而不是“临时触发器”

### 具体视觉表现

在告警详情页右侧或下方的 Agent 区域，会看到：

*   **Triage 总结**
*   **Investigation 结果**
*   **Recommendation 建议**
*   已有结果的状态标签，比如：
    *   已生成
    *   最近更新时间
    *   重新分析按钮

### 前端观感变化

原来：进入页面像“还没分析”  
优化后：进入页面像“**这个告警已经有完整研判记录**”

* * *

2\. Recommendation → compile-plan → Twin 真实链路接入
-----------------------------------------------

### 会体现在哪

*   **页面**：`/alerts/[id]` 告警详情页
*   **区域**：
    *   `AgentPanel` 的 recommendation 区
    *   `ActionBuilder`
    *   `DryRunPanel`
    *   以及跳转到拓扑页后的 dry-run overlay

### 你会看到什么变化

现在 recommendation 更像一段建议文字，前端自己猜动作类型。  
优化后会变成：

*   recommendation 下方新增一个更明确的入口，比如：
    *   **“编译为处置计划”**
    *   **“生成演练动作”**
*   点击后会出现一组**结构化动作卡片**
*   每个动作卡片能看到：
    *   动作类型
    *   目标对象
    *   置信度
    *   推理说明
    *   证据来源
    *   回滚说明

### 具体视觉表现

在 recommendation 区块下，会新增一个“编译结果”区域，例如：

*   `block_ip -> 192.168.1.20`
*   `rate_limit_service -> web:443`
*   `segment_subnet -> 10.0.2.0/24`

并且每条动作会带：

*   `confidence`
*   `reasoning_summary`
*   `derived_from_evidence`

然后用户可以继续：

*   确认计划
*   创建 dry-run
*   在拓扑图里查看影响

### 前端观感变化

原来：建议只是文字  
优化后：建议会长成“**可操作的处置动作列表**”

* * *

3\. 威胁增强 `threat_context` 的前端类型与渲染
----------------------------------

### 会体现在哪

*   **页面**：`/alerts/[id]` 告警详情页
*   **区域**：
    *   `AgentPanel` 的 Investigation 区
    *   `AgentPanel` 的 Recommendation 区

### 你会看到什么变化

优化后，调查结果和建议结果里会多出一个**威胁上下文**模块。

### 具体视觉表现

在 Investigation 结果里，你会看到类似：

*   **MITRE Tactics**
*   **MITRE Techniques**
*   **Threat Context / 威胁语境**
*   **Confidence / 置信度**
*   **参考链接 / Intel Refs**

推荐做成标签 + 信息块的形式，比如：

*   `Discovery`
*   `Credential Access`
*   `Impact`

以及 technique tag：

*   `T1046`
*   `T1110`
*   `T1498`

下面再配一段短说明：

*   为什么这个告警会映射到这些 tactics / techniques
*   当前映射置信度是多少
*   可点击的参考链接有哪些

### 前端观感变化

原来：系统只会说“像扫描/暴力破解”  
优化后：系统会更像真正的 SOC 界面，能说“**这类行为在标准安全框架里属于什么攻击语境**”

* * *

4\. Twin / Scenario 的 WebSocket 事件消费修复
--------------------------------------

### 会体现在哪

*   **页面**：
    *   `/alerts/[id]`
    *   `/topology`
    *   `/scenarios`
*   **区域**：
    *   `DryRunPanel`
    *   `ScenarioRunPanel`
    *   拓扑页的 dry-run 叠加层
    *   列表/状态更新区

### 你会看到什么变化

现在很多实时事件“订阅了但没真正刷新好”。  
优化后会变成：

*   创建 dry-run 后，`DryRunPanel` 会**自动出现完整结果**
*   Scenario 运行后，`ScenarioRunPanel` 会**实时更新状态**
*   不用手动刷新页面，也不会出现“事件到了但界面没变”的情况

### 具体视觉表现

#### 在告警详情页的 DryRunPanel

你会看到：

*   创建成功后立即出现：
    *   dry run id
    *   风险值
    *   影响对象
    *   动作列表
    *   结果状态

#### 在 `/scenarios`

你会看到：

*   运行中的场景有状态变化：
    *   pending
    *   running
    *   completed
    *   failed
*   checks / metrics 会自动更新
*   运行完成后，详情自动展开或自动刷新

### 前端观感变化

原来：实时链路有点断断续续  
优化后：会更像“**系统真的在流动，动作执行完会自动反映到界面**”

* * *

5\. 告警详情页闭环刷新：证据链 / 建议 / dry-run 自动刷新
-------------------------------------

### 会体现在哪

*   **页面**：`/alerts/[id]`
*   **区域**：
    *   `EvidenceChainView`
    *   `AgentPanel`
    *   `DryRunPanel`
    *   告警详情头部状态区

### 你会看到什么变化

这是最能提升“闭环感”的优化之一。

现在你在同页点击：

*   investigate
*   recommend
*   dry-run

页面很多区域不会自己更新。  
优化后会变成：

*   investigate 完成后，证据链会立即多出新节点
*   recommend 完成后，建议区会立即更新
*   dry-run 创建后，证据链 / 计划 / 风险结果会同步刷新

### 具体视觉表现

在告警详情页：

#### EvidenceChainView

会即时新增或更新：

*   hypothesis 节点
*   recommendation 节点
*   action / dry-run 关联节点

#### AgentPanel

会立即显示最新调查和建议结果

#### DryRunPanel

会立即显示新 dry-run 结果，而不是停留在旧状态

### 前端观感变化

原来：你点了按钮，但界面像没完全跟上  
优化后：会形成真正的：

**证据链 → 调查 → 建议 → 演练**

这一整条可见闭环

* * *

6\. 流水线可观测性前端补齐（pipeline stages UI）
-----------------------------------

### 会体现在哪

*   **页面**：
    *   `/pcaps`
    *   `/scenarios`（如果复用）
*   **区域**：
    *   PCAP 处理详情区
    *   Scenario 运行详情区
    *   新增的 pipeline timeline / stage card 区域

### 你会看到什么变化

现在 PCAP 页主要只能看到：

*   上传状态
*   处理状态
*   flow 数
*   alert 数

优化后会多出一个**阶段级进度区**。

### 具体视觉表现

在 `/pcaps` 页面，每条处理任务或详情面板中，会新增一个类似时间线/步骤条的区域：

*   `parse`
*   `feature_extract`
*   `detect`
*   `aggregate`
*   `investigate`
*   `recommend`
*   `compile_plan`
*   `dry_run`
*   `visualize`

每个阶段会显示：

*   状态（未开始 / 进行中 / 完成 / 失败）
*   耗时
*   摘要信息

例如：

*   parse：2.1s
*   detect：发现 4 个异常 flow
*   aggregate：生成 2 条告警

### 在 `/scenarios`

可能会复用相同组件，显示某次场景回归里每个阶段的执行情况。

### 前端观感变化

原来：只能看到“处理好了没”  
优化后：能看到“**处理是怎么一步步跑出来的**”

* * *

7\. 拓扑页 `dryRunId` 查询错误回退修复
---------------------------

### 会体现在哪

*   **页面**：`/topology`
*   **区域**：
    *   dry-run overlay
    *   页面状态提示区
    *   可能的 not found / loading 区域

### 你会看到什么变化

现在最危险的问题是：如果当前 `dryRunId` 没找到，页面可能错把别的 dry-run 结果显示出来。

优化后会变成：

*   只有正确匹配当前 `dryRunId` 的结果才会显示
*   找不到时，页面会明确告诉你：
    *   未找到 dry-run
    *   dry-run 已失效
    *   正在加载

### 具体视觉表现

在 `/topology` 页：

#### 正常情况

会显示当前 dry-run 对应的影响高亮和 overlay

#### 异常情况

不会再莫名显示别的计划，而是显示：

*   `Dry run not found`
*   `Loading dry run...`
*   `No dry run selected`

### 前端观感变化

原来：可能“看起来有结果，但其实是错的”  
优化后：**显示更可信，不会串页**

* * *

8\. EvidenceChainView 节点类型样式修复
------------------------------

### 会体现在哪

*   **页面**：`/alerts/[id]`
*   **区域**：`EvidenceChainView`

### 你会看到什么变化

现在 `hypothesis` 节点因为类型判断写错，样式掉到默认分支里，不够明显。

优化后会变成：

*   `hypothesis` 节点有专属颜色/图标/样式
*   它和 evidence、recommendation、action 节点能明显区分开

### 具体视觉表现

在证据链图里，你会更容易一眼看出：

*   哪些是原始证据
*   哪些是调查/假设节点
*   哪些是建议节点
*   哪些是处置动作节点

### 前端观感变化

原来：证据链里有些节点“长得差不多”  
优化后：**层级更清楚，读图更容易**

* * *

9\. real 模式隐藏 mock 调试入口 `simulateWs`
------------------------------------

### 会体现在哪

*   **页面**：`/alerts`
*   **区域**：告警列表页顶部或工具区

### 你会看到什么变化

优化后，在 real 模式下：

*   `simulateWs` 按钮不会再出现

mock/dev 模式下它还可以保留。

### 前端观感变化

原来：真实界面里混进了调试按钮  
优化后：**页面更像正式产品界面**

* * *

最后，按页面整体看会有什么效果
===============

* * *

`/alerts` 告警列表页
---------------

### 会体现的优化

*   事件刷新更稳定
*   real 模式不再显示 `simulateWs`

### 你会看到

*   列表新增/更新更自然
*   工具栏更干净、更正式

* * *

`/alerts/[id]` 告警详情页
--------------------

### 会体现的优化最多

*   Agent 结果回填
*   threat\_context 展示
*   compile-plan 结果展示
*   dry-run 实时刷新
*   证据链闭环刷新
*   hypothesis 样式修复

### 你会看到

这个页面会从“详情查看页”升级成真正的：

**告警研判与处置工作台**

因为这里会同时出现：

*   告警信息
*   证据链
*   triage / investigation / recommendation
*   threat context
*   结构化行动计划
*   dry-run 结果

而且这些内容会互相联动刷新。

* * *

`/pcaps`
--------

### 会体现的优化

*   pipeline stages UI

### 你会看到

从“文件处理状态页”升级成“**处理流水线可观测页**”

* * *

`/topology`
-----------

### 会体现的优化

*   dry-run overlay 精准加载修复
*   继续承接 compile-plan / dry-run 的结果展示

### 你会看到

*   当前 dry-run 的影响结果更可信
*   错误状态更明确
*   不会再串别的 dry-run 数据

* * *

`/scenarios`
------------

### 会体现的优化

*   scenario 事件消费修复
*   pipeline 观测补齐（若复用）

### 你会看到

*   运行状态更实时
*   checks / metrics 更新更连贯
*   可能会出现更清晰的 stage 执行过程

* * *

一句话总总结
======

这些优化做完后，前端最明显的变化是：

告警详情页
-----

会变成真正的主战场，能完整展示：  
**证据 → 调查 → 威胁语境 → 建议 → 编译计划 → 演练结果**

PCAP / Scenario 页
-----------------

会变得更“可观测”，用户能看懂系统怎么一步步跑

拓扑页
---

会变得更“可信”，不会再误显示别的 dry-run

列表页
---

会更干净，更像正式系统

如果你愿意，我下一条可以继续帮你整理一份  
**“前端页面-组件-优化项对照表”**，做成非常清楚的表格版。



---
Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)
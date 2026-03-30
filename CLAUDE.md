# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NetTwin-SOC is a network security platform combining PCAP analysis, ML-based anomaly detection, digital twin simulation, and AI-driven triage. It has two independently runnable services: a FastAPI backend and a Next.js frontend.

## Commands

### Backend (Python 3.11+)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload --port 8000

# Run all tests
pytest app/tests/

# Run a single test file
pytest app/tests/unit/test_detection.py -v

# Run by category
pytest app/tests/unit/
pytest app/tests/integration/
pytest app/tests/regression/

# Lint
ruff check .
ruff format .

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend (Node 18+)

```bash
cd frontend

npm install
npm run dev          # dev server on :3000
npm run dev:turbo    # with Turbo
npm run build
npm run lint
```

### Full Stack (Docker)

```bash
cd infra
docker-compose up    # backend :8000, frontend :3000
```

## Architecture

### Data Pipeline (9 stages)

PCAP upload → Parsing (dpkt) → Feature Extraction (20+ features/flow) → Detection (IsolationForest) → Alert Aggregation → Agent Investigation → Recommendations → Plan Compilation → Digital Twin Dry-run

Each stage is a discrete service in `backend/app/services/`. The `pipeline/` service tracks observability across all stages.


## 约束
你正在修改仓库 want-be-human/project。请严格基于当前代码实现，不要凭空重构不存在的模块。先阅读并分析这些文件，再开始修改：

### 后端：
- backend/app/api/routers/scenarios.py
- backend/app/services/scenarios/service.py
- backend/app/models/scenario.py
- backend/app/schemas/scenario.py
- backend/app/api/routers/stream.py
- backend/app/api/routers/pipeline.py
- backend/app/models/pipeline.py
- backend/app/services/pipeline/__init__.py
- backend/app/services/pipeline/tracker.py
- backend/app/services/pipeline/models.py

### 前端：
- frontend/src/app/(main)/scenarios/page.tsx
- frontend/src/components/scenarios/ScenarioList.tsx
- frontend/src/components/scenarios/ScenarioRunPanel.tsx
- frontend/src/components/pipeline/PipelineStageTimeline.tsx
- frontend/src/lib/api/real.ts
- frontend/src/lib/api/types.ts
- frontend/src/components/providers/WSProvider.tsx

### 总目标：
1. 回归场景支持“归档 + 二次确认硬删除”
2. 创建场景升级为“可配置 benchmark”，检查项改为可视化表单
3. scenario run 升级为“实时阶段流 + 延迟指标 + 失败归因”
4. 接入 OpenTelemetry，用于 scenario run 的 traces / metrics / logs
5. 把 processing time 拆成“校验耗时 validation_latency_ms”和“pipeline 耗时 pipeline_latency_ms”
6. 删除旧的不必要逻辑，避免“新逻辑失败就退回旧逻辑”的双轨代码
7. 尽量保持现有目录结构和风格一致，优先做强完整、强健壮的实现

### 硬性要求：
- 先给出“现状问题清单 + 修改计划 + 影响文件列表”
- 再实施修改
- 每改完一个子任务，都同步删除对应旧逻辑和无用字段/分支
- 所有 API / Schema / TypeScript 类型必须一致
- 所有 WebSocket 事件名、payload、前端订阅、后端广播必须一一对齐
- 所有 UI 状态必须显式区分：业务 fail、执行异常、删除中、归档中、运行中、实时阶段流中
- 所有删除操作必须二次确认
- 所有新增数据模型/字段都要给出迁移方案
- 输出内容必须包含：
  1) 修改说明
  2) 关键代码 diff 或完整文件
  3) 数据库迁移
  4) 测试点
  5) 手工验收步骤

### 禁止事项：
- 禁止保留“旧字段继续展示但新字段也加上”的临时兼容层，除非明确说明迁移窗口
- 禁止前端写死 benchmark 默认检查项
- 禁止只做 UI，不改后端 schema / service
- 禁止只发 scenario.run.done，不做中间阶段事件
- 禁止把 pipeline_latency_ms 和 validation_latency_ms 混成一个字段
- 禁止用“try 新逻辑，except 后走旧逻辑”的回退实现
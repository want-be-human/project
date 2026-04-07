# NetTwin-SOC

基于数字孪生的网络流量安全分析平台。上传 PCAP 文件，自动完成流量解析、三层复合异常检测、告警生成、AI 智能研判、数字孪生推演与决策建议，帮助安全运维人员快速定位并响应威胁。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL · Alembic |
| 检测引擎 | IsolationForest · 规则增强 · 图特征 · XGBoost |
| AI 研判 | 四阶段 WorkflowEngine（Triage → Investigate → Recommend → Plan）|
| 前端 | Next.js (TypeScript) · Tailwind CSS |
| 部署 | Docker Compose |

## 快速启动

**前置要求：** Docker & Docker Compose、Node.js 18+

```bash
# 1. 看可配置的环境变量
cp infra/env.example infra/.env

# 2. 启动后端 + 数据库
cd infra
docker compose up -d

# 3. 启动前端（开发模式）
cd ../frontend
npm install
npm run dev
```

- 后端 API：http://localhost:8000
- 前端界面：http://localhost:3000
- API 文档：http://localhost:8000/docs

## 目录结构

```
.
├── backend/        # FastAPI 后端（检测引擎、AI 研判、WebSocket）
├── frontend/       # Next.js 前端
├── infra/          # Docker Compose 配置
└── contract/       # API 接口契约
```

## 核心功能

1. **流量解析** — 上传 PCAP，提取 36+ 维网络流特征
2. **三层检测** — IsolationForest 基线 → 规则/图特征增强 → XGBoost 精排
3. **告警研判** — AI 四阶段工作流，结合 MITRE ATT&CK 本地知识库
4. **数字孪生** — 在沙箱环境中模拟攻击路径与防御推演
5. **决策建议** — 三级推荐框架，输出可执行响应方案
6. **实时通信** — WebSocket 推送检测进度与告警事件

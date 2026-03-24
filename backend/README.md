# 网孪 - SOC 后端
网络流量分析与数字孪生安全平台 - 后端服务
## 简易入门指南
### 先决条件
- Python 3.11 及以上版本
- pip
### 安装步骤
```bash
cd 后端目录
```
# 创建虚拟环境
python -m venv venv
# 启动虚拟环境
# Windows 系统：
“venv\Scripts\activate”
# Linux 或 Mac 系统：
“source venv/bin/activate”
# 安装依赖项
使用 pip 命令安装 requirements.txt 文件中的依赖项。```

### 跑步
# 开发模式
使用 uvicorn 运行应用程序，并启用自动重新加载功能。主机设置为 0.0.0.0，端口设置为 8000。
# 生产模式
使用以下命令启动应用：uvicorn app.main:app --host 0.0.0.0 --port 800```

### Docker
# 构建
docker build -t nettwin-backend .
# 运行
docker run -p 8000:8000 -v $(pwd)/data:/app/data nettwin-backend```

## API 文档
一旦启动后，可访问以下页面：
- Swagger UI：http://localhost:8000/docs
- ReDoc：http://localhost：8000/redoc
## API 端点（第 1 周）
### 健康检查
```bash
curl http://localhost:8000/api/v1/health
``````
回复：
```json
{"ok": true, "data": {"status": "ok"}, "error": null}
``````

### 上传 PCAP 文件
```bash
curl -X POST http://localhost:8000/api/v1/pcaps/upload \
-F "file=@capture.pcap"```

### 列出 PCAP 文件
```bash
curl http://localhost:8000/api/v1/pcaps
``````

### 获取 PCAP 状态
```bash
curl http://localhost:8000/api/v1/pcaps/{pcap_id}/status
``````

## 环境变量
| 变量 | 默认值 | 描述 ||----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/nettwin.db` | 数据库连接字符串 |
| `DATA_DIR` | `./data` | 数据存储目录 |
| `DEBUG` | `false` | 启用调试模式 |
| `MODEL_PARAMS` | `{}` | 用于检测模型参数的 JSON 字符串 |
| `PIPELINE_OBSERVABILITY_ENABLED` | `true` | 启用管道阶段跟踪 |
| `STRUCTURED_LOG_ENABLED` | `false` | 启用 JSON 行结构化日志记录 |
| `THREAT_ENRICHMENT_ENABLED` | `true` | 启用 MITRE 威胁增强功能 |
## 文件目录结构
```
后端/
├── app/
│   ├── main.py           # FastAPI 应用程序入口
│   ├── api/
│   │   ├── deps.py       # 依赖项（数据库会话）
│   │   └── routers/      # API 路由处理程序
│   ├── core/
│   │   ├── config.py     # 配置
│   │   ├── errors.py     # 错误处理
│   │   ├── logging.py    # 日志设置
│   │   └── utils.py      # 工具
│   ├── models/           # SQLAlchemy ORM 模型
│   ├── schemas/          # Pydantic 模式（符合 DOC C 标准）
│   ├── services/         # 商业逻辑
│   └── tests/            # 单元测试和集成测试
├── scripts/
│   └── seed_samples.py   # 生成合同样本
├── Dockerfile
├── pyproject.toml
└── requirements.txt```

## 合同遵守情况
所有 API 响应均严格遵循 DOC C v1.1 的规范定义。
有关示例数据包，请参阅“../合同/示例/”目录。
## 管道可观测性
后端会通过 9 个明确定义的流程阶段来跟踪 PCAP 处理过程：
| # | 阶段 | 触发因素 | 描述 ||---|-------|---------|-------------|
| 1 | `解析` | PCAP 上传 | 将 PCAP 文件解析为网络流量 |
| 2 | `特征提取` | PCAP 上传 | 每个流量提取 20 多个特征 |
| 3 | `检测` | PCAP 上传 | 使用孤立森林进行异常评分 |
| 4 | `聚合` | PCAP 上传 | 将流量归类为警报 |
| 5 | `调查` | 用户请求 | 代理分类与调查 |
| 6 | `推荐` | 用户请求 | 代理推荐 |
| 7 | `编译计划` | 用户请求 | 为 Twin 编译行动计划 |
| 8 | `模拟运行` | 用户请求 | Twin 模拟 |
| 9 | `可视化` | 用户请求 | 拓扑图/证据图 |
每个阶段都会记录以下信息：“状态”、“延迟时间（单位：毫秒）”、“开始时间”、“完成时间”、“关键指标”、“错误摘要”、“输入摘要”、“输出摘要”。
### API 端点
# 获取 PCAP 流程的运行信息
使用 curl 命令访问：http://localhost：8000/api/v1/pipeline/{pcap_id}
# 获取阶段详情
使用 curl 命令发送请求至：http://localhost:8000/api/v1/pipeline/{pcap_id}/stages```

### 功能开关/特性标志
- `PIPELINE_OBSERVABILITY_ENABLED=false` — 禁用管道跟踪（PCAP 处理仍可正常进行）
- `STRUCTURED_LOG_ENABLED=true` — 切换为带有 run_id/stage/latency 字段的 JSON 行格式记录
## 测试
# 所有测试
pytest app/tests/
# 仅进行单元测试
pytest app/tests/unit/
# 回归测试（已修复的 PCAP 固定测试用例）
pytest app/tests/regression/
# 集成/端到端测试
pytest app/tests/integration/
# 以详细输出方式运行
pytest -v app/tests/```

### 回归测试用例
在“app/tests/fixtures/”目录中对 PCAP 固定配置进行了修复：
- `regression_ssh_bruteforce.pcap` — SSH 暴力破解场景（80 条流，2 个或更多警报）
- `regression_port_scan.pcap` — 端口扫描场景（60 条流，0 个警报）
- `regression_normal_traffic.pcap` — 正常流量基准（2 条流，0 个警报）
基准值定义在 `app/tests/fixtures/expected/baselines.json` 文件中。
使用以下命令重新生成测试数据：`python -m app.tests.fixtures.generate_fixtures`
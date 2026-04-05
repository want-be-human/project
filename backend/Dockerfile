# NetTwin-SOC 后端 Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# 创建数据目录
RUN mkdir -p /app/data/pcaps
RUN mkdir -p /app/data/pcaps /app/models

# 环境变量
ENV DATABASE_URL="sqlite:///./data/nettwin.db"
ENV DATA_DIR="/app/data"
ENV PYTHONPATH="/app"

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

# 启动应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

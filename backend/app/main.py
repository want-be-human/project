"""
NetTwin-SOC 后端应用。
FastAPI 主入口。
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.errors import AppException
from app.core.loop import set_main_loop
from app.api.deps import init_db
from app.api.routers import (
    health,
    pcaps,
    flows,
    alerts,
    topology,
    agent,
    evidence,
    twin,
    scenarios,
    stream,
    pipeline,
    dashboard,
    batch,
)
from app.schemas.common import ApiResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期处理器。"""
    # 启动阶段
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()
    logger.info("Database initialized")

    # 初始化内部事件总线并注册 WebSocket 消费者
    from app.core.events import get_event_bus
    from app.api.routers.stream import ws_consumer
    get_event_bus()  # ensure singleton is created
    await ws_consumer.register()
    logger.info("EventBus initialised, WebSocket consumer registered")

    # 初始化 OpenTelemetry 可观测（tracer / meter）
    from app.core.observability import init_observability
    init_observability()

    # 保存主事件循环引用，供后台线程安全调度异步广播
    loop = asyncio.get_running_loop()
    set_main_loop(loop)
    logger.info("主事件循环引用已保存")

    # 启动批量接入 Job Runner
    from app.services.batch.runner import get_job_runner
    runner = get_job_runner()
    await runner.start()
    logger.info("JobRunner 已启动")

    yield

    # 关闭阶段
    await runner.stop()
    logger.info("JobRunner 已停止")
    await ws_consumer.unregister()
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Network Traffic Analysis & Digital Twin Security Platform",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 异常处理器
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """按 DOC C 统一响应封装处理应用异常。"""
    response = ApiResponse.failure(
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """记录并封装 Pydantic 校验异常。"""
    errors = exc.errors()
    logger.warning(f"Validation error on {request.method} {request.url.path}: {errors}")
    messages = []
    for err in errors:
        loc = " -> ".join(str(part) for part in err.get("loc", []))
        messages.append(f"{loc}: {err.get('msg', 'invalid')}")
    response = ApiResponse.failure(
        code="VALIDATION_ERROR",
        message="; ".join(messages) or "Request validation failed",
        details={"errors": errors},
    )
    return JSONResponse(
        status_code=422,
        content=response.model_dump(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未预期异常。"""
    logger.exception(f"Unexpected error: {exc}")
    response = ApiResponse.failure(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        details={"type": type(exc).__name__} if settings.DEBUG else {},
    )
    return JSONResponse(
        status_code=500,
        content=response.model_dump(),
    )


# 按 API 前缀注册路由 - 对应 DOC C C6 路径映射
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(pcaps.router, prefix=settings.API_V1_PREFIX)
app.include_router(flows.router, prefix=settings.API_V1_PREFIX)
app.include_router(alerts.router, prefix=settings.API_V1_PREFIX)
app.include_router(topology.router, prefix=settings.API_V1_PREFIX)
app.include_router(agent.router, prefix=settings.API_V1_PREFIX)
app.include_router(agent.lookup_router, prefix=settings.API_V1_PREFIX)
app.include_router(evidence.router, prefix=settings.API_V1_PREFIX)
app.include_router(twin.router, prefix=settings.API_V1_PREFIX)
app.include_router(scenarios.router, prefix=settings.API_V1_PREFIX)
app.include_router(stream.router, prefix=settings.API_V1_PREFIX)
app.include_router(pipeline.router, prefix=settings.API_V1_PREFIX)
# 仪表盘路由 — 安全态势总览
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
# 批量接入路由
app.include_router(batch.router, prefix=settings.API_V1_PREFIX)


# 根路径响应
@app.get("/", include_in_schema=False)
async def root():
    """根路径重定向说明。"""
    return {"message": f"Welcome to {settings.APP_NAME}", "docs": "/docs"}

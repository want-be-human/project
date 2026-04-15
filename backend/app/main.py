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
    analytics,
)
from app.schemas.common import ApiResponse

logger = get_logger(__name__)

_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()
    logger.info("数据库已初始化")

    from app.core.events import get_event_bus
    from app.api.routers.stream import ws_consumer
    get_event_bus()
    await ws_consumer.register()
    logger.info("EventBus 已初始化，WebSocket 消费者已注册")

    from app.core.observability import init_observability
    init_observability()

    set_main_loop(asyncio.get_running_loop())
    logger.info("主事件循环引用已保存")

    from app.services.batch.runner import get_job_runner
    runner = get_job_runner()
    await runner.start()
    logger.info("JobRunner 已启动")

    yield

    await runner.stop()
    logger.info("JobRunner 已停止")
    await ws_consumer.unregister()
    logger.info("正在关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="网络流量分析与数字孪生安全平台",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=_ALLOWED_METHODS,
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    response = ApiResponse.failure(code=exc.code, message=exc.message, details=exc.details)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
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
    return JSONResponse(status_code=422, content=response.model_dump())


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unexpected error: {exc}")
    response = ApiResponse.failure(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        details={"type": type(exc).__name__} if settings.DEBUG else {},
    )
    return JSONResponse(status_code=500, content=response.model_dump())


# 路由注册顺序对应 DOC C C6 路径映射，不要随意调整
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
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router, prefix=settings.API_V1_PREFIX)
app.include_router(batch.router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}", "docs": "/docs"}

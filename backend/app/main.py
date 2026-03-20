"""
NetTwin-SOC Backend Application.
FastAPI main entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.errors import AppException
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
)
from app.schemas.common import ApiResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()
    logger.info("Database initialized")

    # Initialise internal event bus & register WebSocket consumer
    from app.core.events import get_event_bus
    from app.api.routers.stream import ws_consumer
    get_event_bus()  # ensure singleton is created
    await ws_consumer.register()
    logger.info("EventBus initialised, WebSocket consumer registered")

    yield

    # Shutdown
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle application exceptions with DOC C envelope format."""
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
    """Handle Pydantic validation errors with logging and envelope format."""
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
    """Handle unexpected exceptions."""
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


# Register routers with API prefix - DOC C C6 path mapping
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


# Root redirect
@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to docs."""
    return {"message": f"Welcome to {settings.APP_NAME}", "docs": "/docs"}

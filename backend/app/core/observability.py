"""
OpenTelemetry 可观测性初始化模块。

根据 OTEL_EXPORTER 环境变量选择 exporter：
- "console"（默认/开发）：ConsoleSpanExporter + ConsoleMetricExporter
- "otlp"（生产）：OTLPSpanExporter + OTLPMetricExporter（读 OTEL_EXPORTER_OTLP_ENDPOINT）

在应用启动时调用 init_observability() 一次，之后通过
get_scenario_tracer() / get_scenario_meter() 获取 tracer/meter。
"""

from __future__ import annotations

import os
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# 模块级单例，避免重复初始化
_initialized = False


def init_observability(service_name: str = "nettwin-soc") -> None:
    """
    初始化 TracerProvider 和 MeterProvider。

    环境变量：
    - OTEL_EXPORTER: "console"（默认）或 "otlp"
    - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP gRPC 端点（仅 otlp 模式需要）
    - OTEL_SERVICE_NAME: 覆盖 service_name 参数
    """
    global _initialized
    if _initialized:
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        svc = os.getenv("OTEL_SERVICE_NAME", service_name)
        exporter_type = os.getenv("OTEL_EXPORTER", "console").lower()
        resource = Resource(attributes={SERVICE_NAME: svc})

        # ── Tracer Provider ──────────────────────────────────────────
        if exporter_type == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            span_exporter = OTLPSpanExporter()
            logger.info("OTel tracer: OTLP exporter (endpoint=%s)",
                        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "<default>"))
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            span_exporter = ConsoleSpanExporter()
            logger.info("OTel tracer: console exporter（开发模式）")

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        # ── Meter Provider ───────────────────────────────────────────
        if exporter_type == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        else:
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
            metric_reader = PeriodicExportingMetricReader(ConsoleMetricExporter())

        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        _initialized = True
        logger.info("OpenTelemetry 初始化完成 (service=%s, exporter=%s)", svc, exporter_type)

    except ImportError:
        # OTel 包未安装时静默降级，不影响业务逻辑
        logger.warning(
            "opentelemetry-sdk 未安装，OTel 可观测功能已禁用。"
            "如需启用，请安装 opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
        )
    except Exception:
        logger.warning("OpenTelemetry 初始化失败，可观测功能已禁用", exc_info=True)


def get_scenario_tracer() -> "trace.Tracer":  # type: ignore[name-defined]
    """获取场景运行专用 tracer。OTel 未初始化时返回 NoOp tracer。"""
    try:
        from opentelemetry import trace
        return trace.get_tracer("nettwin.scenarios")
    except ImportError:
        return _noop_tracer()


def get_scenario_meter() -> "metrics.Meter":  # type: ignore[name-defined]
    """获取场景运行专用 meter。OTel 未初始化时返回 NoOp meter。"""
    try:
        from opentelemetry import metrics
        return metrics.get_meter("nettwin.scenarios")
    except ImportError:
        return _noop_meter()


# ------------------------------------------------------------------
# NoOp 降级实现（OTel 包未安装时使用）
# ------------------------------------------------------------------

class _NoOpSpan:
    """OTel 未安装时的空 span，所有方法均为空操作。"""
    def set_attribute(self, *a: object, **kw: object) -> None: pass
    def record_exception(self, *a: object, **kw: object) -> None: pass
    def set_status(self, *a: object, **kw: object) -> None: pass
    def end(self) -> None: pass
    def __enter__(self): return self
    def __exit__(self, *a: object) -> None: pass


class _NoOpTracer:
    def start_span(self, *a: object, **kw: object) -> _NoOpSpan:
        return _NoOpSpan()
    def start_as_current_span(self, *a: object, **kw: object):
        return _NoOpSpan()


class _NoOpInstrument:
    def add(self, *a: object, **kw: object) -> None: pass
    def record(self, *a: object, **kw: object) -> None: pass


class _NoOpMeter:
    def create_counter(self, *a: object, **kw: object) -> _NoOpInstrument:
        return _NoOpInstrument()
    def create_histogram(self, *a: object, **kw: object) -> _NoOpInstrument:
        return _NoOpInstrument()


def _noop_tracer() -> _NoOpTracer:
    return _NoOpTracer()


def _noop_meter() -> _NoOpMeter:
    return _NoOpMeter()

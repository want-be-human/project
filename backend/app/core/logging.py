"""
日志配置。
"""

import json
import logging
import sys
from typing import Any

from app.core.config import settings


class StructuredLogFormatter(logging.Formatter):
    """
    面向流水线可观测性的 JSON 行日志格式化器。

    每行日志输出一个 JSON 对象，包含字段：
    ``timestamp``、``level``、``logger``、``message``，以及
    通过 ``logger.info("msg", extra={...})`` 传入的扩展字段。

    仅当 ``settings.STRUCTURED_LOG_ENABLED = True`` 时启用。
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # 如存在额外字段则一并合并（如 run_id、stage、latency_ms）
        for key in ("run_id", "stage", "latency_ms", "metrics", "pcap_id", "status"):
            val = getattr(record, key, None)
            if val is not None:
                log_obj[key] = val
        if record.exc_info and record.exc_info[1]:
            log_obj["exception"] = str(record.exc_info[1])
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging() -> None:
    """配置应用日志。"""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    handler = logging.StreamHandler(sys.stdout)

    if settings.STRUCTURED_LOG_ENABLED:
        handler.setFormatter(StructuredLogFormatter(datefmt="%Y-%m-%dT%H:%M:%SZ"))
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    # 根日志记录器配置
    logging.basicConfig(
        level=log_level,
        handlers=[handler],
    )

    # 降低第三方库日志噪声
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger 实例。"""
    return logging.getLogger(name)


class LoggerMixin:
    """为任意类提供日志能力的 Mixin。"""

    @property
    def logger(self) -> logging.Logger:
        return get_logger(self.__class__.__name__)

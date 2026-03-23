"""
错误处理与自定义异常。
遵循 DOC C C0.3 错误码规范。
"""

from typing import Any
from fastapi import status


# DOC C C0.3 错误码
class ErrorCode:
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppException(Exception):
    """应用异常基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class BadRequestError(AppException):
    """400 Bad Request - 参数错误。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code=ErrorCode.BAD_REQUEST,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class NotFoundError(AppException):
    """404 Not Found - 资源不存在。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ConflictError(AppException):
    """409 Conflict - 状态冲突。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code=ErrorCode.CONFLICT,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class UnsupportedMediaError(AppException):
    """415 Unsupported Media Type - 非 pcap 文件。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code=ErrorCode.UNSUPPORTED_MEDIA,
            message=message,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            details=details,
        )


class ProcessingFailedError(AppException):
    """500 Processing Failed - 解析/检测失败。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code=ErrorCode.PROCESSING_FAILED,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class ValidationError(AppException):
    """422 Validation Error - 模式校验失败。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class InternalError(AppException):
    """500 Internal Error - 未知错误。"""

    def __init__(self, message: str = "Internal server error", details: dict[str, Any] | None = None):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )

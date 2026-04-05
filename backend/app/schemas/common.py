"""
API 响应通用 Schema。
遵循 DOC C C0.2 统一响应信封规范。
"""

from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """DOC C C0.2 定义的错误详情结构。"""

    code: str = Field(..., description="DOC C C0.3 定义的错误码")
    message: str = Field(..., description="面向人的错误信息")
    details: dict[str, Any] = Field(default_factory=dict, description="附加错误详情")


class ApiResponse(BaseModel, Generic[T]):
    """
    DOC C C0.2 定义的统一 API 响应信封。

    成功: { "ok": true, "data": {...}, "error": null }
    失败: { "ok": false, "data": null, "error": {...} }
    """

    ok: bool = Field(..., description="请求是否成功")
    data: T | None = Field(default=None, description="成功时的响应数据")
    error: ErrorDetail | None = Field(default=None, description="失败时的错误详情")

    @classmethod
    def success(cls, data: T) -> "ApiResponse[T]":
        """创建成功响应。"""
        return cls(ok=True, data=data, error=None)

    @classmethod
    def failure(cls, code: str, message: str, details: dict[str, Any] | None = None) -> "ApiResponse[None]":
        """创建失败响应。"""
        return cls(  # type: ignore[return-value]
            ok=False,
            data=None,
            error=ErrorDetail(code=code, message=message, details=details or {}),
        )


class PaginatedData(BaseModel, Generic[T]):
    """分页列表包装，包含总数信息。"""

    items: list[T]
    total: int = Field(..., ge=0, description="满足条件的总记录数（分页前）")
    limit: int = Field(..., ge=1, description="请求的页大小")
    offset: int = Field(..., ge=0, description="请求的偏移量")


class PaginationParams(BaseModel):
    """通用分页参数。"""

    limit: int = Field(default=50, ge=1, le=1000, description="最大返回条目数")
    offset: int = Field(default=0, ge=0, description="跳过的条目数")


class HealthStatus(BaseModel):
    """健康检查响应数据。"""

    status: str = Field(default="ok", description="服务状态")

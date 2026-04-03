"""
批量接入路由。

提供批次创建、文件上传、启动处理、取消、重试等 API 端点。
"""

from fastapi import APIRouter, Depends, UploadFile, File, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger
from app.schemas.batch import (
    BatchSchema,
    BatchDetailSchema,
    BatchFileSchema,
    JobSchema,
    CreateBatchRequest,
    CancelBatchRequest,
    BatchStartResponse,
    BatchRetryResponse,
)
from app.schemas.common import ApiResponse
from app.services.batch.runner import get_job_runner
from app.services.batch.service import BatchService

logger = get_logger(__name__)

router = APIRouter(prefix="/batches", tags=["batches"])


# ── 批次管理 ──────────────────────────────────────────────────

@router.post(
    "",
    response_model=ApiResponse[BatchSchema],
    summary="创建批次",
    description="创建一个新的批量接入批次。",
)
async def create_batch(
    request: CreateBatchRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchSchema]:
    """创建批次。"""
    svc = BatchService(db)
    batch = svc.create_batch(
        name=request.name,
        source=request.source,
        tags=request.tags,
    )
    return ApiResponse.success(batch)


@router.get(
    "",
    response_model=ApiResponse[list[BatchSchema]],
    summary="列出批次",
    description="分页列出所有批次，可按状态过滤。",
)
async def list_batches(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[list[BatchSchema]]:
    """列出批次。"""
    svc = BatchService(db)
    batches = svc.list_batches(limit=limit, offset=offset, status=status)
    return ApiResponse.success(batches)


@router.get(
    "/{batch_id}",
    response_model=ApiResponse[BatchDetailSchema],
    summary="批次详情",
    description="获取批次详情，包含文件列表。",
)
async def get_batch_detail(
    batch_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchDetailSchema]:
    """获取批次详情。"""
    svc = BatchService(db)
    detail = svc.get_batch_detail(batch_id)
    return ApiResponse.success(detail)


# ── 文件上传 ──────────────────────────────────────────────────

@router.post(
    "/{batch_id}/files",
    response_model=ApiResponse[list[BatchFileSchema]],
    summary="上传批次文件",
    description="向批次上传一个或多个 PCAP 文件。支持多文件上传。",
)
async def upload_batch_files(
    batch_id: str,
    files: list[UploadFile] = File(..., description="PCAP 文件列表"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[BatchFileSchema]]:
    """上传文件到批次。"""
    svc = BatchService(db)
    file_tuples = [(f.filename or "unknown.pcap", f.file) for f in files]
    results = svc.upload_files(batch_id, file_tuples)
    return ApiResponse.success(results)


@router.get(
    "/{batch_id}/files",
    response_model=ApiResponse[list[BatchFileSchema]],
    summary="批次文件列表",
    description="列出批次中的文件，可按状态过滤。",
)
async def list_batch_files(
    batch_id: str,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[list[BatchFileSchema]]:
    """列出批次文件。"""
    svc = BatchService(db)
    files = svc.list_batch_files(batch_id, limit=limit, offset=offset, status=status)
    return ApiResponse.success(files)


# ── 处理控制 ──────────────────────────────────────────────────

@router.post(
    "/{batch_id}/start",
    response_model=ApiResponse[BatchStartResponse],
    summary="启动批次处理",
    description="为批次中所有已接受的文件创建作业并开始处理。",
)
async def start_batch(
    batch_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchStartResponse]:
    """启动批次处理。"""
    svc = BatchService(db)
    response, job_ids = svc.start_batch(batch_id)

    # 将 job 入队到 runner
    runner = get_job_runner()
    for jid in job_ids:
        await runner.enqueue(jid)

    return ApiResponse.success(response)


@router.post(
    "/{batch_id}/cancel",
    response_model=ApiResponse[BatchSchema],
    summary="取消批次",
    description="取消批次处理。正在运行的作业将在当前阶段结束后停止。",
)
async def cancel_batch(
    batch_id: str,
    request: CancelBatchRequest = CancelBatchRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[BatchSchema]:
    """取消批次。"""
    svc = BatchService(db)
    batch = svc.cancel_batch(batch_id, reason=request.reason)

    # 通知 runner 取消正在运行的 job
    runner = get_job_runner()
    await runner.cancel_batch(batch_id)

    return ApiResponse.success(batch)


@router.delete(
    "/{batch_id}",
    response_model=ApiResponse[dict],
    summary="删除批次",
    description="删除批次及所有关联数据（文件、作业、PCAP 记录）。正在处理的批次需先取消。",
)
async def delete_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """删除批次。"""
    svc = BatchService(db)
    pcap_ids, staging_paths = svc.delete_batch(batch_id)

    # 通知 runner 清理取消标记
    runner = get_job_runner()
    runner._cancel_batch_set.discard(batch_id)

    # 关联 PCAP 和暂存文件在后台清理，不阻塞响应
    if pcap_ids or staging_paths:
        background_tasks.add_task(_cleanup_batch_assets, batch_id, pcap_ids, staging_paths)

    return ApiResponse.success({"deleted": True, "pcap_ids": pcap_ids})


def _cleanup_batch_assets(
    batch_id: str,
    pcap_ids: list[str],
    staging_paths: list,
) -> None:
    """后台清理批次关联的 PCAP 文件和暂存文件。"""
    from app.core.database import SessionLocal
    from app.services.ingestion.service import IngestionService

    logger = get_logger(__name__)

    # 用独立 session 删除 PCAP（避免与请求 session 冲突）
    db = SessionLocal()
    try:
        for pcap_id in pcap_ids:
            try:
                ingestion = IngestionService(db)
                ingestion.delete_pcap(pcap_id)
            except Exception as e:
                logger.warning(f"删除批次 {batch_id} 关联的 PCAP {pcap_id} 失败: {e}")
    finally:
        db.close()

    # 清理暂存区文件
    for sp in staging_paths:
        if sp.exists():
            try:
                sp.unlink()
            except Exception:
                pass

    logger.info(f"批次 {batch_id} 后台清理完成（{len(pcap_ids)} 个 PCAP）")


# ── 重试 ──────────────────────────────────────────────────────

@router.post(
    "/{batch_id}/retry",
    response_model=ApiResponse[BatchRetryResponse],
    summary="重试批次失败文件",
    description="重试批次中所有失败的文件。",
)
async def retry_batch(
    batch_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchRetryResponse]:
    """重试批次中所有失败文件。"""
    svc = BatchService(db)
    response, job_ids = svc.retry_batch(batch_id)

    runner = get_job_runner()
    for jid in job_ids:
        await runner.enqueue(jid)

    return ApiResponse.success(response)


@router.post(
    "/{batch_id}/files/{file_id}/retry",
    response_model=ApiResponse[JobSchema],
    summary="重试单个文件",
    description="重试批次中单个失败的文件。",
)
async def retry_file(
    batch_id: str,
    file_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[JobSchema]:
    """重试单个文件。"""
    svc = BatchService(db)
    job_schema, job_id = svc.retry_file(batch_id, file_id)

    runner = get_job_runner()
    await runner.enqueue(job_id)

    return ApiResponse.success(job_schema)


# ── 作业历史 ──────────────────────────────────────────────────

@router.get(
    "/{batch_id}/files/{file_id}/jobs",
    response_model=ApiResponse[list[JobSchema]],
    summary="文件作业历史",
    description="查看文件的所有作业执行记录。",
)
async def list_file_jobs(
    batch_id: str,
    file_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[list[JobSchema]]:
    """查看文件作业历史。"""
    svc = BatchService(db)
    jobs = svc.list_file_jobs(batch_id, file_id)
    return ApiResponse.success(jobs)

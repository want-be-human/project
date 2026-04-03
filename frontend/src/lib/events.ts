/**
 * 统一事件名常量 — 必须与 contract/events/registry.json 保持一致。
 * 前端所有 wsClient.onEvent() 调用必须使用此文件中的常量，禁止硬编码字符串。
 */

// ── PCAP 处理事件 ──
export const PCAP_PROCESS_PROGRESS = 'pcap.process.progress' as const;
export const PCAP_PROCESS_DONE     = 'pcap.process.done' as const;
export const PCAP_PROCESS_FAILED   = 'pcap.process.failed' as const;

// ── 告警事件 ──
export const ALERT_CREATED = 'alert.created' as const;
export const ALERT_UPDATED = 'alert.updated' as const;

// ── 数字孪生事件 ──
export const TWIN_DRYRUN_CREATED = 'twin.dryrun.created' as const;

// ── 场景运行事件 ──
export const SCENARIO_RUN_STARTED     = 'scenario.run.started' as const;
export const SCENARIO_STAGE_STARTED   = 'scenario.stage.started' as const;
export const SCENARIO_STAGE_COMPLETED = 'scenario.stage.completed' as const;
export const SCENARIO_STAGE_FAILED    = 'scenario.stage.failed' as const;
export const SCENARIO_RUN_PROGRESS    = 'scenario.run.progress' as const;
export const SCENARIO_RUN_DONE        = 'scenario.run.done' as const;

// ── 流水线可观测性事件 ──
export const PIPELINE_RUN_STARTED     = 'pipeline.run.started' as const;
export const PIPELINE_STAGE_COMPLETED = 'pipeline.stage.completed' as const;
export const PIPELINE_STAGE_FAILED    = 'pipeline.stage.failed' as const;
export const PIPELINE_RUN_DONE        = 'pipeline.run.done' as const;

// ── 批量接入事件 ──
export const BATCH_CREATED            = 'batch.created' as const;
export const BATCH_UPLOAD_PROGRESS    = 'batch.upload.progress' as const;
export const BATCH_PROCESSING_STARTED = 'batch.processing.started' as const;
export const BATCH_COMPLETED          = 'batch.completed' as const;
export const BATCH_FAILED             = 'batch.failed' as const;
export const BATCH_CANCELLED          = 'batch.cancelled' as const;
export const BATCH_FILE_STATUS        = 'batch.file.status' as const;
export const BATCH_JOB_STARTED        = 'batch.job.started' as const;
export const BATCH_JOB_STAGE_STARTED  = 'batch.job.stage.started' as const;
export const BATCH_JOB_STAGE_COMPLETED = 'batch.job.stage.completed' as const;
export const BATCH_JOB_STAGE_FAILED   = 'batch.job.stage.failed' as const;
export const BATCH_JOB_COMPLETED      = 'batch.job.completed' as const;
export const BATCH_JOB_FAILED         = 'batch.job.failed' as const;

/** 所有已知事件名的联合类型 */
export type EventName =
  | typeof PCAP_PROCESS_PROGRESS
  | typeof PCAP_PROCESS_DONE
  | typeof PCAP_PROCESS_FAILED
  | typeof ALERT_CREATED
  | typeof ALERT_UPDATED
  | typeof TWIN_DRYRUN_CREATED
  | typeof SCENARIO_RUN_STARTED
  | typeof SCENARIO_STAGE_STARTED
  | typeof SCENARIO_STAGE_COMPLETED
  | typeof SCENARIO_STAGE_FAILED
  | typeof SCENARIO_RUN_PROGRESS
  | typeof SCENARIO_RUN_DONE
  | typeof PIPELINE_RUN_STARTED
  | typeof PIPELINE_STAGE_COMPLETED
  | typeof PIPELINE_STAGE_FAILED
  | typeof PIPELINE_RUN_DONE
  | typeof BATCH_CREATED
  | typeof BATCH_UPLOAD_PROGRESS
  | typeof BATCH_PROCESSING_STARTED
  | typeof BATCH_COMPLETED
  | typeof BATCH_FAILED
  | typeof BATCH_CANCELLED
  | typeof BATCH_FILE_STATUS
  | typeof BATCH_JOB_STARTED
  | typeof BATCH_JOB_STAGE_STARTED
  | typeof BATCH_JOB_STAGE_COMPLETED
  | typeof BATCH_JOB_STAGE_FAILED
  | typeof BATCH_JOB_COMPLETED
  | typeof BATCH_JOB_FAILED;

/** 事件 payload 类型映射 — 提供类型安全的订阅 */
export interface EventPayloadMap {
  [PCAP_PROCESS_PROGRESS]: { pcap_id: string; percent: number };
  [PCAP_PROCESS_DONE]: { pcap_id: string; flow_count: number; alert_count: number };
  [PCAP_PROCESS_FAILED]: { pcap_id: string; error?: string };
  [ALERT_CREATED]: { alert_id: string; severity: string };
  [ALERT_UPDATED]: { alert_id: string; status: string };
  [TWIN_DRYRUN_CREATED]: { dry_run_id: string; alert_id: string; risk: number };
  [SCENARIO_RUN_STARTED]: { scenario_id: string; run_id: string; scenario_name: string; total_stages: number };
  [SCENARIO_STAGE_STARTED]: { scenario_id: string; run_id: string; stage: string; stage_index: number; total_stages: number };
  [SCENARIO_STAGE_COMPLETED]: { scenario_id: string; run_id: string; stage: string; status: string; latency_ms: number; key_metrics: Record<string, any> };
  [SCENARIO_STAGE_FAILED]: { scenario_id: string; run_id: string; stage: string; status: string; error_summary: string; failure_attribution: any };
  [SCENARIO_RUN_PROGRESS]: { scenario_id: string; run_id: string; completed_stages: number; total_stages: number; percent: number };
  [SCENARIO_RUN_DONE]: { scenario_id: string; run_id: string; status: string };
  [PIPELINE_RUN_STARTED]: { run_id: string; pcap_id: string };
  [PIPELINE_STAGE_COMPLETED]: { run_id: string; pcap_id: string; stage: string; latency_ms: number };
  [PIPELINE_STAGE_FAILED]: { run_id: string; pcap_id: string; stage: string; error_summary: string };
  [PIPELINE_RUN_DONE]: { run_id: string; pcap_id: string; status: string; total_latency_ms: number };
  // 批量接入事件
  [BATCH_CREATED]: { batch_id: string; name: string; total_files: number };
  [BATCH_UPLOAD_PROGRESS]: { batch_id: string; uploaded_count: number; total_count: number };
  [BATCH_PROCESSING_STARTED]: { batch_id: string; jobs_count: number };
  [BATCH_COMPLETED]: { batch_id: string; status: string; total_flow_count: number; total_alert_count: number; total_latency_ms: number };
  [BATCH_FAILED]: { batch_id: string; error: string; failed_files: number };
  [BATCH_CANCELLED]: { batch_id: string; reason?: string };
  [BATCH_FILE_STATUS]: { batch_id: string; batch_file_id: string; filename: string; status: string; flow_count?: number; alert_count?: number; error?: string };
  [BATCH_JOB_STARTED]: { batch_id: string; job_id: string; batch_file_id: string; pcap_id?: string };
  [BATCH_JOB_STAGE_STARTED]: { batch_id: string; job_id: string; stage: string };
  [BATCH_JOB_STAGE_COMPLETED]: { batch_id: string; job_id: string; stage: string; latency_ms: number };
  [BATCH_JOB_STAGE_FAILED]: { batch_id: string; job_id: string; stage: string; error: string };
  [BATCH_JOB_COMPLETED]: { batch_id: string; job_id: string; batch_file_id: string; flow_count: number; alert_count: number; latency_ms: number };
  [BATCH_JOB_FAILED]: { batch_id: string; job_id: string; batch_file_id: string; error: string; retry_count: number };
}

/** 所有事件名数组（用于契约测试） */
export const ALL_EVENT_NAMES: EventName[] = [
  PCAP_PROCESS_PROGRESS, PCAP_PROCESS_DONE, PCAP_PROCESS_FAILED,
  ALERT_CREATED, ALERT_UPDATED, TWIN_DRYRUN_CREATED,
  SCENARIO_RUN_STARTED, SCENARIO_STAGE_STARTED, SCENARIO_STAGE_COMPLETED,
  SCENARIO_STAGE_FAILED, SCENARIO_RUN_PROGRESS, SCENARIO_RUN_DONE,
  PIPELINE_RUN_STARTED, PIPELINE_STAGE_COMPLETED, PIPELINE_STAGE_FAILED, PIPELINE_RUN_DONE,
  BATCH_CREATED, BATCH_UPLOAD_PROGRESS, BATCH_PROCESSING_STARTED,
  BATCH_COMPLETED, BATCH_FAILED, BATCH_CANCELLED, BATCH_FILE_STATUS,
  BATCH_JOB_STARTED, BATCH_JOB_STAGE_STARTED, BATCH_JOB_STAGE_COMPLETED,
  BATCH_JOB_STAGE_FAILED, BATCH_JOB_COMPLETED, BATCH_JOB_FAILED,
];

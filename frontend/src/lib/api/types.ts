
export interface PcapFile {
  version?: string;
  id: string; // uuid
  created_at: string; // ISO8601
  filename: string;
  size_bytes: number;
  status: 'uploaded' | 'processing' | 'done' | 'failed';
  progress?: number; // 0-100
  flow_count?: number;
  alert_count?: number;
  /** 处理失败时的错误信息 */
  error_message?: string;
}

export interface FlowRecord {
  version?: string;
  id: string;
  created_at: string;
  pcap_id: string;
  ts_start: string;
  ts_end: string;
  src_ip: string;
  src_port: number;
  dst_ip: string;
  dst_port: number;
  proto: string;
  packets_fwd: number;
  packets_bwd: number;
  bytes_fwd: number;
  bytes_bwd: number;
  features: Record<string, any>;
  anomaly_score: number | null;
  label?: string | null;
  // 复合检测扩展字段
  baseline_score?: number | null;
  rule_score?: number | null;
  final_score?: number | null;
  final_label?: string | null;
}

export interface Alert {
  version: string;
  id: string;
  created_at: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'new' | 'triaged' | 'investigating' | 'resolved' | 'false_positive';
  type: string;
  time_window: {
    start: string;
    end: string;
  };
  entities: {
    primary_src_ip: string;
    primary_dst_ip?: string;
    primary_service?: {
      proto: string;
      dst_port: number;
    };
  };
  evidence: {
    flow_ids: string[];
    top_flows: Array<{
      flow_id: string;
      anomaly_score: number;
      summary: string;
    }>;
    top_features: Array<{
      name: string;
      value: number | string;
      direction?: string;
    }>;
    pcap_ref: {
      pcap_id: string;
      offset_hint?: number | null;
    };
  };
  aggregation?: {
    rule: string;
    group_key: string;
    count_flows: number;
    dimensions?: string[];
    composite_score?: number;
    score_breakdown?: Record<string, number>;
    type_reason?: { type: string; reason_codes: string[]; details: Record<string, any> };
    aggregation_summary?: string;
    type_summary?: string;
    severity_summary?: string;
  };
  agent?: {
    triage_summary: string | null;
    investigation_id: string | null;
    recommendation_id: string | null;
  };
  twin?: {
    plan_id: string | null;
    dry_run_id: string | null;
  };
  tags?: string[];
  notes?: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  risk: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  weight: number;
  protocols: string[];
  services: Array<{proto: string, port: number}>;
  alert_ids: string[];
  activeIntervals: [string, string][];
  risk?: number;  // 边级风险分值（后端已有，前端新增）
}

export interface GraphResponse {
  version: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta: {
    start: string;
    end: string;
    mode: string;
  };
}

export interface EvidenceChainNode {
  id: string;
  type: 'alert' | 'flow' | 'feature' | 'hypothesis' | 'action' | 'dryrun';
  label: string;
}

export interface EvidenceChainEdge {
  source: string;
  target: string;
  type: 'supports' | 'explains' | 'inferred_as' | 'leads_to' | 'simulated_by';
}

export interface EvidenceChain {
  version: string;
  id: string;
  created_at: string;
  alert_id: string;
  nodes: EvidenceChainNode[];
  edges: EvidenceChainEdge[];
}

export interface ThreatTechnique {
    technique_id: string;
    technique_name: string;
    technique_name_zh?: string;
    tactic_id: string;
    tactic_name: string;
    tactic_name_zh?: string;
    confidence: number;
    description?: string;
    description_zh?: string;
    intel_refs?: string[];
}

export interface ThreatContext {
    techniques: ThreatTechnique[];
    tactics: string[];
    tactics_zh?: string[];
    enrichment_confidence: number;
    enrichment_source: string;
}

export interface Investigation {
    version: string;
    id: string;
    created_at: string;
    alert_id: string;
    hypothesis: string;
    why: string[];
    impact: {
        scope: string[];
        confidence: number;
    };
    next_steps: string[];
    safety_note?: string;
    threat_context?: ThreatContext | null;
}

export interface Recommendation {
    version: string;
    id: string;
    created_at: string;
    alert_id: string;
    actions: Array<{
        title: string;
        priority: 'high' | 'medium' | 'low';
        steps: string[];
        rollback: string[];
        risk: string;
        action_intent?: 'executable' | 'monitoring' | 'advisory';
        compile_hint?: { preferred_action_type: string; reason: string } | null;
    }>;
    threat_context?: ThreatContext | null;
}

export interface ActionPlan {
    version?: string;
    id: string;
    created_at: string;
    alert_id: string;
    source: 'agent' | 'manual';
    actions: any[]; 
    notes?: string;
}

export interface CompiledAction {
    action_type: 'block_ip' | 'isolate_host' | 'segment_subnet' | 'rate_limit_service';
    target: { type: 'ip' | 'subnet' | 'service'; value: string };
    params: Record<string, any>;
    rollback: { action_type: string; params: Record<string, any> } | null;
    confidence: number;
    derived_from_evidence: string[];
    reasoning_summary: string;
}

export interface SkippedAction {
    title: string;
    reason: string;
    action_intent: string;
    suggestion: string;
}

export interface CompilePlanRequest {
    recommendation_id?: string | null;
    language?: 'zh' | 'en';
}

export interface CompilePlanResponse {
    plan: ActionPlan;
    compilation: {
        recommendation_id: string;
        rules_matched: number;
        actions_skipped: number;
        compiler_version: string;
        skipped_actions: SkippedAction[];
        all_skipped: boolean;
        empty_reason: string | null;
    };
}

// ── Dry-Run 多维可达性与风险分解类型（v1.2）──

export interface PairReachabilityMetric {
  source: string;
  target: string;
  reachable_before: boolean;
  reachable_after: boolean;
  protocols: string[];
}

export interface ReachabilityDetail {
  pair_reachability_drop: number;
  service_reachability_drop: number;
  subnet_reachability_drop: number;
  pair_metrics: PairReachabilityMetric[];
}

export interface ImpactedServiceDetail {
  service: string;
  importance_weight: number;
  affected_edge_count: number;
  affected_node_count: number;
  traffic_proportion: number;
  alert_severity_stats: Record<string, number>;
  risk_contribution: number;
}

export interface ServiceRiskBreakdown {
  weighted_service_score: number;
  node_impact_score: number;
  edge_impact_score: number;
  alert_severity_score: number;
  traffic_proportion_score: number;
  historical_score: number;
  composite_risk: number;
}

export interface ExplainSection {
  section: string;
  title: string;
  content: string[];
}

export interface DryRunResult {
    version?: string;
    id: string;
    created_at?: string;
    alert_id: string;
    plan_id: string;
    /** 变更前的完整图结构（用于 before/diff 视图渲染） */
    graph_before?: GraphResponse;
    /** 变更后的完整图结构（用于 after 视图渲染） */
    graph_after?: GraphResponse;
    /** dry-run 时间窗口起始（ISO8601 UTC） */
    dry_run_start?: string;
    /** dry-run 时间窗口结束（ISO8601 UTC） */
    dry_run_end?: string;
    /** dry-run 图模式（ip/subnet） */
    dry_run_mode?: string;
    impact: {
        impacted_nodes_count?: number;
        impacted_edges_count?: number;
        reachability_drop?: number;
        service_disruption_risk?: number;
        affected_services?: string[];
        warnings?: string[];
        // v1.2 新增字段
        removed_node_ids?: string[];
        removed_edge_ids?: string[];
        affected_node_ids?: string[];
        affected_edge_ids?: string[];
        reachability_detail?: ReachabilityDetail;
        impacted_services?: ImpactedServiceDetail[];
        service_risk_breakdown?: ServiceRiskBreakdown;
        confidence?: number;
        /** 节点级风险分值变化：nodeId → 执行动作后的新风险值 */
        node_risk_deltas?: Record<string, number>;
        /** 边级权重变化：edgeId → 执行动作后的新权重 */
        edge_weight_deltas?: Record<string, number>;
        [key: string]: any;
    };
    alternative_paths?: Array<{
        from: string;
        to: string;
        path: string[];
    }>;
    explain?: string[];
    explain_sections?: ExplainSection[];
}

export interface Scenario {
    version?: string;
    id: string;
    created_at?: string;
    name: string;
    description?: string;
    status: 'active' | 'archived';
    tags?: string[];
    pcap_ref: {
        pcap_id: string;
    };
    expectations: {
        // 基础结果类
        min_alerts: number;
        max_alerts?: number;
        exact_alerts?: number;
        min_high_severity_count: number;
        dry_run_required: boolean;

        // 模式匹配类
        must_have?: Array<{ type: string; severity_at_least?: string }>;
        forbidden_types?: string[];

        // 证据类
        evidence_chain_contains?: string[];
        required_entities?: string[];
        required_feature_names?: string[];

        // 性能类
        max_pipeline_latency_ms?: number;
        max_validation_latency_ms?: number;
        required_pipeline_stages?: string[];
        no_failed_stages: boolean;
    };
}

export interface ScenarioRunResult {
    version?: string;
    id: string;
    created_at?: string;
    scenario_id: string;
    status: 'pass' | 'fail';
    checks: Array<{
        name: string;
        pass: boolean;
        details?: any;
    }>;
    metrics: {
        alert_count: number;
        high_severity_count: number;
        avg_dry_run_risk: number;
        validation_latency_ms?: number;  // 新增：校验耗时
        pipeline_latency_ms?: number;    // 新增：Pipeline 耗时
        [key: string]: number | undefined;
    };
    timeline?: ScenarioRunTimeline;  // 新增：阶段时间线
}

export type PipelineStageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

// 结构化失败归因（新增）
export interface FailureAttribution {
    check_name: string;
    expected: any;
    actual: any;
    category: 'data_missing' | 'assertion_failed' | 'service_error' | 'timeout';
}

// 场景阶段记录（新增）
export interface ScenarioStageRecord {
    stage_name: string;
    status: PipelineStageStatus;
    started_at: string | null;
    completed_at: string | null;
    latency_ms: number | null;
    key_metrics: Record<string, any>;
    error_summary: string | null;
    failure_attribution: FailureAttribution | null;
    input_summary: Record<string, any>;
    output_summary: Record<string, any>;
}

// 场景运行时间线（新增）
export interface ScenarioRunTimeline {
    id: string;
    scenario_id: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    total_latency_ms: number | null;
    validation_latency_ms: number | null;
    pipeline_latency_ms: number | null;
    stages: ScenarioStageRecord[];
    failed_stage: string | null;
}

export interface StageRecord {
    stage_name: string;
    status: PipelineStageStatus;
    started_at: string | null;
    completed_at: string | null;
    latency_ms: number | null;
    key_metrics: Record<string, any>;
    error_summary: string | null;
    input_summary: Record<string, any>;
    output_summary: Record<string, any>;
}

export interface PipelineRun {
    version?: string;
    id: string;
    pcap_id: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    total_latency_ms: number | null;
    stages: StageRecord[];
    created_at: string | null;
}


// ==================== Dashboard 仪表盘类型定义 ====================

/** 仪表盘聚合响应 */
/** 卡片级迷你趋势线数据 */
export interface MetricSparklines {
  /** 最近 7 天每日 PCAP 上传数量 */
  pcap_trend: number[];
  /** 最近 7 天每日 Flow 新增数量 */
  flow_trend: number[];
  /** 最近 7 天每日开放告警数量 */
  alert_open_trend: number[];
}

export interface DashboardSummary {
  overview: DashboardOverview;
  trends: DashboardTrends;
  distributions: DashboardDistributions;
  topology_snapshot: TopologySnapshot;
  recent_activity: ActivityEvent[];
  metric_sparklines: MetricSparklines;
}

/** 总览指标 */
export interface DashboardOverview {
  /** PCAP 总数 */
  pcap_total: number;
  /** 处理中的 PCAP 数量 */
  pcap_processing: number;
  /** 最后完成时间（ISO8601） */
  pcap_last_done_at: string | null;
  /** 24 小时内上传数量 */
  pcap_24h_count: number;
  /** Flow 总数 */
  flow_total: number;
  /** 24 小时内新增 Flow 数量 */
  flow_24h_count: number;
  /** Alert 总数 */
  alert_total: number;
  /** 开放告警数量（new + triaged + investigating） */
  alert_open_count: number;
  /** 按严重程度分组的告警计数 */
  alert_by_severity: Record<string, number>;
  /** 按类型分组的告警计数 */
  alert_by_type: Record<string, number>;
  /** 最后分析时间（ISO8601） */
  alert_last_analysis_at: string | null;
  /** Dry-Run 总数 */
  dryrun_total: number;
  /** 平均中断风险值 */
  dryrun_avg_disruption_risk: number;
  /** 最后一次 dry-run 的 impact 摘要 */
  dryrun_last_result: Record<string, any> | null;
  /** Scenario 总数 */
  scenario_total: number;
  /** 最后运行状态 */
  scenario_last_status: string | null;
  /** 通过率（0.0 ~ 1.0） */
  scenario_pass_rate: number;
  /** 场景运行总数 */
  scenario_run_total: number;
  /** 最后一次流水线运行快照 */
  pipeline_last_run: PipelineSnapshot | null;
}

/** 最后一次流水线运行快照 */
export interface PipelineSnapshot {
  id: string;
  pcap_id: string;
  status: string;
  /** 解析后的 stages_log */
  stages: Array<Record<string, any>>;
  total_latency_ms: number | null;
  /** 失败阶段列表 */
  failed_stages: string[];
}

/** 单日趋势数据 */
export interface TrendDay {
  /** 日期，格式如 "2024-01-15" */
  date: string;
  low: number;
  medium: number;
  high: number;
  critical: number;
}

/** 告警趋势 */
export interface DashboardTrends {
  days: TrendDay[];
}

/** 分布项 */
export interface DistributionItem {
  type: string;
  count: number;
}

/** 告警类型分布 */
export interface DashboardDistributions {
  items: DistributionItem[];
}

/** 迷你拓扑快照 */
export interface TopologySnapshot {
  /** 节点数量 */
  node_count: number;
  /** 边数量 */
  edge_count: number;
  /** 前 10 个高风险节点 */
  top_risk_nodes: Array<{ id: string; label: string; risk: number }>;
  /** 前 10 条高风险边 */
  top_risk_edges: Array<{ id: string; source: string; target: string; risk: number }>;
}

/** 活动事件 */
export interface ActivityEvent {
  id: string;
  type: 'pcap' | 'pipeline' | 'alert' | 'dryrun' | 'scenario';
  /** 动作类型标识符，如 "created"、"completed"、"executed" */
  kind: string;
  /** 实体类型，如 "pcap"、"pipeline"、"alert"、"dryrun"、"scenario" */
  entity_type: string;
  /** 关联实体的 ID */
  entity_id: string;
  /** 事件摘要（标准化标识符，如 "alert.created"） */
  summary: string;
  /** 结构化上下文数据 */
  payload: Record<string, any>;
  /** 可选导航链接 */
  href?: string | null;
  /** 类型特定的额外信息（保留以兼容旧数据） */
  detail: Record<string, any>;
  /** 创建时间（ISO8601） */
  created_at: string;
}


// ==================== 批量接入类型定义 ====================

/** 批次状态 */
export type BatchStatus =
  | 'created' | 'uploading' | 'validating' | 'processing'
  | 'completed' | 'partial_failure' | 'failed' | 'cancelled';

/** 批次文件状态 */
export type BatchFileStatus =
  | 'accepted' | 'rejected' | 'duplicate' | 'queued'
  | 'parsing' | 'featurizing' | 'detecting' | 'aggregating'
  | 'done' | 'failed';

/** 作业状态 */
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

/** 批次摘要 */
export interface Batch {
  version: string;
  id: string;
  created_at: string;
  name: string;
  status: BatchStatus;
  source: string | null;
  tags: string[] | null;
  total_files: number;
  completed_files: number;
  failed_files: number;
  total_flow_count: number;
  total_alert_count: number;
  total_size_bytes: number;
  started_at: string | null;
  completed_at: string | null;
  total_latency_ms: number | null;
  error_message: string | null;
}

/** 批次文件记录 */
export interface BatchFileRecord {
  version: string;
  id: string;
  created_at: string;
  batch_id: string;
  pcap_id: string | null;
  original_filename: string;
  size_bytes: number;
  sha256: string | null;
  status: BatchFileStatus;
  sequence: number;
  flow_count: number;
  alert_count: number;
  error_message: string | null;
  reject_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
  latency_ms: number | null;
  retry_count: number;
}

/** 批次详情（含文件列表） */
export interface BatchDetail extends Batch {
  files: BatchFileRecord[];
}

/** 作业记录 */
export interface BatchJob {
  version: string;
  id: string;
  created_at: string;
  batch_id: string;
  batch_file_id: string;
  pcap_id: string | null;
  status: JobStatus;
  current_stage: string | null;
  stages_log: Array<Record<string, any>> | null;
  retry_count: number;
  started_at: string | null;
  completed_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
}

/** 创建批次请求 */
export interface CreateBatchRequest {
  name?: string;
  source?: string;
  tags?: string[];
}

/** 启动批次响应 */
export interface BatchStartResponse {
  batch_id: string;
  jobs_created: number;
  skipped_files: number;
}

/** 重试批次响应 */
export interface BatchRetryResponse {
  batch_id: string;
  jobs_created: number;
  files_retried: number;
}

// ==================== Analytics 标准化分析类型定义 ====================

/** 评分因子 */
export interface ScoreFactor {
  name: string;
  value: number;
  weight: number;
  description: string;
}

/** 标准化评分结果 */
export interface ScoreResult {
  value: number;
  factors: ScoreFactor[];
  score_version: string;
  computed_at: string;
  explain?: string | null;
  breakdown?: Record<string, any> | null;
}

/** 分析总览（含评分） */
export interface AnalyticsOverview {
  pcap_total: number;
  pcap_processing: number;
  pcap_24h_count: number;
  flow_total: number;
  flow_24h_count: number;
  alert_total: number;
  alert_open_count: number;
  alert_by_severity: Record<string, number>;
  dryrun_total: number;
  dryrun_avg_disruption_risk: number;
  scenario_total: number;
  scenario_pass_rate: number;
  posture_score: ScoreResult | null;
}

/** 高风险资产条目 */
export interface TopAssetItem {
  id: string;
  label: string;
  risk: number;
  category: string;
}

/** 高风险资产排行 */
export interface TopAssets {
  top_risk_nodes: TopAssetItem[];
  top_risk_edges: TopAssetItem[];
  top_alert_types: Array<{ type: string; count: number }>;
}


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
    tactic_id: string;
    tactic_name: string;
    confidence: number;
    description?: string;
    intel_refs?: string[];
}

export interface ThreatContext {
    techniques: ThreatTechnique[];
    tactics: string[];
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
    };
}

export interface DryRunResult {
    version?: string;
    id: string;
    created_at?: string;
    alert_id: string;
    plan_id: string;
    impact: {
        impacted_nodes_count?: number;
        reachability_drop?: number;
        service_disruption_risk?: number;
        warnings?: string[];
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
}

export interface Scenario {
    version?: string;
    id: string;
    created_at?: string;
    name: string;
    description?: string;
    tags?: string[];
    pcap_ref: {
        pcap_id: string;
    };
    expectations: {
        min_alerts: number;
        must_have?: Array<{ type: string; severity_at_least?: string }>;
        evidence_chain_contains?: string[];
        dry_run_required: boolean;
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
        processing_time_ms?: number;
        [key: string]: number | undefined;
    };
}

export type PipelineStageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

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

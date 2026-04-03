import {
  PcapFile, FlowRecord, Alert, GraphResponse, Investigation,
  Recommendation, ActionPlan, DryRunResult, Scenario, ScenarioRunResult,
  EvidenceChain, CompilePlanRequest, CompilePlanResponse,
  PipelineRun, StageRecord, DashboardSummary,
  Batch, BatchDetail, BatchFileRecord, BatchJob,
  CreateBatchRequest, BatchStartResponse, BatchRetryResponse,
} from './types';

// 服务端（Server Component）优先使用内部网络地址，客户端使用公开地址
const BASE_URL =
  typeof window === 'undefined'
    ? (process.env.API_BASE_URL_INTERNAL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000')
    : (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000');

interface Envelope<T> {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string; details?: any } | null;
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, options);
  if (!res.ok) {
        let detail = '';
        try {
            const payload = await res.json();
            if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
                const first = payload.detail[0];
                detail = first?.msg ? ` - ${first.msg}` : '';
            } else if (payload?.error?.message) {
                detail = ` - ${payload.error.message}`;
            } else if (typeof payload?.detail === 'string') {
                detail = ` - ${payload.detail}`;
            }
        } catch {
            // 忽略解析失败，保留 status text 作为兜底提示
        }
        throw new Error(`API Error: ${res.status} ${res.statusText}${detail}`);
  }
  // 204 No Content — no body to parse
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  const envelope: Envelope<T> = await res.json();
  if (!envelope.ok || envelope.data === null || envelope.data === undefined) {
    throw new Error(envelope.error?.message || 'Unknown API error');
  }
  return envelope.data;
}

export const realApi = {
    uploadPcap: async (file: File): Promise<PcapFile> => {
        const formData = new FormData();
        formData.append('file', file);
        return fetchJson<PcapFile>('/api/v1/pcaps/upload', {
            method: 'POST',
            body: formData,
        });
    },
    listPcaps: async (params?: {limit?: number, offset?: number}): Promise<PcapFile[]> => {
        const query = new URLSearchParams(params as any).toString();
        return fetchJson<PcapFile[]>(`/api/v1/pcaps?${query}`);
    },
    getPcapStatus: async (id: string): Promise<PcapFile> => {
        return fetchJson<PcapFile>(`/api/v1/pcaps/${id}/status`);
    },
    processPcap: async (id: string, body: any): Promise<{accepted: true}> => {
        return fetchJson<{accepted: true}>(`/api/v1/pcaps/${id}/process`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
    },

    listFlows: async (params: any): Promise<FlowRecord[]> => {
        const query = new URLSearchParams(params).toString();
        return fetchJson<FlowRecord[]>(`/api/v1/flows?${query}`);
    },
    getFlow: async (id: string): Promise<FlowRecord> => {
        return fetchJson<FlowRecord>(`/api/v1/flows/${id}`);
    },

    listAlerts: async (params: any): Promise<Alert[]> => {
        const query = new URLSearchParams(params).toString();
        return fetchJson<Alert[]>(`/api/v1/alerts?${query}`);
    },
    getAlert: async (id: string): Promise<Alert> => {
        return fetchJson<Alert>(`/api/v1/alerts/${id}`);
    },
    patchAlert: async (id: string, patch: Partial<Alert>): Promise<Alert> => {
         return fetchJson<Alert>(`/api/v1/alerts/${id}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(patch)
        });
    },

    getGraph: async (params: any): Promise<GraphResponse> => {
        const query = new URLSearchParams(params).toString();
        return fetchJson<GraphResponse>(`/api/v1/topology/graph?${query}`);
    },

    triage: async (id: string, body: any): Promise<{triage_summary: string}> => {
         return fetchJson<{triage_summary: string}>(`/api/v1/alerts/${id}/triage`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
    },
    investigate: async (id: string, body?: any): Promise<Investigation> => {
         return fetchJson<Investigation>(`/api/v1/alerts/${id}/investigate`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body ?? {})
        });
    },
    recommend: async (id: string, body?: any): Promise<Recommendation> => {
         return fetchJson<Recommendation>(`/api/v1/alerts/${id}/recommend`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body ?? {})
        });
    },

    getEvidenceChain: async (id: string): Promise<EvidenceChain> => {
        return fetchJson<EvidenceChain>(`/api/v1/alerts/${id}/evidence-chain`);
    },

    getInvestigation: async (id: string): Promise<Investigation> => {
        return fetchJson<Investigation>(`/api/v1/investigations/${id}`);
    },
    getRecommendation: async (id: string): Promise<Recommendation> => {
        return fetchJson<Recommendation>(`/api/v1/recommendations/${id}`);
    },

    compilePlan: async (alertId: string, body?: CompilePlanRequest): Promise<CompilePlanResponse> => {
        return fetchJson<CompilePlanResponse>(`/api/v1/alerts/${alertId}/compile-plan`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body ?? {})
        });
    },

    dryRunPlan: async (planId: string, body?: any): Promise<DryRunResult> => {
         return fetchJson<DryRunResult>(`/api/v1/twin/plans/${planId}/dry-run`, {
            method: 'POST',
             headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body || {})
        });
    },
    listDryRuns: async (params: any): Promise<DryRunResult[]> => {
         const query = new URLSearchParams(params).toString();
        return fetchJson<DryRunResult[]>(`/api/v1/twin/dry-runs?${query}`);
    },
    getDryRun: async (id: string): Promise<DryRunResult> => {
        return fetchJson<DryRunResult>(`/api/v1/twin/dry-runs/${id}`);
    },

    createScenario: async (body: any): Promise<Scenario> => {
         return fetchJson<Scenario>(`/api/v1/scenarios`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
    },
    listScenarios: async (params: { include_archived?: boolean; limit?: number; offset?: number }): Promise<Scenario[]> => {
        const query = new URLSearchParams(
            Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]))
        ).toString();
        return fetchJson<Scenario[]>(`/api/v1/scenarios${query ? `?${query}` : ''}`);
    },
    runScenario: async (id: string): Promise<ScenarioRunResult> => {
         return fetchJson<ScenarioRunResult>(`/api/v1/scenarios/${id}/run`, {
            method: 'POST'
        });
    },
    getLatestScenarioRun: async (scenarioId: string): Promise<ScenarioRunResult> => {
        return fetchJson<ScenarioRunResult>(`/api/v1/scenarios/${scenarioId}/latest-run`);
    },
    archiveScenario: async (id: string): Promise<Scenario> => {
        return fetchJson<Scenario>(`/api/v1/scenarios/${id}/archive`, { method: 'PATCH' });
    },
    unarchiveScenario: async (id: string): Promise<Scenario> => {
        return fetchJson<Scenario>(`/api/v1/scenarios/${id}/unarchive`, { method: 'PATCH' });
    },
    deleteScenario: async (id: string): Promise<void> => {
        await fetchJson<void>(`/api/v1/scenarios/${id}`, { method: 'DELETE' });
    },

    getPipelineRun: async (pcapId: string): Promise<PipelineRun> => {
        return fetchJson<PipelineRun>(`/api/v1/pipeline/${pcapId}`);
    },
    getPipelineStages: async (pcapId: string): Promise<StageRecord[]> => {
        return fetchJson<StageRecord[]>(`/api/v1/pipeline/${pcapId}/stages`);
    },

    /** 删除 PCAP 文件及其所有关联数据 */
    deletePcap: async (id: string): Promise<{ deleted: boolean }> => {
        return fetchJson<{ deleted: boolean }>(`/api/v1/pcaps/${id}`, { method: 'DELETE' });
    },

    /** 获取仪表盘聚合数据 */
    getDashboardSummary: async (): Promise<DashboardSummary> => {
        return fetchJson<DashboardSummary>('/api/v1/dashboard/summary');
    },

    // ── 批量接入 API ──

    /** 创建批次 */
    createBatch: async (body: CreateBatchRequest): Promise<Batch> => {
        return fetchJson<Batch>('/api/v1/batches', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    /** 列出批次 */
    listBatches: async (params?: { limit?: number; offset?: number; status?: string }): Promise<Batch[]> => {
        const query = params ? new URLSearchParams(
            Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]))
        ).toString() : '';
        return fetchJson<Batch[]>(`/api/v1/batches${query ? `?${query}` : ''}`);
    },

    /** 获取批次详情 */
    getBatchDetail: async (batchId: string): Promise<BatchDetail> => {
        return fetchJson<BatchDetail>(`/api/v1/batches/${batchId}`);
    },

    /** 上传批次文件（多文件） */
    uploadBatchFiles: async (batchId: string, files: File[]): Promise<BatchFileRecord[]> => {
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }
        return fetchJson<BatchFileRecord[]>(`/api/v1/batches/${batchId}/files`, {
            method: 'POST',
            body: formData,
        });
    },

    /** 列出批次文件 */
    getBatchFiles: async (batchId: string, params?: { limit?: number; offset?: number; status?: string }): Promise<BatchFileRecord[]> => {
        const query = params ? new URLSearchParams(
            Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]))
        ).toString() : '';
        return fetchJson<BatchFileRecord[]>(`/api/v1/batches/${batchId}/files${query ? `?${query}` : ''}`);
    },

    /** 启动批次处理 */
    startBatch: async (batchId: string): Promise<BatchStartResponse> => {
        return fetchJson<BatchStartResponse>(`/api/v1/batches/${batchId}/start`, {
            method: 'POST',
        });
    },

    /** 取消批次 */
    cancelBatch: async (batchId: string, body?: { reason?: string }): Promise<Batch> => {
        return fetchJson<Batch>(`/api/v1/batches/${batchId}/cancel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body ?? {}),
        });
    },

    /** 重试批次所有失败文件 */
    retryBatch: async (batchId: string): Promise<BatchRetryResponse> => {
        return fetchJson<BatchRetryResponse>(`/api/v1/batches/${batchId}/retry`, {
            method: 'POST',
        });
    },

    /** 重试单个文件 */
    retryBatchFile: async (batchId: string, fileId: string): Promise<BatchJob> => {
        return fetchJson<BatchJob>(`/api/v1/batches/${batchId}/files/${fileId}/retry`, {
            method: 'POST',
        });
    },

    /** 查看文件作业历史 */
    getBatchFileJobs: async (batchId: string, fileId: string): Promise<BatchJob[]> => {
        return fetchJson<BatchJob[]>(`/api/v1/batches/${batchId}/files/${fileId}/jobs`);
    },

    /** 删除批次及所有关联数据 */
    deleteBatch: async (batchId: string): Promise<{ deleted: boolean; pcap_ids: string[] }> => {
        return fetchJson<{ deleted: boolean; pcap_ids: string[] }>(`/api/v1/batches/${batchId}`, {
            method: 'DELETE',
        });
    },
};

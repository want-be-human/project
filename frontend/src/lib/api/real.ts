import { 
  PcapFile, FlowRecord, Alert, GraphResponse, Investigation, 
  Recommendation, ActionPlan, DryRunResult, Scenario, ScenarioRunResult,
  EvidenceChain
} from './types';

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

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
            }
        } catch {
            // ignore parsing failures and keep status text fallback
        }
        throw new Error(`API Error: ${res.status} ${res.statusText}${detail}`);
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

    createPlan: async (body: any): Promise<ActionPlan> => {
         // Transform frontend action shape to backend PlanAction schema
         const allowedActionTypes = new Set([
            'block_ip',
            'isolate_host',
            'segment_subnet',
            'rate_limit_service',
         ]);
         const normalizeTarget = (target: any) => {
            if (typeof target === 'string') {
                return { type: 'ip', value: target || '0.0.0.0' };
            }
            const allowedTargetTypes = new Set(['ip', 'subnet', 'service']);
            const type = allowedTargetTypes.has(target?.type) ? target.type : 'ip';
            const value = typeof target?.value === 'string' && target.value.trim()
                ? target.value
                : '0.0.0.0';
            return { type, value };
         };
         const normalizeRollback = (rollback: any) => {
            // Backend expects rollback as object {action_type, params} or null
            if (!rollback || typeof rollback !== 'object' || Array.isArray(rollback)) {
                return null;
            }
            if (typeof rollback.action_type !== 'string' || !rollback.action_type) {
                return null;
            }
            return {
                action_type: rollback.action_type,
                params: rollback.params && typeof rollback.params === 'object' ? rollback.params : {},
            };
         };
         const transformed = {
            ...body,
            actions: (body.actions || []).map((a: any) => ({
                action_type: allowedActionTypes.has(a.action_type || a.type)
                    ? (a.action_type || a.type)
                    : 'block_ip',
                target: normalizeTarget(a.target),
                params: a.params || {},
                rollback: normalizeRollback(a.rollback),
            })),
         };
         console.log('[createPlan] transformed payload:', JSON.stringify(transformed, null, 2));
         return fetchJson<ActionPlan>(`/api/v1/twin/plans`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(transformed)
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

    createScenario: async (body: any): Promise<Scenario> => {
         return fetchJson<Scenario>(`/api/v1/scenarios`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
    },
    listScenarios: async (params: any): Promise<Scenario[]> => {
        const query = new URLSearchParams(params).toString();
        return fetchJson<Scenario[]>(`/api/v1/scenarios?${query}`);
    },
    runScenario: async (id: string): Promise<ScenarioRunResult> => {
         return fetchJson<ScenarioRunResult>(`/api/v1/scenarios/${id}/run`, {
            method: 'POST'
        });
    }
};

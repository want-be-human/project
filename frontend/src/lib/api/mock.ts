import { 
  PcapFile, FlowRecord, Alert, GraphResponse, Investigation, 
  Recommendation, ActionPlan, DryRunResult, Scenario, ScenarioRunResult,
  EvidenceChain
} from './types';

// Static load to ensure bundler picks them up if possible
// Use ../../../../contract/samples to reach project_root/contract/samples
// @ts-ignore
import flowSample from '../../../../contract/samples/flow.sample.json';
// @ts-ignore
import alertSample from '../../../../contract/samples/alert.sample.json';
// @ts-ignore
import graphSample from '../../../../contract/samples/graph.sample.json';
// @ts-ignore
import investigationSample from '../../../../contract/samples/investigation.sample.json';
// @ts-ignore
import recommendationSample from '../../../../contract/samples/recommendation.sample.json';
// @ts-ignore
import actionPlanSample from '../../../../contract/samples/actionplan.sample.json';
// @ts-ignore
import dryRunSample from '../../../../contract/samples/dryrun.sample.json';
// @ts-ignore
import evidenceChainSample from '../../../../contract/samples/evidencechain.sample.json';
// @ts-ignore
import scenarioSample from '../../../../contract/samples/scenario.sample.json';
// @ts-ignore
import scenarioRunResultSample from '../../../../contract/samples/scenario_run_result.sample.json';

const mockPcap: PcapFile = {
    id: "11111111-2222-3333-4444-555555555555",
    created_at: new Date().toISOString(),
    filename: "demo.pcap",
    size: 1024 * 1024 * 5,
    status: "done",
    progress: 100,
    flow_count: 1000,
    alert_count: 5
};

export const mockApi = {
    uploadPcap: async (file: File): Promise<PcapFile> => {
        return { ...mockPcap, filename: file.name, status: 'uploaded', progress: 0 };
    },
    listPcaps: async (): Promise<PcapFile[]> => {
        return [mockPcap];
    },
    getPcapStatus: async (id: string): Promise<PcapFile> => {
        return mockPcap;
    },
    processPcap: async (id: string, body: any): Promise<{accepted: true}> => {
        return { accepted: true };
    },

    listFlows: async (params: any): Promise<FlowRecord[]> => {
        return [flowSample as unknown as FlowRecord];
    },
    getFlow: async (id: string): Promise<FlowRecord> => {
        return flowSample as unknown as FlowRecord;
    },

    listAlerts: async (params: any): Promise<Alert[]> => {
        return [alertSample as unknown as Alert];
    },
    getAlert: async (id: string): Promise<Alert> => {
        return alertSample as unknown as Alert;
    },
    patchAlert: async (id: string, patch: Partial<Alert>): Promise<Alert> => {
        return { ...alertSample as unknown as Alert, ...patch };
    },

    getGraph: async (params: any): Promise<GraphResponse> => {
        return graphSample as unknown as GraphResponse;
    },

    triage: async (id: string, body: any): Promise<{triage_summary: string}> => {
        return { triage_summary: "Automated triage: This looks like a brute force attack." };
    },
    investigate: async (id: string): Promise<Investigation> => {
        return investigationSample as unknown as Investigation;
    },
    recommend: async (id: string): Promise<Recommendation> => {
        return recommendationSample as unknown as Recommendation;
    },

    getEvidenceChain: async (id: string): Promise<EvidenceChain> => {
        return evidenceChainSample as unknown as EvidenceChain;
    },

    createPlan: async (body: any): Promise<ActionPlan> => {
        return actionPlanSample as unknown as ActionPlan;
    },
    dryRunPlan: async (planId: string, body?: any): Promise<DryRunResult> => {
        return dryRunSample as unknown as DryRunResult;
    },
    listDryRuns: async (params: any): Promise<DryRunResult[]> => {
        return [dryRunSample as unknown as DryRunResult];
    },

    createScenario: async (body: any): Promise<Scenario> => {
        return scenarioSample as unknown as Scenario;
    },
    listScenarios: async (params: any): Promise<Scenario[]> => {
        return [scenarioSample as unknown as Scenario];
    },
    runScenario: async (id: string): Promise<ScenarioRunResult> => {
        return scenarioRunResultSample as unknown as ScenarioRunResult;
    }
};

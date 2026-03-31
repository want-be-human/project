'use client';

import { Scenario, ScenarioRunResult, ScenarioStageRecord, ScenarioRunTimeline, FailureAttribution } from '@/lib/api/types';
import { api } from '@/lib/api';
import { wsClient } from '@/lib/ws';
import {
  SCENARIO_RUN_STARTED,
  SCENARIO_STAGE_STARTED,
  SCENARIO_STAGE_COMPLETED,
  SCENARIO_STAGE_FAILED,
  SCENARIO_RUN_PROGRESS,
  SCENARIO_RUN_DONE,
} from '@/lib/events';
import { useState, useEffect } from 'react';
import { Play, CheckCircle2, XCircle, Clock, Activity, ShieldAlert, BarChart3, RefreshCw, AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import StageTimeline from '@/components/shared/StageTimeline';

interface Props {
  scenario: Scenario | null;
  onRunStatusChange: (scenarioId: string | undefined) => void;
}

// 场景阶段名称到 i18n 键名的映射
const SCENARIO_STAGE_I18N_KEY_MAP: Record<string, string> = {
  load_scenario:                  'stageLoadScenario',
  load_alerts:                    'stageLoadAlerts',
  check_alert_volume:             'stageCheckAlertVolume',
  check_required_patterns:        'stageCheckRequiredPatterns',
  check_evidence_chain:           'stageCheckEvidenceChain',
  check_dry_run:                  'stageCheckDryRun',
  check_entities_and_features:    'stageCheckEntitiesAndFeatures',
  check_pipeline_constraints:     'stageCheckPipelineConstraints',
  summarize_result:               'stageSummarizeResult',
};

export default function ScenarioRunPanel({ scenario, onRunStatusChange }: Props) {
  const t = useTranslations('scenarios');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ScenarioRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // 实时阶段流状态
  const [liveStages, setLiveStages] = useState<ScenarioStageRecord[]>([]);
  const [liveTimeline, setLiveTimeline] = useState<ScenarioRunTimeline | null>(null);
  const [stageProgress, setStageProgress] = useState<{ completed: number; total: number } | null>(null);

  // 选择新场景时清空旧结果
  useEffect(() => {
    setResult(null);
    setError(null);
    setLiveStages([]);
    setLiveTimeline(null);
    setStageProgress(null);
  }, [scenario?.id]);

  // 订阅 6 个 WebSocket 事件实现实时阶段流
  useEffect(() => {
    if (!scenario) return;

    const unsubs = [
      // 1. scenario.run.started - 运行开始
      wsClient.onEvent(SCENARIO_RUN_STARTED, (p: any) => {
        if (p.scenario_id !== scenario.id) return;
        setLiveStages([]);
        setLiveTimeline(null);
        setStageProgress({ completed: 0, total: p.total_stages || 9 });
      }),

      // 2. scenario.stage.started - 阶段开始
      wsClient.onEvent(SCENARIO_STAGE_STARTED, (p: any) => {
        if (p.scenario_id !== scenario.id) return;
        setLiveStages(prev => [...prev, {
          stage_name: p.stage,
          status: 'running',
          started_at: null,
          completed_at: null,
          latency_ms: null,
          key_metrics: {},
          error_summary: null,
          failure_attribution: null,
          input_summary: {},
          output_summary: {},
        }]);
      }),

      // 3. scenario.stage.completed - 阶段完成
      wsClient.onEvent(SCENARIO_STAGE_COMPLETED, (p: any) => {
        if (p.scenario_id !== scenario.id) return;
        setLiveStages(prev => prev.map(s =>
          s.stage_name === p.stage
            ? { ...s, status: 'completed', latency_ms: p.latency_ms, key_metrics: p.key_metrics || {} }
            : s
        ));
      }),

      // 4. scenario.stage.failed - 阶段失败
      wsClient.onEvent(SCENARIO_STAGE_FAILED, (p: any) => {
        if (p.scenario_id !== scenario.id) return;
        setLiveStages(prev => prev.map(s =>
          s.stage_name === p.stage
            ? {
                ...s,
                status: 'failed',
                error_summary: p.error_summary,
                failure_attribution: p.failure_attribution,
              }
            : s
        ));
      }),

      // 5. scenario.run.progress - 进度更新
      wsClient.onEvent(SCENARIO_RUN_PROGRESS, (p: any) => {
        if (p.scenario_id !== scenario.id) return;
        setStageProgress({ completed: p.completed_stages, total: p.total_stages });
      }),

      // 6. scenario.run.done - 运行完成（仅在非主动运行时补拉）
      wsClient.onEvent(SCENARIO_RUN_DONE, async (p: any) => {
        if (p.scenario_id !== scenario.id) return;
        if (running) return;
        setRefreshing(true);
        try {
          const full = await api.getLatestScenarioRun(p.scenario_id);
          setResult(full);
          if (full.timeline) {
            setLiveTimeline(full.timeline);
          }
        } catch (e) {
          console.error('Failed to fetch scenario run detail:', e);
        } finally {
          setRefreshing(false);
        }
      }),
    ];

    return () => unsubs.forEach(u => u());
  }, [scenario?.id, running]);

  const handleRun = async () => {
    if (!scenario) return;
    setRunning(true);
    setError(null);
    setResult(null);
    setLiveStages([]);
    setLiveTimeline(null);
    setStageProgress(null);
    onRunStatusChange(scenario.id);

    try {
      const res = await api.runScenario(scenario.id);
      setResult(res);
      if (res.timeline) {
        setLiveTimeline(res.timeline);
      }
    } catch (e: any) {
      setError(e.message || t('runError'));
    } finally {
      setRunning(false);
      onRunStatusChange(undefined);
    }
  };

  if (!scenario) {
    return (
      <div className="bg-white rounded-lg shadow border border-gray-200 h-full flex items-center justify-center text-gray-400 p-8 text-center flex-col">
        <Activity className="w-12 h-12 mb-4 text-gray-300" />
        <p>{t('selectPrompt')}</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-start bg-gray-50 rounded-t-lg">
        <div>
          <h2 className="text-xl font-bold text-gray-900 mb-1">{scenario.name}</h2>
          <p className="text-sm text-gray-500">{scenario.description || t('noDescription')}</p>
        </div>
        <div className="flex items-center gap-3">
          {refreshing && (
            <span className="flex items-center gap-1 text-xs text-indigo-500">
              <RefreshCw className="w-3 h-3 animate-spin" /> {t('refreshing')}
            </span>
          )}
          {running ? (
            <button
              key="running"
              disabled
              className="flex items-center gap-2 px-4 py-2 rounded-md font-medium bg-gray-300 text-gray-500 cursor-not-allowed"
            >
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>{t('runningBtn')}</span>
            </button>
          ) : scenario.status === 'archived' ? (
            <button
              key="archived"
              disabled
              title={t('archiveDisabledRunning')}
              className="flex items-center gap-2 px-4 py-2 rounded-md font-medium bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200"
            >
              <Play className="w-4 h-4" />
              <span>{t('runScenario')}</span>
            </button>
          ) : (
            <button
              key="idle"
              onClick={handleRun}
              className="flex items-center gap-2 px-4 py-2 rounded-md font-medium bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-colors"
            >
              <Play className="w-4 h-4" />
              <span>{t('runScenario')}</span>
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6 bg-gray-50/50">
        
        {/* Archived notice */}
        {scenario.status === 'archived' && (
          <div className="p-3 bg-gray-100 border border-gray-200 rounded-md text-sm text-gray-500 flex items-center gap-2 mb-4">
            <span className="font-medium">{t('archived')}</span>
            <span>—</span>
            <span>{t('archivedRunNotice')}</span>
          </div>
        )}

        {/* Pre-run state */}
        {!result && !running && !error && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <p>{t('ready')}</p>
            <p className="text-sm mt-2">{t('clickToRun')}</p>
          </div>
        )}

        {/* Loading state with real-time progress */}
        {running && (
          <div className="space-y-4">
            <div className="flex flex-col items-center justify-center py-6">
              <p className="text-indigo-600 font-medium animate-pulse mb-2">{t('executing')}</p>
              <p className="text-sm text-gray-500">{t('executingDetail')}</p>
              {stageProgress && (
                <div className="mt-4 w-full max-w-md">
                  <div className="flex justify-between text-xs text-gray-600 mb-1">
                    <span>{t('progress')}</span>
                    <span>{stageProgress.completed} / {stageProgress.total}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${(stageProgress.completed / stageProgress.total) * 100}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
            {/* 实时阶段列表 */}
            {liveStages.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">{t('liveStages')}</h3>
                <StageTimeline
                  run={{
                    status: 'running',
                    started_at: null,
                    total_latency_ms: null,
                    stages: liveStages,
                  }}
                  loading={false}
                  error={null}
                  stageI18nKeyMap={SCENARIO_STAGE_I18N_KEY_MAP}
                  i18nNamespace="scenarios"
                />
              </div>
            )}
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md">
            <p className="font-bold flex items-center gap-2"><XCircle className="w-5 h-5"/> <span>{t('error')}</span></p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        {/* Result state */}
        {result && !running && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
            
            {/* Status Banner */}
            <div className={`p-4 rounded-lg flex items-center gap-3 border ${
              result.status === 'pass' 
                ? 'bg-green-50 border-green-200 text-green-800' 
                : 'bg-red-50 border-red-200 text-red-800'
            }`}>
              {result.status === 'pass' ? <CheckCircle2 className="w-8 h-8" /> : <XCircle className="w-8 h-8" />}
              <div>
                <h3 className="font-bold text-lg capitalize">{result.status === 'pass' ? t('passed') : t('failed')}</h3>
                <p className="opacity-80 text-sm">{t('completedAt', { time: new Date(result.created_at || Date.now()).toLocaleString() })}</p>
              </div>
            </div>

            {/* Metrics with Latency Breakdown */}
            {result.metrics && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" /> {t('metricsDashboard')}
                </h3>
                {/* 第一行：4 个主要指标 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <MetricCard label={t('totalAlerts')} value={result.metrics.alert_count} />
                  <MetricCard label={t('highSeverity')} value={result.metrics.high_severity_count} color="text-red-600" />
                  <MetricCard label={t('avgRisk')} value={result.metrics.avg_dry_run_risk?.toFixed(2)} />
                  <MetricCard
                    label={t('validationLatency')}
                    value={result.metrics.validation_latency_ms != null ? `${result.metrics.validation_latency_ms.toFixed(0)} ms` : '-'}
                  />
                </div>
                {/* 第二行：Pipeline 延迟（独立卡片） */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <MetricCard
                    label={t('pipelineLatency')}
                    value={
                      result.metrics.pipeline_latency_ms != null
                        ? `${result.metrics.pipeline_latency_ms.toFixed(0)} ms`
                        : t('noPipelineData')
                    }
                    color={result.metrics.pipeline_latency_ms != null ? "text-gray-900" : "text-gray-400"}
                  />
                </div>
              </div>
            )}

            {/* Checks Checklist */}
            {result.checks && result.checks.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4" /> {t('policyChecks')}
                </h3>
                <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
                  <div className="grid grid-cols-12 bg-gray-50 border-b border-gray-200 p-3 text-xs font-semibold text-gray-500 uppercase">
                    <div className="col-span-1 text-center">{t('checkStatus')}</div>
                    <div className="col-span-4">{t('checkName')}</div>
                    <div className="col-span-7">{t('checkDetails')}</div>
                  </div>
                  <div className="divide-y divide-gray-100">
                    {result.checks.map((check, idx) => (
                      <div key={idx} className="grid grid-cols-12 p-3 text-sm items-center">
                        <div className="col-span-1 flex justify-center">
                          {check.pass
                            ? <CheckCircle2 className="w-5 h-5 text-green-500" />
                            : <XCircle className="w-5 h-5 text-red-500" />
                          }
                        </div>
                        <div className="col-span-4 font-medium text-gray-700">
                          {check.name}
                        </div>
                        <div className="col-span-7 text-gray-600 font-mono text-xs overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(check.details, null, 2)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Scenario Stage Timeline */}
            {liveTimeline && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4" /> {t('stageTimeline')}
                </h3>
                {liveTimeline.failed_stage && (
                  <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-md flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                    <div className="text-sm text-red-700">
                      <span className="font-medium">{t('failedStage')}:</span> {liveTimeline.failed_stage}
                    </div>
                  </div>
                )}
                <StageTimeline
                  run={liveTimeline}
                  loading={false}
                  error={null}
                  stageI18nKeyMap={SCENARIO_STAGE_I18N_KEY_MAP}
                  i18nNamespace="scenarios"
                  renderExtraDetail={(stage) => {
                    if (stage.failure_attribution) {
                      const attr = stage.failure_attribution as FailureAttribution;
                      return (
                        <div>
                          <div className="font-medium text-red-700 mb-1">{t('failureAttribution')}</div>
                          <div className="bg-red-50 px-3 py-2 rounded border border-red-200 text-xs space-y-1">
                            <div><span className="font-semibold">{t('checkName')}:</span> {attr.check_name}</div>
                            <div><span className="font-semibold">{t('expected')}:</span> {JSON.stringify(attr.expected)}</div>
                            <div><span className="font-semibold">{t('actual')}:</span> {JSON.stringify(attr.actual)}</div>
                            <div><span className="font-semibold">{t('category')}:</span> {attr.category}</div>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, color = "text-gray-900" }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm flex flex-col justify-center">
      <div className="text-xs text-gray-500 font-medium mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value ?? '-'}</div>
    </div>
  );
}
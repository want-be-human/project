'use client';

import { useState } from 'react';
import { PipelineRun, PipelineStageStatus } from '@/lib/api/types';
import {
  CheckCircle2, XCircle, Loader2, Clock, SkipForward,
  ChevronDown, ChevronRight, Activity,
} from 'lucide-react';
import { format } from 'date-fns';

const STAGE_LABELS: Record<string, string> = {
  parse:           'Parse',
  feature_extract: 'Feature Extraction',
  detect:          'Detection',
  aggregate:       'Aggregation',
  investigate:     'Investigation',
  recommend:       'Recommendation',
  compile_plan:    'Plan Compilation',
  dry_run:         'Dry Run',
  visualize:       'Visualization',
};

function getStageLabel(name: string): string {
  return STAGE_LABELS[name] ?? name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function getStatusStyle(status: string) {
  switch (status as PipelineStageStatus) {
    case 'success':
      return {
        badge: 'bg-green-100 text-green-800',
        icon: <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />,
        overallBg: 'bg-green-50 border-green-200 text-green-800',
      };
    case 'failed':
      return {
        badge: 'bg-red-100 text-red-800',
        icon: <XCircle className="w-4 h-4 text-red-500 shrink-0" />,
        overallBg: 'bg-red-50 border-red-200 text-red-800',
      };
    case 'running':
      return {
        badge: 'bg-blue-100 text-blue-800',
        icon: <Loader2 className="w-4 h-4 text-blue-500 animate-spin shrink-0" />,
        overallBg: 'bg-blue-50 border-blue-200 text-blue-800',
      };
    case 'skipped':
      return {
        badge: 'bg-gray-100 text-gray-500',
        icon: <SkipForward className="w-4 h-4 text-gray-400 shrink-0" />,
        overallBg: 'bg-gray-50 border-gray-200 text-gray-600',
      };
    case 'pending':
    default:
      return {
        badge: 'bg-gray-100 text-gray-500',
        icon: <Clock className="w-4 h-4 text-gray-400 shrink-0" />,
        overallBg: 'bg-gray-50 border-gray-200 text-gray-600',
      };
  }
}

interface PipelineStageTimelineProps {
  pipelineRun: PipelineRun | null;
  loading: boolean;
  error: string | null;
}

export default function PipelineStageTimeline({ pipelineRun, loading, error }: PipelineStageTimelineProps) {
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());

  const toggleStage = (name: string) => {
    setExpandedStages(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
        <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
        <span>Loading pipeline data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
        {error}
      </div>
    );
  }

  if (!pipelineRun) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
        <Activity className="w-4 h-4" />
        <span>Pipeline data unavailable</span>
      </div>
    );
  }

  const overallStyle = getStatusStyle(pipelineRun.status);

  return (
    <div className="space-y-3">
      {/* Overall status banner */}
      <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${overallStyle.overallBg}`}>
        {overallStyle.icon}
        <div className="flex-1 min-w-0">
          <span className="font-semibold capitalize">{pipelineRun.status}</span>
          {pipelineRun.started_at && (
            <span className="ml-3 text-xs opacity-70">
              {format(new Date(pipelineRun.started_at), 'yyyy-MM-dd HH:mm:ss')}
            </span>
          )}
        </div>
        {pipelineRun.total_latency_ms != null && (
          <span className="text-xs font-mono opacity-80 shrink-0">
            Total: {pipelineRun.total_latency_ms.toFixed(0)} ms
          </span>
        )}
      </div>

      {/* Stage list */}
      {pipelineRun.stages.length === 0 ? (
        <div className="text-sm text-gray-400 px-4 py-3 border border-gray-100 rounded-lg bg-gray-50">
          No stage data recorded
        </div>
      ) : (
        <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden bg-white">
          {pipelineRun.stages.map((stage) => {
            const style = getStatusStyle(stage.status);
            const expanded = expandedStages.has(stage.stage_name);
            const hasMetrics = stage.key_metrics && Object.keys(stage.key_metrics).length > 0;
            const hasDetail = !!(stage.error_summary || hasMetrics ||
              (stage.input_summary && Object.keys(stage.input_summary).length > 0) ||
              (stage.output_summary && Object.keys(stage.output_summary).length > 0));

            return (
              <div key={stage.stage_name}>
                <button
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 text-left transition-colors"
                  onClick={() => hasDetail && toggleStage(stage.stage_name)}
                >
                  {style.icon}
                  <span className="flex-1 font-medium text-gray-900 text-sm">
                    {getStageLabel(stage.stage_name)}
                  </span>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${style.badge}`}>
                    {stage.status}
                  </span>
                  {stage.latency_ms != null && (
                    <span className="text-xs text-gray-400 font-mono ml-2 shrink-0">
                      {stage.latency_ms.toFixed(0)} ms
                    </span>
                  )}
                  {hasDetail && (
                    expanded
                      ? <ChevronDown className="w-4 h-4 text-gray-400 ml-1 shrink-0" />
                      : <ChevronRight className="w-4 h-4 text-gray-400 ml-1 shrink-0" />
                  )}
                </button>

                {expanded && hasDetail && (
                  <div className="px-4 pb-4 pt-1 bg-gray-50 border-t border-gray-100 space-y-2">
                    {stage.error_summary && (
                      <div className="px-3 py-2 bg-red-50 border border-red-100 rounded text-xs text-red-700">
                        {stage.error_summary}
                      </div>
                    )}
                    {hasMetrics && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 mb-1">Key Metrics</p>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                          {Object.entries(stage.key_metrics).map(([k, v]) => (
                            <div key={k} className="flex items-baseline gap-1">
                              <dt className="text-xs text-gray-500 truncate">{k}:</dt>
                              <dd className="text-xs font-mono text-gray-800 truncate">
                                {typeof v === 'number' ? v.toLocaleString() : String(v)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                    {stage.input_summary && Object.keys(stage.input_summary).length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 mb-1">Input</p>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                          {Object.entries(stage.input_summary).map(([k, v]) => (
                            <div key={k} className="flex items-baseline gap-1">
                              <dt className="text-xs text-gray-500 truncate">{k}:</dt>
                              <dd className="text-xs font-mono text-gray-800 truncate">{String(v)}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                    {stage.output_summary && Object.keys(stage.output_summary).length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 mb-1">Output</p>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                          {Object.entries(stage.output_summary).map(([k, v]) => (
                            <div key={k} className="flex items-baseline gap-1">
                              <dt className="text-xs text-gray-500 truncate">{k}:</dt>
                              <dd className="text-xs font-mono text-gray-800 truncate">{String(v)}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

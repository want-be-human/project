'use client';

import { Alert } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import { FileSearch, Layers, ShieldAlert, Link2 } from 'lucide-react';
import { clsx } from 'clsx';

interface AlertTraceabilitySectionProps {
  alert: Alert;
}

/** 评分分项中文标签 */
const SCORE_LABELS: Record<string, string> = {
  max_score: '最高异常分',
  flow_density: '流密度',
  duration_factor: '持续时长',
  aggregation_quality: '聚合质量',
};

/** 评分分项对应颜色 */
const SCORE_COLORS: Record<string, string> = {
  max_score: 'bg-red-500',
  flow_density: 'bg-amber-500',
  duration_factor: 'bg-blue-500',
  aggregation_quality: 'bg-emerald-500',
};

export default function AlertTraceabilitySection({ alert }: AlertTraceabilitySectionProps) {
  const t = useTranslations('alertDetail');
  const tc = useTranslations('confidence');
  const agg = alert.aggregation;
  if (!agg) return null;

  const hasTraceability = agg.aggregation_summary || agg.type_summary || agg.severity_summary;
  if (!hasTraceability) return null;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
        <FileSearch className="w-5 h-5 text-indigo-600" />
        {t('traceabilityTitle')}
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 聚合依据 */}
        {agg.aggregation_summary && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" />
              {t('aggregationBasis')}
            </h3>
            <p className="text-sm text-gray-700">{agg.aggregation_summary}</p>
            {agg.dimensions && (
              <div className="flex flex-wrap gap-1.5">
                {agg.dimensions.map((dim) => (
                  <span key={dim} className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600 font-mono">
                    {dim}
                  </span>
                ))}
              </div>
            )}
            <div className="font-mono text-xs text-gray-400 break-all">{agg.group_key}</div>
          </div>
        )}

        {/* 类型判定依据 */}
        {agg.type_summary && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5" />
              {t('typeBasis')}
            </h3>
            <p className="text-sm text-gray-700">{agg.type_summary}</p>
            {agg.type_reason?.reason_codes && (
              <div className="flex flex-wrap gap-1.5">
                {agg.type_reason.reason_codes.map((code) => (
                  <span key={code} className="px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700 font-mono border border-indigo-100">
                    {code}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 严重度依据 */}
        {agg.severity_summary && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider">
              {t('severityBasis')}
            </h3>
            {agg.composite_score !== undefined && (
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs text-gray-500" title={tc('compositeScoreTooltip')}>{tc('compositeScoreLabel')}:</span>
                <span className="text-sm font-semibold text-gray-900">{(agg.composite_score * 100).toFixed(1)}%</span>
              </div>
            )}
            <p className="text-sm text-gray-700">{agg.severity_summary}</p>
            {agg.score_breakdown && (
              <div className="space-y-1.5">
                {Object.entries(agg.score_breakdown)
                  .filter(([key]) => key !== 'composite')
                  .map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2 text-xs">
                      <span className="w-20 text-gray-500 shrink-0">{SCORE_LABELS[key] || key}</span>
                      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                        <div
                          className={clsx('h-full rounded-full transition-all', SCORE_COLORS[key] || 'bg-gray-400')}
                          style={{ width: `${Math.min(val * 100, 100)}%` }}
                        />
                      </div>
                      <span className="w-10 text-right font-mono text-gray-600">{val.toFixed(2)}</span>
                    </div>
                  ))}
              </div>
            )}
            <p className="text-[10px] text-gray-400 mt-1">{tc('disclaimer')}</p>
          </div>
        )}

        {/* 关联 Flow 核对 */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
            <Link2 className="w-3.5 h-3.5" />
            {t('relatedFlows')}
          </h3>
          <p className="text-sm text-gray-600">
            {t('totalFlows')}{' '}
            <span className="font-semibold text-gray-900">{alert.evidence.flow_ids.length}</span>
          </p>
          {alert.evidence.top_flows.length > 0 && (
            <div className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden">
              <table className="min-w-full text-sm text-left">
                <thead className="bg-gray-100 text-gray-600">
                  <tr>
                    <th className="px-3 py-1.5 font-medium">{t('flowId')}</th>
                    <th className="px-3 py-1.5 font-medium">{t('score')}</th>
                    <th className="px-3 py-1.5 font-medium">{t('summary')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {alert.evidence.top_flows.map((flow, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      <td className="px-3 py-1.5 font-mono text-xs text-blue-600 cursor-pointer hover:underline" title={flow.flow_id}>
                        {flow.flow_id.substring(0, 12)}...
                      </td>
                      <td className="px-3 py-1.5">
                        <span className={clsx('font-medium', flow.anomaly_score > 0.8 ? 'text-red-600' : 'text-orange-500')}>
                          {flow.anomaly_score.toFixed(2)}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-gray-700">{flow.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

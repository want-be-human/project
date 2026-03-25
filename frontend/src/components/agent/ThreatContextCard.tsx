'use client';

import { ThreatContext } from '@/lib/api/types';
import { useTranslations, useLocale } from 'next-intl';
import { ShieldAlert, ExternalLink } from 'lucide-react';

interface ThreatContextCardProps {
  threatContext?: ThreatContext | null;
}

function confidenceColor(confidence: number): string {
  if (confidence > 0.7) return 'text-red-700 bg-red-50 border-red-200';
  if (confidence > 0.4) return 'text-orange-700 bg-orange-50 border-orange-200';
  return 'text-gray-600 bg-gray-50 border-gray-200';
}

function confidenceBadgeColor(confidence: number): string {
  if (confidence > 0.7) return 'bg-red-100 text-red-700';
  if (confidence > 0.4) return 'bg-orange-100 text-orange-700';
  return 'bg-gray-100 text-gray-600';
}

export default function ThreatContextCard({ threatContext }: ThreatContextCardProps) {
  const t = useTranslations('agent');
  const tc = useTranslations('confidence');
  const locale = useLocale();

  if (!threatContext || threatContext.techniques.length === 0) return null;

  const localized = (zh: string | undefined | null, en: string) => {
    if (locale === 'zh' && zh) return zh;
    return en;
  };

  const displayTactics = locale === 'zh' && threatContext.tactics_zh
    ? threatContext.tactics_zh
    : threatContext.tactics;

  return (
    <div className="mt-4 border border-rose-200 bg-rose-50/50 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-rose-100/60 border-b border-rose-200">
        <ShieldAlert className="w-4 h-4 text-rose-600" />
        <h4 className="text-xs font-bold text-rose-800 uppercase tracking-wider">{t('threatContext')}</h4>
        <span
          className={`ml-auto text-[10px] font-medium px-2 py-0.5 rounded-full ${confidenceBadgeColor(threatContext.enrichment_confidence)}`}
          title={tc('enrichmentConfidenceTooltip')}
        >
          {tc('enrichmentConfidenceLabel')} {Math.round(threatContext.enrichment_confidence * 100)}%
        </span>
      </div>

      <div className="p-4 space-y-3">
        {/* Tactics row */}
        {displayTactics.length > 0 && (
          <div>
            <h5 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">{t('tactics')}</h5>
            <div className="flex flex-wrap gap-1.5">
              {displayTactics.map((tactic, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-100 text-rose-700 border border-rose-200"
                >
                  {tactic}
                  {locale === 'zh' && threatContext.tactics[idx] && (
                    <span className="text-[9px] text-rose-400 ml-1">({threatContext.tactics[idx]})</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Techniques list */}
        <div>
          <h5 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">{t('techniques')}</h5>
          <div className="space-y-2">
            {threatContext.techniques.map((tech) => (
              <div
                key={tech.technique_id}
                className={`rounded-md border p-2.5 ${confidenceColor(tech.confidence)}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] font-mono font-bold shrink-0">{tech.technique_id}</span>
                    <span className="text-xs font-medium truncate">
                      {localized(tech.technique_name_zh, tech.technique_name)}
                    </span>
                    {locale === 'zh' && tech.technique_name_zh && (
                      <span className="text-[9px] text-gray-400 truncate">{tech.technique_name}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/60 border border-current/10">
                      {localized(tech.tactic_name_zh, tech.tactic_name)}
                    </span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${confidenceBadgeColor(tech.confidence)}`}>
                      {Math.round(tech.confidence * 100)}%
                    </span>
                  </div>
                </div>

                {(tech.description || tech.description_zh) && (
                  <p className="mt-1 text-[11px] opacity-80">
                    {localized(tech.description_zh, tech.description ?? '')}
                  </p>
                )}

                {tech.intel_refs && tech.intel_refs.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    {tech.intel_refs.map((ref, i) => (
                      <a
                        key={i}
                        href={ref}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-800 underline underline-offset-2"
                      >
                        <ExternalLink className="w-2.5 h-2.5" />
                        {t('references')}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Source footer + disclaimer */}
        <div className="text-[10px] text-gray-400 pt-1 border-t border-rose-100 space-y-0.5">
          <div>{t('enrichmentSource')} {threatContext.enrichment_source}</div>
          <div>{tc('disclaimer')}</div>
        </div>
      </div>
    </div>
  );
}

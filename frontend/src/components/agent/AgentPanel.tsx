'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { Investigation, Recommendation } from '@/lib/api/types';
import { useTranslations, useLocale } from 'next-intl';
import { Search, Shield, Lightbulb, Loader2, History, RefreshCw } from 'lucide-react';
import ThreatContextCard from './ThreatContextCard';

interface AgentPanelProps {
  alertId: string;
  initialTriageSummary?: string | null;
  initialInvestigation?: Investigation | null;
  initialRecommendation?: Recommendation | null;
  onRecommendationLoaded?: (rec: Recommendation) => void;
  onOperationCompleted?: () => Promise<void>;
}

export default function AgentPanel({
  alertId,
  initialTriageSummary = null,
  initialInvestigation = null,
  initialRecommendation = null,
  onRecommendationLoaded,
  onOperationCompleted,
}: AgentPanelProps) {
  const t = useTranslations('agent');
  const tc = useTranslations('confidence');
  const locale = useLocale();
  const [activeTab, setActiveTab] = useState<'triage' | 'investigate' | 'recommend'>('triage');

  // "fresh" 状态：当前会话中由用户触发运行得到的新结果
  const [freshTriage, setFreshTriage] = useState<string | null>(null);
  const [freshInvestigation, setFreshInvestigation] = useState<Investigation | null>(null);
  const [freshRecommendation, setFreshRecommendation] = useState<Recommendation | null>(null);

  const [loading, setLoading] = useState(false);

  // 派生展示值：优先 fresh 结果，否则回退到初始（回填）props
  const triageSummary = freshTriage ?? initialTriageSummary;
  const investigation = freshInvestigation ?? initialInvestigation;
  const recommendation = freshRecommendation ?? initialRecommendation;

  // 派生历史标记
  const triageFromHistory = !freshTriage && !!initialTriageSummary;
  const investigationFromHistory = !freshInvestigation && !!initialInvestigation;
  const recommendationFromHistory = !freshRecommendation && !!initialRecommendation;

  const handleTriage = async () => {
    setLoading(true);
    try {
      const res = await api.triage(alertId, { language: locale });
      setFreshTriage(res.triage_summary);
      onOperationCompleted?.();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleInvestigate = async () => {
    setLoading(true);
    try {
      const res = await api.investigate(alertId, { language: locale });
      setFreshInvestigation(res);
      onOperationCompleted?.();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleRecommend = async () => {
    setLoading(true);
    try {
      const res = await api.recommend(alertId, { language: locale });
      setFreshRecommendation(res);
      if (onRecommendationLoaded) {
        onRecommendationLoaded(res);
      }
      onOperationCompleted?.();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  /** 用于标识该结果来自历史运行的小徽标 */
  const HistoryBadge = ({ createdAt }: { createdAt?: string }) => (
    <div className="flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-1 mb-3 w-fit">
      <History className="w-3 h-3" />
      <span>
        {t('existingResult')}
        {createdAt && ` · ${new Date(createdAt).toLocaleString()}`}
      </span>
    </div>
  );

  /** 展示在既有结果下方的重新运行按钮 */
  const RerunButton = ({ label, onClick }: { label: string; onClick: () => void }) => (
    <button
      onClick={onClick}
      className="mt-3 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
    >
      <RefreshCw className="w-3 h-3" />
      {label}
    </button>
  );

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div className="flex border-b border-gray-100">
        <button
          onClick={() => setActiveTab('triage')}
          className={`px-4 py-3 text-sm font-medium flex items-center gap-2 ${
            activeTab === 'triage' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Shield className="w-4 h-4" /> {t('triage')}
          {triageSummary && <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />}
        </button>
        <button
          onClick={() => setActiveTab('investigate')}
          className={`px-4 py-3 text-sm font-medium flex items-center gap-2 ${
            activeTab === 'investigate' ? 'text-purple-600 border-b-2 border-purple-600' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Search className="w-4 h-4" /> {t('investigate')}
          {investigation && <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />}
        </button>
        <button
          onClick={() => setActiveTab('recommend')}
          className={`px-4 py-3 text-sm font-medium flex items-center gap-2 ${
            activeTab === 'recommend' ? 'text-amber-600 border-b-2 border-amber-600' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Lightbulb className="w-4 h-4" /> {t('recommend')}
          {recommendation && <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />}
        </button>
      </div>

      <div className="p-4 min-h-[150px]">
        {loading && (
          <div className="flex justify-center items-center h-20 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> {t('processing')}
          </div>
        )}

        {/* ─── Triage Tab ─── */}
        {!loading && activeTab === 'triage' && (
          <div>
            {!triageSummary ? (
              <div className="text-center py-6">
                <p className="text-gray-500 mb-4">{t('triagePrompt')}</p>
                <button
                  onClick={handleTriage}
                  className="px-4 py-2 bg-blue-50 text-blue-600 rounded-md hover:bg-blue-100 text-sm font-medium"
                >
                  {t('startTriage')}
                </button>
              </div>
            ) : (
              <div>
                {triageFromHistory && <HistoryBadge />}
                <div className="prose prose-sm max-w-none text-gray-700 bg-gray-50 p-4 rounded-md">
                  {triageSummary}
                </div>
                <RerunButton label={t('rerunTriage')} onClick={handleTriage} />
              </div>
            )}
          </div>
        )}

        {/* ─── Investigate Tab ─── */}
        {!loading && activeTab === 'investigate' && (
          <div>
            {!investigation ? (
              <div className="text-center py-6">
                <p className="text-gray-500 mb-4">{t('investigatePrompt')}</p>
                <button
                  onClick={handleInvestigate}
                  className="px-4 py-2 bg-purple-50 text-purple-600 rounded-md hover:bg-purple-100 text-sm font-medium"
                >
                  {t('startInvestigation')}
                </button>
              </div>
            ) : (
              <div>
                {investigationFromHistory && <HistoryBadge createdAt={investigation.created_at} />}
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">{t('hypothesis')}</h4>
                    <p className="text-sm font-medium text-gray-900">{investigation.hypothesis}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">{t('why')}</h4>
                      <ul className="list-disc pl-4 text-sm text-gray-600">
                        {investigation.why.map((r, i) => <li key={i}>{r}</li>)}
                      </ul>
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">{t('nextSteps')}</h4>
                      <ul className="list-disc pl-4 text-sm text-gray-600">
                        {investigation.next_steps.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                  </div>
                  <div className="bg-yellow-50 text-yellow-800 text-xs p-2 rounded border border-yellow-200" title={tc('investigationConfidenceTooltip')}>
                    {tc('investigationConfidenceLabel')}: {(investigation.impact?.confidence ?? 0) * 100}%
                    <span className="block text-[10px] text-yellow-600 mt-0.5">{tc('disclaimer')}</span>
                  </div>
                  <ThreatContextCard threatContext={investigation.threat_context} />
                </div>
                <RerunButton label={t('rerunInvestigation')} onClick={handleInvestigate} />
              </div>
            )}
          </div>
        )}

        {/* ─── Recommend Tab ─── */}
        {!loading && activeTab === 'recommend' && (
          <div>
            {!recommendation ? (
              <div className="text-center py-6">
                 <p className="text-gray-500 mb-4">{t('recommendPrompt')}</p>
                <button
                  onClick={handleRecommend}
                  className="px-4 py-2 bg-amber-50 text-amber-600 rounded-md hover:bg-amber-100 text-sm font-medium"
                >
                  {t('loadRecommendations')}
                </button>
              </div>
            ) : (
              <div>
                {recommendationFromHistory && <HistoryBadge createdAt={recommendation.created_at} />}
                <div className="space-y-3">
                  {recommendation.actions.map((action, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 border border-gray-100 rounded-md bg-gray-50">
                      <div className="bg-white p-2 rounded shadow-sm">
                        <Lightbulb className="w-4 h-4 text-amber-500" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-gray-900">{action.title}</h4>
                        <p className="text-xs text-gray-500 mt-1">
                          {t('priorityLabel')} <span className="font-mono">{action.priority}</span>
                        </p>
                        {action.steps.length > 0 && (
                          <ul className="mt-1 text-xs text-gray-600 list-disc list-inside">
                            {action.steps.map((step: string, j: number) => (
                              <li key={j}>{step}</li>
                            ))}
                          </ul>
                        )}
                        <div className="mt-2 flex gap-2">
                          <span className="text-[10px] px-1.5 py-0.5 bg-red-100 text-red-700 rounded">{t('riskLabel')} {action.risk}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <ThreatContextCard threatContext={recommendation.threat_context} />
                <RerunButton label={t('rerunRecommendation')} onClick={handleRecommend} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

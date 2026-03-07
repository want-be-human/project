'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { Investigation, Recommendation } from '@/lib/api/types';
import { useTranslations, useLocale } from 'next-intl';
import { Play, Search, Shield, Lightbulb, Loader2 } from 'lucide-react';

interface AgentPanelProps {
  alertId: string;
  onRecommendationLoaded?: (rec: Recommendation) => void;
}

export default function AgentPanel({ alertId, onRecommendationLoaded }: AgentPanelProps) {
  const t = useTranslations('agent');
  const locale = useLocale();
  const [activeTab, setActiveTab] = useState<'triage' | 'investigate' | 'recommend'>('triage');
  
  const [triageSummary, setTriageSummary] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  
  const [loading, setLoading] = useState(false);

  const handleTriage = async () => {
    setLoading(true);
    try {
      const res = await api.triage(alertId, { language: locale });
      setTriageSummary(res.triage_summary);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleInvestigate = async () => {
    setLoading(true);
    try {
      const res = await api.investigate(alertId);
      setInvestigation(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleRecommend = async () => {
    setLoading(true);
    try {
      const res = await api.recommend(alertId);
      setRecommendation(res);
      if (onRecommendationLoaded) {
        onRecommendationLoaded(res);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

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
        </button>
        <button
          onClick={() => setActiveTab('investigate')}
          className={`px-4 py-3 text-sm font-medium flex items-center gap-2 ${
            activeTab === 'investigate' ? 'text-purple-600 border-b-2 border-purple-600' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Search className="w-4 h-4" /> {t('investigate')}
        </button>
        <button
          onClick={() => setActiveTab('recommend')}
          className={`px-4 py-3 text-sm font-medium flex items-center gap-2 ${
            activeTab === 'recommend' ? 'text-amber-600 border-b-2 border-amber-600' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Lightbulb className="w-4 h-4" /> {t('recommend')}
        </button>
      </div>

      <div className="p-4 min-h-[150px]">
        {loading && (
          <div className="flex justify-center items-center h-20 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> {t('processing')}
          </div>
        )}

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
              <div className="prose prose-sm max-w-none text-gray-700 bg-gray-50 p-4 rounded-md">
                {triageSummary}
              </div>
            )}
          </div>
        )}

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
                <div className="bg-yellow-50 text-yellow-800 text-xs p-2 rounded border border-yellow-200">
                  {t('confidence')} {(investigation.impact?.confidence ?? 0) * 100}%
                </div>
              </div>
            )}
          </div>
        )}

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
              <div className="space-y-3">
                {recommendation.actions.map((action, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 border border-gray-100 rounded-md bg-gray-50">
                    <div className="bg-white p-2 rounded shadow-sm">
                      <Lightbulb className="w-4 h-4 text-amber-500" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-gray-900">{action.title}</h4>
                      <p className="text-xs text-gray-500 mt-1">
                        {t('typeLabel')} <span className="font-mono">{action.type}</span> • 
                        {t('targetLabel')} <span className="font-mono">{JSON.stringify(action.target)}</span>
                      </p>
                      <div className="mt-2 flex gap-2">
                        <span className="text-[10px] px-1.5 py-0.5 bg-red-100 text-red-700 rounded">{t('riskLabel')} {action.risk}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

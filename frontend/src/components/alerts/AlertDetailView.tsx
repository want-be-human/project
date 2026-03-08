'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Alert, EvidenceChain, Recommendation, ActionPlan } from '@/lib/api/types';
import AlertEvidenceSection from '@/components/alerts/AlertEvidenceSection';
import EvidenceChainView from '@/components/evidence/EvidenceChainView';
import AgentPanel from '@/components/agent/AgentPanel';
import ActionBuilder from '@/components/twin/ActionBuilder';
import DryRunPanel from '@/components/twin/DryRunPanel';
import { ArrowLeft, Tag, Clock, ShieldAlert, Activity } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';
import { clsx } from 'clsx';

interface AlertDetailViewProps {
  alert: Alert;
  evidenceChain: EvidenceChain | null;
  onAlertUpdate: (alert: Alert) => void;
}

export default function AlertDetailView({ alert, evidenceChain, onAlertUpdate }: AlertDetailViewProps) {
  const t = useTranslations('alertDetail');
  const ta = useTranslations('alerts');
  const router = useRouter();
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [actionPlan, setActionPlan] = useState<ActionPlan | null>(null);

  const handleStatusChange = async (newStatus: string) => {
    const previousAlert = { ...alert };
    const updated = { ...alert, status: newStatus as Alert['status'] };
    onAlertUpdate(updated);

    try {
      await api.patchAlert(alert.id, { status: newStatus as Alert['status'] });
    } catch (e) {
      console.error("Failed to update status", e);
      onAlertUpdate(previousAlert);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-100 text-red-800 border-red-200';
      case 'high': return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'medium': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'low': return 'bg-blue-100 text-blue-800 border-blue-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  return (
    <div className="max-w-5xl mx-auto pb-12">
      <button 
        onClick={() => router.back()}
        className="flex items-center text-sm text-gray-500 hover:text-gray-900 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4 mr-1" />
        <span>{t('backToAlerts')}</span>
      </button>

      {/* Alert Header */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900 capitalize">{t('detected', { type: alert.type })}</h1>
              <span className={clsx("px-2.5 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full border", getSeverityColor(alert.severity))}>
                {alert.severity}
              </span>
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span className="flex items-center gap-1">
                <Clock className="w-4 h-4" />
                <span>{format(new Date(alert.created_at), 'yyyy-MM-dd HH:mm:ss')}</span>
              </span>
              <span className="flex items-center gap-1 group relative">
                <ShieldAlert className="w-4 h-4" />
                <span>ID:</span>
                <span className="font-mono text-xs cursor-help border-b border-dotted border-gray-400">
                  {alert.id.substring(0, 8)}...
                </span>
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-gray-900 text-white text-xs rounded py-1 px-2 whitespace-nowrap z-10">
                  {alert.id}
                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
                </div>
              </span>
            </div>
          </div>
          
          <div className="flex flex-col items-end gap-2">
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wider">{t('status')}</label>
            <select
              value={alert.status}
              onChange={(e) => handleStatusChange(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1.5 text-sm font-medium bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="new">{ta('new')}</option>
              <option value="triaged">{ta('triaged')}</option>
              <option value="investigating">{ta('investigating')}</option>
              <option value="resolved">{ta('resolved')}</option>
              <option value="false_positive">{ta('falsePositive')}</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6 pt-6 border-t border-gray-100">
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{t('source')}</h3>
            <div className="font-mono text-sm text-gray-900 bg-gray-50 p-2 rounded border border-gray-200">
              {alert.entities.primary_src_ip}
            </div>
          </div>
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{t('destination')}</h3>
            <div className="font-mono text-sm text-gray-900 bg-gray-50 p-2 rounded border border-gray-200">
              {alert.entities.primary_dst_ip || 'N/A'}
              {alert.entities.primary_service && ` : ${alert.entities.primary_service.dst_port} (${alert.entities.primary_service.proto})`}
            </div>
          </div>
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{t('tags')}</h3>
            <div className="flex flex-wrap gap-2">
              {alert.tags?.map(tag => (
                <span key={tag} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100">
                  <Tag className="w-3 h-3" />
                  <span>{tag}</span>
                </span>
              ))}
              {(!alert.tags || alert.tags.length === 0) && <span className="text-sm text-gray-400">{t('noTags')}</span>}
            </div>
          </div>
        </div>

        {/* Aggregation info (from DOC C) */}
        {alert.aggregation && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{t('aggregation')}</h3>
            <div className="flex gap-6 text-sm text-gray-600">
              <span>{t('rule')} <span className="font-mono text-xs">{alert.aggregation.rule}</span></span>
              <span>{t('group')} <span className="font-mono text-xs">{alert.aggregation.group_key}</span></span>
              <span>{t('flowCount')} <span className="font-semibold">{alert.aggregation.count_flows}</span></span>
            </div>
          </div>
        )}
      </div>

      {/* Evidence Section */}
      <AlertEvidenceSection alert={alert} />

      {/* Evidence Chain */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-600" />
            <span>{t('evidenceChain')}</span>
          </h2>
          <button 
            onClick={() => {
              const params = new URLSearchParams({ highlightAlertId: alert.id });
              if (alert.time_window?.start) params.set('start', alert.time_window.start);
              if (alert.time_window?.end) params.set('end', alert.time_window.end);
              router.push(`/topology?${params.toString()}`);
            }}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium px-3 py-1 bg-blue-50 rounded-full hover:bg-blue-100 transition-colors"
          >
            {t('viewIn3D')}
          </button>
        </div>
        
        {evidenceChain ? (
          <EvidenceChainView chain={evidenceChain} />
        ) : (
          <div className="text-center py-12 text-gray-500 bg-gray-50 rounded border border-dashed border-gray-300">
            {t('noEvidence')}
          </div>
        )}
      </div>

      {/* Agent + Remediation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-6">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-purple-600" />
            <span>{t('aiAnalyst')}</span>
          </h2>
          <AgentPanel alertId={alert.id} onRecommendationLoaded={setRecommendation} />
        </div>

        <div className="space-y-6">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <Activity className="w-5 h-5 text-indigo-600" />
            <span>{t('remediation')}</span>
          </h2>
          
          <ActionBuilder 
            alertId={alert.id} 
            initialRecommendation={recommendation} 
            onPlanCreated={setActionPlan}
          />
          
          {actionPlan && (
            <DryRunPanel alertId={alert.id} planId={actionPlan.id} />
          )}
        </div>
      </div>
    </div>
  );
}

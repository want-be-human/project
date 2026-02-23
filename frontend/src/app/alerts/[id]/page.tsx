'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Alert, EvidenceChain } from '@/lib/api/types';
import AlertEvidenceSection from '@/components/alerts/AlertEvidenceSection';
import EvidenceChainView from '@/components/evidence/EvidenceChainView';
import { ArrowLeft, Tag, Clock, ShieldAlert, Activity } from 'lucide-react';
import { format } from 'date-fns';
import { clsx } from 'clsx';

export default function AlertDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  
  const [alert, setAlert] = useState<Alert | null>(null);
  const [evidenceChain, setEvidenceChain] = useState<EvidenceChain | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [alertData, chainData] = await Promise.all([
          api.getAlert(id),
          api.getEvidenceChain(id)
        ]);
        setAlert(alertData);
        setEvidenceChain(chainData);
      } catch (e: any) {
        setError(e.message || 'Failed to load alert details');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const handleStatusChange = async (newStatus: string) => {
    if (!alert) return;
    
    // 立即更新本地状态 (Optimistic update)
    const previousAlert = { ...alert };
    setAlert({ ...alert, status: newStatus as any });
    
    try {
      await api.patchAlert(id, { status: newStatus as any });
    } catch (e) {
      console.error("Failed to update status", e);
      // 失败时回滚状态
      setAlert(previousAlert);
    }
  };

  if (loading) return <div className="p-12 text-center text-gray-500">Loading alert details...</div>;
  if (error || !alert) return <div className="p-12 text-center text-red-500">{error || 'Alert not found'}</div>;

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
        <ArrowLeft className="w-4 h-4 mr-1" /> Back to Alerts
      </button>

      {/* Alert Header */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900 capitalize">{alert.type} Detected</h1>
              <span className={clsx("px-2.5 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full border", getSeverityColor(alert.severity))}>
                {alert.severity}
              </span>
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> {format(new Date(alert.created_at), 'yyyy-MM-dd HH:mm:ss')}</span>
              <span className="flex items-center gap-1 group relative">
                <ShieldAlert className="w-4 h-4" /> ID: 
                <span className="font-mono text-xs cursor-help border-b border-dotted border-gray-400">
                  {alert.id.substring(0, 8)}...
                </span>
                {/* Tooltip */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-gray-900 text-white text-xs rounded py-1 px-2 whitespace-nowrap z-10">
                  {alert.id}
                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
                </div>
              </span>
            </div>
          </div>
          
          <div className="flex flex-col items-end gap-2">
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wider">Status</label>
            <select
              value={alert.status}
              onChange={(e) => handleStatusChange(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1.5 text-sm font-medium bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="new">New</option>
              <option value="triaged">Triaged</option>
              <option value="investigating">Investigating</option>
              <option value="resolved">Resolved</option>
              <option value="false_positive">False Positive</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6 pt-6 border-t border-gray-100">
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Source</h3>
            <div className="font-mono text-sm text-gray-900 bg-gray-50 p-2 rounded border border-gray-200">
              {alert.entities.primary_src_ip}
            </div>
          </div>
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Destination</h3>
            <div className="font-mono text-sm text-gray-900 bg-gray-50 p-2 rounded border border-gray-200">
              {alert.entities.primary_dst_ip || 'N/A'}
              {alert.entities.primary_service && ` : ${alert.entities.primary_service.dst_port} (${alert.entities.primary_service.proto})`}
            </div>
          </div>
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Tags</h3>
            <div className="flex flex-wrap gap-2">
              {alert.tags?.map(tag => (
                <span key={tag} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100">
                  <Tag className="w-3 h-3" /> {tag}
                </span>
              ))}
              {(!alert.tags || alert.tags.length === 0) && <span className="text-sm text-gray-400">No tags</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Evidence Section */}
      <AlertEvidenceSection alert={alert} />

      {/* Evidence Chain (Week 5) */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold text-gray-900">Evidence Chain</h2>
          <button 
            onClick={() => router.push(`/topology?highlightAlertId=${alert.id}`)}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            View in 3D Topology →
          </button>
        </div>
        {evidenceChain ? (
          <EvidenceChainView chain={evidenceChain} />
        ) : (
          <div className="text-center py-12 text-gray-500 bg-gray-50 rounded border border-dashed border-gray-300">
            No evidence chain available for this alert.
          </div>
        )}
      </div>

      {/* Placeholders for Week 7 */}
      <div className="bg-gray-50 rounded-lg border border-dashed border-gray-300 p-8 text-center text-gray-500">
        <ShieldAlert className="w-8 h-8 mx-auto mb-3 text-gray-400" />
        <h3 className="text-lg font-medium text-gray-900 mb-1">Agent Investigation & Dry-Run</h3>
        <p className="text-sm">Will be implemented in Week 7.</p>
      </div>

    </div>
  );
}

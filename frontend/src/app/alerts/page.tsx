'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { Alert } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import AlertFilterBar from '@/components/alerts/AlertFilterBar';
import AlertTable from '@/components/alerts/AlertTable';
import { wsClient } from '@/lib/ws';

export default function AlertsPage() {
  const t = useTranslations('alerts');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [filters, setFilters] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{message: string, type: 'info' | 'success'} | null>(null);

  const fetchAlerts = async () => {
    try {
      const data = await api.listAlerts({});
      setAlerts(data);
    } catch (e) {
      console.error("Failed to list alerts", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();

    // Subscribe to WS events
    const unsubscribeCreated = wsClient.onEvent('alert.created', (data) => {
      setToast({ message: t('toastCreated', { severity: data.severity }), type: 'info' });
      fetchAlerts(); // Refresh list
      setTimeout(() => setToast(null), 3000);
    });

    const unsubscribeUpdated = wsClient.onEvent('alert.updated', (data) => {
      setToast({ message: t('toastUpdated', { status: data.status }), type: 'success' });
      fetchAlerts(); // Refresh list
      setTimeout(() => setToast(null), 3000);
    });

    return () => {
      unsubscribeCreated();
      unsubscribeUpdated();
    };
  }, []);

  const handleFilterChange = useCallback((newFilters: any) => {
    setFilters(newFilters);
  }, []);

  const handleStatusChange = async (id: string, newStatus: string) => {
    try {
      // Optimistic update
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, status: newStatus as any } : a));
      
      await api.patchAlert(id, { status: newStatus as any });
    } catch (e) {
      console.error("Failed to update alert status", e);
      // Revert on failure
      fetchAlerts();
    }
  };

  // Derive filtered alerts
  const filteredAlerts = alerts.filter(a => {
    if (filters.status && a.status !== filters.status) return false;
    if (filters.severity && a.severity !== filters.severity) return false;
    if (filters.type && a.type !== filters.type) return false;
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-100px)] flex flex-col relative">
      {/* Toast Notification */}
      {toast && (
        <div className={`absolute top-0 right-0 m-4 p-4 rounded shadow-lg z-50 text-white transition-opacity ${toast.type === 'info' ? 'bg-blue-600' : 'bg-green-600'}`}>
          {toast.message}
        </div>
      )}

      <div className="flex justify-between items-center mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t('title')}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t('description')}
          </p>
        </div>
        <button 
          onClick={() => wsClient.simulateEvent('alert.created', { alert_id: 'test', severity: 'high' })}
          className="text-xs bg-gray-200 hover:bg-gray-300 px-3 py-1 rounded text-gray-700"
        >
          {t('simulateWs')}
        </button>
      </div>

      <div className="shrink-0">
        <AlertFilterBar onFilterChange={handleFilterChange} />
      </div>

      <div className="flex-grow overflow-hidden relative">
        {loading ? (
          <div className="text-center py-12 text-gray-500">{t('loading')}</div>
        ) : (
          <AlertTable 
            alerts={filteredAlerts} 
            onStatusChange={handleStatusChange}
          />
        )}
      </div>
    </div>
  );
}

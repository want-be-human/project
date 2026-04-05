'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { Alert, AlertListParams } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import AlertFilterBar from '@/components/alerts/AlertFilterBar';
import AlertTable from '@/components/alerts/AlertTable';
import Pagination from '@/components/shared/Pagination';
import { wsClient } from '@/lib/ws';
import { ALERT_CREATED, ALERT_UPDATED } from '@/lib/events';

export default function AlertsPage() {
  const t = useTranslations('alerts');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<AlertListParams>({});
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{message: string, type: 'info' | 'success'} | null>(null);

  // Use ref to access latest pagination/filter state in WebSocket callbacks
  const paramsRef = useRef({ filters, limit, offset });
  paramsRef.current = { filters, limit, offset };

  const fetchAlerts = useCallback(async (params: AlertListParams) => {
    setLoading(true);
    try {
      const result = await api.listAlerts(params);
      setAlerts(result.items);
      setTotal(result.total);
    } catch (e) {
      console.error("Failed to list alerts", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAlerts({ ...filters, limit, offset });
  }, [filters, limit, offset, fetchAlerts]);

  useEffect(() => {
    const unsubscribeCreated = wsClient.onEvent(ALERT_CREATED, (data) => {
      setToast({ message: t('toastCreated', { severity: data.severity }), type: 'info' });
      const { filters: f, limit: l, offset: o } = paramsRef.current;
      fetchAlerts({ ...f, limit: l, offset: o });
      setTimeout(() => setToast(null), 3000);
    });

    const unsubscribeUpdated = wsClient.onEvent(ALERT_UPDATED, (data) => {
      setToast({ message: t('toastUpdated', { status: data.status }), type: 'success' });
      const { filters: f, limit: l, offset: o } = paramsRef.current;
      fetchAlerts({ ...f, limit: l, offset: o });
      setTimeout(() => setToast(null), 3000);
    });

    return () => {
      unsubscribeCreated();
      unsubscribeUpdated();
    };
  }, [fetchAlerts, t]);

  const handleFilterChange = useCallback((newFilters: AlertListParams) => {
    setFilters(newFilters);
    setOffset(0);
  }, []);

  const handleStatusChange = async (id: string, newStatus: string) => {
    try {
      // 乐观更新
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, status: newStatus as any } : a));

      await api.patchAlert(id, { status: newStatus as any });
    } catch (e) {
      console.error("Failed to update alert status", e);
      // 失败时回滚
      fetchAlerts({ ...filters, limit, offset });
    }
  };

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-100px)] flex flex-col relative">
      {/* Toast 提示 */}
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
      </div>

      <div className="shrink-0">
        <AlertFilterBar onFilterChange={handleFilterChange} />
      </div>

      <div className="flex-grow overflow-hidden relative">
        {loading ? (
          <div className="text-center py-12 text-gray-500">{t('loading')}</div>
        ) : (
          <AlertTable
            alerts={alerts}
            onStatusChange={handleStatusChange}
          />
        )}
      </div>

      <Pagination
        total={total}
        limit={limit}
        offset={offset}
        onPageChange={setOffset}
        onPageSizeChange={(newLimit) => { setLimit(newLimit); setOffset(0); }}
      />
    </div>
  );
}

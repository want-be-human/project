'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Alert, EvidenceChain } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import AlertDetailView from '@/components/alerts/AlertDetailView';

export default function AlertDetailPage() {
  const t = useTranslations('alertDetail');
  const params = useParams();
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

  if (loading) return <div className="p-12 text-center text-gray-500">{t('loading')}</div>;
  if (error || !alert) return <div className="p-12 text-center text-red-500">{error || t('notFound')}</div>;

  return (
    <AlertDetailView 
      alert={alert} 
      evidenceChain={evidenceChain} 
      onAlertUpdate={setAlert} 
    />
  );
}

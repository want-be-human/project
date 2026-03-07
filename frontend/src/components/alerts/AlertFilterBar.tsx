import { useState } from 'react';
import { useTranslations } from 'next-intl';

interface AlertFilters {
  status?: string;
  severity?: string;
  type?: string;
}

interface AlertFilterBarProps {
  onFilterChange: (filters: AlertFilters) => void;
}

export default function AlertFilterBar({ onFilterChange }: AlertFilterBarProps) {
  const t = useTranslations('alerts');
  const [filters, setFilters] = useState<AlertFilters>({});

  const updateFilter = (key: keyof AlertFilters, value: string) => {
    const newFilters = {
      ...filters,
      [key]: value || undefined
    };
    setFilters(newFilters);
    onFilterChange(newFilters);
  };

  return (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 mb-4 flex gap-4 items-end flex-wrap">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('statusLabel')}</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('status', e.target.value)}
        >
          <option value="">All</option>
          <option value="new">{t('new')}</option>
          <option value="triaged">{t('triaged')}</option>
          <option value="investigating">{t('investigating')}</option>
          <option value="resolved">{t('resolved')}</option>
          <option value="false_positive">{t('falsePositive')}</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('severityLabel')}</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('severity', e.target.value)}
        >
          <option value="">All</option>
          <option value="low">{t('low')}</option>
          <option value="medium">{t('medium')}</option>
          <option value="high">{t('high')}</option>
          <option value="critical">{t('critical')}</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('typeLabel')}</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('type', e.target.value)}
        >
          <option value="">All</option>
          <option value="anomaly">{t('anomaly')}</option>
          <option value="scan">{t('scan')}</option>
          <option value="dos">{t('dos')}</option>
          <option value="bruteforce">{t('bruteforce')}</option>
          <option value="exfil">{t('exfil')}</option>
          <option value="unknown">{t('unknown')}</option>
        </select>
      </div>
      <div className="flex-grow"></div>
    </div>
  );
}

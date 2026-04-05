import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';

interface FlowFilters {
  src_ip?: string;
  dst_ip?: string;
  proto?: string;
  min_score?: string;
  pcap_id?: string;
  time_start?: string;
  time_end?: string;
}

interface FlowFilterBarProps {
  onFilterChange: (filters: FlowFilters) => void;
}

export default function FlowFilterBar({ onFilterChange }: FlowFilterBarProps) {
  const t = useTranslations('flows');
  const [filters, setFilters] = useState<FlowFilters>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const emitChange = useCallback((newFilters: FlowFilters) => {
    onFilterChange(newFilters);
  }, [onFilterChange]);

  const updateFilter = (key: keyof FlowFilters, value: string, debounce = false) => {
    const newFilters = {
      ...filters,
      [key]: value || undefined
    };
    setFilters(newFilters);

    if (debounce) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => emitChange(newFilters), 300);
    } else {
      emitChange(newFilters);
    }
  };

  return (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 mb-4 flex gap-4 items-end flex-wrap">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('pcapId')}</label>
        <input
          type="text"
          placeholder={t('pcapIdPlaceholder')}
          className="border border-gray-300 rounded px-3 py-2 text-sm w-44 focus:ring-blue-500 focus:border-blue-500 font-mono text-xs"
          onChange={(e) => updateFilter('pcap_id', e.target.value, true)}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('srcIp')}</label>
        <input
          type="text"
          placeholder={t('srcIpPlaceholder')}
          className="border border-gray-300 rounded px-3 py-2 text-sm w-40 focus:ring-blue-500 focus:border-blue-500"
          onChange={(e) => updateFilter('src_ip', e.target.value, true)}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('dstIp')}</label>
        <input
          type="text"
          placeholder={t('dstIpPlaceholder')}
          className="border border-gray-300 rounded px-3 py-2 text-sm w-40"
          onChange={(e) => updateFilter('dst_ip', e.target.value, true)}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('protocol')}</label>
        <select
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('proto', e.target.value)}
        >
          <option value="">{t('all')}</option>
          <option value="TCP">TCP</option>
          <option value="UDP">UDP</option>
          <option value="ICMP">ICMP</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('minScore')}</label>
        <input
          type="number"
          min="0"
          max="1"
          step="0.1"
          placeholder="0.0"
          className="border border-gray-300 rounded px-3 py-2 text-sm w-24"
          onChange={(e) => updateFilter('min_score', e.target.value)}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('startTime')}</label>
        <input
          type="datetime-local"
          className="border border-gray-300 rounded px-3 py-2 text-sm w-48"
          onChange={(e) => updateFilter('time_start', e.target.value)}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{t('endTime')}</label>
        <input
          type="datetime-local"
          className="border border-gray-300 rounded px-3 py-2 text-sm w-48"
          onChange={(e) => updateFilter('time_end', e.target.value)}
        />
      </div>
      <div className="flex-grow"></div>
    </div>
  );
}

export type { FlowFilters };

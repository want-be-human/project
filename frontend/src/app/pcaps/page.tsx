'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { PcapFile } from '@/lib/api/types';
import PcapUploadPanel from '@/components/pcaps/PcapUploadPanel';
import PcapListTable from '@/components/pcaps/PcapListTable';

export default function PcapsPage() {
  const [pcaps, setPcaps] = useState<PcapFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const fetchPcaps = async () => {
    try {
      const data = await api.listPcaps();
      setPcaps(data);
    } catch (e) {
      console.error("Failed to list pcaps", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPcaps();
  }, []);

  const handleProcess = async (id: string) => {
    setProcessingId(id);
    try {
      await api.processPcap(id, { mode: 'flows_and_detect' });
      // In real implementation, we'd rely on WS updates. 
      // For now, simple optimistic update or re-fetch
      fetchPcaps(); 
    } catch (e) {
      console.error(e);
      alert('Failed to start processing');
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">PCAP Management</h1>
          <p className="text-sm text-gray-500 mt-1">
            Upload traffic captures for analysis.
          </p>
        </div>
      </div>

      <PcapUploadPanel onUploadSuccess={fetchPcaps} />
      
      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : (
        <PcapListTable 
          pcaps={pcaps} 
          onProcess={handleProcess}
          processingId={processingId}
        />
      )}
    </div>
  );
}

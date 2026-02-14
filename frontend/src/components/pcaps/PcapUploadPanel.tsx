'use client';

import { useState } from 'react';
import { Upload, FileUp } from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils'; // Assuming you added this in previous step, else remove cn

export default function PcapUploadPanel({ onUploadSuccess }: { onUploadSuccess: () => void }) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setIsUploading(true);
    setError(null);
    try {
      await api.uploadPcap(file);
      onUploadSuccess();
    } catch (e: any) {
      setError(e.message || 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 mb-6">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <Upload className="w-5 h-5 text-blue-600" />
        Upload PCAP
      </h2>
      <div 
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
          isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400",
          isUploading && "opacity-50 pointer-events-none"
        )}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) handleFile(file);
        }}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="p-3 bg-gray-100 rounded-full">
            <FileUp className="w-6 h-6 text-gray-600" />
          </div>
          <div className="text-sm text-gray-600">
            <span className="font-semibold text-blue-600">Click to upload</span> or drag and drop
          </div>
          <p className="text-xs text-gray-500">PCAP/PCAPNG files (Max 100MB)</p>
          <input 
            type="file" 
            className="hidden" 
            id="file-upload"
            accept=".pcap,.pcapng,.cap"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
          <label 
            htmlFor="file-upload" 
            className="absolute inset-0 cursor-pointer" 
          />
        </div>
      </div>
      {error && (
        <div className="mt-3 text-sm text-red-600 bg-red-50 p-2 rounded">
          {error}
        </div>
      )}
      {isUploading && (
        <div className="mt-3 text-sm text-blue-600 text-center animate-pulse">
          Uploading...
        </div>
      )}
    </div>
  );
}

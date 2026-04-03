'use client';

import { useState, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Upload, FileUp, X } from 'lucide-react';

interface Props {
  onBatchCreated: (batchId: string) => void;
  onFilesSelected: (files: File[]) => void;
  selectedFiles: File[];
  onRemoveFile: (index: number) => void;
  isCreating: boolean;
  onCreateAndUpload: (name: string, source: string, tags: string[]) => void;
}

/** 创建批次 + 多文件拖拽选择面板 */
export default function BatchCreatePanel({
  onBatchCreated, onFilesSelected, selectedFiles, onRemoveFile,
  isCreating, onCreateAndUpload,
}: Props) {
  const t = useTranslations('batches');
  const [name, setName] = useState('');
  const [source, setSource] = useState('');
  const [tagsStr, setTagsStr] = useState('');
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(
      f => /\.(pcap|pcapng|cap)$/i.test(f.name)
    );
    if (files.length > 0) onFilesSelected(files);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) onFilesSelected(files);
    e.target.value = '';
  };

  const handleSubmit = () => {
    const tags = tagsStr.split(',').map(s => s.trim()).filter(Boolean);
    onCreateAndUpload(name, source, tags);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('createTitle')}</h2>

      {/* 批次信息 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('batchName')}</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder={t('batchNamePlaceholder')}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('source')}</label>
          <input
            type="text"
            value={source}
            onChange={e => setSource(e.target.value)}
            placeholder={t('sourcePlaceholder')}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('tags')}</label>
          <input
            type="text"
            value={tagsStr}
            onChange={e => setTagsStr(e.target.value)}
            placeholder={t('tagsPlaceholder')}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          />
        </div>
      </div>

      {/* 文件拖拽区 */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <Upload className="w-8 h-8 mx-auto mb-2 text-gray-400" />
        <p className="text-sm text-gray-600">{t('dragAndDrop')}</p>
        <p className="text-xs text-gray-400 mt-1">{t('orClick')} · {t('fileTypes')}</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pcap,.pcapng,.cap"
          onChange={handleFileInput}
          className="hidden"
        />
      </div>

      {/* 已选文件列表 */}
      {selectedFiles.length > 0 && (
        <div className="mt-4">
          <div className="text-sm font-medium text-gray-700 mb-2">
            {t('selectFiles')} ({selectedFiles.length})
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {selectedFiles.map((file, i) => (
              <div key={i} className="flex items-center justify-between bg-gray-50 rounded px-3 py-2 text-sm">
                <div className="flex items-center gap-2">
                  <FileUp className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-700">{file.name}</span>
                  <span className="text-gray-400">{formatSize(file.size)}</span>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); onRemoveFile(i); }}
                  className="text-gray-400 hover:text-red-500"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 提交按钮 */}
      {selectedFiles.length > 0 && (
        <div className="mt-4 flex justify-end">
          <button
            onClick={handleSubmit}
            disabled={isCreating}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
          >
            {isCreating ? t('creating') : `${t('create')} & ${t('upload')}`}
          </button>
        </div>
      )}
    </div>
  );
}

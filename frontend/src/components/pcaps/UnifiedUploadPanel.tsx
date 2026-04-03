'use client';

import { useState, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Upload, FileUp, X, Loader2 } from 'lucide-react';

/**
 * 统一上传面板。
 *
 * 所有上传（包括单文件）均走 Batch API 路径。
 * 用户选择文件后，填写可选元数据，点击提交。
 * 文件和元数据通过 onSubmit 回调传给父组件。
 */

interface UnifiedUploadPanelProps {
  /** 是否正在上传/创建中 */
  isUploading: boolean;
  /** 上传错误信息 */
  uploadError: string | null;
  /** 统一提交回调，files 始终由面板传给父组件 */
  onSubmit: (files: File[], name: string, source: string, tags: string[]) => Promise<void>;
  /** 上传完成后的回调 */
  onUploadComplete?: () => void;
}

export default function UnifiedUploadPanel({
  isUploading,
  uploadError,
  onSubmit,
  onUploadComplete,
}: UnifiedUploadPanelProps) {
  const t = useTranslations('pcaps');

  // ── 暂存文件队列 ──
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── 批次元数据（多文件时显示） ──
  const [batchName, setBatchName] = useState('');
  const [batchSource, setBatchSource] = useState('');
  const [batchTags, setBatchTags] = useState('');

  // ── 文件操作 ──
  const addFiles = useCallback((files: File[]) => {
    const valid = files.filter(f => /\.(pcap|pcapng|cap)$/i.test(f.name));
    if (valid.length > 0) {
      setStagedFiles(prev => [...prev, ...valid]);
    }
  }, []);

  const removeFile = useCallback((index: number) => {
    setStagedFiles(prev => prev.filter((_, i) => i !== index));
  }, []);

  const clearFiles = useCallback(() => {
    setStagedFiles([]);
    setBatchName('');
    setBatchSource('');
    setBatchTags('');
  }, []);

  // ── 拖拽处理 ──
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
  }, [addFiles]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    addFiles(files);
    e.target.value = '';
  }, [addFiles]);

  // ── 提交：把文件 + 元数据一起传给父组件 ──
  const handleSubmit = async () => {
    if (stagedFiles.length === 0 || isUploading) return;

    try {
      const tags = batchTags.split(',').map(s => s.trim()).filter(Boolean);
      await onSubmit(stagedFiles, batchName, batchSource, tags);
      clearFiles();
      onUploadComplete?.();
    } catch {
      // 错误由 uploadError prop 展示
    }
  };

  // ── 格式化 ──
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      {/* 拖拽/选择区 */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
          dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        } ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <Upload className="w-8 h-8 mx-auto mb-2 text-gray-400" />
        <p className="text-sm text-gray-600">
          {stagedFiles.length > 1 ? t('multiFileHint') : t('singleFileHint')}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {t('fileTypes')}
        </p>
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
      {stagedFiles.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700">
              {t('stagedFilesCount', { count: stagedFiles.length })}
            </span>
            <button
              onClick={clearFiles}
              disabled={isUploading}
              className="text-xs text-gray-500 hover:text-red-600 disabled:opacity-50"
            >
              {t('clearQueue')}
            </button>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {stagedFiles.map((file, i) => (
              <div key={`${file.name}-${i}`} className="flex items-center justify-between bg-gray-50 rounded px-3 py-2 text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <FileUp className="w-4 h-4 text-gray-400 shrink-0" />
                  <span className="text-gray-700 truncate">{file.name}</span>
                  <span className="text-gray-400 shrink-0">{formatSize(file.size)}</span>
                </div>
                <button
                  onClick={() => removeFile(i)}
                  disabled={isUploading}
                  className="text-gray-400 hover:text-red-500 disabled:opacity-50 shrink-0 ml-2"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 批次元数据（多文件时显示） */}
      {stagedFiles.length > 1 && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">{t('batchName')}</label>
            <input
              type="text"
              value={batchName}
              onChange={e => setBatchName(e.target.value)}
              placeholder={t('batchNamePlaceholder')}
              disabled={isUploading}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">{t('batchSource')}</label>
            <input
              type="text"
              value={batchSource}
              onChange={e => setBatchSource(e.target.value)}
              placeholder={t('batchSourcePlaceholder')}
              disabled={isUploading}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">{t('batchTags')}</label>
            <input
              type="text"
              value={batchTags}
              onChange={e => setBatchTags(e.target.value)}
              placeholder={t('batchTagsPlaceholder')}
              disabled={isUploading}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm disabled:opacity-50"
            />
          </div>
        </div>
      )}

      {/* 提交按钮 */}
      {stagedFiles.length > 0 && (
        <div className="mt-4 flex justify-end">
          <button
            onClick={handleSubmit}
            disabled={isUploading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
          >
            {isUploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {t('uploading')}
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                {stagedFiles.length > 1 ? t('createBatchAndUpload') : t('uploadAndProcess')}
              </>
            )}
          </button>
        </div>
      )}

      {/* 错误 */}
      {uploadError && (
        <div className="mt-3 text-sm text-red-600 bg-red-50 p-2 rounded">
          {uploadError}
        </div>
      )}
    </div>
  );
}

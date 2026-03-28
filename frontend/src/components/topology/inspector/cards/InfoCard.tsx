'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

/** 可折叠信息卡片容器 */
interface InfoCardProps {
  title: string;
  icon?: React.ReactNode;
  defaultCollapsed?: boolean;
  children: React.ReactNode;
}

export default function InfoCard({ title, icon, defaultCollapsed = false, children }: InfoCardProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      {/* 卡片头部 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        {icon && <span className="text-gray-500 shrink-0">{icon}</span>}
        <span className="text-xs font-semibold text-gray-700 flex-grow">{title}</span>
        {collapsed
          ? <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
          : <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" />}
      </button>
      {/* 卡片内容 */}
      {!collapsed && (
        <div className="px-3 py-2.5 space-y-2">
          {children}
        </div>
      )}
    </div>
  );
}

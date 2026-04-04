'use client';

import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  /** 空状态提示文案 */
  message: string;
  /** 自定义图标，默认为 Inbox */
  icon?: React.ReactNode;
}

/**
 * 统一空状态占位组件
 * 用于图表或卡片无数据时的内容区占位
 * flex-1 确保在父容器（DashboardCard）中撑满剩余高度，防止卡片塌缩
 */
export default function EmptyState({ message, icon }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-2 text-gray-500">
      {icon ?? <Inbox className="w-8 h-8 opacity-40" />}
      <p className="text-sm">{message}</p>
    </div>
  );
}

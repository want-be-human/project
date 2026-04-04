'use client';

import { cn } from '@/lib/utils';

interface DashboardCardProps {
  /** 卡片标题 */
  title?: string;
  /** 标题栏右侧内容插槽（如时间范围按钮、徽章等） */
  headerRight?: React.ReactNode;
  /** 卡片主体内容 */
  children: React.ReactNode;
  /** 额外的 className，可用于覆盖默认 padding 等 */
  className?: string;
}

/**
 * 仪表盘通用卡片容器
 * 统一深色主题样式：圆角、边框、背景模糊、悬停高亮
 * 所有图表和动态组件共享此容器，避免样式散落重复
 */
export default function DashboardCard({
  title,
  headerRight,
  children,
  className,
}: DashboardCardProps) {
  return (
    <div
      className={cn(
        'bg-gray-900/80 border border-gray-700/50 hover:border-cyan-500/40 transition-colors rounded-2xl p-4 backdrop-blur-sm h-full flex flex-col',
        className,
      )}
    >
      {/* 标题行：仅在有 title 或 headerRight 时渲染 */}
      {(title || headerRight) && (
        <div className="flex items-center justify-between mb-3">
          {title && (
            <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          )}
          {headerRight}
        </div>
      )}
      {children}
    </div>
  );
}

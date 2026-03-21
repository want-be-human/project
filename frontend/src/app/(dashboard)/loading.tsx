/**
 * Dashboard 骨架屏占位组件
 * Next.js 自动在页面数据加载期间展示此组件
 * 模拟最终页面的五层布局结构，使用 animate-pulse 表示加载中状态
 * 需求: 6.1, 6.2, 6.3, 6.4
 */
export default function DashboardLoading() {
  return (
    <div className="relative min-h-screen bg-gray-950">
      {/* 网格背景层（与真实页面一致） */}
      <div className="grid-background" aria-hidden="true" />
      {/* 主内容骨架区域 */}
      <div className="relative z-10 flex flex-col gap-6 px-6 pt-6 pb-8">
        {/* A 层：Hero 骨架 */}
        <div className="bg-gray-900/80 border border-gray-700/50 rounded-2xl p-5 animate-pulse">
          {/* 标题占位 */}
          <div className="h-7 w-40 bg-gray-700/50 rounded mb-4" />
          {/* 三栏布局占位 */}
          <div className="flex flex-col lg:flex-row lg:items-center gap-6">
            {/* 左侧信息块 */}
            <div className="flex-1 space-y-3">
              <div className="bg-gray-800/60 rounded-lg px-3 py-2 h-[52px]" />
              <div className="bg-gray-800/60 rounded-lg px-3 py-2 h-[52px]" />
            </div>
            {/* 中间环形图占位 */}
            <div className="flex flex-col items-center gap-2 shrink-0">
              <div className="h-3 w-16 bg-gray-700/50 rounded" />
              <div className="w-40 h-40 rounded-full border-8 border-gray-700/30" />
            </div>
            {/* 右侧信息块 */}
            <div className="flex-1 space-y-3">
              <div className="bg-gray-800/60 rounded-lg px-3 py-2 h-[52px]" />
              <div className="bg-gray-800/60 rounded-lg px-3 py-2 h-[52px]" />
            </div>
          </div>
        </div>

        {/* B 层：六张指标卡片骨架 */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="bg-gray-900/80 border border-gray-700/50 rounded-2xl p-4 h-[120px] animate-pulse"
            >
              <div className="h-3 w-20 bg-gray-700/50 rounded mb-3" />
              <div className="h-6 w-16 bg-gray-700/50 rounded mb-2" />
              <div className="h-2 w-24 bg-gray-700/50 rounded" />
            </div>
          ))}
        </div>

        {/* C 层：图表区域骨架 */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch min-h-[500px]">
          {/* 左侧告警趋势图 */}
          <div className="lg:col-span-2 bg-gray-900/80 border border-gray-700/50 rounded-2xl animate-pulse" />
          {/* 右侧分布图 + 流水线图 */}
          <div className="flex flex-col gap-6">
            <div className="flex-1 bg-gray-900/80 border border-gray-700/50 rounded-2xl animate-pulse" />
            <div className="flex-1 bg-gray-900/80 border border-gray-700/50 rounded-2xl animate-pulse" />
          </div>
        </div>

        {/* D 层：拓扑 + 活动流骨架 */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
          <div className="lg:col-span-2 bg-gray-900/80 border border-gray-700/50 rounded-2xl h-[480px] animate-pulse" />
          <div className="bg-gray-900/80 border border-gray-700/50 rounded-2xl h-[480px] animate-pulse" />
        </section>
      </div>
    </div>
  );
}

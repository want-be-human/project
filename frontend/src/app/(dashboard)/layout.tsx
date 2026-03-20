import DashboardNav from '@/components/layout/DashboardNav';

/**
 * Dashboard 独立深色布局
 * 不包含 TopBar，不使用白色背景，不添加 p-6 内边距
 * 使用深色全屏容器，包含浮动导航按钮确保用户可导航到其他页面
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* 浮动导航按钮：左上角，点击展开导航菜单 */}
      <DashboardNav />
      {children}
    </div>
  );
}

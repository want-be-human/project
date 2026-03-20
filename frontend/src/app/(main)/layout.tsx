import SideNav from '@/components/layout/SideNav';
import TopBar from '@/components/layout/TopBar';

/**
 * 内页共享布局：包含侧边导航 + 顶部工作区栏
 * 适用于 pcaps、flows、alerts、topology、scenarios 等业务页面
 * Dashboard 首页不使用此布局
 */
export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 text-gray-900">
      <SideNav />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}

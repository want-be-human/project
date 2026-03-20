import SideNav from '@/components/layout/SideNav';
import TopBar from '@/components/layout/TopBar';

/**
 * (main) route group 的共享布局
 * 承载 SideNav + TopBar 壳，服务于 alerts、flows、pcaps、scenarios、topology 等子页面
 */
export default function MainLayout({ children }: { children: React.ReactNode }) {
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

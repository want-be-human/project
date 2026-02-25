import type { Metadata } from 'next';
import './globals.css';
import SideNav from '@/components/layout/SideNav';
import TopBar from '@/components/layout/TopBar';

export const metadata: Metadata = {
  title: 'NetTwin SOC',
  description: 'Network Digital Twin SOC Interface',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex h-screen overflow-hidden bg-gray-50 text-gray-900" suppressHydrationWarning>
        <SideNav />
        <div className="flex-1 flex flex-col overflow-hidden">
          <TopBar />
          <main className="flex-1 overflow-auto p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

import type { Metadata } from 'next';
import './globals.css';
import SideNav from '@/components/layout/SideNav';
import TopBar from '@/components/layout/TopBar';
import WSProvider from '@/components/providers/WSProvider';

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
        <WSProvider>
          <SideNav />
          <div className="flex-1 flex flex-col overflow-hidden">
            <TopBar />
            <main className="flex-1 overflow-auto p-6">
              {children}
            </main>
          </div>
        </WSProvider>
      </body>
    </html>
  );
}

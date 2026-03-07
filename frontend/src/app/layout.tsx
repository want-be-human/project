import type { Metadata } from 'next';
import './globals.css';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import SideNav from '@/components/layout/SideNav';
import TopBar from '@/components/layout/TopBar';
import WSProvider from '@/components/providers/WSProvider';

export const metadata: Metadata = {
  title: 'NetTwin SOC',
  description: 'Network Digital Twin SOC Interface',
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="flex h-screen overflow-hidden bg-gray-50 text-gray-900" suppressHydrationWarning>
        <NextIntlClientProvider messages={messages}>
          <WSProvider>
            <SideNav />
            <div className="flex-1 flex flex-col overflow-hidden">
              <TopBar />
              <main className="flex-1 overflow-auto p-6">
                {children}
              </main>
            </div>
          </WSProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

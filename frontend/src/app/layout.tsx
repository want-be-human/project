import type { Metadata } from 'next';
import './globals.css';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import WSProvider from '@/components/providers/WSProvider';

export const metadata: Metadata = {
  title: 'NetTwin SOC',
  description: 'Network Digital Twin SOC Interface',
};

// 根布局仅保留全局 Provider，SideNav 和 TopBar 已移至 (main) route group 的 layout 中
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <body suppressHydrationWarning>
        <NextIntlClientProvider messages={messages}>
          <WSProvider>
            {children}
          </WSProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

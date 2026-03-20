import type { Metadata } from 'next';
import './globals.css';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import WSProvider from '@/components/providers/WSProvider';

export const metadata: Metadata = {
  title: 'NetTwin SOC',
  description: 'Network Digital Twin SOC Interface',
};

/**
 * 根布局：仅提供全局 Provider（i18n、WebSocket）
 * 不包含 SideNav / TopBar，由子布局按需添加
 */
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="h-screen overflow-hidden bg-gray-950 text-gray-900" suppressHydrationWarning>
        <NextIntlClientProvider messages={messages}>
          <WSProvider>
            {children}
          </WSProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

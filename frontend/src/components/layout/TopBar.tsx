'use client';

import { useTranslations } from 'next-intl';
import LanguageSwitcher from '@/components/layout/LanguageSwitcher';

export default function TopBar() {
  const t = useTranslations('topbar');
  const tc = useTranslations('common');
  const mode = process.env.NEXT_PUBLIC_API_MODE || 'mock';

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
      <div className="font-semibold text-gray-700">
        {t('workspace')}
      </div>
      <div className="flex items-center gap-3">
        <span className={`px-2 py-1 rounded text-xs font-mono uppercase ${mode === 'real' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
          {tc('mode', { mode })}
        </span>
        <LanguageSwitcher />
      </div>
    </header>
  );
}

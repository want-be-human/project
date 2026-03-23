'use client';

import { useTranslations } from 'next-intl';
import LanguageSwitcher from '@/components/layout/LanguageSwitcher';

export default function TopBar() {
  const t = useTranslations('topbar');

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
      <div className="font-semibold text-gray-700">
        {t('workspace')}
      </div>
      <div className="flex items-center gap-3">
        <LanguageSwitcher />
      </div>
    </header>
  );
}

'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

/**
 * 浮动导航按钮组件
 * 在 Dashboard 全屏深色布局中提供导航入口，点击展开导航菜单
 */

const navItems = [
  { href: '/alerts', labelKey: 'alerts' as const },
  { href: '/flows', labelKey: 'flows' as const },
  { href: '/pcaps', labelKey: 'pcaps' as const },
  { href: '/scenarios', labelKey: 'scenarios' as const },
  { href: '/topology', labelKey: 'topology' as const },
];

export default function DashboardNav() {
  const [open, setOpen] = useState(false);
  const t = useTranslations('nav');

  return (
    <div className="fixed top-4 left-4 z-50">
      {/* 汉堡菜单按钮 */}
      <button
        onClick={() => setOpen(!open)}
        className="w-10 h-10 flex items-center justify-center rounded-lg bg-gray-800/80 backdrop-blur border border-gray-700/50 text-gray-300 hover:text-white hover:bg-gray-700/80 transition-colors"
        aria-label={open ? '关闭导航' : '打开导航'}
      >
        {open ? (
          /* 关闭图标 */
          <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          /* 汉堡图标 */
          <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        )}
      </button>

      {/* 展开的导航菜单 */}
      {open && (
        <nav className="mt-2 w-48 rounded-lg bg-gray-800/90 backdrop-blur border border-gray-700/50 shadow-xl overflow-hidden">
          <ul className="py-1">
            {navItems.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="block px-4 py-2 text-sm text-gray-300 hover:text-white hover:bg-gray-700/60 transition-colors"
                  onClick={() => setOpen(false)}
                >
                  {t(item.labelKey)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  );
}

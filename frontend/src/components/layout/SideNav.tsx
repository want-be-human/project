import Link from 'next/link';
import { getTranslations } from 'next-intl/server';

const navItems = [
  { href: '/', labelKey: 'dashboard' as const },
  { href: '/pcaps', labelKey: 'pcaps' as const },
  { href: '/flows', labelKey: 'flows' as const },
  { href: '/alerts', labelKey: 'alerts' as const },
  { href: '/topology', labelKey: 'topology' as const },
  { href: '/scenarios', labelKey: 'scenarios' as const },
];

export default async function SideNav() {
  const t = await getTranslations('nav');

  return (
    <nav className="w-64 bg-gray-900 text-white flex-shrink-0 min-h-screen p-4">
      <div className="mb-8 p-2">
        <h1 className="text-xl font-bold">{t('title')}</h1>
      </div>
      <ul className="space-y-2">
        {navItems.map((item) => (
          <li key={item.href}>
            <Link 
              href={item.href} 
              className="block p-2 rounded hover:bg-gray-800 transition-colors"
            >
              {t(item.labelKey)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

import Link from 'next/link';
import { getTranslations } from 'next-intl/server';

export default async function DashboardPage() {
  const t = await getTranslations('dashboard');

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t('title')}</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Link href="/pcaps" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">{t('pcapsTitle')}</h2>
          <p className="text-gray-600">{t('pcapsDesc')}</p>
        </Link>
        <Link href="/alerts" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">{t('alertsTitle')}</h2>
          <p className="text-gray-600">{t('alertsDesc')}</p>
        </Link>
        <Link href="/topology" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">{t('topologyTitle')}</h2>
          <p className="text-gray-600">{t('topologyDesc')}</p>
        </Link>
        <Link href="/scenarios" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">{t('scenariosTitle')}</h2>
          <p className="text-gray-600">{t('scenariosDesc')}</p>
        </Link>
      </div>
    </div>
  );
}

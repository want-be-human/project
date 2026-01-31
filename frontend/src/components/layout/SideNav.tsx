import Link from 'next/link';

const navItems = [
  { href: '/', label: 'Dashboard' },
  { href: '/pcaps', label: 'PCAPs' },
  { href: '/flows', label: 'Flows' },
  { href: '/alerts', label: 'Alerts' },
  { href: '/topology', label: 'Topology' },
  { href: '/scenarios', label: 'Scenarios' },
];

export default function SideNav() {
  return (
    <nav className="w-64 bg-gray-900 text-white flex-shrink-0 min-h-screen p-4">
      <div className="mb-8 p-2">
        <h1 className="text-xl font-bold">NetTwin SOC</h1>
      </div>
      <ul className="space-y-2">
        {navItems.map((item) => (
          <li key={item.href}>
            <Link 
              href={item.href} 
              className="block p-2 rounded hover:bg-gray-800 transition-colors"
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

import Link from 'next/link';

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Link href="/pcaps" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">PCAPs</h2>
          <p className="text-gray-600">Upload and process PCAP files</p>
        </Link>
        <Link href="/alerts" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">Alerts</h2>
          <p className="text-gray-600">View and triage alerts</p>
        </Link>
        <Link href="/topology" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">Topology</h2>
          <p className="text-gray-600">3D Network Twin</p>
        </Link>
        <Link href="/scenarios" className="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
          <h2 className="text-lg font-semibold mb-2">Scenarios</h2>
          <p className="text-gray-600">Run security scenarios</p>
        </Link>
      </div>
    </div>
  );
}

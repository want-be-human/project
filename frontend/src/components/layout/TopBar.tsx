export default function TopBar() {
  const mode = process.env.NEXT_PUBLIC_API_MODE || 'mock';

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
      <div className="font-semibold text-gray-700">
        Workspace
      </div>
      <div>
        <span className={`px-2 py-1 rounded text-xs font-mono uppercase ${mode === 'real' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
          {mode} mode
        </span>
      </div>
    </header>
  );
}

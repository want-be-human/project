# Frontend for NetTwin SOC

## Development

1. Install dependencies:
   `ash
   npm install
   ``n
2. Run dev server:
   `ash
   npm run dev
   ``n
3. Open [http://localhost:3000](http://localhost:3000).

## Mock Mode vs Real Mode

To switch between Mock (standalone) and Real (backend connected) modes, set the NEXT_PUBLIC_API_MODE environment variable.

- **Mock Mode** (default):
  `ash
  NEXT_PUBLIC_API_MODE=mock npm run dev
  ``n  In this mode, the app reads data from ../../contract/samples/*.json.

- **Real Mode**:
  `ash
  NEXT_PUBLIC_API_MODE=real NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
  ``n  In this mode, the app proxies requests to the backend.

## Structure

- src/app: Routes (Next.js App Router)
- src/components: UI Components
- src/lib/api: API Client layer (Mock/Real switch)

# NetTwin-SOC Infrastructure

Docker Compose and deployment configuration.

## Quick Start

```bash
# Start all services (development hot reload enabled by docker-compose.override.yml)
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

## Auto Reload In Docker (Dev)

This folder includes `docker-compose.override.yml` for development.

- Backend: mounts `../backend/app` and runs `uvicorn --reload`
- Frontend: mounts `../frontend` and runs `next dev`
- Frontend API URL uses `http://localhost:8000` (browser-accessible host), not `http://backend:8000`

After any code change, containers pick it up automatically.

```bash
# Recreate once after compose changes
docker compose up -d --build

# Follow logs to confirm hot reload is running
docker compose logs -f backend frontend
```

If you need production-like behavior without auto reload, run only the base file:

```bash
docker compose -f docker-compose.yml up -d --build
```

## Services

- **backend**: FastAPI application on port 8000
- **frontend**: Next.js application on port 3000 (placeholder)
- **db**: PostgreSQL database on port 5432 (optional)

## Environment Variables

Copy `env.example` to `.env` and configure:

```bash
cp env.example .env
```

## Development vs Production

For development, SQLite is used by default. For production, enable PostgreSQL by uncommenting the `db` service in docker-compose.yml.

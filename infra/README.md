# NetTwin-SOC Infrastructure

Docker Compose and deployment configuration.

## Quick Start

```bash
# Start all services with hot reload
docker compose -f infra/docker-compose.yml up -d --build

# View logs
docker compose -f infra/docker-compose.yml logs -f

# Stop services
docker compose -f infra/docker-compose.yml down
```

## Single Docker Config

`infra/docker-compose.yml` is the only Compose file you need for local development.

- Backend mounts source code and runs `uvicorn --reload`
- Frontend mounts source code and runs `next dev --webpack`
- Frontend uses polling-friendly file watching for Docker Desktop/Windows bind mounts
- Frontend API URL defaults to `http://localhost:8000` so browser requests reach the backend correctly

After any code change, containers pick it up automatically.

```bash
# Recreate once after compose changes
docker compose -f infra/docker-compose.yml up -d --build

# Follow logs to confirm hot reload is running
docker compose -f infra/docker-compose.yml logs -f backend frontend
```

## Services

- **backend**: FastAPI application on port 8000
- **frontend**: Next.js application on port 3000 with Fast Refresh
- **db**: PostgreSQL database on port 5432 (optional)

## Environment Variables

Copy `env.example` to `.env` and configure:

```bash
cp env.example .env
```

## Development vs Production

For development, SQLite is used by default. If you later need production-specific container settings, add them in a separate deployment location instead of changing this development compose file.

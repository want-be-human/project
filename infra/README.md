# NetTwin-SOC Infrastructure

Docker Compose and deployment configuration.

## Quick Start

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
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

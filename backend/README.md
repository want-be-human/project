# NetTwin-SOC Backend

Network Traffic Analysis & Digital Twin Security Platform - Backend Service

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running

```bash
# Development mode
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
# Build
docker build -t nettwin-backend .

# Run
docker run -p 8000:8000 -v $(pwd)/data:/app/data nettwin-backend
```

## API Documentation

Once running, access:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints (Week 1)

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```
Response:
```json
{"ok": true, "data": {"status": "ok"}, "error": null}
```

### Upload PCAP
```bash
curl -X POST http://localhost:8000/api/v1/pcaps/upload \
  -F "file=@capture.pcap"
```

### List PCAPs
```bash
curl http://localhost:8000/api/v1/pcaps
```

### Get PCAP Status
```bash
curl http://localhost:8000/api/v1/pcaps/{pcap_id}/status
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/nettwin.db` | Database connection string |
| `DATA_DIR` | `./data` | Data storage directory |
| `DEBUG` | `false` | Enable debug mode |
| `MODEL_PARAMS` | `{}` | JSON string for detection model parameters |

## Directory Structure

```
backend/
├── app/
│   ├── main.py           # FastAPI application entry
│   ├── api/
│   │   ├── deps.py       # Dependencies (DB session)
│   │   └── routers/      # API route handlers
│   ├── core/
│   │   ├── config.py     # Configuration
│   │   ├── errors.py     # Error handling
│   │   ├── logging.py    # Logging setup
│   │   └── utils.py      # Utilities
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic schemas (DOC C compliant)
│   ├── services/         # Business logic
│   └── tests/            # Unit & integration tests
├── scripts/
│   └── seed_samples.py   # Generate contract samples
├── Dockerfile
├── pyproject.toml
└── requirements.txt
```

## Contract Compliance

All API responses strictly follow DOC C v1.1 schema definitions.
See `../contract/samples/` for example payloads.

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
| `PIPELINE_OBSERVABILITY_ENABLED` | `true` | Enable pipeline stage tracking |
| `STRUCTURED_LOG_ENABLED` | `false` | Enable JSON-line structured logging |
| `WORKFLOW_ENGINE_ENABLED` | `true` | Enable workflow engine for agent stages |
| `THREAT_ENRICHMENT_ENABLED` | `true` | Enable MITRE threat enrichment |

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

## Pipeline Observability

The backend tracks PCAP processing through 9 defined pipeline stages:

| # | Stage | Trigger | Description |
|---|-------|---------|-------------|
| 1 | `parse` | PCAP upload | Parse PCAP into network flows |
| 2 | `feature_extract` | PCAP upload | Extract 20+ features per flow |
| 3 | `detect` | PCAP upload | IsolationForest anomaly scoring |
| 4 | `aggregate` | PCAP upload | Group flows into alerts |
| 5 | `investigate` | User request | Agent triage & investigation |
| 6 | `recommend` | User request | Agent recommendation |
| 7 | `compile_plan` | User request | Compile action plan for Twin |
| 8 | `dry_run` | User request | Twin simulation |
| 9 | `visualize` | User request | Topology/evidence graph |

Each stage records: `status`, `latency_ms`, `started_at`, `completed_at`, `key_metrics`, `error_summary`, `input_summary`, `output_summary`.

### API Endpoints

```bash
# Get pipeline run for a PCAP
curl http://localhost:8000/api/v1/pipeline/{pcap_id}

# Get stage details
curl http://localhost:8000/api/v1/pipeline/{pcap_id}/stages
```

### Feature Flags

- `PIPELINE_OBSERVABILITY_ENABLED=false` — Disables pipeline tracking (PCAP processing continues normally)
- `STRUCTURED_LOG_ENABLED=true` — Switches to JSON-line log format with run_id/stage/latency fields

## Testing

```bash
# All tests
pytest app/tests/

# Unit tests only
pytest app/tests/unit/

# Regression tests (fixed PCAP fixtures)
pytest app/tests/regression/

# Integration/E2E tests
pytest app/tests/integration/

# Run with verbose output
pytest -v app/tests/
```

### Regression Test Fixtures

Fixed PCAP fixtures in `app/tests/fixtures/`:
- `regression_ssh_bruteforce.pcap` — SSH brute-force scenario (80 flows, 2+ alerts)
- `regression_port_scan.pcap` — Port scan scenario (60 flows, 0 alerts)
- `regression_normal_traffic.pcap` — Normal traffic baseline (2 flows, 0 alerts)

Baselines are defined in `app/tests/fixtures/expected/baselines.json`.
Regenerate fixtures with: `python -m app.tests.fixtures.generate_fixtures`

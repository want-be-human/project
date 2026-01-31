# NetTwin-SOC

Network Traffic Analysis & Digital Twin Security Platform

## Overview

NetTwin-SOC is an intelligent network security operations center platform that combines:
- **Traffic Analysis**: PCAP parsing, flow extraction, and anomaly detection
- **Digital Twin**: Pre-action simulation (dry-run) for risk assessment
- **Evidence Chain**: Explainable AI reasoning from anomaly to action
- **Scenario Regression**: Automated validation and training scenarios

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### One-Line Start
```bash
cd infra && docker-compose up -d
```

### Access
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Frontend: http://localhost:3000 (when available)

## Project Structure

```
repo/
├── backend/           # FastAPI backend (Claude)
├── frontend/          # Next.js frontend (Gemini)
├── contract/          # API contract & samples
│   └── samples/       # DOC C compliant JSON samples
├── infra/             # Docker Compose & deployment
└── reports/           # Metrics & demo scripts
```

## API Contract (v1.1)

All API responses follow DOC C v1.1 specifications:
- Unified envelope: `{ ok: boolean, data: T | null, error: ErrorDetail | null }`
- ISO8601 UTC timestamps
- Strict field names (case-sensitive)

See [contract/README.md](contract/README.md) for details.

## Development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Generate Demo PCAPs
```bash
cd backend
python -m scripts.generate_demo_pcaps
```

### Run Tests
```bash
cd backend
pytest app/tests/
```

## Key Features (v1.1)

1. **PCAP Processing**: Upload → Parse → Extract Flows → Detect Anomalies
2. **Alert Generation**: Aggregation rules, evidence collection
3. **Topology Graph**: IP/subnet mode, time-based edge intervals
4. **Agent Analysis**: Triage → Investigate → Recommend
5. **Twin Dry-run**: ActionPlan simulation with impact assessment
6. **Evidence Chain**: Explainable link from anomaly to action
7. **Scenario Regression**: Automated testing & validation

## License

Proprietary - For competition/academic use only.

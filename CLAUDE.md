# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NetTwin-SOC is a network security platform combining PCAP analysis, ML-based anomaly detection, digital twin simulation, and AI-driven triage. It has two independently runnable services: a FastAPI backend and a Next.js frontend.

## Commands

### Backend (Python 3.11+)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload --port 8000

# Run all tests
pytest app/tests/

# Run a single test file
pytest app/tests/unit/test_detection.py -v

# Run by category
pytest app/tests/unit/
pytest app/tests/integration/
pytest app/tests/regression/

# Lint
ruff check .
ruff format .

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend (Node 18+)

```bash
cd frontend

npm install
npm run dev          # dev server on :3000
npm run dev:turbo    # with Turbo
npm run build
npm run lint
```

### Full Stack (Docker)

```bash
cd infra
docker-compose up    # backend :8000, frontend :3000
```

## Architecture

### Data Pipeline (9 stages)

PCAP upload → Parsing (dpkt) → Feature Extraction (20+ features/flow) → Detection (IsolationForest) → Alert Aggregation → Agent Investigation → Recommendations → Plan Compilation → Digital Twin Dry-run

Each stage is a discrete service in `backend/app/services/`. The `pipeline/` service tracks observability across all stages.



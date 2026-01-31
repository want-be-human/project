# Contract Directory

This directory contains the API contract definition and sample data files for NetTwin-SOC.

## Version

**Contract Version: v1.1**

## Purpose

- **samples/**: Sample JSON files matching DOC C schemas (used by frontend mock and backend tests)
- **schemas/**: (Optional) JSON Schema or OpenAPI definitions

## Usage

### Frontend Mock Mode

Frontend can load samples from `samples/*.json` to mock API responses during development.

### Backend Testing

Backend tests validate that API outputs match the structure in `samples/*.json`.

### Seed Data

`backend/scripts/seed_samples.py` can regenerate samples from actual database records.

## Schema Change Process

1. Update DOC C first (authoritative source)
2. Update `samples/*.json` to match new schema
3. Update backend Pydantic schemas
4. Update frontend TypeScript types
5. Run contract compliance tests

## Sample Files

| File | Description | DOC C Reference |
|------|-------------|-----------------|
| `flow.sample.json` | FlowRecord example | C1.2 |
| `alert.sample.json` | Alert example | C1.3 |
| `graph.sample.json` | Topology GraphResponse | C5.1 |
| `investigation.sample.json` | Agent Investigation | C1.4 |
| `recommendation.sample.json` | Agent Recommendation | C1.5 |
| `actionplan.sample.json` | Twin ActionPlan | C2.1 |
| `dryrun.sample.json` | Twin DryRunResult | C2.2 |
| `evidencechain.sample.json` | EvidenceChain | C3.1 |
| `scenario.sample.json` | Scenario definition | C4.1 |
| `scenario_run_result.sample.json` | ScenarioRunResult | C4.2 |

## Validation Rules

All sample files must:

1. Have field names exactly matching DOC C (case-sensitive)
2. Use valid UUID format for `id` fields
3. Use ISO8601 UTC format for timestamps (`2026-01-31T12:00:00Z`)
4. Have internally consistent references (e.g., `alert.evidence.flow_ids` should reference valid flow IDs)

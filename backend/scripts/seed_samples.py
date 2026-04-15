#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from datetime import datetime


SAMPLES = {
    "flow.sample.json": {
        "version": "1.1",
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "created_at": "2026-01-31T10:30:00Z",
        "pcap_id": "11111111-2222-3333-4444-555555555555",
        "ts_start": "2026-01-31T10:00:00Z",
        "ts_end": "2026-01-31T10:00:05Z",
        "src_ip": "192.0.2.10",
        "src_port": 54321,
        "dst_ip": "198.51.100.20",
        "dst_port": 22,
        "proto": "TCP",
        "packets_fwd": 10,
        "packets_bwd": 2,
        "bytes_fwd": 800,
        "bytes_bwd": 120,
        "features": {
            "total_packets": 12,
            "total_bytes": 920,
            "bytes_per_packet": 76.67,
            "flow_duration_ms": 5000,
            "fwd_ratio_packets": 0.833,
            "fwd_ratio_bytes": 0.870,
            "iat_mean_ms": 416.67,
            "iat_std_ms": 150.0,
            "syn_count": 8,
            "ack_count": 10,
            "rst_count": 0,
            "fin_count": 0,
            "dst_port_bucket": "0-1023"
        },
        "anomaly_score": 0.97,
        "label": None
    },
    "alert.sample.json": {
        "version": "1.1",
        "id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
        "created_at": "2026-01-31T10:35:00Z",
        "severity": "high",
        "status": "new",
        "type": "bruteforce",
        "time_window": {
            "start": "2026-01-31T10:00:00Z",
            "end": "2026-01-31T10:05:00Z"
        },
        "entities": {
            "primary_src_ip": "192.0.2.10",
            "primary_dst_ip": "198.51.100.20",
            "primary_service": {
                "proto": "TCP",
                "dst_port": 22
            }
        },
        "evidence": {
            "flow_ids": [
                "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "a1b2c3d4-e5f6-7890-abcd-ef1234567891"
            ],
            "top_flows": [
                {
                    "flow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "anomaly_score": 0.97,
                    "summary": "TCP/22 SYN burst from 192.0.2.10"
                }
            ],
            "top_features": [
                {"name": "syn_count", "value": 120, "direction": "high"},
                {"name": "iat_mean_ms", "value": 50.5, "direction": "low"}
            ],
            "pcap_ref": {
                "pcap_id": "11111111-2222-3333-4444-555555555555",
                "offset_hint": None
            }
        },
        "aggregation": {
            "rule": "same_src_ip + 60s_window",
            "group_key": "192.0.2.10@60s",
            "count_flows": 18
        },
        "agent": {
            "triage_summary": None,
            "investigation_id": None,
            "recommendation_id": None
        },
        "twin": {
            "plan_id": None,
            "dry_run_id": None
        },
        "tags": ["demo", "ssh"],
        "notes": ""
    }
}

REQUIRED_FILES = [
    "flow.sample.json",
    "alert.sample.json",
    "graph.sample.json",
    "investigation.sample.json",
    "recommendation.sample.json",
    "actionplan.sample.json",
    "dryrun.sample.json",
    "evidencechain.sample.json",
    "scenario.sample.json",
    "scenario_run_result.sample.json",
]


def validate_sample(path: Path) -> tuple[bool, list[str]]:
    if not path.exists():
        return False, [f"File not found: {path}"]

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    errors = []
    if "version" not in data:
        errors.append("Missing required field: version")
    elif data["version"] != "1.1":
        errors.append(f"Invalid version: {data['version']} (expected 1.1)")

    if "id" not in data:
        errors.append("Missing required field: id")

    if "created_at" not in data:
        errors.append("Missing required field: created_at")
    else:
        try:
            datetime.strptime(data["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            errors.append(f"Invalid timestamp format: {data['created_at']} (expected ISO8601 UTC)")

    return len(errors) == 0, errors


def validate_all(samples_dir: Path) -> bool:
    print(f"Validating samples in: {samples_dir}")
    print("-" * 50)

    all_valid = True
    for filename in REQUIRED_FILES:
        ok, errors = validate_sample(samples_dir / filename)
        if ok:
            print(f"OK {filename}")
        else:
            print(f"FAIL {filename}")
            for error in errors:
                print(f"    - {error}")
            all_valid = False

    print("-" * 50)
    print("All samples valid!" if all_valid else "Some samples have errors. Fix them before proceeding.")
    return all_valid


def regenerate(samples_dir: Path, force: bool = False):
    print(f"Regenerating samples in: {samples_dir}")
    samples_dir.mkdir(parents=True, exist_ok=True)

    for filename, data in SAMPLES.items():
        path = samples_dir / filename
        if path.exists() and not force:
            print(f"  Skipping {filename} (exists, use --force to overwrite)")
            continue
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Generated {filename}")


def main():
    samples_dir = Path(__file__).parent.parent.parent / "contract" / "samples"
    args = sys.argv[1:]

    if "--regenerate" in args or "--force" in args:
        regenerate(samples_dir, force="--force" in args)
        return

    if not validate_all(samples_dir):
        sys.exit(1)


if __name__ == "__main__":
    main()

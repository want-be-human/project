#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.database import SessionLocal, engine  # noqa: E402
from app.services.scenarios.service import ScenariosService  # noqa: E402
from app.schemas.scenario import ScenarioExpectations  # noqa: E402

import app.models.pcap  # noqa: F401, E402
import app.models.flow  # noqa: F401, E402
import app.models.alert  # noqa: F401, E402
import app.models.investigation  # noqa: F401, E402
import app.models.recommendation  # noqa: F401, E402
import app.models.twin  # noqa: F401, E402
import app.models.scenario  # noqa: F401, E402
from app.models.base import Base  # noqa: E402


def _print_scenario(s, idx: int | None = None):
    prefix = f"[{idx}] " if idx is not None else ""
    print(f"  {prefix}{s.id}  {s.name}  tags={s.tags}")


def _print_result(result):
    icon = "PASS" if result.status == "pass" else "FAIL"
    print(f"\n  Result: {icon}  (id={result.id})")
    print(f"  Scenario: {result.scenario_id}")
    for chk in result.checks:
        mark = "OK" if chk.pass_ else "NO"
        print(f"    [{mark}] {chk.name}  {chk.details}")
    m = result.metrics
    print(f"  Metrics: alerts={m.alert_count}, high_sev={m.high_severity_count}, avg_risk={m.avg_dry_run_risk}")


def cmd_list(args):
    db = SessionLocal()
    try:
        scenarios = ScenariosService(db).list_scenarios(limit=500)
        if not scenarios:
            print("No scenarios found.")
            return 0
        print(f"Scenarios ({len(scenarios)}):")
        for i, s in enumerate(scenarios, 1):
            _print_scenario(s, i)
        return 0
    finally:
        db.close()


def cmd_run(args):
    db = SessionLocal()
    try:
        svc = ScenariosService(db)
        model = svc.get_scenario(args.target)
        if model is None:
            from app.models.scenario import Scenario
            model = db.query(Scenario).filter(Scenario.name == args.target).first()
        if model is None:
            print(f"Scenario not found: {args.target}", file=sys.stderr)
            return 1
        print(f"Running scenario: {model.name} ({model.id})")
        result = svc.run_scenario(model)
        _print_result(result)
        return 0 if result.status == "pass" else 1
    finally:
        db.close()


def cmd_run_all(args):
    db = SessionLocal()
    try:
        svc = ScenariosService(db)
        scenarios = svc.list_scenarios(limit=500)
        if not scenarios:
            print("No scenarios to run.")
            return 0
        passed = 0
        failed = 0
        for s in scenarios:
            model = svc.get_scenario(s.id)
            if model is None:
                print(f"\n--- {s.name} ({s.id}) --- SKIPPED (not found)")
                failed += 1
                continue
            print(f"\n--- {s.name} ({s.id}) ---")
            result = svc.run_scenario(model)
            _print_result(result)
            if result.status == "pass":
                passed += 1
            else:
                failed += 1
        print(f"\n{'='*40}")
        print(f"Total: {len(scenarios)}  Passed: {passed}  Failed: {failed}")
        return 0 if failed == 0 else 1
    finally:
        db.close()


def cmd_create(args):
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()
    try:
        svc = ScenariosService(db)
        expectations = ScenarioExpectations(**data.get("expectations", {}))
        pcap_id = data.get("pcap_ref", {}).get("pcap_id", data.get("pcap_id", ""))
        scenario = svc.create_scenario(
            name=data["name"],
            description=data.get("description", ""),
            pcap_id=pcap_id,
            expectations=expectations,
            tags=data.get("tags", []),
        )
        print(f"Created scenario: {scenario.id}  {scenario.name}")
        return 0
    finally:
        db.close()


def main():
    Base.metadata.create_all(bind=engine)

    parser = argparse.ArgumentParser(description="NetTwin 场景命令行工具")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List scenarios")

    p_run = sub.add_parser("run", help="Run one scenario")
    p_run.add_argument("target", help="Scenario ID or name")

    sub.add_parser("run-all", help="Run all scenarios")

    p_create = sub.add_parser("create", help="Create scenario from JSON file")
    p_create.add_argument("--file", required=True, help="JSON definition file path")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handlers = {
        "list": cmd_list,
        "run": cmd_run,
        "run-all": cmd_run_all,
        "create": cmd_create,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()

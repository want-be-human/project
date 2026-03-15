#!/usr/bin/env python3
"""
run_scenarios_cli.py  –  命令行 Scenario 回归运行器

DOC B §B2 推荐脚本：不经过 HTTP，直接调用 ScenariosService
在本地或 CI 环境中快速回归验证。

Usage:
    # 列出所有 Scenario
    python -m scripts.run_scenarios_cli list

    # 运行指定 Scenario（按 ID 或名称）
    python -m scripts.run_scenarios_cli run <scenario_id_or_name>

    # 运行全部 Scenario
    python -m scripts.run_scenarios_cli run-all

    # 从 JSON 文件创建 Scenario
    python -m scripts.run_scenarios_cli create --file scenario_def.json

NOTE: 需要 PYTHONPATH 包含 backend/ 目录（与 pytest 运行方式一致）。
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: 确保 backend/ 在 sys.path
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.database import SessionLocal, engine  # noqa: E402
from app.services.scenarios.service import ScenariosService  # noqa: E402
from app.schemas.scenario import ScenarioExpectations  # noqa: E402

# Import all models so Base.metadata knows about every table
import app.models.pcap  # noqa: F401, E402
import app.models.flow  # noqa: F401, E402
import app.models.alert  # noqa: F401, E402
import app.models.investigation  # noqa: F401, E402
import app.models.recommendation  # noqa: F401, E402
import app.models.twin  # noqa: F401, E402
import app.models.scenario  # noqa: F401, E402
from app.models.base import Base  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_db():
    """获取一个 DB session（非 generator）。"""
    return SessionLocal()


def _print_scenario(s, idx: int | None = None):
    prefix = f"[{idx}] " if idx is not None else ""
    print(f"  {prefix}{s.id}  {s.name}  tags={s.tags}")


def _print_run_result(result):
    status_icon = "PASS ✓" if result.status == "pass" else "FAIL ✗"
    print(f"\n  Result: {status_icon}  (id={result.id})")
    print(f"  Scenario: {result.scenario_id}")
    for chk in result.checks:
        icon = "✓" if chk.pass_ else "✗"
        print(f"    [{icon}] {chk.name}  {chk.details}")
    m = result.metrics
    print(f"  Metrics: alerts={m.alert_count}, high_sev={m.high_severity_count}, avg_risk={m.avg_dry_run_risk}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args):
    """列出所有 Scenario。"""
    db = _get_db()
    try:
        svc = ScenariosService(db)
        scenarios = svc.list_scenarios(limit=500)
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
    """运行指定 Scenario。"""
    db = _get_db()
    try:
        svc = ScenariosService(db)
        # 先按 ID 查，查不到按 name 查
        model = svc.get_scenario(args.target)
        if model is None:
            from app.models.scenario import Scenario
            model = db.query(Scenario).filter(Scenario.name == args.target).first()
        if model is None:
            print(f"Scenario not found: {args.target}", file=sys.stderr)
            return 1
        print(f"Running scenario: {model.name} ({model.id})")
        result = svc.run_scenario(model)
        _print_run_result(result)
        return 0 if result.status == "pass" else 1
    finally:
        db.close()


def cmd_run_all(args):
    """运行全部 Scenario，返回是否全部 pass。"""
    db = _get_db()
    try:
        svc = ScenariosService(db)
        scenarios = svc.list_scenarios(limit=500)
        if not scenarios:
            print("No scenarios to run.")
            return 0
        total = len(scenarios)
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
            _print_run_result(result)
            if result.status == "pass":
                passed += 1
            else:
                failed += 1
        print(f"\n{'='*40}")
        print(f"Total: {total}  Passed: {passed}  Failed: {failed}")
        return 0 if failed == 0 else 1
    finally:
        db.close()


def cmd_create(args):
    """从 JSON 文件创建 Scenario。"""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 1
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = _get_db()
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    Base.metadata.create_all(bind=engine)

    parser = argparse.ArgumentParser(
        description="NetTwin Scenario CLI – 命令行回归运行器",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="列出所有 Scenario")

    # run
    p_run = sub.add_parser("run", help="运行指定 Scenario")
    p_run.add_argument("target", help="Scenario ID 或 name")

    # run-all
    sub.add_parser("run-all", help="运行全部 Scenario")

    # create
    p_create = sub.add_parser("create", help="从 JSON 文件创建 Scenario")
    p_create.add_argument("--file", required=True, help="JSON 定义文件路径")

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

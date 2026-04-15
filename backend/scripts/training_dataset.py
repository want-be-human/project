from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


_CSV_SUFFIXES = {".csv"}
_PCAP_SUFFIXES = {".pcap", ".pcapng"}
_HEADER_ALIASES = {
    "source_ip": {"source_ip", "src_ip"},
    "source_port": {"source_port", "src_port"},
    "destination_ip": {"destination_ip", "dst_ip"},
    "destination_port": {"destination_port", "dst_port"},
    "protocol": {"protocol", "proto"},
    "timestamp": {"timestamp", "flow_start_time", "start_time"},
    "label": {"label", "attack", "class"},
}
_DAY_FIRST_FORMATS = (
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %I:%M:%S %p",
    "%d/%m/%Y %I:%M %p",
)
_MONTH_FIRST_FORMATS = (
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
)
_ISO_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
)


@dataclass(frozen=True)
class DatasetSource:
    name: str
    pcap: Path
    labels_csv: Path | None = None
    include_families: tuple[str, ...] = ()
    default_family: str | None = None
    timestamp_day_first: bool = True


@dataclass(frozen=True)
class LabelRecord:
    family: str
    raw_label: str
    timestamp: datetime | None


def normalize_protocol(value: str | int | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"6", "TCP"}:
        return "TCP"
    if text in {"17", "UDP"}:
        return "UDP"
    if text in {"1", "ICMP"}:
        return "ICMP"
    return text or "OTHER"


def canonical_session_key(
    src_ip: str,
    src_port: int,
    dst_ip: str,
    dst_port: int,
    proto: str,
) -> tuple[str, int, str, int, str]:
    endpoint_a = (src_ip, int(src_port))
    endpoint_b = (dst_ip, int(dst_port))
    left, right = sorted((endpoint_a, endpoint_b))
    return left[0], left[1], right[0], right[1], normalize_protocol(proto)


def map_official_label_family(raw_label: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", raw_label.strip().lower()).strip()
    if not normalized:
        return None
    if normalized in {"benign", "normal"}:
        return "normal"
    if "patator" in normalized or "brute force" in normalized:
        return "bruteforce"
    if "portscan" in normalized or "port scan" in normalized:
        return "scan"
    if any(token in normalized for token in ("dos", "ddos", "slowloris", "slowhttptest", "goldeneye", "hulk")):
        return "dos"
    return None


def parse_official_timestamp(raw_value: str, *, day_first: bool = True) -> datetime | None:
    text = raw_value.strip()
    if not text:
        return None

    formats = list(_ISO_FORMATS)
    if day_first:
        formats.extend(_DAY_FIRST_FORMATS)
        formats.extend(_MONTH_FIRST_FORMATS)
    else:
        formats.extend(_MONTH_FIRST_FORMATS)
        formats.extend(_DAY_FIRST_FORMATS)

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def assign_default_family(
    flows: list[dict],
    family: str,
    source_name: str,
) -> tuple[list[dict], dict]:
    labeled: list[dict] = []
    for flow in flows:
        copied = dict(flow)
        copied["_dataset_source"] = source_name
        copied["_label"] = 0 if family == "normal" else 1
        copied["_attack_type"] = family
        copied["_label_raw"] = family
        labeled.append(copied)

    stats = {
        "source": source_name,
        "label_mode": "default_family",
        "total_flows": len(flows),
        "labeled_flows": len(labeled),
        "unmatched_flows": 0,
        "family_counts": dict(Counter(flow["_attack_type"] for flow in labeled)),
    }
    return labeled, stats


def label_flows_with_official_csv(
    flows: list[dict],
    labels_csv: Path,
    *,
    include_families: tuple[str, ...] = (),
    tolerance_sec: int = 120,
    source_name: str = "dataset",
    timestamp_day_first: bool = True,
) -> tuple[list[dict], dict]:
    include_set = set(include_families)
    index, csv_stats = _build_label_index(
        labels_csv,
        include_families=include_set,
        timestamp_day_first=timestamp_day_first,
    )

    labeled: list[dict] = []
    unmatched = 0
    ambiguous = 0

    for flow in flows:
        match = _match_flow_label(flow, index, tolerance_sec=tolerance_sec)
        if match is None:
            unmatched += 1
            continue
        if match == "ambiguous":
            ambiguous += 1
            continue

        copied = dict(flow)
        copied["_dataset_source"] = source_name
        copied["_label"] = 0 if match.family == "normal" else 1
        copied["_attack_type"] = match.family
        copied["_label_raw"] = match.raw_label
        labeled.append(copied)

    stats = {
        "source": source_name,
        "label_mode": "official_csv",
        "labels_csv": str(labels_csv),
        "total_flows": len(flows),
        "labeled_flows": len(labeled),
        "unmatched_flows": unmatched,
        "ambiguous_flows": ambiguous,
        "family_counts": dict(Counter(flow["_attack_type"] for flow in labeled)),
        "csv_stats": csv_stats,
    }
    return labeled, stats


def load_dataset_manifest(manifest_path: Path) -> tuple[list[DatasetSource], dict]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent
    sources: list[DatasetSource] = []

    for item in payload.get("sources", []):
        pcap_path = _resolve_path(base_dir, item["pcap"])
        labels_csv = _resolve_path(base_dir, item["labels_csv"]) if item.get("labels_csv") else None
        sources.append(
            DatasetSource(
                name=item["name"],
                pcap=pcap_path,
                labels_csv=labels_csv,
                include_families=tuple(item.get("include_families", [])),
                default_family=item.get("default_family"),
                timestamp_day_first=bool(item.get("timestamp_day_first", True)),
            )
        )

    config = {
        "name": payload.get("name", manifest_path.stem),
        "window_sec": int(payload.get("window_sec", 60)),
        "label_match_tolerance_sec": int(payload.get("label_match_tolerance_sec", 120)),
        "source_count": len(sources),
    }
    return sources, config


def build_cicids2017_core_sources(dataset_root: Path) -> list[DatasetSource]:
    monday_pcap = _pick_dataset_file(dataset_root, _PCAP_SUFFIXES, required_terms=("monday",))
    monday_csv = _pick_dataset_file(
        dataset_root,
        _CSV_SUFFIXES,
        required_terms=("monday",),
        required=False,
    )
    tuesday_pcap = _pick_dataset_file(dataset_root, _PCAP_SUFFIXES, required_terms=("tuesday",))
    tuesday_csv = _pick_dataset_file(dataset_root, _CSV_SUFFIXES, required_terms=("tuesday",))
    wednesday_pcap = _pick_dataset_file(dataset_root, _PCAP_SUFFIXES, required_terms=("wednesday",))
    wednesday_csv = _pick_dataset_file(dataset_root, _CSV_SUFFIXES, required_terms=("wednesday",))
    friday_pcap = _pick_dataset_file(
        dataset_root,
        _PCAP_SUFFIXES,
        required_terms=("friday",),
        preferred_terms=("afternoon", "portscan"),
    )
    friday_csv = _pick_dataset_file(
        dataset_root,
        _CSV_SUFFIXES,
        required_terms=("friday",),
        preferred_terms=("afternoon", "portscan"),
    )

    return [
        DatasetSource(
            name="cicids2017_monday_benign",
            pcap=monday_pcap,
            labels_csv=monday_csv,
            include_families=("normal",),
            default_family="normal" if monday_csv is None else None,
            timestamp_day_first=True,
        ),
        DatasetSource(
            name="cicids2017_tuesday_bruteforce",
            pcap=tuesday_pcap,
            labels_csv=tuesday_csv,
            include_families=("normal", "bruteforce"),
            timestamp_day_first=True,
        ),
        DatasetSource(
            name="cicids2017_wednesday_dos",
            pcap=wednesday_pcap,
            labels_csv=wednesday_csv,
            include_families=("normal", "dos"),
            timestamp_day_first=True,
        ),
        DatasetSource(
            name="cicids2017_friday_portscan",
            pcap=friday_pcap,
            labels_csv=friday_csv,
            include_families=("normal", "scan"),
            timestamp_day_first=True,
        ),
    ]


def _build_label_index(
    labels_csv: Path,
    *,
    include_families: set[str],
    timestamp_day_first: bool,
) -> tuple[dict[tuple[str, int, str, int, str], list[LabelRecord]], dict]:
    index: dict[tuple[str, int, str, int, str], list[LabelRecord]] = defaultdict(list)
    total_rows = 0
    kept_rows = 0
    skipped_unmapped = 0

    with labels_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        field_map = _resolve_field_map(reader.fieldnames or [])

        for row in reader:
            total_rows += 1
            raw_label = str(row.get(field_map["label"], "")).strip()
            family = map_official_label_family(raw_label)
            if family is None or (include_families and family not in include_families):
                skipped_unmapped += 1
                continue

            src_ip = str(row.get(field_map["source_ip"], "")).strip()
            dst_ip = str(row.get(field_map["destination_ip"], "")).strip()
            if not src_ip or not dst_ip:
                continue

            src_port = _safe_int(row.get(field_map["source_port"]))
            dst_port = _safe_int(row.get(field_map["destination_port"]))
            proto = normalize_protocol(row.get(field_map["protocol"]))
            timestamp = parse_official_timestamp(
                str(row.get(field_map["timestamp"], "")),
                day_first=timestamp_day_first,
            )
            key = canonical_session_key(src_ip, src_port, dst_ip, dst_port, proto)
            index[key].append(
                LabelRecord(
                    family=family,
                    raw_label=raw_label,
                    timestamp=timestamp,
                )
            )
            kept_rows += 1

    for records in index.values():
        records.sort(
            key=lambda record: (
                record.timestamp or datetime.min,
                record.raw_label,
            )
        )

    stats = {
        "total_rows": total_rows,
        "kept_rows": kept_rows,
        "skipped_rows": skipped_unmapped,
        "session_keys": len(index),
        "included_families": sorted(include_families) if include_families else [],
    }
    return index, stats


def _match_flow_label(
    flow: dict,
    index: dict[tuple[str, int, str, int, str], list[LabelRecord]],
    *,
    tolerance_sec: int,
) -> LabelRecord | str | None:
    key = canonical_session_key(
        str(flow.get("src_ip", "")),
        _safe_int(flow.get("src_port")),
        str(flow.get("dst_ip", "")),
        _safe_int(flow.get("dst_port")),
        str(flow.get("proto", "")),
    )
    candidates = index.get(key, [])
    if not candidates:
        return None

    flow_time = flow.get("ts_start")
    if isinstance(flow_time, datetime):
        # 统一为 naive 以避免 aware/naive 比较错误
        ft = flow_time.replace(tzinfo=None) if flow_time.tzinfo else flow_time
        timed = [
            (
                abs((ft - (rec.timestamp.replace(tzinfo=None) if rec.timestamp.tzinfo else rec.timestamp)).total_seconds()),
                rec,
            )
            for rec in candidates
            if rec.timestamp is not None
        ]
        if timed:
            timed.sort(key=lambda item: item[0])
            best_delta, best_record = timed[0]
            if best_delta <= tolerance_sec:
                return best_record

    families = {record.family for record in candidates}
    if len(families) == 1:
        return candidates[0]

    return "ambiguous"


def _pick_dataset_file(
    dataset_root: Path,
    suffixes: set[str],
    *,
    required_terms: tuple[str, ...],
    preferred_terms: tuple[str, ...] = (),
    required: bool = True,
) -> Path | None:
    candidates: list[Path] = []
    for path in dataset_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        text = str(path.relative_to(dataset_root)).lower()
        if all(term in text for term in required_terms):
            candidates.append(path)

    if not candidates:
        if required:
            terms = ", ".join(required_terms)
            raise FileNotFoundError(f"No dataset file found under {dataset_root} for terms: {terms}")
        return None

    def _score(path: Path) -> tuple[int, int, int, str]:
        text = str(path.relative_to(dataset_root)).lower()
        preferred_hits = sum(1 for term in preferred_terms if term in text)
        return (-preferred_hits, len(path.parts), len(path.name), text)

    candidates.sort(key=_score)
    return candidates[0]


def _resolve_field_map(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(name): name for name in fieldnames}
    resolved: dict[str, str] = {}

    for canonical_name, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                resolved[canonical_name] = normalized[alias]
                break
        else:
            raise KeyError(f"Missing required CSV column for {canonical_name}: {sorted(aliases)}")

    return resolved


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _safe_int(value: object) -> int:
    try:
        text = str(value or "").strip()
        return int(float(text)) if text else 0
    except (TypeError, ValueError):
        return 0


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()

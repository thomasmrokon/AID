from __future__ import annotations

import argparse
import contextlib
import io
import itertools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


LAB_DIR = Path(__file__).resolve().parent

SITES = ("compact", "long", "irregular")
USAGES = ("production", "logistics", "office", "datacenter", "mixed")
PATTERNS: dict[str, tuple[tuple[float, float], ...]] = {
    "balanced": (
        (0.28, 0.72),
        (0.70, 0.72),
        (0.30, 0.32),
        (0.70, 0.32),
        (0.50, 0.52),
        (0.50, 0.18),
        (0.18, 0.50),
        (0.82, 0.50),
    ),
    "diagonal": (
        (0.18, 0.78),
        (0.36, 0.66),
        (0.54, 0.54),
        (0.72, 0.42),
        (0.82, 0.28),
        (0.28, 0.24),
        (0.62, 0.80),
        (0.42, 0.36),
    ),
    "edge": (
        (0.10, 0.88),
        (0.50, 0.88),
        (0.90, 0.88),
        (0.10, 0.12),
        (0.50, 0.12),
        (0.90, 0.12),
        (0.10, 0.50),
        (0.90, 0.50),
    ),
    "cluster": (
        (0.44, 0.58),
        (0.48, 0.56),
        (0.52, 0.54),
        (0.56, 0.52),
        (0.46, 0.48),
        (0.50, 0.46),
        (0.54, 0.44),
        (0.58, 0.42),
    ),
}


@dataclass(frozen=True)
class MatrixRow:
    site: str
    usage: str
    pattern: str
    parcels: int
    required_missing: int
    optional_missing: int
    min_coverage_pct: float
    max_center_distance_m: float
    max_overlap_m2: float
    max_outside_m2: float
    max_spacing_violation_m: float
    priority_inversions: int
    repeated_size_delta_pct: float
    hard_ok: bool
    warnings: tuple[str, ...]


def _load_app_helpers() -> dict[str, Any]:
    sys.path.insert(0, str(LAB_DIR))
    source = (LAB_DIR / "app.py").read_text().split("\nst.set_page_config", 1)[0]
    namespace: dict[str, Any] = {}
    with contextlib.redirect_stderr(io.StringIO()):
        exec(source, namespace)
    return namespace


def _build_functions(ns: dict[str, Any], usage: str) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for template in ns["FUNCTION_TEMPLATES"][usage]:
        count = int(template.get("count", 1))
        area = float(template.get("area", template.get("area_m2")))
        priority = template.get("priority", 99)
        for idx in range(1, count + 1):
            suffix = f" {idx}" if count > 1 else ""
            function = {
                "id": f"{template['key']}_{idx}",
                "name": f"{template['name']}{suffix}",
                "kind": template["kind"],
                "area_m2": area,
                "key": template["key"],
                "priority": priority,
                "shape": template.get("shape", "auto"),
                "alignment": template.get("alignment", "auto"),
            }
            function["geometry_generator"] = ns["_geometry_generator_label"](function)
            functions.append(function)
    return functions


def _point_for(ns: dict[str, Any], polygon: Any, u: float, v: float) -> tuple[float, float]:
    minx, miny, maxx, maxy = polygon.bounds
    point = ns["Point"](minx + (maxx - minx) * u, miny + (maxy - miny) * v)
    if polygon.buffer(0.01).contains(point):
        return (float(point.x), float(point.y))
    nearest = polygon.representative_point()
    return (float(nearest.x), float(nearest.y))


def _priority_inversions(ns: dict[str, Any], parcels: list[dict[str, Any]]) -> int:
    by_priority: dict[int, list[float]] = {}
    for parcel in parcels:
        priority = ns["_priority_value"](parcel["function"].get("priority", 99))
        by_priority.setdefault(priority, []).append(min(100.0, float(parcel.get("coverage_pct", 0.0))))
    inversions = 0
    priorities = sorted(by_priority)
    for high in priorities:
        high_avg = sum(by_priority[high]) / len(by_priority[high])
        for low in priorities:
            if low <= high:
                continue
            low_avg = sum(by_priority[low]) / len(by_priority[low])
            if low_avg > high_avg + 2.0:
                inversions += 1
    return inversions


def _repeated_size_delta_pct(parcels: list[dict[str, Any]]) -> float:
    grouped: dict[tuple[str, float, str], list[float]] = {}
    for parcel in parcels:
        function = parcel["function"]
        key = (str(function.get("key")), float(function.get("area_m2", 0.0)), str(function.get("priority")))
        grouped.setdefault(key, []).append(float(parcel.get("coverage_pct", 0.0)))
    deltas = [max(values) - min(values) for values in grouped.values() if len(values) > 1]
    return max(deltas, default=0.0)


def _evaluate_row(ns: dict[str, Any], site: str, usage: str, pattern: str, setback_m: float, spacing_m: float) -> MatrixRow:
    functions = _build_functions(ns, usage)
    placement_polygon = ns["_build_boundary"](site, setback_m)
    pattern_points = PATTERNS[pattern]
    placements = {site_id: {} for site_id in SITES}
    for index, function in enumerate(functions):
        anchor = _point_for(ns, placement_polygon, *pattern_points[index % len(pattern_points)])
        placements[site][function["id"]] = {"anchor": anchor, "order": index + 1}
    ns["_placement_store"] = lambda placements=placements: placements

    with contextlib.redirect_stderr(io.StringIO()):
        patch = ns["_build_patchwork"](site, functions, setback_m, spacing_m, True)

    parcels = patch.get("parcels", [])
    required_missing = [item for item in patch.get("missing", []) if not item.get("optional")]
    optional_missing = [item for item in patch.get("missing", []) if item.get("optional")]
    max_overlap = max((float(a["geometry"].intersection(b["geometry"]).area) for a, b in itertools.combinations(parcels, 2)), default=0.0)
    max_outside = 0.0
    max_spacing_violation = max((float(parcel.get("spacing_violation_m", 0.0)) for parcel in parcels), default=0.0)
    for parcel in parcels:
        allowed = patch["build_boundary"] if parcel["function"]["kind"] in ns["BUILDING_BOUNDARY_KINDS"] else patch["site_polygon"]
        max_outside = max(max_outside, float(parcel["geometry"].difference(allowed.buffer(0.01)).area))
    min_coverage = min((float(parcel.get("coverage_pct", 0.0)) for parcel in parcels), default=100.0)
    max_center = max((float(parcel.get("center_distance_m", 0.0)) for parcel in parcels), default=0.0)
    inversions = _priority_inversions(ns, parcels)
    repeated_delta = _repeated_size_delta_pct(parcels)

    warnings: list[str] = []
    if min_coverage < 50.0:
        warnings.append("low-coverage")
    if max_center > 40.0:
        warnings.append("far-anchor")
    if inversions:
        warnings.append("priority-inversion")
    if repeated_delta > 2.0:
        warnings.append("repeated-size-delta")

    hard_ok = not required_missing and max_overlap <= 0.6 and max_outside <= 0.6 and max_spacing_violation <= 0.06
    return MatrixRow(
        site=site,
        usage=usage,
        pattern=pattern,
        parcels=len(parcels),
        required_missing=len(required_missing),
        optional_missing=len(optional_missing),
        min_coverage_pct=round(min_coverage, 1),
        max_center_distance_m=round(max_center, 1),
        max_overlap_m2=round(max_overlap, 2),
        max_outside_m2=round(max_outside, 2),
        max_spacing_violation_m=round(max_spacing_violation, 2),
        priority_inversions=inversions,
        repeated_size_delta_pct=round(repeated_delta, 1),
        hard_ok=hard_ok,
        warnings=tuple(warnings),
    )


def _mode_scope(mode: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if mode == "smoke":
        return ("compact",), ("production", "logistics"), ("balanced",)
    if mode == "stress":
        return SITES, USAGES, tuple(PATTERNS)
    return SITES, USAGES, ("balanced", "diagonal")


def run_matrix(mode: str, setback_m: float, spacing_m: float) -> list[MatrixRow]:
    ns = _load_app_helpers()
    sites, usages, patterns = _mode_scope(mode)
    rows: list[MatrixRow] = []
    for site in sites:
        for usage in usages:
            for pattern in patterns:
                rows.append(_evaluate_row(ns, site, usage, pattern, setback_m, spacing_m))
    return rows


def _print_rows(rows: list[MatrixRow]) -> None:
    failures = [row for row in rows if not row.hard_ok]
    warning_rows = [row for row in rows if row.warnings]
    print(f"runs={len(rows)} hard_failures={len(failures)} warnings={len(warning_rows)}")
    header = (
        "site      usage      pattern   ok parcels miss min_cov center overlap outside spacing inv repeat warn"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        warn = ",".join(row.warnings) if row.warnings else "-"
        print(
            f"{row.site:9s} {row.usage:10s} {row.pattern:8s} "
            f"{'yes' if row.hard_ok else 'NO ':3s} "
            f"{row.parcels:7d} {row.required_missing:4d} "
            f"{row.min_coverage_pct:7.1f} {row.max_center_distance_m:6.1f} "
            f"{row.max_overlap_m2:7.2f} {row.max_outside_m2:7.2f} "
            f"{row.max_spacing_violation_m:7.2f} {row.priority_inversions:3d} "
            f"{row.repeated_size_delta_pct:6.1f} {warn}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Traffic & Trassen Lab placement matrix checks.")
    parser.add_argument("--mode", choices=("smoke", "standard", "stress"), default="standard")
    parser.add_argument("--setback", type=float, default=8.0)
    parser.add_argument("--spacing", type=float, default=5.0)
    parser.add_argument("--json", type=Path, help="Optional path for JSON result export.")
    args = parser.parse_args()

    rows = run_matrix(args.mode, args.setback, args.spacing)
    _print_rows(rows)
    if args.json:
        args.json.write_text(json.dumps([asdict(row) for row in rows], indent=2, ensure_ascii=False))
    return 1 if any(not row.hard_ok for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())

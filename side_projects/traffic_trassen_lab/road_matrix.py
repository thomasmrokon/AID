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

from placement_matrix import PATTERNS, SITES, USAGES, _build_functions, _load_app_helpers, _mode_scope, _point_for


ACCESS_VARIANTS: dict[str, tuple[tuple[float, float, str], ...]] = {
    "single_both": ((0.50, 0.98, "both"),),
    "split": ((0.24, 0.98, "lkw"), (0.76, 0.02, "pkw")),
    "opposite_both": ((0.50, 0.98, "both"), (0.50, 0.02, "both")),
}

ROAD_OPTION_VARIANTS: dict[str, dict[str, str]] = {
    "balanced": {"flow": "auto", "network": "auto", "service": "auto", "parking": "auto", "objective": "balanced"},
    "area": {"flow": "auto", "network": "minimal", "service": "auto", "parking": "edge", "objective": "area"},
    "traffic": {"flow": "separate", "network": "spine", "service": "per_building", "parking": "office", "objective": "traffic"},
}

TARGETED_CASES: tuple[tuple[str, str, str, str, str], ...] = (
    ("compact", "production", "balanced", "single_both", "balanced"),
    ("compact", "logistics", "balanced", "single_both", "balanced"),
    ("compact", "production", "diagonal", "single_both", "area"),
    ("compact", "logistics", "diagonal", "single_both", "traffic"),
    ("long", "production", "balanced", "single_both", "balanced"),
    ("long", "logistics", "diagonal", "single_both", "traffic"),
    ("irregular", "production", "diagonal", "single_both", "balanced"),
    ("irregular", "mixed", "diagonal", "single_both", "area"),
)

COVERAGE_FLOORS_BY_PRIORITY = {
    1: 65.0,
    2: 60.0,
    3: 45.0,
    4: 35.0,
    5: 30.0,
}


@dataclass(frozen=True)
class RoadMatrixRow:
    site: str
    usage: str
    pattern: str
    access_variant: str
    road_option_variant: str
    parcels: int
    roads: int
    required_missing: int
    missing_roads: int
    incompatible_routes: int
    disconnected_parcels: int
    max_outside_m2: float
    max_non_target_overlap_m2: float
    max_building_intrusion_m2: float
    max_required_shortfall_pct: float
    priority_starvations: int
    total_road_area_m2: float
    hard_ok: bool
    warnings: tuple[str, ...]


def _make_access(ns: dict[str, Any], site: str, u: float, v: float, access_type: str, index: int) -> dict[str, Any]:
    polygon = ns["_site_polygon"](site)
    seed = _point_for(ns, polygon, u, v)
    projected = ns["project_point_to_site_boundary"](ns["DEMO_SITES"][site], seed)
    return {"id": f"Z{index}", "access_type": access_type, **projected}


def _access_is_compatible(ns: dict[str, Any], access: dict[str, Any], need: str) -> bool:
    return bool(ns["_access_supports_need"](access, need))


def _priority_floor(priority: Any) -> float:
    if priority == "optional":
        return 0.0
    try:
        priority_value = int(priority)
    except (TypeError, ValueError):
        priority_value = 99
    return COVERAGE_FLOORS_BY_PRIORITY.get(priority_value, 25.0)


def _area_summary(ns: dict[str, Any], functions: list[dict[str, Any]], parcels: list[dict[str, Any]]) -> tuple[float, int, list[str]]:
    by_key: dict[str, dict[str, Any]] = {}
    for function in functions:
        key = str(function.get("key", function["id"]))
        row = by_key.setdefault(key, {"required": 0.0, "realized": 0.0, "priority": function.get("priority", 99), "name": ns["_base_function_name"](function["name"])})
        row["required"] += float(function.get("area_m2", 0.0))
        if ns["_priority_value"](function.get("priority", 99)) < ns["_priority_value"](row["priority"]):
            row["priority"] = function.get("priority", 99)
    for parcel in parcels:
        function = parcel["function"]
        key = str(function.get("key", function["id"]))
        row = by_key.setdefault(key, {"required": 0.0, "realized": 0.0, "priority": function.get("priority", 99), "name": ns["_base_function_name"](function["name"])})
        row["realized"] += float(parcel.get("actual_area_m2", 0.0))

    max_shortfall = 0.0
    starvations = 0
    warnings: list[str] = []
    coverages: list[tuple[int, float, str]] = []
    for row in by_key.values():
        required = float(row["required"])
        if required <= 0.0:
            continue
        realized = float(row["realized"])
        coverage = min(120.0, realized / required * 100.0)
        shortfall = max(0.0, 100.0 - coverage)
        max_shortfall = max(max_shortfall, shortfall)
        priority = row["priority"]
        priority_value = ns["_priority_value"](priority)
        coverages.append((priority_value, coverage, str(row["name"])))
        floor = _priority_floor(priority)
        if coverage + 0.1 < floor:
            warnings.append(f"area-below-floor:{row['name']}:{coverage:.0f}<floor{floor:.0f}")

    for high_priority, high_coverage, high_name in coverages:
        for low_priority, low_coverage, low_name in coverages:
            if low_priority <= high_priority:
                continue
            if low_coverage > high_coverage + 15.0 and high_coverage < 90.0:
                starvations += 1
                warnings.append(f"priority-starvation:{high_name}<{low_name}")
    return max_shortfall, starvations, warnings


def _road_overlap_metrics(parcels: list[dict[str, Any]], segments: list[dict[str, Any]]) -> tuple[float, float, list[str]]:
    max_non_target_overlap = 0.0
    max_building_intrusion = 0.0
    warnings: list[str] = []
    parcel_by_id = {str(parcel["function"].get("id", "")): parcel for parcel in parcels}
    for segment in segments:
        corridor = segment["corridor"]
        width_m = float(segment.get("width_m", 7.5))
        allowed_ids = {str(segment.get("function_id", "")), str(segment.get("source_id", "")), str(segment.get("target_id", ""))}
        for parcel in parcels:
            function = parcel["function"]
            parcel_id = str(function.get("id", ""))
            overlap = float(corridor.intersection(parcel["geometry"]).area)
            if overlap <= 0.05:
                continue
            # Edge contact is allowed. Count only overlap that reaches into the
            # inner footprint; this catches roads through buildings while not
            # flagging a corridor that merely docks at a facade or yard edge.
            inner = parcel["geometry"].buffer(-max(1.5, min(width_m / 2.0, 4.0)), cap_style=2, join_style=2)
            deep_overlap = 0.0 if inner.is_empty else float(corridor.intersection(inner).area)
            if parcel_id not in allowed_ids:
                max_non_target_overlap = max(max_non_target_overlap, deep_overlap)
                if deep_overlap > 2.0:
                    warnings.append(f"road-crosses-non-target:{segment.get('id')}->{parcel_id}:{deep_overlap:.0f}m2")
                continue
            if str(function.get("kind", "")) == "building":
                max_building_intrusion = max(max_building_intrusion, deep_overlap)
                if deep_overlap > 0.6:
                    warnings.append(f"road-in-building:{segment.get('id')}->{parcel_id}:{deep_overlap:.0f}m2")
    # Graph sanity: every function_link must start from a function that already has a segment.
    reached = {str(segment.get("function_id", "")) for segment in segments if segment.get("kind") == "access_link"}
    for segment in segments:
        source_id = str(segment.get("source_id", ""))
        if segment.get("kind") == "function_link" and source_id not in reached and source_id in parcel_by_id:
            warnings.append(f"function-link-from-unreached-source:{segment.get('id')}:{source_id}")
        reached.add(str(segment.get("function_id", "")))
    return max_non_target_overlap, max_building_intrusion, warnings


def _evaluate_row(
    ns: dict[str, Any],
    site: str,
    usage: str,
    pattern: str,
    access_variant: str,
    road_option_variant: str,
    setback_m: float,
    spacing_m: float,
) -> RoadMatrixRow:
    functions = _build_functions(ns, usage)
    placement_polygon = ns["_build_boundary"](site, setback_m)
    pattern_points = PATTERNS[pattern]
    placements = {site_id: {} for site_id in SITES}
    for index, function in enumerate(functions):
        anchor = _point_for(ns, placement_polygon, *pattern_points[index % len(pattern_points)])
        placements[site][function["id"]] = {"anchor": anchor, "order": index + 1}
    ns["_placement_store"] = lambda placements=placements: placements

    access_points = [
        _make_access(ns, site, u, v, access_type, index)
        for index, (u, v, access_type) in enumerate(ACCESS_VARIANTS[access_variant], start=1)
    ]
    road_options = ROAD_OPTION_VARIANTS[road_option_variant]
    with contextlib.redirect_stderr(io.StringIO()):
        patch = ns["_build_patchwork"](site, functions, setback_m, spacing_m, True, access_points)
    patch = ns["_with_road_network"](site, access_points, patch, functions, setback_m, road_options)

    parcels = patch.get("parcels", [])
    segments = patch.get("road_network", {}).get("segments", [])
    required_missing = [item for item in patch.get("missing", []) if not item.get("optional")]
    access_by_id = {access["id"]: access for access in access_points}
    incompatible = 0
    max_outside = 0.0
    corridor_union = None

    for segment in segments:
        access = access_by_id.get(segment.get("access_id"))
        if access is None or not _access_is_compatible(ns, access, str(segment.get("need", "both"))):
            incompatible += 1
        max_outside = max(max_outside, float(segment.get("outside_area_m2", 0.0)))
        corridor = segment["corridor"]
        corridor_union = corridor if corridor_union is None else corridor_union.union(corridor)

    missing_roads = 0 if segments else len(parcels)
    disconnected_parcels = 0
    max_parcel_distance = 0.0
    if corridor_union is not None:
        distances = [float(parcel["geometry"].distance(corridor_union)) for parcel in parcels]
        max_parcel_distance = max(distances, default=0.0)
        disconnected_parcels = sum(1 for distance in distances if distance > 12.0)

    max_non_target_overlap, max_building_intrusion, overlap_warnings = _road_overlap_metrics(parcels, segments)
    max_shortfall, priority_starvations, area_warnings = _area_summary(ns, functions, parcels)

    road_area = float(patch.get("road_network", {}).get("total_area_m2", 0.0))
    site_area = float(patch["site_polygon"].area)
    warnings: list[str] = []
    warnings.extend(overlap_warnings)
    warnings.extend(area_warnings)
    if max_parcel_distance > 12.0:
        warnings.append("parcel-too-far-from-road")
    if road_area > site_area * 0.18:
        warnings.append("high-road-area")
    if max_outside > 1.0:
        warnings.append("road-outside-site")
    if required_missing:
        warnings.append("required-function-missing")
    if missing_roads:
        warnings.append("missing-road-network")
    if incompatible:
        warnings.append("incompatible-access")

    hard_ok = (
        not required_missing
        and missing_roads == 0
        and incompatible == 0
        and max_outside <= 1.0
        and max_non_target_overlap <= 2.0
        and max_building_intrusion <= 0.6
        and disconnected_parcels == 0
        and not any(warning.startswith("area-below-floor") for warning in warnings)
        and priority_starvations == 0
        and road_area <= site_area * 0.22
    )
    return RoadMatrixRow(
        site=site,
        usage=usage,
        pattern=pattern,
        access_variant=access_variant,
        road_option_variant=road_option_variant,
        parcels=len(parcels),
        roads=len(segments),
        required_missing=len(required_missing),
        missing_roads=missing_roads,
        incompatible_routes=incompatible,
        disconnected_parcels=disconnected_parcels,
        max_outside_m2=round(max_outside, 2),
        max_non_target_overlap_m2=round(max_non_target_overlap, 1),
        max_building_intrusion_m2=round(max_building_intrusion, 1),
        max_required_shortfall_pct=round(max_shortfall, 1),
        priority_starvations=priority_starvations,
        total_road_area_m2=round(road_area, 1),
        hard_ok=hard_ok,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _road_mode_scope(mode: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    sites, usages, patterns = _mode_scope(mode)
    if mode == "smoke":
        return sites, usages, patterns, ("single_both",), ("balanced",)
    if mode == "stress":
        return sites, usages, patterns, tuple(ACCESS_VARIANTS), tuple(ROAD_OPTION_VARIANTS)
    return sites, usages, patterns, ("single_both",), ("balanced", "area", "traffic")


def run_matrix(mode: str, setback_m: float, spacing_m: float) -> list[RoadMatrixRow]:
    ns = _load_app_helpers()
    rows: list[RoadMatrixRow] = []
    if mode == "targeted":
        for site, usage, pattern, access_variant, road_option_variant in TARGETED_CASES:
            rows.append(_evaluate_row(ns, site, usage, pattern, access_variant, road_option_variant, setback_m, spacing_m))
        return rows
    sites, usages, patterns, access_variants, road_option_variants = _road_mode_scope(mode)
    for site, usage, pattern, access_variant, road_option_variant in itertools.product(sites, usages, patterns, access_variants, road_option_variants):
        rows.append(_evaluate_row(ns, site, usage, pattern, access_variant, road_option_variant, setback_m, spacing_m))
    return rows


def _print_rows(rows: list[RoadMatrixRow]) -> None:
    failures = [row for row in rows if not row.hard_ok]
    warning_rows = [row for row in rows if row.warnings]
    print(f"runs={len(rows)} hard_failures={len(failures)} warnings={len(warning_rows)}")
    header = "site      usage      pattern   access        options   ok parcels roads miss no_road bad_type far_fn outside cross bldg_in short% prio road_area warn"
    print(header)
    print("-" * len(header))
    for row in rows:
        warn = ",".join(row.warnings[:4]) if row.warnings else "-"
        if len(row.warnings) > 4:
            warn += ",..."
        print(
            f"{row.site:9s} {row.usage:10s} {row.pattern:8s} {row.access_variant:13s} {row.road_option_variant:8s} "
            f"{'yes' if row.hard_ok else 'NO ':3s} "
            f"{row.parcels:7d} {row.roads:5d} {row.required_missing:4d} {row.missing_roads:7d} "
            f"{row.incompatible_routes:8d} {row.disconnected_parcels:6d} "
            f"{row.max_outside_m2:7.2f} {row.max_non_target_overlap_m2:5.1f} {row.max_building_intrusion_m2:7.1f} "
            f"{row.max_required_shortfall_pct:6.1f} {row.priority_starvations:4d} {row.total_road_area_m2:9.0f} {warn}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Traffic & Trassen Lab road corridor quality checks.")
    parser.add_argument("--mode", choices=("smoke", "targeted", "standard", "stress"), default="targeted")
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

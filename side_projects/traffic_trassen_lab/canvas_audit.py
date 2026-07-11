from __future__ import annotations

import argparse
import contextlib
import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import Point, Polygon

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR))

from engine import DEMO_SITES, project_point_to_site_boundary  # noqa: E402
from placement_matrix import _build_functions, _load_app_helpers, _point_for  # noqa: E402
from variant_planner import SKELETON_TYPES, generate_variant_candidates, score_to_dict  # noqa: E402

CASES: tuple[dict[str, str], ...] = (
    {"site": "compact", "usage": "production", "pattern": "balanced", "planner": "variants"},
    {"site": "compact", "usage": "logistics", "pattern": "balanced", "planner": "variants"},
    {"site": "long", "usage": "production", "pattern": "balanced", "planner": "variants"},
    {"site": "irregular", "usage": "mixed", "pattern": "diagonal", "planner": "variants"},
)

PATTERNS: dict[str, tuple[tuple[float, float], ...]] = {
    "balanced": ((0.30, 0.72), (0.30, 0.30), (0.72, 0.70), (0.58, 0.48), (0.72, 0.30)),
    "diagonal": ((0.18, 0.78), (0.36, 0.64), (0.55, 0.48), (0.72, 0.34), (0.82, 0.22)),
}


FUNCTION_AUDIT_RULES: dict[str, dict[str, float]] = {
    "prod": {"coverage": 75.0, "short_side": 18.0, "max_aspect": 6.0, "frontage": 6.0},
    "hall": {"coverage": 75.0, "short_side": 22.0, "max_aspect": 6.0, "frontage": 8.0},
    "warehouse": {"coverage": 70.0, "short_side": 14.0, "max_aspect": 7.0, "frontage": 6.0},
    "office": {"coverage": 50.0, "short_side": 7.0, "max_aspect": 4.0, "frontage": 3.5},
    "yard": {"coverage": 60.0, "short_side": 16.0, "max_aspect": 5.0, "frontage": 7.5},
    "parking": {"coverage": 55.0, "short_side": 10.0, "max_aspect": 8.0, "frontage": 3.5},
    "dc": {"coverage": 75.0, "short_side": 20.0, "max_aspect": 6.0, "frontage": 8.0},
    "tech": {"coverage": 60.0, "short_side": 10.0, "max_aspect": 5.0, "frontage": 5.0},
    "security": {"coverage": 60.0, "short_side": 8.0, "max_aspect": 5.0, "frontage": 3.5},
}
DEFAULT_AUDIT_RULE = {"coverage": 50.0, "short_side": 6.0, "max_aspect": 10.0, "frontage": 0.0}


@dataclass(frozen=True)
class CanvasAuditRow:
    site: str
    usage: str
    pattern: str
    planner: str
    skeleton: str
    ok: bool
    parcels: int
    roads: int
    realized_pct: float
    road_area_pct: float
    max_deep_road_overlap_m2: float
    max_road_distance_m: float
    canvas_payload_ok: bool
    min_function_coverage_pct: float
    min_short_side_m: float
    max_aspect_ratio: float
    min_road_frontage_m: float
    warnings: tuple[str, ...]
    snapshot: str


def _access_for(site: str) -> dict[str, Any]:
    polygon = Polygon(DEMO_SITES[site].polygon)
    minx, _miny, maxx, maxy = polygon.bounds
    projected = project_point_to_site_boundary(DEMO_SITES[site], ((minx + maxx) / 2.0, maxy))
    return {"id": "Z1", "access_type": "both", **projected}


def _set_placements(ns: dict[str, Any], site: str, functions: list[dict[str, Any]], pattern: str, setback_m: float) -> dict[str, dict[str, Any]]:
    placement_polygon = ns["_build_boundary"](site, setback_m)
    pattern_points = PATTERNS[pattern]
    placements = {site_id: {} for site_id in DEMO_SITES}
    for index, function in enumerate(functions):
        anchor = _point_for(ns, placement_polygon, *pattern_points[index % len(pattern_points)])
        placements[site][function["id"]] = {"anchor": anchor, "order": index + 1}
    ns["_placement_store"] = lambda placements=placements: placements
    return placements[site]


def _road_union(segments: list[dict[str, Any]]) -> Any | None:
    union = None
    for segment in segments:
        geom = segment.get("corridor")
        if geom is None or geom.is_empty:
            continue
        union = geom if union is None else union.union(geom)
    return union


def _max_road_distance(parcels: list[dict[str, Any]], segments: list[dict[str, Any]]) -> float:
    union = _road_union(segments)
    if union is None:
        return 999.0 if parcels else 0.0
    return max((float(parcel["geometry"].distance(union)) for parcel in parcels), default=0.0)


def _max_deep_overlap(parcels: list[dict[str, Any]], segments: list[dict[str, Any]]) -> float:
    max_overlap = 0.0
    for segment in segments:
        corridor = segment.get("corridor")
        if corridor is None or corridor.is_empty:
            continue
        width_m = float(segment.get("width_m", 7.5))
        for parcel in parcels:
            inner = parcel["geometry"].buffer(-max(1.5, min(width_m / 2.0, 4.0)), cap_style=2, join_style=2)
            if inner.is_empty:
                continue
            max_overlap = max(max_overlap, float(corridor.intersection(inner).area))
    return max_overlap


def _function_rule(function: dict[str, Any]) -> dict[str, float]:
    return FUNCTION_AUDIT_RULES.get(str(function.get("key", "")), DEFAULT_AUDIT_RULE)


def _shape_metrics(geom: Any) -> tuple[float, float]:
    if geom is None or geom.is_empty:
        return 0.0, 999.0
    minx, miny, maxx, maxy = geom.bounds
    width = max(0.0, float(maxx - minx))
    height = max(0.0, float(maxy - miny))
    short_side = min(width, height)
    aspect = max(width, height) / max(0.1, short_side)
    return short_side, aspect


def _road_frontage_m(parcel: dict[str, Any], road_union: Any | None) -> float:
    if road_union is None or road_union.is_empty:
        return 0.0
    # The generated road corridor and parcel may be separated by a small numeric
    # gap because both are clipped/optimized independently. A 1 m tolerance
    # still requires a real edge relation and avoids counting remote proximity.
    return float(parcel["geometry"].boundary.intersection(road_union.buffer(1.0, cap_style=2, join_style=2)).length)


def _parcel_quality_warnings(parcels: list[dict[str, Any]], road_union: Any | None) -> tuple[list[str], float, float, float, float]:
    warnings: list[str] = []
    min_coverage = 100.0
    min_short_side = 999.0
    max_aspect = 0.0
    min_frontage = 999.0
    for parcel in parcels:
        function = parcel["function"]
        name = str(function.get("name", function.get("id", "Funktion")))
        rule = _function_rule(function)
        coverage = float(parcel.get("coverage_pct", 0.0))
        short_side, aspect = _shape_metrics(parcel.get("display_geometry", parcel.get("geometry")))
        frontage = _road_frontage_m(parcel, road_union)
        min_coverage = min(min_coverage, coverage)
        min_short_side = min(min_short_side, short_side)
        max_aspect = max(max_aspect, aspect)
        if float(rule["frontage"]) > 0.0:
            min_frontage = min(min_frontage, frontage)
        if coverage + 0.1 < float(rule["coverage"]):
            warnings.append(f"low-function-coverage:{name}:{coverage:.0f}%<{rule['coverage']:.0f}%")
        if short_side + 0.1 < float(rule["short_side"]):
            warnings.append(f"bad-function-depth:{name}:{short_side:.1f}m<{rule['short_side']:.1f}m")
        if aspect > float(rule["max_aspect"]) + 0.05:
            warnings.append(f"bad-function-aspect:{name}:{aspect:.1f}>{rule['max_aspect']:.1f}")
        if float(rule["frontage"]) > 0.0 and frontage + 0.1 < float(rule["frontage"]):
            warnings.append(f"low-road-frontage:{name}:{frontage:.1f}m<{rule['frontage']:.1f}m")
    if not parcels:
        return warnings, 0.0, 0.0, 0.0, 0.0
    if min_frontage == 999.0:
        min_frontage = 0.0
    return warnings, min_coverage, min_short_side, max_aspect, min_frontage


def _realized_pct(functions: list[dict[str, Any]], parcels: list[dict[str, Any]]) -> float:
    required = sum(float(fn.get("area_m2", 0.0)) for fn in functions if fn.get("priority") != "optional")
    parcel_by_id = {parcel["function"]["id"]: parcel for parcel in parcels}
    realized = 0.0
    for fn in functions:
        if fn.get("priority") == "optional":
            continue
        parcel = parcel_by_id.get(fn["id"])
        if parcel is None:
            continue
        realized += min(float(parcel.get("actual_area_m2", 0.0)), float(fn.get("area_m2", 0.0)))
    return 100.0 if required <= 0 else realized / required * 100.0


def _payload_ok(payload: dict[str, Any]) -> bool:
    if not payload.get("site_polygon") or not payload.get("build_boundary"):
        return False
    if any(not parcel.get("points") for parcel in payload.get("parcels", [])):
        return False
    if any(not road.get("points") for road in payload.get("roads", [])):
        return False
    bounds = payload.get("bounds", {})
    return all(key in bounds for key in ("minx", "miny", "maxx", "maxy")) and bounds["maxx"] > bounds["minx"] and bounds["maxy"] > bounds["miny"]


def _poly_points(geom: Any) -> list[tuple[float, float]]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [(float(x), float(y)) for x, y in geom.exterior.coords]
    geoms = list(getattr(geom, "geoms", []))
    if not geoms:
        return []
    largest = max(geoms, key=lambda item: item.area)
    return [(float(x), float(y)) for x, y in largest.exterior.coords]


def _draw_patch(ns: dict[str, Any], patch: dict[str, Any], path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 7), dpi=140)
    site_poly = patch["site_polygon"]
    build_boundary = patch["build_boundary"]
    ax.add_patch(MplPolygon(_poly_points(site_poly), fill=True, facecolor="#f4faf7", edgecolor="#1f2937", linewidth=1.8))
    ax.add_patch(MplPolygon(_poly_points(build_boundary), fill=False, edgecolor="#64748b", linewidth=1.5, linestyle=(0, (4, 4))))
    for segment in patch.get("road_network", {}).get("segments", []):
        points = _poly_points(segment.get("corridor"))
        if points:
            ax.add_patch(MplPolygon(points, fill=True, facecolor="#94a3b8", alpha=0.45, edgecolor="#475569", linewidth=1.0))
        line = segment.get("centerline")
        if line is not None and not line.is_empty:
            xs, ys = line.xy
            ax.plot(xs, ys, color="#475569", linewidth=1.0, linestyle="--")
    for parcel in patch.get("parcels", []):
        fn = parcel["function"]
        color = ns["_function_color"](fn)
        points = _poly_points(parcel["display_geometry"])
        if not points:
            continue
        ax.add_patch(MplPolygon(points, fill=True, facecolor=color, alpha=0.42, edgecolor=color, linewidth=1.4, linestyle="--"))
        cx, cy = parcel["display_geometry"].centroid.coords[0]
        ax.text(cx, cy, f"{fn['name']}\n{parcel['actual_area_m2']:.0f} m2", ha="center", va="center", fontsize=8, color="#111827")
    ax.set_title(title, fontsize=11)
    minx, miny, maxx, maxy = site_poly.bounds
    pad = max(maxx - minx, maxy - miny) * 0.12
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _patch_for_case(ns: dict[str, Any], case: dict[str, str], setback_m: float, spacing_m: float) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    site = case["site"]
    usage = case["usage"]
    functions = _build_functions(ns, usage)
    placements = _set_placements(ns, site, functions, case["pattern"], setback_m)
    access_points = [_access_for(site)]
    with contextlib.redirect_stderr(io.StringIO()):
        if case["planner"] == "variants":
            variants = generate_variant_candidates(ns, site, functions, access_points, setback_m, spacing_m, True)
            score, patch = variants[0]
            patch = {**patch, "variant_scores": [score_to_dict(item_score) for item_score, _candidate in variants]}
            skeleton = score.skeleton
        else:
            patch = ns["_build_patchwork"](site, functions, setback_m, spacing_m, True, access_points)
            patch = ns["_with_road_network"](site, access_points, patch, functions, setback_m, {"planner": "graph", "flow": "auto", "network": "auto", "service": "auto", "parking": "auto", "objective": "balanced"})
            skeleton = str(patch.get("road_network", {}).get("strategy", "graph"))
    return skeleton, patch, functions, access_points, placements


def audit_case(ns: dict[str, Any], case: dict[str, str], out_dir: Path, setback_m: float = 8.0, spacing_m: float = 5.0) -> CanvasAuditRow:
    skeleton, patch, functions, access_points, placements = _patch_for_case(ns, case, setback_m, spacing_m)
    payload = ns["_drag_plan_payload"](case["site"], access_points, patch, functions, placements, functions[0]["id"] if functions else None)
    parcels = patch.get("parcels", [])
    segments = patch.get("road_network", {}).get("segments", [])
    realized = _realized_pct(functions, parcels)
    site_area = float(patch["site_polygon"].area)
    road_area = float(patch.get("road_network", {}).get("total_area_m2", 0.0))
    road_pct = road_area / site_area * 100.0 if site_area > 0 else 0.0
    max_overlap = _max_deep_overlap(parcels, segments)
    max_distance = _max_road_distance(parcels, segments)
    road_union = _road_union(segments)
    parcel_warnings, min_function_coverage, min_short_side, max_aspect, min_frontage = _parcel_quality_warnings(parcels, road_union)
    warnings: list[str] = []
    if len(parcels) < len([fn for fn in functions if fn.get("priority") != "optional"]):
        warnings.append("missing-visible-parcel")
    if realized < 60.0:
        warnings.append(f"low-realized:{realized:.0f}%")
    if road_pct > 24.0:
        warnings.append(f"high-road-area:{road_pct:.1f}%")
    if max_overlap > 1.0:
        warnings.append(f"road-overlap:{max_overlap:.1f}m2")
    if max_distance > 24.0:
        warnings.append(f"far-from-road:{max_distance:.1f}m")
    warnings.extend(parcel_warnings)
    if not _payload_ok(payload):
        warnings.append("bad-canvas-payload")
    snapshot = out_dir / f"{case['site']}_{case['usage']}_{case['pattern']}_{case['planner']}.png"
    _draw_patch(ns, patch, snapshot, f"{case['site']} / {case['usage']} / {case['planner']} / {skeleton}")
    ok = not warnings
    return CanvasAuditRow(
        site=case["site"],
        usage=case["usage"],
        pattern=case["pattern"],
        planner=case["planner"],
        skeleton=skeleton,
        ok=ok,
        parcels=len(parcels),
        roads=len(segments),
        realized_pct=round(realized, 1),
        road_area_pct=round(road_pct, 1),
        max_deep_road_overlap_m2=round(max_overlap, 1),
        max_road_distance_m=round(max_distance, 1),
        canvas_payload_ok=_payload_ok(payload),
        min_function_coverage_pct=round(min_function_coverage, 1),
        min_short_side_m=round(min_short_side, 1),
        max_aspect_ratio=round(max_aspect, 1),
        min_road_frontage_m=round(min_frontage, 1),
        warnings=tuple(warnings),
        snapshot=str(snapshot),
    )


def run_audit(mode: str, out_dir: Path) -> list[CanvasAuditRow]:
    ns = _load_app_helpers()
    cases = CASES[:1] if mode == "single" else CASES
    return [audit_case(ns, case, out_dir) for case in cases]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Traffic & Trassen Lab canvas payloads and snapshots.")
    parser.add_argument("--mode", choices=("single", "sweep"), default="sweep")
    parser.add_argument("--out-dir", type=Path, default=Path("side_projects/traffic_trassen_lab/artifacts/canvas_audit"))
    args = parser.parse_args()
    rows = run_audit(args.mode, args.out_dir)
    failures = [row for row in rows if not row.ok]
    print(f"canvas_audit cases={len(rows)} failed={len(failures)} snapshots={args.out_dir}")
    header = "site      usage      pattern   planner  ok skeleton       area% road% dist overlap cov_min side_min aspect front parcels roads warnings"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.site:9s} {row.usage:10s} {row.pattern:8s} {row.planner:8s} "
            f"{'yes' if row.ok else 'NO ':3s} {row.skeleton[:13]:13s} "
            f"{row.realized_pct:5.1f} {row.road_area_pct:5.1f} {row.max_road_distance_m:5.1f} "
            f"{row.max_deep_road_overlap_m2:7.1f} {row.min_function_coverage_pct:7.1f} "
            f"{row.min_short_side_m:8.1f} {row.max_aspect_ratio:6.1f} {row.min_road_frontage_m:5.1f} "
            f"{row.parcels:7d} {row.roads:5d} "
            f"{','.join(row.warnings) if row.warnings else '-'}"
        )
        print(f"  snapshot: {row.snapshot}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

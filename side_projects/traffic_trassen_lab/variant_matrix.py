from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from placement_matrix import PATTERNS, SITES, _build_functions, _load_app_helpers, _mode_scope, _point_for
from road_matrix import ACCESS_VARIANTS, _make_access
from variant_planner import generate_variant_candidates, score_to_dict


TARGETED_CASES: tuple[tuple[str, str, str, str], ...] = (
    ("compact", "production", "balanced", "single_both"),
    ("compact", "production", "diagonal", "single_both"),
    ("compact", "logistics", "balanced", "single_both"),
    ("compact", "logistics", "diagonal", "single_both"),
    ("long", "production", "balanced", "single_both"),
    ("long", "logistics", "diagonal", "single_both"),
    ("irregular", "production", "diagonal", "single_both"),
    ("irregular", "mixed", "diagonal", "single_both"),
)


def _set_placements(ns: dict[str, Any], site: str, functions: list[dict[str, Any]], pattern: str, setback_m: float) -> None:
    placement_polygon = ns["_build_boundary"](site, setback_m)
    pattern_points = PATTERNS[pattern]
    placements = {site_id: {} for site_id in SITES}
    for index, function in enumerate(functions):
        anchor = _point_for(ns, placement_polygon, *pattern_points[index % len(pattern_points)])
        placements[site][function["id"]] = {"anchor": anchor, "order": index + 1}
    ns["_placement_store"] = lambda placements=placements: placements


def _run_case(ns: dict[str, Any], site: str, usage: str, pattern: str, access_variant: str, setback_m: float, spacing_m: float) -> dict[str, Any]:
    functions = _build_functions(ns, usage)
    _set_placements(ns, site, functions, pattern, setback_m)
    access_points = [
        _make_access(ns, site, u, v, access_type, index)
        for index, (u, v, access_type) in enumerate(ACCESS_VARIANTS[access_variant], start=1)
    ]
    with contextlib.redirect_stderr(io.StringIO()):
        variants = generate_variant_candidates(ns, site, functions, access_points, setback_m, spacing_m, True)
    best_score, _ = variants[0]
    return {
        "site": site,
        "usage": usage,
        "pattern": pattern,
        "access_variant": access_variant,
        "best": score_to_dict(best_score),
        "variants": [score_to_dict(score) for score, _patch in variants],
    }


def _cases_for_mode(mode: str) -> list[tuple[str, str, str, str]]:
    if mode == "targeted":
        return list(TARGETED_CASES)
    sites, usages, patterns = _mode_scope(mode)
    access_variants = ("single_both",) if mode != "stress" else tuple(ACCESS_VARIANTS)
    return [(site, usage, pattern, access) for site in sites for usage in usages for pattern in patterns for access in access_variants]


def run_matrix(mode: str, setback_m: float, spacing_m: float, max_cases: int | None = None) -> list[dict[str, Any]]:
    ns = _load_app_helpers()
    cases = _cases_for_mode(mode)
    if max_cases is not None:
        cases = cases[:max_cases]
    return [_run_case(ns, site, usage, pattern, access, setback_m, spacing_m) for site, usage, pattern, access in cases]


def _print_results(results: list[dict[str, Any]]) -> None:
    failures = [row for row in results if not row["best"]["hard_ok"]]
    print(f"cases={len(results)} hard_failures={len(failures)}")
    header = "site      usage      pattern   ok best          score realized road% dist overlap warnings"
    print(header)
    print("-" * len(header))
    for row in results:
        best = row["best"]
        warnings = ",".join(best["warnings"][:3]) if best["warnings"] else "-"
        if len(best["warnings"]) > 3:
            warnings += ",..."
        print(
            f"{row['site']:9s} {row['usage']:10s} {row['pattern']:8s} "
            f"{'yes' if best['hard_ok'] else 'NO ':3s} {best['skeleton']:13s} "
            f"{best['score']:7.0f} {best['realized_pct']:8.1f} {best['road_area_pct']:5.1f} "
            f"{best['max_road_distance_m']:5.1f} {best['max_deep_overlap_m2']:7.1f} {warnings}"
        )
        for variant in row["variants"][:3]:
            print(
                f"  - {variant['skeleton']:13s} score={variant['score']:7.0f} "
                f"ok={'yes' if variant['hard_ok'] else 'NO '} area={variant['realized_pct']:5.1f}% "
                f"road={variant['road_area_pct']:4.1f}% dist={variant['max_road_distance_m']:4.1f} "
                f"warn={','.join(variant['warnings'][:2]) if variant['warnings'] else '-'}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Traffic & Trassen Lab skeleton variant checks.")
    parser.add_argument("--mode", choices=("smoke", "targeted", "standard", "stress"), default="targeted")
    parser.add_argument("--setback", type=float, default=8.0)
    parser.add_argument("--spacing", type=float, default=5.0)
    parser.add_argument("--json", type=Path, help="Optional path for JSON result export.")
    parser.add_argument("--max-cases", type=int, default=None, help="Limit number of cases for fast iteration.")
    args = parser.parse_args()

    results = run_matrix(args.mode, args.setback, args.spacing, args.max_cases)
    _print_results(results)
    if args.json:
        args.json.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    return 1 if any(not row["best"]["hard_ok"] for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

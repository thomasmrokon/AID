from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from shapely.geometry import Point, Polygon
from streamlit.testing.v1 import AppTest

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR))

from engine import DEMO_SITES, project_point_to_site_boundary  # noqa: E402

APP_PATH = LAB_DIR / "app.py"

USAGE_FUNCTION_IDS: dict[str, tuple[str, ...]] = {
    "production": ("prod_1", "warehouse_1", "office_1", "yard_1", "parking_1"),
    "logistics": ("hall_1", "yard_1", "office_1", "parking_1"),
    "office": ("office_1", "parking_1", "delivery_1", "tech_1"),
    "datacenter": ("dc_1", "tech_1", "security_1", "parking_1"),
    "mixed": ("prod_1", "warehouse_1", "office_1", "yard_1", "parking_1"),
}

PATTERNS: dict[str, tuple[tuple[float, float], ...]] = {
    "balanced": ((0.30, 0.72), (0.30, 0.30), (0.72, 0.70), (0.58, 0.48), (0.72, 0.30)),
    "diagonal": ((0.18, 0.78), (0.36, 0.64), (0.55, 0.48), (0.72, 0.34), (0.82, 0.22)),
}

CASES: tuple[dict[str, str], ...] = (
    {"site": "compact", "usage": "production", "pattern": "balanced", "planner": "variants"},
    {"site": "compact", "usage": "logistics", "pattern": "balanced", "planner": "variants"},
    {"site": "long", "usage": "production", "pattern": "balanced", "planner": "variants"},
    {"site": "irregular", "usage": "mixed", "pattern": "diagonal", "planner": "variants"},
)


def _point_for(site: str, u: float, v: float) -> tuple[float, float]:
    polygon = Polygon(DEMO_SITES[site].polygon)
    minx, miny, maxx, maxy = polygon.bounds
    point = Point(minx + (maxx - minx) * u, miny + (maxy - miny) * v)
    if polygon.buffer(0.01).contains(point):
        return (round(float(point.x), 2), round(float(point.y), 2))
    nearest = polygon.representative_point()
    return (round(float(nearest.x), 2), round(float(nearest.y), 2))


def _access_for(site: str) -> dict[str, Any]:
    polygon = Polygon(DEMO_SITES[site].polygon)
    minx, miny, maxx, maxy = polygon.bounds
    projected = project_point_to_site_boundary(DEMO_SITES[site], ((minx + maxx) / 2.0, maxy))
    return {"id": "Z1", "access_type": "both", **projected}


def _placements_for(site: str, usage: str, pattern: str) -> dict[str, dict[str, Any]]:
    points = PATTERNS[pattern]
    placements: dict[str, dict[str, Any]] = {}
    for index, fid in enumerate(USAGE_FUNCTION_IDS[usage], start=1):
        placements[fid] = {"anchor": _point_for(site, *points[(index - 1) % len(points)]), "order": index}
    return placements


def _set_widget_value(widgets: Any, label: str, value: Any) -> bool:
    for widget in widgets:
        if widget.label == label:
            widget.set_value(value)
            return True
    return False


def _click_button(app: AppTest, label: str) -> bool:
    for button in app.button:
        if button.label == label:
            button.click()
            return True
    return False


def _print_exceptions(app: AppTest) -> None:
    for exc in app.exception:
        print(exc.value)


def run_case(case: dict[str, str]) -> bool:
    site = case["site"]
    usage = case["usage"]
    pattern = case["pattern"]
    planner = case["planner"]
    app = AppTest.from_file(str(APP_PATH), default_timeout=140)
    app.session_state["lab_access_points"] = {site: [_access_for(site)]}
    app.session_state["lab_function_placements"] = {site: _placements_for(site, usage, pattern)}

    app.run()
    if app.exception:
        print(f"FAIL initial {site}/{usage}/{planner}")
        _print_exceptions(app)
        return False

    _set_widget_value(app.selectbox, "Grundstück", site)
    _set_widget_value(app.selectbox, "Nutzung", usage)
    _set_widget_value(app.radio, "Arbeitsmodus", "Optimierung")
    app.run()
    if app.exception:
        print(f"FAIL optimize-mode {site}/{usage}/{planner}")
        _print_exceptions(app)
        return False

    if not _click_button(app, "Erschließung berechnen"):
        print(f"FAIL button-missing {site}/{usage}/{planner}")
        return False
    app.run()
    if app.exception:
        print(f"FAIL calculate {site}/{usage}/{planner}")
        _print_exceptions(app)
        return False

    if planner == "variants" and len(app.dataframe) < 1:
        print(f"FAIL no-variant-table {site}/{usage}/{planner}")
        return False
    print(f"OK {site}/{usage}/{pattern}/{planner}: dataframes={len(app.dataframe)}")
    return True


def run_ui_smoke(mode: str = "single") -> int:
    cases = CASES[:1] if mode == "single" else CASES
    results = [run_case(case) for case in cases]
    failed = len([item for item in results if not item])
    print(f"ui_smoke cases={len(results)} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run interactive Streamlit UI smoke checks for Traffic & Trassen Lab.")
    parser.add_argument("--mode", choices=("single", "sweep"), default="single")
    args = parser.parse_args()
    raise SystemExit(run_ui_smoke(args.mode))

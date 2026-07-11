from __future__ import annotations

import heapq
import math
import sys
from html import escape
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from shapely.geometry import LineString, Point, Polygon, box

APP_DIR = Path(__file__).parent if "__file__" in globals() else Path("side_projects/traffic_trassen_lab").resolve()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from engine import DEMO_SITES, project_point_to_site_boundary
from variant_planner import generate_variant_candidates, score_to_dict

Point2D = tuple[float, float]

ACCESS_TYPE_LABELS = {"both": "PKW + LKW", "pkw": "PKW", "lkw": "LKW"}
ACCESS_TYPE_COLORS = {"both": "#B91C1C", "pkw": "#2563EB", "lkw": "#D97706"}
ACCESS_TYPE_WIDTHS_M = {"both": 7.5, "pkw": 3.5, "lkw": 7.5}

USAGE_LABELS = {
    "production": "Produktion / Montage",
    "logistics": "Logistik / Distribution",
    "office": "Büro / Verwaltung",
    "datacenter": "Datacenter / kritische Infrastruktur",
    "mixed": "Gemischter Industriecampus",
}
TRAFFIC_LEVEL_LABELS = {"low": "niedrig", "medium": "mittel", "high": "hoch"}
SEPARATION_LABELS = {"shared": "gemeinsame Führung möglich", "separate": "PKW und LKW trennen"}
USAGE_DEFAULTS = {
    "production": {"pkw": "medium", "lkw": "medium", "separate": False},
    "logistics": {"pkw": "medium", "lkw": "high", "separate": True},
    "office": {"pkw": "high", "lkw": "low", "separate": False},
    "datacenter": {"pkw": "low", "lkw": "medium", "separate": True},
    "mixed": {"pkw": "high", "lkw": "medium", "separate": True},
}

FUNCTION_COLORS = {"building": "#4F7CAC", "outdoor": "#C88A3D", "parking": "#6C8F5F", "technical": "#7B61FF"}
FUNCTION_KEY_COLORS = {
    "prod": "#2563EB",
    "warehouse": "#0F766E",
    "hall": "#2563EB",
    "office": "#7C3AED",
    "yard": "#D97706",
    "parking": "#4D7C0F",
    "outside": "#A16207",
    "dc": "#DC2626",
    "tech": "#7B61FF",
    "security": "#BE123C",
    "delivery": "#EA580C",
}
FUNCTION_KIND_LABELS = {"building": "Gebäude", "outdoor": "Außenfläche", "parking": "Stellplätze", "technical": "Technik"}
FUNCTION_ASPECTS = {"building": 1.55, "outdoor": 1.8, "parking": 2.35, "technical": 1.25}
SHAPE_PREFERENCE_LABELS = {"auto": "automatisch", "compact": "kompakt", "wide": "breit", "tall": "hoch"}
ALIGNMENT_LABELS = {"auto": "automatisch", "free": "frei", "south": "Südkante", "north": "Nordkante", "west": "Westkante", "east": "Ostkante"}
PRIORITY_OPTIONS = [str(value) for value in range(1, 11)] + ["optional"]
ROAD_FLOW_LABELS = {"auto": "automatisch", "shared": "PKW + LKW gemeinsam", "separate": "PKW und LKW getrennt"}
ROAD_NETWORK_LABELS = {"auto": "automatisch", "minimal": "minimaler Anschluss", "spine": "Spange / Rückgrat", "loop": "Ring / Umfahrung"}
ROAD_SERVICE_LABELS = {"auto": "automatisch", "central_yard": "zentraler Andienhof", "per_building": "je Gebäude anbinden"}
ROAD_PARKING_LABELS = {"auto": "automatisch", "entrance": "am Eingang", "office": "am Büro", "edge": "flächensparend am Rand"}
ROAD_OBJECTIVE_LABELS = {"balanced": "ausgewogen", "area": "Flächen maximieren", "traffic": "Verkehr robust"}
BUILDING_BOUNDARY_KINDS = {"building", "technical"}
GEOMETRY_GENERATOR_PROFILES = {
    "prod": {"label": "Produktionshalle", "min_width_m": 24.0, "min_depth_m": 24.0, "aspects": (1.8, 2.4, 1.35), "default_shape": "wide"},
    "warehouse": {"label": "Lagerhalle", "min_width_m": 18.0, "min_depth_m": 18.0, "aspects": (2.2, 3.0, 1.5), "default_shape": "wide"},
    "hall": {"label": "Logistikhalle", "min_width_m": 30.0, "min_depth_m": 30.0, "aspects": (2.4, 3.2, 1.7), "default_shape": "wide"},
    "office": {"label": "Büro", "min_width_m": 12.0, "min_depth_m": 10.0, "aspects": (1.0, 1.25, 0.8, 1.6), "default_shape": "compact"},
    "yard": {"label": "Andienhof LKW", "min_width_m": 28.0, "min_depth_m": 24.0, "aspects": (2.0, 2.8, 3.6, 1.4), "default_shape": "wide"},
    "parking": {"label": "PKW-Stellplatzfeld", "min_width_m": 16.0, "min_depth_m": 18.0, "aspects": (2.8, 4.0, 1.8, 5.0), "default_shape": "wide"},
    "outside": {"label": "Außenlager", "min_width_m": 20.0, "min_depth_m": 18.0, "aspects": (2.2, 3.0, 1.5), "default_shape": "wide"},
    "dc": {"label": "Datacenter", "min_width_m": 28.0, "min_depth_m": 28.0, "aspects": (1.35, 1.0, 1.8), "default_shape": "compact"},
    "tech": {"label": "Technikfläche", "min_width_m": 12.0, "min_depth_m": 12.0, "aspects": (1.0, 1.4, 0.7), "default_shape": "compact"},
    "security": {"label": "Sicherheitszone", "min_width_m": 14.0, "min_depth_m": 14.0, "aspects": (1.0, 1.5, 0.7), "default_shape": "compact"},
    "delivery": {"label": "Kleinanlieferung", "min_width_m": 12.0, "min_depth_m": 16.0, "aspects": (1.6, 2.2, 1.0), "default_shape": "wide"},
}
GEOMETRY_KIND_FALLBACKS = {
    "building": {"label": "Gebäude", "min_width_m": 12.0, "min_depth_m": 10.0, "aspects": (1.55, 1.0, 2.2), "default_shape": "compact"},
    "outdoor": {"label": "Außenfläche", "min_width_m": 18.0, "min_depth_m": 14.0, "aspects": (1.8, 2.6, 1.0), "default_shape": "wide"},
    "parking": {"label": "Stellplatzfeld", "min_width_m": 16.0, "min_depth_m": 18.0, "aspects": (2.8, 4.0, 1.8), "default_shape": "wide"},
    "technical": {"label": "Technik", "min_width_m": 10.0, "min_depth_m": 10.0, "aspects": (1.0, 1.3, 0.75), "default_shape": "compact"},
}
COMPONENT_DIR = APP_DIR / "drag_plan_component"
drag_plan_component = None


def _drag_plan_component(*, payload: dict[str, Any], key: str, default=None):
    global drag_plan_component
    if drag_plan_component is None:
        drag_plan_component = components.declare_component("traffic_drag_plan", path=str(COMPONENT_DIR))
    return drag_plan_component(payload=payload, height=780, key=key, default=default)
FUNCTION_LIBRARY = {
    "prod": {"name": "Produktionshalle", "kind": "building", "default_area": 2800, "category": "Gebäude"},
    "warehouse": {"name": "Lager", "kind": "building", "default_area": 1200, "category": "Gebäude"},
    "hall": {"name": "Logistikhalle", "kind": "building", "default_area": 3600, "category": "Gebäude"},
    "office": {"name": "Büro", "kind": "building", "default_area": 600, "category": "Gebäude"},
    "yard": {"name": "Andienhof", "kind": "outdoor", "default_area": 900, "category": "Außenflächen"},
    "parking": {"name": "Stellplätze", "kind": "parking", "default_area": 700, "category": "Verkehr"},
    "outside": {"name": "Außenlager", "kind": "outdoor", "default_area": 900, "category": "Außenflächen"},
    "delivery": {"name": "Anlieferung", "kind": "outdoor", "default_area": 250, "category": "Verkehr"},
    "dc": {"name": "Datacenter", "kind": "building", "default_area": 2600, "category": "Gebäude"},
    "tech": {"name": "Technikfläche", "kind": "technical", "default_area": 180, "category": "Technik"},
    "security": {"name": "Sicherheitszone", "kind": "outdoor", "default_area": 800, "category": "Sicherheit"},
}

USAGE_SCENARIOS = {
    "production": [
        {"key": "prod", "count": 1, "area": 2800, "priority": 1},
        {"key": "warehouse", "count": 1, "area": 1200, "priority": 2},
        {"key": "office", "count": 1, "area": 600, "priority": 3},
        {"key": "yard", "count": 1, "area": 900, "priority": 4},
        {"key": "parking", "count": 1, "area": 700, "priority": 5},
    ],
    "logistics": [
        {"key": "hall", "count": 1, "area": 3600, "priority": 1},
        {"key": "yard", "count": 1, "area": 1600, "priority": 2},
        {"key": "office", "count": 1, "area": 450, "priority": 3},
        {"key": "parking", "count": 1, "area": 650, "priority": 4},
        {"key": "outside", "count": 0, "area": 900, "priority": "optional"},
    ],
    "office": [
        {"key": "office", "name": "Bürogebäude", "count": 1, "area": 1800, "priority": 1},
        {"key": "parking", "count": 1, "area": 1400, "priority": 2},
        {"key": "delivery", "count": 1, "area": 250, "priority": 3},
        {"key": "tech", "count": 1, "area": 180, "priority": 4},
    ],
    "datacenter": [
        {"key": "dc", "count": 1, "area": 2600, "priority": 1},
        {"key": "tech", "name": "Technikhof", "count": 1, "area": 900, "priority": 2},
        {"key": "security", "count": 1, "area": 800, "priority": 3},
        {"key": "parking", "count": 1, "area": 350, "priority": 4},
    ],
    "mixed": [
        {"key": "prod", "count": 1, "area": 1800, "priority": 1},
        {"key": "warehouse", "count": 1, "area": 1200, "priority": 2},
        {"key": "office", "count": 1, "area": 800, "priority": 3},
        {"key": "yard", "count": 1, "area": 900, "priority": 4},
        {"key": "parking", "count": 1, "area": 900, "priority": 5},
    ],
}


def _library_template(key: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    item = FUNCTION_LIBRARY[key]
    return {
        "key": key,
        "name": str(overrides.get("name", item["name"])),
        "kind": item["kind"],
        "count": int(overrides.get("count", 1)),
        "area": float(overrides.get("area", item["default_area"])),
        "priority": overrides.get("priority", 99),
        "category": item.get("category", FUNCTION_KIND_LABELS.get(str(item["kind"]), "Funktion")),
    }


def _scenario_defaults(usage: str) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in USAGE_SCENARIOS[usage]}


def _scenario_keys(usage: str) -> list[str]:
    return [item["key"] for item in USAGE_SCENARIOS[usage]]


def _templates_from_scenarios() -> dict[str, list[dict[str, Any]]]:
    return {usage: [_library_template(item["key"], item) for item in items] for usage, items in USAGE_SCENARIOS.items()}


FUNCTION_TEMPLATES = _templates_from_scenarios()


def _site_area(site_id: str) -> float:
    return round(float(Polygon(DEMO_SITES[site_id].polygon).area), 1)


def _site_polygon(site_id: str) -> Polygon:
    return Polygon(DEMO_SITES[site_id].polygon).buffer(0)


def _function_color(function: dict[str, Any]) -> str:
    key = str(function.get("key", ""))
    if key in FUNCTION_KEY_COLORS:
        return FUNCTION_KEY_COLORS[key]
    return FUNCTION_COLORS.get(str(function.get("kind", "")), "#4F7CAC")


def _function_chip_marker(function: dict[str, Any], active: bool) -> dict[str, Any]:
    return {
        "symbol": "square",
        "size": 18 if active else 13,
        "color": _function_color(function),
        "line": {"color": "#111827", "width": 2 if active else 1},
    }


def _chip_status(function_id: str, placements: dict[str, Any], patchwork: dict[str, Any]) -> str:
    if function_id not in placements:
        return "offen"
    if any(parcel["function"]["id"] == function_id for parcel in patchwork.get("parcels", [])):
        return "berechnet"
    if any(item["function"]["id"] == function_id for item in patchwork.get("missing", [])):
        return "nicht platzierbar"
    return "gesetzt"


def _build_boundary(site_id: str, setback_m: float) -> Polygon:
    poly = _site_polygon(site_id)
    boundary = poly.buffer(-float(setback_m), join_style=2)
    return boundary if not boundary.is_empty and boundary.area > 50 else poly


def _access_store() -> dict[str, list[dict[str, Any]]]:
    if "lab_access_points" not in st.session_state:
        st.session_state.lab_access_points = {}
    return st.session_state.lab_access_points


def _placement_store() -> dict[str, dict[str, dict[str, Any]]]:
    if "lab_function_placements" not in st.session_state:
        st.session_state.lab_function_placements = {}
    return st.session_state.lab_function_placements


def _function_settings_store() -> dict[str, dict[str, dict[str, float | int | str]]]:
    if "lab_function_settings" not in st.session_state:
        st.session_state.lab_function_settings = {}
    return st.session_state.lab_function_settings


def _road_plan_store() -> dict[str, dict[str, Any]]:
    if "lab_road_plans" not in st.session_state:
        st.session_state.lab_road_plans = {}
    return st.session_state.lab_road_plans


def _road_plan_signature(site_id: str, usage: str, functions: list[dict[str, Any]], placements: dict[str, Any], access_points: list[dict[str, Any]], options: dict[str, str], setback_m: float, spacing_m: float, equalize_repeated: bool) -> tuple[Any, ...]:
    function_sig = tuple(
        (fn["id"], str(fn.get("key", "")), round(float(fn.get("area_m2", 0.0)), 2), str(fn.get("priority", "")))
        for fn in functions
    )
    placement_sig = tuple(
        sorted(
            (fid, round(float(value["anchor"][0]), 2), round(float(value["anchor"][1]), 2), int(value.get("order", 0)))
            for fid, value in placements.items()
            if any(fn["id"] == fid for fn in functions)
        )
    )
    access_sig = tuple(
        (item["id"], str(item.get("access_type", "both")), round(float(item["point"][0]), 2), round(float(item["point"][1]), 2))
        for item in access_points
    )
    options_sig = tuple(sorted((key, str(value)) for key, value in options.items()))
    geometry_sig = (round(float(setback_m), 2), round(float(spacing_m), 2), bool(equalize_repeated))
    return (site_id, usage, function_sig, placement_sig, access_sig, options_sig, geometry_sig)


def _function_key_store() -> dict[str, list[str]]:
    if "lab_function_keys_by_usage" not in st.session_state:
        st.session_state.lab_function_keys_by_usage = {}
    return st.session_state.lab_function_keys_by_usage


def _function_keys_for_usage(usage: str) -> list[str]:
    store = _function_key_store()
    keys = store.setdefault(usage, list(_scenario_keys(usage)))
    cleaned = [key for key in keys if key in FUNCTION_LIBRARY]
    if cleaned != keys:
        store[usage] = cleaned
    return store[usage]


def _function_templates_for_usage(usage: str) -> list[dict[str, Any]]:
    defaults = _scenario_defaults(usage)
    return [_library_template(key, defaults.get(key, {})) for key in _function_keys_for_usage(usage)]


def _add_function_to_usage(usage: str, key: str) -> None:
    if key not in FUNCTION_LIBRARY:
        return
    keys = _function_keys_for_usage(usage)
    if key not in keys:
        keys.append(key)
    item = _function_settings_store().setdefault(usage, {}).setdefault(key, {})
    template = _library_template(key)
    item.setdefault("count", 1)
    item.setdefault("area", template["area"])
    item.setdefault("priority", min(10, len(keys)))
    item.setdefault("shape", "auto")
    item.setdefault("alignment", "auto")


def _remove_function_from_usage(usage: str, key: str) -> None:
    keys = _function_keys_for_usage(usage)
    if key in keys:
        keys.remove(key)
    _function_settings_store().setdefault(usage, {}).pop(key, None)
    prefix = f"{key}_"
    for site_store in _placement_store().values():
        for function_id in list(site_store):
            if function_id.startswith(prefix):
                site_store.pop(function_id, None)


def _reset_usage_functions(usage: str) -> None:
    _function_key_store()[usage] = list(_scenario_keys(usage))
    _function_settings_store().pop(usage, None)


def _add_access(site_id: str, point: Point2D) -> None:
    projected = project_point_to_site_boundary(DEMO_SITES[site_id], point)
    store = _access_store()
    items = list(store.get(site_id, []))
    px, py = projected["point"]
    duplicate = any(abs(item["point"][0] - px) < 0.5 and abs(item["point"][1] - py) < 0.5 for item in items)
    if not duplicate:
        items.append({"id": f"Z{len(items) + 1}", "access_type": "both", **projected})
        store[site_id] = items


def _delete_access(site_id: str, access_id: str) -> None:
    store = _access_store()
    remaining = [item for item in store.get(site_id, []) if item["id"] != access_id]
    for idx, item in enumerate(remaining, start=1):
        item["id"] = f"Z{idx}"
    store[site_id] = remaining


def _update_access_type(site_id: str, access_id: str, access_type: str) -> None:
    items = list(_access_store().get(site_id, []))
    for item in items:
        if item["id"] == access_id:
            item["access_type"] = access_type
            break
    _access_store()[site_id] = items


def _normalize_access_points(site_id: str) -> list[dict[str, Any]]:
    items = list(_access_store().get(site_id, []))
    for item in items:
        if item.get("access_type") not in ACCESS_TYPE_LABELS:
            item["access_type"] = "both"
    _access_store()[site_id] = items
    return items


def _access_width_m(access_type: str) -> float:
    return ACCESS_TYPE_WIDTHS_M.get(access_type, ACCESS_TYPE_WIDTHS_M["both"])


def _access_edge_segment(access: dict[str, Any]) -> tuple[Point2D, Point2D]:
    width = _access_width_m(access.get("access_type", "both"))
    (x0, y0), (x1, y1) = access["segment"]
    cx, cy = access["point"]
    dx, dy = x1 - x0, y1 - y0
    edge_length = max(0.01, math.hypot(dx, dy))
    if edge_length <= width:
        return (x0, y0), (x1, y1)
    tx, ty = dx / edge_length, dy / edge_length
    center_t = max(0.0, min(edge_length, (cx - x0) * tx + (cy - y0) * ty))
    start_t = center_t - width / 2
    end_t = center_t + width / 2
    if start_t < 0:
        end_t -= start_t
        start_t = 0.0
    if end_t > edge_length:
        start_t -= end_t - edge_length
        end_t = edge_length
    start_t = max(0.0, start_t)
    return (x0 + tx * start_t, y0 + ty * start_t), (x0 + tx * end_t, y0 + ty * end_t)


def _sample_boundary(site_id: str, spacing_m: float = 2.0) -> list[Point2D]:
    site = DEMO_SITES[site_id]
    coords = list(site.polygon) + [site.polygon[0]]
    samples: list[Point2D] = []
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length / spacing_m))
        for idx in range(steps + 1):
            t = idx / steps
            point = (round(x0 + (x1 - x0) * t, 2), round(y0 + (y1 - y0) * t, 2))
            if not samples or samples[-1] != point:
                samples.append(point)
    return samples


def _sample_interior(site_id: str, spacing_m: float = 2.0) -> list[Point2D]:
    poly = _site_polygon(site_id)
    minx, miny, maxx, maxy = poly.bounds
    samples: list[Point2D] = []
    y = miny + spacing_m / 2
    while y <= maxy:
        x = minx + spacing_m / 2
        while x <= maxx:
            if poly.contains(Point(x, y)):
                samples.append((round(x, 2), round(y, 2)))
            x += spacing_m
        y += spacing_m
    return samples


def _nearest_sample(point: Point2D, samples: list[Point2D]) -> Point2D:
    if not samples:
        return point
    return min(samples, key=lambda sample: math.dist(point, sample))


def _selected_plot_point(selection) -> dict[str, Any] | None:
    if not selection:
        return None
    selected = getattr(selection, "selection", None) or selection.get("selection", {})
    points = selected.get("points", []) if isinstance(selected, dict) else getattr(selected, "points", [])
    if not points:
        return None
    parsed: list[dict[str, Any]] = []
    for item in points:
        get_value = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
        x = get_value("x")
        y = get_value("y")
        if x is None or y is None:
            continue
        customdata = get_value("customdata", None)
        if isinstance(customdata, (list, tuple)):
            event_kind = customdata[0] if customdata else None
            event_id = customdata[1] if len(customdata) > 1 else None
        else:
            event_kind = customdata
            event_id = None
        parsed.append({"point": (float(x), float(y)), "kind": event_kind, "id": event_id})
    if not parsed:
        return None
    for preferred_kind in ("function_anchor", "function_rect"):
        for item in reversed(parsed):
            if item["kind"] == preferred_kind:
                return item
    return parsed[-1]


def _derive_traffic_requirements(usage: str, pkw_level: str, lkw_level: str, separation: str, access_points: list[dict[str, Any]]) -> dict[str, object]:
    has_pkw = any(item.get("access_type") in {"pkw", "both"} for item in access_points)
    has_lkw = any(item.get("access_type") in {"lkw", "both"} for item in access_points)
    needs_pkw = pkw_level != "low" or usage in {"office", "mixed", "production"}
    needs_lkw = lkw_level != "low" or usage in {"production", "logistics", "datacenter", "mixed"}
    return {
        "has_pkw": has_pkw,
        "has_lkw": has_lkw,
        "needs_pkw": needs_pkw,
        "needs_lkw": needs_lkw,
        "pkw_ok": (not needs_pkw) or has_pkw,
        "lkw_ok": (not needs_lkw) or has_lkw,
        "separate_recommended": separation == "separate" or lkw_level == "high" or bool(USAGE_DEFAULTS[usage]["separate"]),
    }


def _traffic_requirement_rows(requirements: dict[str, object]) -> list[dict[str, str]]:
    yes_no = lambda value: "ja" if value else "nein"
    return [
        {"Prüfung": "PKW-Zufahrt erforderlich", "Wert": yes_no(requirements["needs_pkw"])},
        {"Prüfung": "PKW-Zufahrt vorhanden", "Wert": yes_no(requirements["has_pkw"])},
        {"Prüfung": "LKW-Zufahrt erforderlich", "Wert": yes_no(requirements["needs_lkw"])},
        {"Prüfung": "LKW-Zufahrt vorhanden", "Wert": yes_no(requirements["has_lkw"])},
        {"Prüfung": "PKW/LKW-Trennung empfohlen", "Wert": yes_no(requirements["separate_recommended"])},
    ]


def _geometry_profile(function: dict[str, Any]) -> dict[str, Any]:
    key = str(function.get("key", ""))
    kind = str(function.get("kind", ""))
    profile = GEOMETRY_GENERATOR_PROFILES.get(key) or GEOMETRY_KIND_FALLBACKS.get(kind) or GEOMETRY_KIND_FALLBACKS["building"]
    return dict(profile)


def _geometry_generator_label(function: dict[str, Any]) -> str:
    return str(_geometry_profile(function).get("label", FUNCTION_KIND_LABELS.get(str(function.get("kind", "")), "Standard")))


def _unique_aspects(aspects: list[float] | tuple[float, ...]) -> list[float]:
    unique: list[float] = []
    for aspect in aspects:
        value = float(aspect)
        if value > 0 and all(abs(value - existing) > 0.03 for existing in unique):
            unique.append(value)
    return unique


def _auto_shape_for_function(function: dict[str, Any]) -> str:
    shape = str(_geometry_profile(function).get("default_shape", "compact"))
    return shape if shape in SHAPE_PREFERENCE_LABELS and shape != "auto" else "compact"


def _resolved_shape(function: dict[str, Any]) -> str:
    shape = str(function.get("shape", "auto"))
    if shape == "auto" or shape not in SHAPE_PREFERENCE_LABELS:
        return _auto_shape_for_function(function)
    return shape


def _shape_label(function: dict[str, Any]) -> str:
    shape = str(function.get("shape", "auto"))
    if shape == "auto" or shape not in SHAPE_PREFERENCE_LABELS:
        return f"{SHAPE_PREFERENCE_LABELS[_resolved_shape(function)]} auto"
    return SHAPE_PREFERENCE_LABELS[shape]


def _resolved_alignment(rect: dict[str, Any]) -> str:
    alignment = str(rect["function"].get("alignment", "auto"))
    if alignment != "auto":
        return alignment if alignment in ALIGNMENT_LABELS else "free"
    if not _is_building_function(rect["function"]):
        return "free"
    ax, ay = rect["anchor"]
    centered = dict(rect)
    centered["x"] = ax
    centered["y"] = ay
    # In the interactive workflow the placeholder is the intended center. Auto
    # alignment only takes over when a centered rectangle would leave the buildable
    # area; otherwise it feels like the rectangle ignores the user's placement.
    if _rect_geometry(centered).difference(rect["allowed"].buffer(0.01)).area <= 0.5:
        return "free"
    minx, miny, maxx, maxy = rect["allowed"].bounds
    distances = {"south": abs(ay - miny), "north": abs(maxy - ay), "west": abs(ax - minx), "east": abs(maxx - ax)}
    side, distance = min(distances.items(), key=lambda item: item[1])
    threshold = max(10.0, min(maxx - minx, maxy - miny) * 0.22)
    return side if distance <= threshold else "free"


def _alignment_label_for_function(function: dict[str, Any]) -> str:
    alignment = str(function.get("alignment", "auto"))
    return ALIGNMENT_LABELS.get(alignment, ALIGNMENT_LABELS["auto"])


def _priority_value(value: Any) -> int:
    return 99 if str(value) == "optional" else int(value)


def _is_optional_function(function: dict[str, Any]) -> bool:
    return str(function.get("priority")) == "optional"


def _priority_label(value: Any) -> str:
    return "optional" if str(value) == "optional" else str(int(value))


def _area_fractions_for_function(function: dict[str, Any]) -> tuple[float, ...]:
    if _is_optional_function(function):
        return AREA_FRACTIONS
    priority = _priority_value(function.get("priority", 99))
    if priority <= 2:
        return AREA_FRACTIONS + (0.15, 0.1)
    if priority <= 5:
        return AREA_FRACTIONS + (0.15, 0.1, 0.075)
    return AREA_FRACTIONS + (0.15, 0.1, 0.075, 0.05)


def _function_settings(usage: str) -> dict[str, dict[str, float | int | str]]:
    settings = _function_settings_store().setdefault(usage, {})
    active_keys = set(_function_keys_for_usage(usage))
    for key in list(settings):
        if key not in active_keys:
            settings.pop(key, None)
    for fallback_priority, template in enumerate(_function_templates_for_usage(usage), start=1):
        item = settings.setdefault(template["key"], {})
        item.setdefault("count", template["count"])
        item.setdefault("area", template["area"])
        item.setdefault("priority", template.get("priority", fallback_priority))
        item.setdefault("shape", "auto")
        item.setdefault("alignment", "auto")
    return settings


def _build_function_instances(usage: str, settings: dict[str, dict[str, float | int | str]]) -> list[dict[str, Any]]:
    templates_by_key = {template["key"]: template for template in _function_templates_for_usage(usage)}
    instances: list[dict[str, Any]] = []
    for key, template in templates_by_key.items():
        count = int(settings[key]["count"])
        area = float(settings[key]["area"])
        raw_priority = settings[key].get("priority", 99)
        priority = "optional" if str(raw_priority) == "optional" else _priority_value(raw_priority)
        shape = str(settings[key].get("shape", "auto"))
        if shape not in SHAPE_PREFERENCE_LABELS:
            shape = "auto"
        alignment = str(settings[key].get("alignment", "free"))
        if alignment not in ALIGNMENT_LABELS:
            alignment = "free"
        for idx in range(1, count + 1):
            suffix = f" {idx}" if count > 1 else ""
            function = {"id": f"{key}_{idx}", "name": f"{template['name']}{suffix}", "kind": template["kind"], "area_m2": area, "key": key, "priority": priority, "shape": shape, "alignment": alignment}
            function["geometry_generator"] = _geometry_generator_label(function)
            instances.append(function)
    return instances


def _place_function(site_id: str, function_id: str, point: Point2D) -> None:
    site_store = _placement_store().setdefault(site_id, {})
    order = site_store.get(function_id, {}).get("order", len(site_store) + 1)
    site_store[function_id] = {"anchor": (round(point[0], 2), round(point[1], 2)), "order": order}


def _next_unplaced_function_id(functions: list[dict[str, Any]], placements: dict[str, Any], placed_function_id: str) -> str:
    for fn in functions:
        if fn["id"] != placed_function_id and fn["id"] not in placements:
            return fn["id"]
    return placed_function_id


def _clear_function_placements(site_id: str) -> None:
    _placement_store()[site_id] = {}


def _is_geometry_blocker(item: dict[str, Any]) -> bool:
    return bool(item.get("_geometry_blocker"))


def _rect_geometry(rect: dict[str, Any]):
    if _is_geometry_blocker(rect):
        return rect["geometry"]
    return box(rect["x"] - rect["w"] / 2, rect["y"] - rect["h"] / 2, rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2)


def _preferred_aspect(function: dict[str, Any]) -> float:
    profile = _geometry_profile(function)
    profile_aspects = _unique_aspects(tuple(profile.get("aspects", (FUNCTION_ASPECTS.get(function["kind"], 1.5),))))
    base = profile_aspects[0] if profile_aspects else FUNCTION_ASPECTS.get(function["kind"], 1.5)
    shape = _resolved_shape(function)
    if shape == "compact":
        return min(profile_aspects + [1.0], key=lambda value: abs(math.log(max(0.05, value))))
    if shape == "wide":
        return max([base] + [value for value in profile_aspects if value >= 1.0])
    if shape == "tall":
        tall_options = [1.0 / max(value, 0.1) for value in profile_aspects if value >= 1.0] + [value for value in profile_aspects if value < 1.0]
        return min(tall_options + [0.6])
    return base


def _rect_dimensions(function: dict[str, Any]) -> tuple[float, float]:
    return _rect_dimensions_for_area(function, float(function["area_m2"]), _preferred_aspect(function))


def _clamp_rect_to_allowed(rect: dict[str, Any]) -> None:
    minx, miny, maxx, maxy = rect["allowed"].bounds
    rect["w"] = min(rect["w"], max(2.0, maxx - minx))
    rect["h"] = min(rect["h"], max(2.0, maxy - miny))
    rect["x"] = min(max(rect["x"], minx + rect["w"] / 2), maxx - rect["w"] / 2)
    rect["y"] = min(max(rect["y"], miny + rect["h"] / 2), maxy - rect["h"] / 2)


def _initial_rect(site_id: str, function: dict[str, Any], anchor: Point2D, setback_m: float) -> dict[str, Any]:
    allowed = _build_boundary(site_id, setback_m) if function["kind"] in BUILDING_BOUNDARY_KINDS else _site_polygon(site_id)
    width, height = _rect_dimensions(function)
    rect = {"function": function, "anchor": anchor, "x": anchor[0], "y": anchor[1], "w": width, "h": height, "allowed": allowed}
    _clamp_rect_to_allowed(rect)
    return rect


def _candidate_aspects(function: dict[str, Any]) -> list[float]:
    profile = _geometry_profile(function)
    profile_aspects = _unique_aspects(tuple(profile.get("aspects", (FUNCTION_ASPECTS.get(function["kind"], 1.5),))))
    base = profile_aspects[0] if profile_aspects else FUNCTION_ASPECTS.get(function["kind"], 1.5)
    raw_shape = str(function.get("shape", "auto"))
    shape = _resolved_shape(function)
    if raw_shape == "auto":
        aspects = profile_aspects + [1.0 / max(value, 0.1) for value in profile_aspects if value >= 1.0] + [1.0]
    elif shape == "compact":
        aspects = [1.0, 1.2, 0.85, base, 1.0 / max(base, 0.1)]
    elif shape == "wide":
        aspects = [value for value in profile_aspects if value >= 1.0] + [max(base, 2.6), 3.5, 5.0, 1.0]
    elif shape == "tall":
        aspects = [1.0 / max(value, 0.1) for value in profile_aspects if value >= 1.0] + [value for value in profile_aspects if value < 1.0] + [1.0]
    else:
        aspects = [base, 1.0, 1.0 / max(base, 0.1)]
    return _unique_aspects(aspects)


def _rect_dimensions_for_area(function: dict[str, Any], area_m2: float, aspect: float | None = None, enforce_minimums: bool = True) -> tuple[float, float]:
    area = max(20.0, float(area_m2))
    ratio = max(0.1, aspect if aspect is not None else _preferred_aspect(function))
    base_width = max(4.0, math.sqrt(area * ratio))
    base_height = max(4.0, area / base_width)
    width = base_width
    height = base_height
    if enforce_minimums:
        profile = _geometry_profile(function)
        min_width = float(profile.get("min_width_m", 4.0))
        min_depth = float(profile.get("min_depth_m", 4.0))
        width = max(width, min_width)
        height = max(height, min_depth)
        if width * height > area + 0.1:
            candidates: list[tuple[float, float]] = []
            width_with_depth = area / max(0.1, height)
            if width_with_depth >= min_width - 0.01:
                candidates.append((width_with_depth, height))
            height_with_width = area / max(0.1, width)
            if height_with_width >= min_depth - 0.01:
                candidates.append((width, height_with_width))
            if not candidates:
                # Functional geometry wins over area fraction: a truck yard or
                # parking field may be reduced in area, but not below the
                # dimensions required for its operational use.
                return width, height
            width, height = min(candidates, key=lambda item: abs(math.log(max(0.1, item[0] / max(0.1, item[1])) / ratio)))
    current_area = width * height
    if current_area < area - 0.1:
        scale = math.sqrt(area / max(1.0, current_area))
        width *= scale
        height *= scale
    elif current_area > area + 0.1:
        scale = math.sqrt(area / max(1.0, current_area))
        width *= scale
        height *= scale
    return width, height


def _candidate_centers_for_shape(rect: dict[str, Any], width: float, height: float, include_search: bool = True) -> list[dict[str, Any]]:
    ax, ay = rect["anchor"]
    minx, miny, maxx, maxy = rect["allowed"].bounds
    candidates: list[dict[str, Any]] = []
    offsets = [
        ("center", 0.0, 0.0, 0.0),
        ("corner", width / 2, height / 2, 8.0), ("corner", -width / 2, height / 2, 8.0),
        ("corner", width / 2, -height / 2, 8.0), ("corner", -width / 2, -height / 2, 8.0),
        ("edge", 0.0, height / 2, 5.0), ("edge", 0.0, -height / 2, 5.0),
        ("edge", width / 2, 0.0, 5.0), ("edge", -width / 2, 0.0, 5.0),
    ]
    for mode, dx, dy, penalty in offsets:
        candidates.append({"center": (ax + dx, ay + dy), "anchor_mode": mode, "mode_penalty": penalty})
    if not include_search:
        return candidates
    step = max(6.0, min(width, height) * 0.65)
    max_radius = max(maxx - minx, maxy - miny)
    radius = step
    rings = 0
    while radius <= max_radius + step and rings < 8:
        for angle_deg in range(0, 360, 45):
            angle = math.radians(angle_deg)
            candidates.append({"center": (ax + math.cos(angle) * radius, ay + math.sin(angle) * radius), "anchor_mode": "search", "mode_penalty": 45.0})
        radius += step
        rings += 1
    return candidates


def _candidate_rect(rect: dict[str, Any], center: Point2D, area_m2: float, aspect: float, anchor_mode: str, mode_penalty: float, enforce_minimums: bool = True) -> dict[str, Any]:
    width, height = _rect_dimensions_for_area(rect["function"], area_m2, aspect, enforce_minimums)
    candidate = dict(rect)
    candidate["x"], candidate["y"] = center
    candidate["w"], candidate["h"] = width, height
    candidate["allocated_area_m2"] = width * height
    candidate["aspect"] = aspect
    candidate["anchor_mode"] = anchor_mode
    candidate["mode_penalty"] = mode_penalty
    _clamp_rect_to_allowed(candidate)
    return candidate


def _anchor_gap_m(rect: dict[str, Any]) -> float:
    ax, ay = rect["anchor"]
    return float(_rect_geometry(rect).distance(Point(ax, ay)))



def _is_building_function(function: dict[str, Any]) -> bool:
    return function.get("kind") == "building"


def _required_spacing_m(function_a: dict[str, Any], function_b: dict[str, Any], building_spacing_m: float) -> float:
    if _is_building_function(function_a) and _is_building_function(function_b):
        return max(0.0, float(building_spacing_m))
    return 0.0


def _spacing_violation_m(candidate: dict[str, Any], placed_rects: list[dict[str, Any]], building_spacing_m: float) -> float:
    if _is_geometry_blocker(candidate):
        return 0.0
    geom = _rect_geometry(candidate)
    worst = 0.0
    for other in placed_rects:
        if _is_geometry_blocker(other):
            continue
        required = _required_spacing_m(candidate["function"], other["function"], building_spacing_m)
        if required <= 0:
            continue
        distance = geom.distance(_rect_geometry(other))
        worst = max(worst, required - distance)
    return max(0.0, worst)


def _alignment_gap_m(rect: dict[str, Any]) -> float:
    alignment = _resolved_alignment(rect)
    if alignment == "free":
        return 0.0
    ax, ay = rect["anchor"]
    minx, miny, maxx, maxy = _rect_geometry(rect).bounds
    if alignment == "south":
        return abs(miny - ay)
    if alignment == "north":
        return abs(maxy - ay)
    if alignment == "west":
        return abs(minx - ax)
    if alignment == "east":
        return abs(maxx - ax)
    return 0.0


def _clearance_geometry(rect: dict[str, Any], building_spacing_m: float):
    geom = _rect_geometry(rect)
    if _is_building_function(rect["function"]) and building_spacing_m > 0:
        return geom.buffer(float(building_spacing_m) / 2.0, cap_style=2, join_style=2)
    return geom


def _road_blocker_applies_to_candidate(candidate: dict[str, Any], blocker: dict[str, Any]) -> bool:
    if not _is_geometry_blocker(blocker):
        return True
    allowed_ids = set(blocker.get("allowed_function_ids", ()))
    return str(candidate["function"].get("id", "")) not in allowed_ids


def _is_non_overlapping(candidate: dict[str, Any], placed_rects: list[dict[str, Any]], building_spacing_m: float) -> bool:
    geom = _rect_geometry(candidate)
    outside = geom.difference(candidate["allowed"].buffer(0.01)).area
    if outside > 0.5:
        return False
    for other in placed_rects:
        if not _road_blocker_applies_to_candidate(candidate, other):
            continue
        if geom.intersection(_rect_geometry(other)).area > 0.5:
            return False
    return _spacing_violation_m(candidate, placed_rects, building_spacing_m) <= 0.05


AREA_FRACTIONS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2)


def _score_rect_candidate(
    base: dict[str, Any],
    area: float,
    aspect: float,
    preferred_aspect: float,
    fraction: float,
    candidate_center: dict[str, Any],
    placed_rects: list[dict[str, Any]],
    building_spacing_m: float,
    enforce_minimums: bool,
    mode_penalties: dict[str, float],
) -> dict[str, Any] | None:
    candidate = _candidate_rect(
        base,
        candidate_center["center"],
        area,
        aspect,
        candidate_center["anchor_mode"],
        candidate_center["mode_penalty"],
        enforce_minimums,
    )
    if not _is_non_overlapping(candidate, placed_rects, building_spacing_m):
        return None
    ax, ay = base["anchor"]
    center_distance = math.dist((candidate["x"], candidate["y"]), (ax, ay))
    anchor_gap = _anchor_gap_m(candidate)
    aspect_penalty = abs(math.log(max(0.05, aspect) / max(0.05, preferred_aspect))) * 120.0
    alignment_gap = _alignment_gap_m(candidate)
    area_deficit = max(0.0, 1.0 - fraction)
    # A placed placeholder is a strong intent signal. Prefer a slightly reduced
    # rectangle near the placeholder over a full-size rectangle that jumps to an
    # unrelated free area.
    score = (
        area_deficit * 35_000.0
        + center_distance * center_distance * 220.0
        + anchor_gap * anchor_gap * 5000.0
        + alignment_gap * alignment_gap * 50_000.0
        + aspect_penalty
        + mode_penalties.get(str(candidate.get("anchor_mode")), 9000.0)
        + float(candidate.get("mode_penalty", 0.0)) * 20.0
    )
    return {"rect": candidate, "score": score}


def _best_non_overlapping_rect(base: dict[str, Any], placed_rects: list[dict[str, Any]], building_spacing_m: float, fractions: tuple[float, ...] = AREA_FRACTIONS, enforce_minimums: bool = True, aspects: list[float] | tuple[float, ...] | None = None) -> dict[str, Any] | None:
    target_area = float(base["function"]["area_m2"])
    candidate_aspects = _unique_aspects(tuple(aspects)) if aspects is not None else _candidate_aspects(base["function"])
    best: dict[str, Any] | None = None
    best_score = float("inf")
    mode_penalties = {"center": 0.0, "edge": 2500.0, "corner": 4000.0, "search": 9000.0}
    for index, fraction in enumerate(fractions):
        area = target_area * fraction
        for aspect in candidate_aspects:
            width, height = _rect_dimensions_for_area(base["function"], area, aspect)
            if width > base["allowed"].bounds[2] - base["allowed"].bounds[0] + 0.1 or height > base["allowed"].bounds[3] - base["allowed"].bounds[1] + 0.1:
                continue
            preferred_aspect = _preferred_aspect(base["function"])
            local_centers = _candidate_centers_for_shape(base, width, height, include_search=False)
            found_for_shape = False
            for candidate_center in local_centers:
                candidate = _score_rect_candidate(
                    base, area, aspect, preferred_aspect, fraction, candidate_center, placed_rects, building_spacing_m, enforce_minimums, mode_penalties
                )
                if candidate is None:
                    continue
                found_for_shape = True
                if candidate["score"] < best_score:
                    best = candidate["rect"]
                    best_score = candidate["score"]
            if not found_for_shape:
                search_centers = _candidate_centers_for_shape(base, width, height, include_search=True)[len(local_centers):]
                for candidate_center in search_centers:
                    candidate = _score_rect_candidate(
                        base, area, aspect, preferred_aspect, fraction, candidate_center, placed_rects, building_spacing_m, enforce_minimums, mode_penalties
                    )
                    if candidate is None:
                        continue
                    if candidate["score"] < best_score:
                        best = candidate["rect"]
                        best_score = candidate["score"]
        if best is not None:
            next_fraction = fractions[index + 1] if index + 1 < len(fractions) else None
            if next_fraction is None or best_score <= max(0.0, 1.0 - next_fraction) * 35_000.0:
                return best
    return None if best is None else best


def _group_key(base: dict[str, Any]) -> tuple[int, str, float]:
    function = base["function"]
    return (_priority_value(function.get("priority", 99)), str(function.get("key", function["id"])), float(function["area_m2"]))


def _minimum_area_fraction(function: dict[str, Any]) -> float:
    target_area = max(1.0, float(function.get("area_m2", 0.0)))
    profile = _geometry_profile(function)
    min_width = float(profile.get("min_width_m", 4.0))
    min_depth = float(profile.get("min_depth_m", 4.0))
    return min(1.0, max(0.05, (min_width * min_depth) / target_area))


def _mandatory_cap_for_function(function: dict[str, Any], mandatory_area_cap: Any) -> float | None:
    if mandatory_area_cap is None or _is_optional_function(function):
        return None
    if isinstance(mandatory_area_cap, dict):
        priority = _priority_value(function.get("priority", 99))
        cap = mandatory_area_cap.get(priority, mandatory_area_cap.get(str(priority), mandatory_area_cap.get("default")))
        if cap is None:
            return None
        return max(float(cap), _minimum_area_fraction(function))
    return max(float(mandatory_area_cap), _minimum_area_fraction(function))


def _limited_area_fractions(function: dict[str, Any], mandatory_area_cap: Any) -> tuple[float, ...]:
    fractions = _area_fractions_for_function(function)
    cap = _mandatory_cap_for_function(function, mandatory_area_cap)
    if cap is None:
        return fractions
    cap = max(0.05, min(1.0, cap))
    capped = [fraction for fraction in fractions if fraction <= cap + 0.001]
    if cap not in capped:
        capped.append(cap)
    capped = sorted({round(float(value), 3) for value in capped if value > 0}, reverse=True)
    return tuple(capped) or fractions


def _group_centering_score(rects: list[dict[str, Any]]) -> float:
    return sum(math.dist((rect["x"], rect["y"]), rect["anchor"]) ** 2 for rect in rects) + sum(float(rect.get("mode_penalty", 0.0)) for rect in rects) * 20.0


def _place_group_with_common_fraction(group: list[dict[str, Any]], placed_rects: list[dict[str, Any]], building_spacing_m: float, fractions: tuple[float, ...] | None = None, enforce_minimums: bool = True) -> list[dict[str, Any]] | None:
    fractions = fractions if fractions is not None else (_area_fractions_for_function(group[0]["function"]) if group else AREA_FRACTIONS)
    aspects = _candidate_aspects(group[0]["function"]) if group else [1.0]
    for fraction in fractions:
        best_trial: list[dict[str, Any]] | None = None
        best_score = float("inf")
        for aspect in aspects:
            trial: list[dict[str, Any]] = []
            for base in group:
                rect = _best_non_overlapping_rect(base, placed_rects + trial, building_spacing_m, fractions=(fraction,), enforce_minimums=enforce_minimums, aspects=(aspect,))
                if rect is None:
                    break
                rect["group_fraction"] = fraction
                rect["group_aspect"] = aspect
                trial.append(rect)
            if len(trial) != len(group):
                continue
            score = _group_centering_score(trial)
            if score < best_score:
                best_trial = trial
                best_score = score
        if best_trial is not None:
            return best_trial
    return None


def _base_placeholder(base: dict[str, Any]):
    placeholder = dict(base)
    _clamp_rect_to_allowed(placeholder)
    return _rect_geometry(placeholder).intersection(placeholder["allowed"])


def _parcel_from_rect(rect: dict[str, Any], placed_rects: list[dict[str, Any]], building_spacing_m: float) -> dict[str, Any]:
    geom = _rect_geometry(rect)
    clipped = geom.intersection(rect["allowed"])
    center_distance = math.dist((rect["x"], rect["y"]), rect["anchor"])
    anchor_gap = _anchor_gap_m(rect)
    alignment_gap = _alignment_gap_m(rect)
    spacing_violation = _spacing_violation_m(rect, [other for other in placed_rects if other is not rect], building_spacing_m)
    target_area = float(rect["function"]["area_m2"])
    actual_area = float(geom.area)
    coverage = actual_area / max(1.0, target_area)
    status = "ok" if coverage >= 0.98 else "reduziert"
    return {
        "function": rect["function"],
        "geometry": geom,
        "display_geometry": clipped,
        "anchor": rect["anchor"],
        "center": (rect["x"], rect["y"]),
        "target_area_m2": target_area,
        "actual_area_m2": actual_area,
        "inside_area_m2": clipped.area,
        "coverage_pct": coverage * 100.0,
        "center_distance_m": center_distance,
        "anchor_gap_m": anchor_gap,
        "alignment_gap_m": alignment_gap,
        "spacing_violation_m": spacing_violation,
        "clearance_geometry": _clearance_geometry(rect, building_spacing_m),
        "aspect": rect.get("aspect"),
        "anchor_mode": rect.get("anchor_mode"),
        "group_fraction": rect.get("group_fraction"),
        "grown": bool(rect.get("grown")),
        "shifted": bool(rect.get("shifted")),
        "status": "Abstand verletzt" if spacing_violation > 0.05 else status,
        "conflict": False,
    }


def _append_parcel_from_rect(parcels: list[dict[str, Any]], placed_rects: list[dict[str, Any]], rect: dict[str, Any], building_spacing_m: float) -> None:
    placed_rects.append(rect)
    parcels.append(_parcel_from_rect(rect, placed_rects, building_spacing_m))


def _growth_target_area(rect: dict[str, Any], mandatory_area_cap: Any = None) -> float:
    target_area = float(rect["function"]["area_m2"])
    cap = _mandatory_cap_for_function(rect["function"], mandatory_area_cap)
    if cap is None:
        return target_area
    return max(1.0, target_area * max(0.05, min(1.0, cap)))


def _grow_candidate(rect: dict[str, Any], direction: str, step_m: float, mandatory_area_cap: Any = None) -> dict[str, Any] | None:
    target_area = _growth_target_area(rect, mandatory_area_cap)
    current_area = float(rect["w"] * rect["h"])
    if current_area >= target_area - 0.5:
        return None
    remaining = target_area - current_area
    candidate = dict(rect)
    if direction in {"left", "right", "horizontal"}:
        delta = min(step_m, remaining / max(0.1, rect["h"]))
        if delta <= 0.05:
            return None
        candidate["w"] = rect["w"] + delta
        if direction == "left":
            candidate["x"] = rect["x"] - delta / 2.0
        elif direction == "right":
            candidate["x"] = rect["x"] + delta / 2.0
    elif direction in {"south", "north", "vertical"}:
        delta = min(step_m, remaining / max(0.1, rect["w"]))
        if delta <= 0.05:
            return None
        candidate["h"] = rect["h"] + delta
        if direction == "south":
            candidate["y"] = rect["y"] - delta / 2.0
        elif direction == "north":
            candidate["y"] = rect["y"] + delta / 2.0
    else:
        return None
    candidate["allocated_area_m2"] = candidate["w"] * candidate["h"]
    candidate["aspect"] = candidate["w"] / max(0.1, candidate["h"])
    candidate["grown"] = True
    return candidate


def _best_growth_step(rect: dict[str, Any], placed_rects: list[dict[str, Any]], building_spacing_m: float, step_m: float = 2.0, mandatory_area_cap: Any = None) -> dict[str, Any] | None:
    others = [other for other in placed_rects if other is not rect]
    best: dict[str, Any] | None = None
    best_score = float("-inf")
    for direction in ("horizontal", "vertical", "left", "right", "north", "south"):
        candidate = _grow_candidate(rect, direction, step_m, mandatory_area_cap)
        if candidate is None or not _is_non_overlapping(candidate, others, building_spacing_m):
            continue
        area_gain = candidate["w"] * candidate["h"] - rect["w"] * rect["h"]
        if area_gain <= 0.1:
            continue
        center_cost = math.dist((candidate["x"], candidate["y"]), candidate["anchor"])
        direction_cost = 0.0 if direction in {"horizontal", "vertical"} else 25.0
        score = area_gain - center_cost * 4.0 - _anchor_gap_m(candidate) * 0.05 - _alignment_gap_m(candidate) * 0.05 - direction_cost
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _translate_candidate(rect: dict[str, Any], direction: str, step_m: float) -> dict[str, Any] | None:
    dx, dy = {
        "left": (-step_m, 0.0),
        "right": (step_m, 0.0),
        "north": (0.0, step_m),
        "south": (0.0, -step_m),
    }.get(direction, (0.0, 0.0))
    if dx == 0.0 and dy == 0.0:
        return None
    candidate = dict(rect)
    candidate["x"] = rect["x"] + dx
    candidate["y"] = rect["y"] + dy
    candidate["shifted"] = True
    return candidate


def _min_distance_to_others(rect: dict[str, Any], others: list[dict[str, Any]]) -> float:
    if not others:
        return 999.0
    geom = _rect_geometry(rect)
    return min(float(geom.distance(_rect_geometry(other))) for other in others)


def _best_shift_step(rect: dict[str, Any], placed_rects: list[dict[str, Any]], building_spacing_m: float, step_m: float = 2.0, mandatory_area_cap: Any = None) -> dict[str, Any] | None:
    if _coverage_ratio(rect, mandatory_area_cap) >= 0.98:
        return None
    others = [other for other in placed_rects if other is not rect]
    current_gap = _min_distance_to_others(rect, others)
    current_anchor_gap = _anchor_gap_m(rect)
    best: dict[str, Any] | None = None
    best_score = 0.0
    for direction in ("left", "right", "north", "south"):
        candidate = _translate_candidate(rect, direction, step_m)
        if candidate is None or not _is_non_overlapping(candidate, others, building_spacing_m):
            continue
        growth = _best_growth_step(candidate, [candidate] + others, building_spacing_m, step_m=step_m, mandatory_area_cap=mandatory_area_cap)
        immediate_gain = 0.0 if growth is None else growth["w"] * growth["h"] - candidate["w"] * candidate["h"]
        gap_gain = _min_distance_to_others(candidate, others) - current_gap
        anchor_cost = max(0.0, _anchor_gap_m(candidate) - current_anchor_gap)
        score = immediate_gain * 1.6 + gap_gain * 55.0 - anchor_cost * 1.5
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _best_anchor_repair_step(rect: dict[str, Any], placed_rects: list[dict[str, Any]], building_spacing_m: float, step_m: float = 2.0, mandatory_area_cap: Any = None) -> dict[str, Any] | None:
    current_gap = _anchor_gap_m(rect)
    if current_gap <= 0.05:
        return None
    others = [other for other in placed_rects if other is not rect]
    ax, ay = rect["anchor"]
    directions: list[str] = []
    if ax < rect["x"] - 0.1:
        directions.append("left")
    elif ax > rect["x"] + 0.1:
        directions.append("right")
    if ay < rect["y"] - 0.1:
        directions.append("south")
    elif ay > rect["y"] + 0.1:
        directions.append("north")
    best: dict[str, Any] | None = None
    best_score = 0.0
    for direction in directions:
        candidate = _translate_candidate(rect, direction, step_m)
        if candidate is None or not _is_non_overlapping(candidate, others, building_spacing_m):
            continue
        gap_reduction = current_gap - _anchor_gap_m(candidate)
        if gap_reduction <= 0.05:
            continue
        growth = _best_growth_step(candidate, [candidate] + others, building_spacing_m, step_m=step_m, mandatory_area_cap=mandatory_area_cap)
        growth_gain = 0.0 if growth is None else growth["w"] * growth["h"] - candidate["w"] * candidate["h"]
        score = gap_reduction * 120.0 + growth_gain * 0.25
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _repair_anchor_positions(placed_rects: list[dict[str, Any]], building_spacing_m: float, mandatory_area_cap: Any = None) -> None:
    for _ in range(80):
        candidates = sorted([rect for rect in placed_rects if not _is_geometry_blocker(rect)], key=lambda rect: (_anchor_gap_m(rect), 1.0 - _coverage_ratio(rect, mandatory_area_cap)), reverse=True)
        changed = False
        for rect in candidates:
            repaired = _best_anchor_repair_step(rect, placed_rects, building_spacing_m, mandatory_area_cap=mandatory_area_cap)
            if repaired is None:
                continue
            rect.update(repaired)
            changed = True
            break
        if not changed:
            return


def _best_group_shift_step(group: list[dict[str, Any]], placed_rects: list[dict[str, Any]], building_spacing_m: float, step_m: float = 2.0, mandatory_area_cap: Any = None) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = 0.0
    group_set = set(id(rect) for rect in group)
    for rect in group:
        others = [other for other in placed_rects if other is not rect]
        current_gap = _min_distance_to_others(rect, [other for other in group if other is not rect])
        current_anchor_gap = _anchor_gap_m(rect)
        for direction in ("left", "right", "north", "south"):
            candidate = _translate_candidate(rect, direction, step_m)
            if candidate is None or not _is_non_overlapping(candidate, others, building_spacing_m):
                continue
            trial_group = [candidate if item is rect else item for item in group]
            trial_placed = [candidate if item is rect else item for item in placed_rects]
            grown_group = _common_growth_step(trial_group, trial_placed, building_spacing_m, mandatory_area_cap)
            immediate_gain = 0.0 if grown_group is None else sum(grown["w"] * grown["h"] for grown in grown_group) - sum(item["w"] * item["h"] for item in trial_group)
            group_gap_gain = _min_distance_to_others(candidate, [other for other in group if other is not rect]) - current_gap
            anchor_cost = max(0.0, _anchor_gap_m(candidate) - current_anchor_gap)
            score = immediate_gain * 1.8 + group_gap_gain * 70.0 - anchor_cost * 1.2
            if score > best_score:
                best = candidate
                best_score = score
    return best


def _grow_candidate_to_area(rect: dict[str, Any], direction: str, desired_area: float, mandatory_area_cap: Any = None) -> dict[str, Any] | None:
    current_area = float(rect["w"] * rect["h"])
    target_area = _growth_target_area(rect, mandatory_area_cap)
    desired_area = min(desired_area, target_area)
    if desired_area <= current_area + 0.1:
        return dict(rect)
    candidate = dict(rect)
    if direction in {"left", "right", "horizontal"}:
        delta = (desired_area - current_area) / max(0.1, rect["h"])
        candidate["w"] = rect["w"] + delta
        if direction == "left":
            candidate["x"] = rect["x"] - delta / 2.0
        elif direction == "right":
            candidate["x"] = rect["x"] + delta / 2.0
    elif direction in {"south", "north", "vertical"}:
        delta = (desired_area - current_area) / max(0.1, rect["w"])
        candidate["h"] = rect["h"] + delta
        if direction == "south":
            candidate["y"] = rect["y"] - delta / 2.0
        elif direction == "north":
            candidate["y"] = rect["y"] + delta / 2.0
    else:
        return None
    candidate["allocated_area_m2"] = candidate["w"] * candidate["h"]
    candidate["aspect"] = candidate["w"] / max(0.1, candidate["h"])
    candidate["grown"] = True
    return candidate


def _best_growth_to_area(rect: dict[str, Any], desired_area: float, others: list[dict[str, Any]], building_spacing_m: float, mandatory_area_cap: Any = None) -> dict[str, Any] | None:
    if rect["w"] * rect["h"] >= desired_area - 0.1:
        return dict(rect)
    best: dict[str, Any] | None = None
    best_score = float("inf")
    for direction in ("horizontal", "vertical", "left", "right", "north", "south"):
        candidate = _grow_candidate_to_area(rect, direction, desired_area, mandatory_area_cap)
        if candidate is None or not _is_non_overlapping(candidate, others, building_spacing_m):
            continue
        center_cost = math.dist((candidate["x"], candidate["y"]), candidate["anchor"])
        direction_cost = 0.0 if direction in {"horizontal", "vertical"} else 25.0
        score = center_cost * 4.0 + _anchor_gap_m(candidate) * 0.05 + _alignment_gap_m(candidate) * 0.05 + direction_cost
        if score < best_score:
            best = candidate
            best_score = score
    return best


def _rect_group_key(rect: dict[str, Any]) -> tuple[int, str, float]:
    function = rect["function"]
    return (_priority_value(function.get("priority", 99)), str(function.get("key", function["id"])), float(function["area_m2"]))


def _common_growth_step(group: list[dict[str, Any]], placed_rects: list[dict[str, Any]], building_spacing_m: float, mandatory_area_cap: Any = None) -> list[dict[str, Any]] | None:
    target_area = min(_growth_target_area(rect, mandatory_area_cap) for rect in group)
    current_area = min(float(rect["w"] * rect["h"]) for rect in group)
    if current_area >= target_area - 0.5:
        return None
    desired_area = min(target_area, current_area + 80.0)
    outside_group = [rect for rect in placed_rects if rect not in group]
    best: list[dict[str, Any]] | None = None
    best_score = float("inf")
    for direction in ("horizontal", "vertical", "left", "right", "north", "south"):
        candidates: list[dict[str, Any]] = []
        for rect in group:
            others = outside_group + [other for other in group if other is not rect]
            candidate = _grow_candidate_to_area(rect, direction, desired_area, mandatory_area_cap)
            if candidate is None or not _is_non_overlapping(candidate, others, building_spacing_m):
                break
            candidates.append(candidate)
        if len(candidates) != len(group):
            continue
        valid = True
        for idx, candidate in enumerate(candidates):
            others = outside_group + [other for other_idx, other in enumerate(candidates) if other_idx != idx]
            if not _is_non_overlapping(candidate, others, building_spacing_m):
                valid = False
                break
        if not valid:
            continue
        geometry_spread = max(candidate["w"] for candidate in candidates) - min(candidate["w"] for candidate in candidates) + max(candidate["h"] for candidate in candidates) - min(candidate["h"] for candidate in candidates)
        score = sum(_anchor_gap_m(candidate) for candidate in candidates) + geometry_spread * 100.0
        if score < best_score:
            best = candidates
            best_score = score
    return best


def _coverage_ratio(rect: dict[str, Any], mandatory_area_cap: Any = None) -> float:
    if _is_geometry_blocker(rect):
        return 1.0
    return rect["w"] * rect["h"] / max(1.0, _growth_target_area(rect, mandatory_area_cap))


def _grow_rectangles_to_targets(placed_rects: list[dict[str, Any]], building_spacing_m: float, equalize_repeated: bool, mandatory_area_cap: Any = None) -> None:
    for _ in range(500):
        grouped: dict[tuple[int, str, float], list[dict[str, Any]]] = {}
        for rect in placed_rects:
            if _is_geometry_blocker(rect):
                continue
            if rect["w"] * rect["h"] < _growth_target_area(rect, mandatory_area_cap) - 0.5:
                grouped.setdefault(_rect_group_key(rect), []).append(rect)
        if not grouped:
            return
        changed = False
        groups = sorted(grouped.values(), key=lambda group: (min(_priority_value(rect["function"].get("priority", 99)) for rect in group), min(_coverage_ratio(rect, mandatory_area_cap) for rect in group)))
        for group in groups:
            if equalize_repeated and len(group) > 1 and all(rect.get("group_fraction") is not None for rect in group):
                grown_group = _common_growth_step(group, placed_rects, building_spacing_m, mandatory_area_cap)
                if grown_group is None:
                    shifted = _best_group_shift_step(group, placed_rects, building_spacing_m, mandatory_area_cap=mandatory_area_cap)
                    if shifted is None:
                        continue
                    for rect in placed_rects:
                        if _is_geometry_blocker(rect):
                            continue
                        if rect["function"]["id"] == shifted["function"]["id"]:
                            rect.update(shifted)
                            changed = True
                            break
                    break
                for rect, grown in zip(group, grown_group):
                    rect.update(grown)
                changed = True
                break
            rect = min(group, key=lambda item: _coverage_ratio(item, mandatory_area_cap))
            grown = _best_growth_step(rect, placed_rects, building_spacing_m, mandatory_area_cap=mandatory_area_cap)
            if grown is None:
                shifted = _best_shift_step(rect, placed_rects, building_spacing_m, mandatory_area_cap=mandatory_area_cap)
                if shifted is None:
                    continue
                rect.update(shifted)
                changed = True
                break
            rect.update(grown)
            changed = True
            break
        if not changed:
            return


def _build_patchwork_attempt(site_id: str, functions: list[dict[str, Any]], setback_m: float, building_spacing_m: float, equalize_repeated: bool, mandatory_area_cap: Any, access_points: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    placements = _placement_store().get(site_id, {})
    function_by_id = {item["id"]: item for item in functions}
    placed_ids = [fid for fid in placements if fid in function_by_id]
    placed_ids.sort(key=lambda fid: (_priority_value(function_by_id[fid].get("priority", 99)), -float(function_by_id[fid]["area_m2"]), placements[fid].get("order", 0)))
    base_rects = [_initial_rect(site_id, function_by_id[fid], tuple(placements[fid]["anchor"]), setback_m) for fid in placed_ids]
    grouped_counts: dict[tuple[int, str, float], int] = {}
    for base in base_rects:
        grouped_counts[_group_key(base)] = grouped_counts.get(_group_key(base), 0) + 1

    placed_rects: list[dict[str, Any]] = _road_strategy_blockers(site_id, access_points or [], functions, setback_m)
    missing: list[dict[str, Any]] = []
    enforce_minimums = True
    idx = 0
    while idx < len(base_rects):
        base = base_rects[idx]
        key = _group_key(base)
        group = [base]
        idx += 1
        while idx < len(base_rects) and _group_key(base_rects[idx]) == key:
            group.append(base_rects[idx])
            idx += 1

        repeated_mandatory_group = (equalize_repeated or mandatory_area_cap is not None) and grouped_counts.get(key, 0) > 1 and not _is_optional_function(base["function"])
        fractions = _limited_area_fractions(base["function"], mandatory_area_cap)
        if repeated_mandatory_group:
            group_rects = _place_group_with_common_fraction(group, placed_rects, building_spacing_m, fractions=fractions, enforce_minimums=enforce_minimums)
            if group_rects is not None:
                placed_rects.extend(group_rects)
                continue

        for item in group:
            rect = _best_non_overlapping_rect(item, placed_rects, building_spacing_m, fractions=_limited_area_fractions(item["function"], mandatory_area_cap), enforce_minimums=enforce_minimums)
            if rect is None:
                if _is_optional_function(item["function"]):
                    missing.append({"function": item["function"], "anchor": item["anchor"], "placeholder_geometry": Polygon(), "status": "optional entfallen", "optional": True})
                else:
                    missing.append({"function": item["function"], "anchor": item["anchor"], "placeholder_geometry": _base_placeholder(item), "status": "Pflichtfläche nicht abbildbar"})
                continue
            placed_rects.append(rect)

    _grow_rectangles_to_targets(placed_rects, building_spacing_m, equalize_repeated, mandatory_area_cap)
    _repair_anchor_positions(placed_rects, building_spacing_m, mandatory_area_cap)
    _grow_rectangles_to_targets(placed_rects, building_spacing_m, equalize_repeated, mandatory_area_cap)
    parcels = [_parcel_from_rect(rect, placed_rects, building_spacing_m) for rect in placed_rects if not _is_geometry_blocker(rect)]
    return {
        "parcels": parcels,
        "missing": missing,
        "build_boundary": _build_boundary(site_id, setback_m),
        "site_polygon": _site_polygon(site_id),
        "building_spacing_m": building_spacing_m,
        "equalize_repeated": equalize_repeated,
        "mandatory_area_cap": mandatory_area_cap,
        "balance_mode": mandatory_area_cap is not None,
    }


def _required_missing_count(patchwork: dict[str, Any]) -> int:
    return sum(1 for item in patchwork.get("missing", []) if not item.get("optional"))


def _priority_deficit_weight(priority: int) -> float:
    if priority <= 1:
        return 9.0
    if priority == 2:
        return 5.0
    if priority == 3:
        return 2.4
    if priority == 4:
        return 1.25
    if priority == 5:
        return 0.85
    return 0.55


def _patchwork_balance_score(patchwork: dict[str, Any]) -> float:
    required_missing = _required_missing_count(patchwork)
    optional_missing = sum(1 for item in patchwork.get("missing", []) if item.get("optional"))
    weighted_deficit = 0.0
    priority_floor_penalty = 0.0
    anchor_penalty = 0.0
    priority_coverages: dict[int, list[float]] = {}
    for parcel in patchwork.get("parcels", []):
        priority = _priority_value(parcel["function"].get("priority", 99))
        coverage = min(120.0, float(parcel.get("coverage_pct", 0.0)))
        priority_coverages.setdefault(priority, []).append(min(100.0, coverage))
        deficit = max(0.0, 100.0 - coverage)
        weighted_deficit += deficit * deficit * _priority_deficit_weight(priority)
        if priority <= 2:
            priority_floor_penalty += max(0.0, 60.0 - coverage) ** 2
        gap = float(parcel.get("anchor_gap_m", 0.0))
        anchor_penalty += gap * gap * 18.0
    priority_inversion_penalty = 0.0
    priorities = sorted(priority_coverages)
    for high in priorities:
        high_avg = sum(priority_coverages[high]) / len(priority_coverages[high])
        for low in priorities:
            if low <= high:
                continue
            low_avg = sum(priority_coverages[low]) / len(priority_coverages[low])
            if high_avg + 8.0 < low_avg:
                priority_inversion_penalty += (low_avg - high_avg) ** 2 * _priority_deficit_weight(high)
    return (
        required_missing * 12_000_000.0
        + optional_missing * 1_000.0
        + weighted_deficit * 75.0
        + priority_floor_penalty * 1_500.0
        + priority_inversion_penalty * 110.0
        + anchor_penalty
    )


def _priority_rebalance_caps() -> tuple[dict[int | str, float], ...]:
    return (
        {1: 1.0, 2: 0.95, 3: 0.75, 4: 0.6, 5: 0.55, "default": 0.45},
        {1: 0.9, 2: 0.9, 3: 0.65, 4: 0.5, 5: 0.45, "default": 0.35},
        {1: 0.8, 2: 0.8, 3: 0.6, 4: 0.48, 5: 0.42, "default": 0.35},
        {1: 0.7, 2: 0.7, 3: 0.52, 4: 0.42, 5: 0.36, "default": 0.3},
        {1: 0.6, 2: 0.6, 3: 0.45, 4: 0.36, 5: 0.32, "default": 0.28},
        {1: 0.55, 2: 0.55, 3: 0.35, 4: 0.32, 5: 0.32, "default": 0.3},
        {1: 0.5, 2: 0.55, 3: 0.3, 4: 0.28, 5: 0.28, "default": 0.25},
    )


def _build_patchwork(site_id: str, functions: list[dict[str, Any]], setback_m: float, building_spacing_m: float, equalize_repeated: bool = True, access_points: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    candidates = [_build_patchwork_attempt(site_id, functions, setback_m, building_spacing_m, equalize_repeated, None, access_points)]
    for cap in _priority_rebalance_caps():
        candidates.append(_build_patchwork_attempt(site_id, functions, setback_m, building_spacing_m, equalize_repeated, cap, access_points))
    if all(_required_missing_count(candidate) > 0 for candidate in candidates):
        for cap in (0.6, 0.5, 0.4, 0.3):
            candidates.append(_build_patchwork_attempt(site_id, functions, setback_m, building_spacing_m, equalize_repeated, cap, access_points))
    return min(candidates, key=_patchwork_balance_score)

def _empty_patchwork(site_id: str, setback_m: float, building_spacing_m: float = 0.0, equalize_repeated: bool = True) -> dict[str, Any]:
    return {"parcels": [], "build_boundary": _build_boundary(site_id, setback_m), "site_polygon": _site_polygon(site_id), "building_spacing_m": building_spacing_m, "equalize_repeated": equalize_repeated}


ROAD_COLOR = "#475569"
ROAD_FUNCTION_WIDTHS_M = {
    "parking": 3.5,
    "office": 3.5,
    "delivery": 3.5,
    "yard": 7.5,
    "outside": 7.5,
    "prod": 7.5,
    "warehouse": 7.5,
    "hall": 7.5,
    "dc": 7.5,
    "tech": 5.0,
    "security": 5.0,
}


def _function_road_width_m(function: dict[str, Any]) -> float:
    key = str(function.get("key", ""))
    if key in ROAD_FUNCTION_WIDTHS_M:
        return ROAD_FUNCTION_WIDTHS_M[key]
    kind = str(function.get("kind", ""))
    if kind in {"building", "outdoor"}:
        return 7.5
    if kind == "technical":
        return 5.0
    return 3.5


FUNCTION_TRAFFIC_MODES = {
    "parking": ("pkw",),
    "office": ("pkw",),
    "delivery": ("pkw", "lkw"),
    "yard": ("lkw",),
    "outside": ("lkw",),
    "prod": ("lkw",),
    "warehouse": ("lkw",),
    "hall": ("lkw",),
    "dc": ("pkw", "lkw"),
    "tech": ("lkw",),
    "security": ("pkw",),
}
TRAFFIC_MODE_WIDTHS_M = {"pkw": 3.5, "lkw": 7.5}


def _function_traffic_modes(function: dict[str, Any]) -> tuple[str, ...]:
    key = str(function.get("key", ""))
    if key in FUNCTION_TRAFFIC_MODES:
        return FUNCTION_TRAFFIC_MODES[key]
    kind = str(function.get("kind", ""))
    if kind in {"building", "outdoor", "technical"}:
        return ("lkw",)
    if kind == "parking":
        return ("pkw",)
    return ("pkw",)


def _function_access_need(function: dict[str, Any]) -> str:
    modes = _function_traffic_modes(function)
    if "lkw" in modes:
        return "lkw"
    return "pkw"


def _road_strategy_kind(functions: list[dict[str, Any]]) -> str:
    keys = {str(function.get("key", "")) for function in functions}
    if "dc" in keys:
        return "secure_spine"
    if "hall" in keys:
        return "logistics_spine"
    if "prod" in keys or "warehouse" in keys:
        return "production_spine"
    if "office" in keys and not ({"prod", "warehouse", "hall"} & keys):
        return "office_access"
    return "mixed_spine"


def _strategy_needs_cross_axis(strategy: str) -> bool:
    return strategy in {"production_spine", "logistics_spine", "mixed_spine", "secure_spine"}


def _line_inside_site(line: LineString, site_polygon: Polygon) -> LineString:
    clipped = line.intersection(site_polygon)
    if clipped.is_empty:
        return line
    if clipped.geom_type == "LineString":
        return clipped
    lines = [geom for geom in getattr(clipped, "geoms", []) if geom.geom_type == "LineString"]
    return max(lines, key=lambda geom: geom.length) if lines else line


def _placed_traffic_targets(site_id: str, functions: list[dict[str, Any]], parcels: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    placements = _placement_store().get(site_id, {})
    parcel_by_id = {parcel["function"]["id"]: parcel for parcel in (parcels or [])}
    targets: list[dict[str, Any]] = []
    for function in functions:
        placement = placements.get(function["id"])
        if not placement:
            continue
        modes = _function_traffic_modes(function)
        if not modes:
            continue
        anchor = tuple(placement["anchor"])
        parcel = parcel_by_id.get(function["id"])
        point = (float(anchor[0]), float(anchor[1]))
        if parcel is not None:
            centroid = parcel["geometry"].centroid
            point = (float(centroid.x), float(centroid.y))
        targets.append({
            "id": function["id"],
            "name": function["name"],
            "function": function,
            "point": point,
            "anchor": (float(anchor[0]), float(anchor[1])),
            "geometry": None if parcel is None else parcel["geometry"],
            "modes": modes,
            "priority": _priority_value(function.get("priority", 99)),
            "width_m": _function_road_width_m(function),
            "order": placement.get("order", 0),
        })
    targets.sort(key=lambda item: (item["priority"], -float(item["function"].get("area_m2", 0.0)), item["order"]))
    return targets


def _line_from_access_to_center(site_polygon: Polygon, access: dict[str, Any]) -> LineString:
    start = (float(access["point"][0]), float(access["point"][1]))
    center = site_polygon.representative_point()
    end = (float(center.x), float(center.y))
    return _line_inside_site(LineString([start, end]), site_polygon)


def _orthogonal_route_candidates(start: Point2D, end: Point2D) -> list[LineString]:
    sx, sy = start
    ex, ey = end
    candidates = [
        _clean_line([(sx, sy), (ex, ey)]),
        _clean_line([(sx, sy), (sx, ey), (ex, ey)]),
        _clean_line([(sx, sy), (ex, sy), (ex, ey)]),
    ]
    unique: list[LineString] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for line in candidates:
        key = tuple((round(float(x), 2), round(float(y), 2)) for x, y in line.coords)
        if key in seen:
            continue
        seen.add(key)
        unique.append(line)
    return unique


def _target_connection_points(target: dict[str, Any], source_point: Point2D) -> list[Point2D]:
    geometry = target.get("geometry")
    if geometry is None or geometry.is_empty:
        return [target["point"]]
    boundary = geometry.boundary
    source = Point(source_point)
    nearest = boundary.interpolate(boundary.project(source))
    minx, miny, maxx, maxy = geometry.bounds
    cx, cy = float(geometry.centroid.x), float(geometry.centroid.y)
    points = [
        (float(nearest.x), float(nearest.y)),
        (minx, cy),
        (maxx, cy),
        (cx, miny),
        (cx, maxy),
    ]
    unique: list[Point2D] = []
    seen: set[tuple[float, float]] = set()
    for x, y in points:
        key = (round(float(x), 2), round(float(y), 2))
        if key in seen:
            continue
        seen.add(key)
        unique.append((float(x), float(y)))
    return unique


def _best_function_graph_route(site_polygon: Polygon, start: Point2D, end: Point2D, width_m: float, blockers: list[Any] | None = None) -> LineString:
    candidates = _orthogonal_route_candidates(start, end)
    blockers = blockers or []
    minx, miny, maxx, maxy = site_polygon.bounds
    margin = max(width_m / 2.0 + 2.0, 5.0)
    sx, sy = start
    ex, ey = end
    inside_sx = min(max(sx, minx + margin), maxx - margin)
    inside_sy = min(max(sy, miny + margin), maxy - margin)
    for blocker in blockers:
        bx0, by0, bx1, by1 = blocker.bounds
        for via_x in (bx0 - margin, bx1 + margin):
            if minx + margin <= via_x <= maxx - margin:
                candidates.append(_clean_line([(sx, sy), (sx, inside_sy), (via_x, inside_sy), (via_x, ey), (ex, ey)]))
        for via_y in (by0 - margin, by1 + margin):
            if miny + margin <= via_y <= maxy - margin:
                candidates.append(_clean_line([(sx, sy), (inside_sx, sy), (inside_sx, via_y), (ex, via_y), (ex, ey)]))
    # Keep the interactive graph routing bounded. The grid fallback is useful
    # for one-off routing, but it is too expensive here because this function
    # is called many times while scoring possible road connections.
    unique: list[LineString] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for line in candidates:
        key = tuple((round(float(x), 2), round(float(y), 2)) for x, y in line.coords)
        if key in seen:
            continue
        seen.add(key)
        unique.append(line)
    candidates = unique

    def score(line: LineString) -> tuple[float, float, float, float]:
        raw_corridor = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
        outside_area = float(raw_corridor.difference(site_polygon.buffer(0.01)).area)
        blocker_area = sum(float(raw_corridor.intersection(blocker).area) for blocker in blockers)
        diagonal_penalty = 0.0 if len(line.coords) > 2 else 8.0
        return (blocker_area, outside_area, float(line.length) + diagonal_penalty, abs(line.bounds[2] - line.bounds[0]) + abs(line.bounds[3] - line.bounds[1]))

    best = min(candidates, key=score)
    clipped = _line_inside_site(best, site_polygon)
    return clipped if clipped.length > 0.1 else best


def _traffic_node_distance(site_polygon: Polygon, start: Point2D, end: Point2D, width_m: float, blockers: list[Any] | None = None) -> tuple[float, LineString]:
    line = _best_function_graph_route(site_polygon, start, end, width_m, blockers)
    raw_corridor = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
    outside_area = float(raw_corridor.difference(site_polygon.buffer(0.01)).area)
    blocker_area = sum(float(raw_corridor.intersection(blocker).area) for blocker in (blockers or []))
    return outside_area * 10_000.0 + blocker_area * 2_500.0 + float(line.length), line


def _road_base_width_m(mode: str, road_options: dict[str, str]) -> float:
    base = TRAFFIC_MODE_WIDTHS_M.get(mode, 7.5)
    objective = road_options.get("objective", "balanced")
    if objective == "traffic":
        return base + 1.0
    if objective == "area":
        return max(3.0 if mode == "pkw" else 6.5, base - 0.5)
    return base


def _access_width_for_road_mode(access: dict[str, Any], mode: str, road_options: dict[str, str]) -> float:
    base = _road_base_width_m(mode, road_options)
    if mode == "pkw":
        return base
    if mode == "both":
        return max(base, _access_width_m(str(access.get("access_type", "both"))))
    return max(base, _access_width_m(str(access.get("access_type", "both"))))


def _target_key(target: dict[str, Any]) -> str:
    return str(target.get("function", {}).get("key", ""))


def _node_key(node: dict[str, Any]) -> str:
    return str(node.get("function_key", ""))


def _option_score_adjustment(target: dict[str, Any], node: dict[str, Any], mode: str, road_options: dict[str, str], connected: list[dict[str, Any]], remaining: list[dict[str, Any]], segments: list[dict[str, Any]]) -> float:
    target_key = _target_key(target)
    source_key = _node_key(node)
    score = 0.0
    network = road_options.get("network", "auto")
    service = road_options.get("service", "auto")
    parking = road_options.get("parking", "auto")

    if network == "spine" and segments:
        score += -35_000.0 if node.get("kind") == "function" else 18_000.0
    elif network == "minimal" and node.get("kind") == "function":
        score += 45_000.0
    elif network == "loop" and node.get("kind") == "function":
        score -= 18_000.0

    if mode in {"lkw", "both"}:
        yard_connected = any(_node_key(item) == "yard" for item in connected)
        yard_remaining = any(_target_key(item) == "yard" for item in remaining)
        if service == "central_yard":
            if target_key == "yard":
                score -= 60_000.0
            elif yard_connected and source_key == "yard":
                score -= 20_000.0
            elif yard_connected and node.get("kind") == "access":
                score += 12_000.0
            elif yard_remaining and target_key != "yard":
                score += 35_000.0
        elif service == "per_building":
            if node.get("kind") == "access" and target_key in {"prod", "warehouse", "hall", "dc", "tech", "outside"}:
                score -= 1_200.0
            if source_key == "yard" and target_key in {"prod", "warehouse", "hall"}:
                score += 1_500.0

    if mode in {"pkw", "both"}:
        office_connected = any(_node_key(item) == "office" for item in connected)
        if parking == "entrance":
            parking_remaining = any(_target_key(item) == "parking" for item in remaining)
            if parking_remaining and target_key != "parking":
                score += 25_000.0
            if target_key == "parking" and node.get("kind") == "access":
                score -= 50_000.0
            elif target_key == "parking":
                score += 20_000.0
        elif parking == "office":
            if target_key == "office" and not office_connected:
                score -= 4_000.0
            if target_key == "parking" and source_key == "office":
                score -= 10_000.0
            elif target_key == "parking" and not office_connected:
                score += 2_500.0
        elif parking == "edge":
            if target_key == "parking" and node.get("kind") == "access":
                score -= 5_000.0
            elif target_key == "parking":
                score += 900.0
    return score


def _build_mode_graph_segments(site_polygon: Polygon, access_points: list[dict[str, Any]], targets: list[dict[str, Any]], mode: str, strategy: str, road_options: dict[str, str] | None = None) -> list[dict[str, Any]]:
    road_options = road_options or {}
    mode_targets = list(targets) if mode == "both" else [target for target in targets if mode in target["modes"]]
    if not mode_targets or not access_points:
        return []
    compatible_accesses = list(access_points) if mode == "both" else [access for access in access_points if _access_supports_need(access, mode)] or access_points
    connected: list[dict[str, Any]] = [
        {
            "kind": "access",
            "id": access["id"],
            "name": access["id"],
            "point": (float(access["point"][0]), float(access["point"][1])),
            "access": access,
            "width_m": _access_width_for_road_mode(access, mode, road_options),
            "function_key": "access",
        }
        for access in compatible_accesses
    ]
    remaining = list(mode_targets)
    segments: list[dict[str, Any]] = []
    while remaining:
        best: tuple[float, dict[str, Any], dict[str, Any], LineString] | None = None
        for target in remaining:
            for node in connected:
                width_m = max(_road_base_width_m(mode, road_options), float(target["width_m"]), float(node.get("width_m", 0.0)))
                blockers = [item["geometry"] for item in targets if item.get("geometry") is not None]
                for end in _target_connection_points(target, node["point"]):
                    score, line = _traffic_node_distance(site_polygon, node["point"], end, width_m, blockers)
                    score += target["priority"] * 2.0
                    score += _option_score_adjustment(target, node, mode, road_options, connected, remaining, segments)
                    if best is None or score < best[0]:
                        best = (score, node, target, line)
        if best is None:
            break
        _, source, target, centerline = best
        width_m = max(_road_base_width_m(mode, road_options), float(target["width_m"]), float(source.get("width_m", 0.0)))
        raw_corridor = centerline.buffer(width_m / 2.0, cap_style=2, join_style=2)
        corridor = raw_corridor.intersection(site_polygon)
        segments.append({
            "id": f"S{len(segments) + 1}",
            "kind": "access_link" if source["kind"] == "access" else "function_link",
            "strategy": strategy,
            "mode": mode,
            "access_id": source["id"] if source["kind"] == "access" else source.get("access_id", "-"),
            "access_type": mode,
            "function_id": target["id"],
            "function_name": target["name"],
            "function_key": target["function"].get("key"),
            "need": mode,
            "source_id": source["id"],
            "target_id": target["id"],
            "width_m": width_m,
            "road_options": dict(road_options),
            "centerline": centerline,
            "corridor": corridor,
            "length_m": float(centerline.length),
            "area_m2": float(corridor.area),
            "outside_area_m2": float(raw_corridor.difference(site_polygon.buffer(0.01)).area),
        })
        connected.append({
            "kind": "function",
            "id": target["id"],
            "name": target["name"],
            "point": (float(centerline.coords[-1][0]), float(centerline.coords[-1][1])),
            "geometry": target.get("geometry"),
            "function_key": target["function"].get("key"),
            "access_id": segments[-1]["access_id"],
            "width_m": width_m,
        })
        remaining = [item for item in remaining if item["id"] != target["id"]]
    return segments


def _merge_duplicate_road_segments(segments: list[dict[str, Any]], site_polygon: Polygon) -> list[dict[str, Any]]:
    merged: dict[tuple[tuple[float, float], ...], dict[str, Any]] = {}
    for segment in segments:
        coords = tuple((round(float(x), 2), round(float(y), 2)) for x, y in segment["centerline"].coords)
        reverse_coords = tuple(reversed(coords))
        key = min(coords, reverse_coords)
        if key not in merged:
            item = dict(segment)
            item["modes"] = {str(segment.get("mode", segment.get("need", "both")))}
            merged[key] = item
            continue
        item = merged[key]
        item["width_m"] = max(float(item["width_m"]), float(segment["width_m"]))
        item["modes"].add(str(segment.get("mode", segment.get("need", "both"))))
        item["need"] = "both" if len(item["modes"]) > 1 else next(iter(item["modes"]))
        raw_corridor = item["centerline"].buffer(float(item["width_m"]) / 2.0, cap_style=2, join_style=2)
        item["corridor"] = raw_corridor.intersection(site_polygon)
        item["area_m2"] = float(item["corridor"].area)
        item["outside_area_m2"] = float(raw_corridor.difference(site_polygon.buffer(0.01)).area)
    result = list(merged.values())
    for index, segment in enumerate(result, start=1):
        segment["id"] = f"S{index}"
        segment.pop("modes", None)
    return result


def _road_strategy_label(functions: list[dict[str, Any]], targets: list[dict[str, Any]]) -> str:
    base = _road_strategy_kind(functions)
    target_count = len(targets)
    if target_count <= 1:
        return f"{base}_single_target"
    if target_count <= 3:
        return f"{base}_small_graph"
    return f"{base}_function_graph"


def _build_road_strategy(site_id: str, access_points: list[dict[str, Any]], functions: list[dict[str, Any]], setback_m: float, parcels: list[dict[str, Any]] | None = None, road_options: dict[str, str] | None = None) -> dict[str, Any]:
    road_options = road_options or {}
    site_polygon = _site_polygon(site_id)
    targets = _placed_traffic_targets(site_id, functions, parcels)
    strategy = _road_strategy_label(functions, targets)
    flow = road_options.get("flow", "auto")
    if flow == "auto":
        flow = "separate" if any("lkw" in target["modes"] for target in targets) and any("pkw" in target["modes"] for target in targets) else "shared"
    mode_sequence = ("both",) if flow == "shared" else ("lkw", "pkw")
    segments: list[dict[str, Any]] = []
    for mode in mode_sequence:
        segments.extend(_build_mode_graph_segments(site_polygon, access_points, targets, mode, strategy, road_options))
    segments = _merge_duplicate_road_segments(segments, site_polygon)
    return {
        "strategy": strategy,
        "target_count": len(targets),
        "road_options": dict(road_options),
        "resolved_flow": flow,
        "segments": segments,
        "total_area_m2": sum(float(segment["area_m2"]) for segment in segments),
        "hard_ok": all(float(segment.get("outside_area_m2", 0.0)) <= 1.0 for segment in segments),
    }

def _road_strategy_blockers(site_id: str, access_points: list[dict[str, Any]], functions: list[dict[str, Any]], setback_m: float) -> list[dict[str, Any]]:
    site_polygon = _site_polygon(site_id)
    blockers: list[dict[str, Any]] = []
    for access in access_points:
        start = (float(access["point"][0]), float(access["point"][1]))
        inward = _line_from_access_to_center(site_polygon, access)
        if inward.length <= 0.1:
            continue
        width_m = _access_width_m(str(access.get("access_type", "both")))
        throat_length = min(max(width_m, 8.0), float(inward.length))
        throat = LineString([inward.interpolate(0.0), inward.interpolate(throat_length)])
        geom = throat.buffer(width_m / 2.0, cap_style=2, join_style=2).intersection(site_polygon)
        if geom.is_empty:
            continue
        blockers.append({
            "_geometry_blocker": True,
            "id": f"road_throat_{access['id']}",
            "function": {"id": f"road_throat_{access['id']}", "kind": "road", "priority": 0},
            "geometry": geom,
            "strategy_segment": {"id": access["id"], "kind": "access_throat", "access_id": access["id"]},
            "allowed_function_ids": set(),
        })
    return blockers


def _access_supports_need(access: dict[str, Any], need: str) -> bool:
    access_type = str(access.get("access_type", "both"))
    return access_type == "both" or access_type == need


def _nearest_access_for_parcel(parcel: dict[str, Any], access_points: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not access_points:
        return None
    need = _function_access_need(parcel["function"])
    compatible = [item for item in access_points if _access_supports_need(item, need)]
    candidates = compatible or access_points
    target = parcel["geometry"].centroid
    return min(candidates, key=lambda item: math.dist(tuple(item["point"]), (target.x, target.y)))


def _clean_line(points: list[Point2D]) -> LineString:
    cleaned: list[Point2D] = []
    for point in points:
        if not cleaned or math.dist(cleaned[-1], point) > 0.05:
            cleaned.append(point)
    if len(cleaned) == 1:
        cleaned.append(cleaned[0])
    return LineString(cleaned)


def _route_line_candidates(site_polygon: Polygon, start: Point2D, end: Point2D, width_m: float) -> list[LineString]:
    sx, sy = start
    ex, ey = end
    minx, miny, maxx, maxy = site_polygon.bounds
    margin = max(width_m / 2.0 + 2.0, 5.0)
    via_x_values = [sx, ex, (sx + ex) / 2.0, minx + margin, maxx - margin]
    via_y_values = [sy, ey, (sy + ey) / 2.0, miny + margin, maxy - margin]
    candidates = [
        _clean_line([(sx, sy), (sx, ey), (ex, ey)]),
        _clean_line([(sx, sy), (ex, sy), (ex, ey)]),
        _clean_line([(sx, sy), (ex, ey)]),
    ]
    for via_x in via_x_values:
        candidates.append(_clean_line([(sx, sy), (via_x, sy), (via_x, ey), (ex, ey)]))
    for via_y in via_y_values:
        candidates.append(_clean_line([(sx, sy), (sx, via_y), (ex, via_y), (ex, ey)]))
    unique: list[LineString] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for line in candidates:
        key = tuple((round(float(x), 2), round(float(y), 2)) for x, y in line.coords)
        if key in seen:
            continue
        seen.add(key)
        unique.append(line)
    return unique


def _line_blocker_area(line: LineString, width_m: float, blockers: list[Any]) -> float:
    corridor = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
    return sum(float(corridor.intersection(blocker).area) for blocker in blockers)


def _grid_route_line(site_polygon: Polygon, start: Point2D, end: Point2D, width_m: float, blockers: list[Any], step_m: float = 5.0) -> LineString | None:
    minx, miny, maxx, maxy = site_polygon.bounds
    xs = {round(start[0], 2), round(end[0], 2)}
    ys = {round(start[1], 2), round(end[1], 2)}
    x = minx
    while x <= maxx + 0.1:
        xs.add(round(x, 2))
        x += step_m
    y = miny
    while y <= maxy + 0.1:
        ys.add(round(y, 2))
        y += step_m
    xs_sorted = sorted(xs)
    ys_sorted = sorted(ys)

    def point_ok(point: Point2D) -> bool:
        pt = Point(point)
        if not site_polygon.buffer(0.05).covers(pt):
            return False
        for blocker in blockers:
            if blocker.buffer(width_m / 2.0 + 0.25, cap_style=2, join_style=2).contains(pt):
                return False
        return True

    nodes = {(x, y) for x in xs_sorted for y in ys_sorted if point_ok((x, y))}
    nodes.add((round(start[0], 2), round(start[1], 2)))
    nodes.add((round(end[0], 2), round(end[1], 2)))
    start_node = (round(start[0], 2), round(start[1], 2))
    end_node = (round(end[0], 2), round(end[1], 2))

    def edge_ok(a: Point2D, b: Point2D) -> bool:
        if a == b:
            return False
        line = LineString([a, b])
        if float(line.difference(site_polygon.buffer(0.05)).length) > 0.2:
            return False
        return _line_blocker_area(line, width_m, blockers) <= 0.6

    distances: dict[Point2D, float] = {start_node: 0.0}
    previous: dict[Point2D, Point2D] = {}
    queue: list[tuple[float, Point2D]] = [(0.0, start_node)]
    while queue:
        distance, node = heapq.heappop(queue)
        if node == end_node:
            break
        if distance > distances.get(node, float("inf")) + 0.001:
            continue
        x, y = node
        xi = xs_sorted.index(x)
        yi = ys_sorted.index(y)
        neighbors: list[Point2D] = []
        if xi > 0:
            neighbors.append((xs_sorted[xi - 1], y))
        if xi < len(xs_sorted) - 1:
            neighbors.append((xs_sorted[xi + 1], y))
        if yi > 0:
            neighbors.append((x, ys_sorted[yi - 1]))
        if yi < len(ys_sorted) - 1:
            neighbors.append((x, ys_sorted[yi + 1]))
        for neighbor in neighbors:
            if neighbor not in nodes or not edge_ok(node, neighbor):
                continue
            next_distance = distance + math.dist(node, neighbor)
            if next_distance + 0.001 < distances.get(neighbor, float("inf")):
                distances[neighbor] = next_distance
                previous[neighbor] = node
                priority = next_distance + math.dist(neighbor, end_node)
                heapq.heappush(queue, (priority, neighbor))
    if end_node not in distances:
        return None
    path = [end_node]
    while path[-1] != start_node:
        path.append(previous[path[-1]])
    path.reverse()
    simplified: list[Point2D] = []
    for point in path:
        if len(simplified) >= 2:
            a = simplified[-2]
            b = simplified[-1]
            if (a[0] == b[0] == point[0]) or (a[1] == b[1] == point[1]):
                simplified[-1] = point
                continue
        simplified.append(point)
    return _clean_line(simplified)


def _best_route_line(site_polygon: Polygon, start: Point2D, end: Point2D, width_m: float, blockers: list[Any]) -> LineString:
    candidates = _route_line_candidates(site_polygon, start, end, width_m)
    if blockers:
        grid_line = _grid_route_line(site_polygon, start, end, width_m, blockers)
        if grid_line is not None:
            candidates.append(grid_line)

    def score(line: LineString) -> tuple[float, float, float]:
        raw_corridor = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
        outside_area = float(raw_corridor.difference(site_polygon.buffer(0.01)).area)
        blocker_area = sum(float(raw_corridor.intersection(blocker).area) for blocker in blockers)
        return (outside_area, blocker_area, float(line.length))

    return min(candidates, key=score)


def _parcel_access_point(parcel: dict[str, Any], start: Point2D) -> Point2D:
    boundary = parcel["geometry"].boundary
    start_point = Point(start)
    if boundary.is_empty:
        centroid = parcel["geometry"].centroid
        return (float(centroid.x), float(centroid.y))
    nearest = boundary.interpolate(boundary.project(start_point))
    return (float(nearest.x), float(nearest.y))


def _build_road_network(site_id: str, access_points: list[dict[str, Any]], patchwork: dict[str, Any]) -> dict[str, Any]:
    site_polygon = patchwork.get("site_polygon") or _site_polygon(site_id)
    segments: list[dict[str, Any]] = []
    for parcel in patchwork.get("parcels", []):
        access = _nearest_access_for_parcel(parcel, access_points)
        if access is None:
            continue
        function = parcel["function"]
        start = (float(access["point"][0]), float(access["point"][1]))
        end = _parcel_access_point(parcel, start)
        width_m = max(_function_road_width_m(function), _access_width_m(str(access.get("access_type", "both"))))
        if math.dist(start, end) <= 0.1:
            centroid = parcel["geometry"].centroid
            vx, vy = float(centroid.x) - start[0], float(centroid.y) - start[1]
            length = max(0.01, math.hypot(vx, vy))
            throat = max(width_m, 3.0)
            end = (start[0] + vx / length * throat, start[1] + vy / length * throat)
        blockers = [other["geometry"] for other in patchwork.get("parcels", []) if other is not parcel]
        centerline = _best_route_line(site_polygon, start, end, width_m, blockers)
        raw_corridor = centerline.buffer(width_m / 2.0, cap_style=2, join_style=2)
        corridor = raw_corridor.intersection(site_polygon)
        outside_area = float(corridor.difference(site_polygon.buffer(0.01)).area)
        touches_access = corridor.buffer(0.05).contains(Point(start)) or corridor.buffer(0.05).touches(Point(start))
        touches_parcel = corridor.buffer(0.05).intersects(parcel["geometry"])
        segments.append({
            "id": f"R{len(segments) + 1}",
            "function_id": function["id"],
            "function_name": function["name"],
            "function_key": function.get("key"),
            "access_id": access["id"],
            "need": _function_access_need(function),
            "width_m": width_m,
            "centerline": centerline,
            "corridor": corridor,
            "length_m": float(centerline.length),
            "area_m2": float(corridor.area),
            "outside_area_m2": outside_area,
            "touches_access": touches_access,
            "touches_parcel": touches_parcel,
        })
    total_area = sum(float(item["area_m2"]) for item in segments)
    return {
        "segments": segments,
        "total_area_m2": total_area,
        "hard_ok": all(item["outside_area_m2"] <= 0.6 and item["touches_access"] and item["touches_parcel"] for item in segments),
    }


def _with_road_network(site_id: str, access_points: list[dict[str, Any]], patchwork: dict[str, Any], functions: list[dict[str, Any]] | None = None, setback_m: float = 0.0, road_options: dict[str, str] | None = None) -> dict[str, Any]:
    enriched = dict(patchwork)
    strategy_functions = functions if functions is not None else [parcel["function"] for parcel in enriched.get("parcels", [])]
    enriched["road_network"] = _build_road_strategy(site_id, access_points, strategy_functions, setback_m, enriched.get("parcels", []), road_options) if access_points else {"segments": [], "total_area_m2": 0.0, "hard_ok": True}
    return enriched


def _road_blockers_for_rect(site_id: str, access_points: list[dict[str, Any]], rect: dict[str, Any], building_spacing_m: float) -> list[dict[str, Any]]:
    if not access_points or _is_geometry_blocker(rect):
        return []
    parcel = _parcel_from_rect(rect, [rect], building_spacing_m)
    network = _build_road_network(site_id, access_points, {
        "parcels": [parcel],
        "site_polygon": _site_polygon(site_id),
        "build_boundary": rect.get("allowed", _build_boundary(site_id, 0.0)),
    })
    blockers = []
    for segment in network.get("segments", []):
        geom = segment.get("corridor")
        if geom is None or geom.is_empty:
            continue
        blockers.append({
            "_geometry_blocker": True,
            "id": f"road_blocker_{segment['function_id']}",
            "function": {"id": f"road_{segment['function_id']}", "kind": "road", "priority": 0},
            "geometry": geom,
            "source_function_id": segment["function_id"],
        })
    return blockers


def _all_functions_placed(functions: list[dict[str, Any]], placements: dict[str, Any]) -> bool:
    return bool(functions) and all(fn["id"] in placements for fn in functions)


def _polygon_points(geom) -> tuple[list[float], list[float]]:
    if geom is None or geom.is_empty:
        return [], []
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    elif geom.geom_type != "Polygon":
        polygon_parts = []
        for part in getattr(geom, "geoms", []):
            if part.geom_type == "Polygon":
                polygon_parts.append(part)
            elif part.geom_type == "MultiPolygon":
                polygon_parts.extend(list(part.geoms))
        if not polygon_parts:
            return [], []
        geom = max(polygon_parts, key=lambda g: g.area)
    coords = list(geom.exterior.coords)
    return [float(x) for x, _ in coords], [float(y) for _, y in coords]


def _sample_geometry(geom, spacing_m: float = 5.0) -> list[Point2D]:
    if geom.is_empty:
        return []
    minx, miny, maxx, maxy = geom.bounds
    points: list[Point2D] = []
    y = miny + spacing_m / 2
    while y <= maxy:
        x = minx + spacing_m / 2
        while x <= maxx:
            point = Point(x, y)
            if geom.contains(point) or geom.touches(point):
                points.append((round(x, 2), round(y, 2)))
            x += spacing_m
        y += spacing_m
    if not points:
        centroid = geom.centroid
        points.append((round(float(centroid.x), 2), round(float(centroid.y), 2)))
    return points


def _component_points(geom) -> list[list[float]]:
    xs, ys = _polygon_points(geom)
    return [[round(float(x), 2), round(float(y), 2)] for x, y in zip(xs, ys)]


def _function_chip_scale_px(function: dict[str, Any]) -> int:
    area = max(100.0, float(function.get("area_m2", 100.0)))
    return int(max(20, min(48, round(math.sqrt(area) / 1.45))))


def _drag_plan_payload(site_id: str, access_points: list[dict[str, Any]], patchwork: dict[str, Any], functions: list[dict[str, Any]], placements: dict[str, Any], selected_function_id: str | None) -> dict[str, Any]:
    polygon = _site_polygon(site_id)
    minx, miny, maxx, maxy = polygon.bounds
    pad = max(12.0, max(maxx - minx, maxy - miny) * 0.12)
    function_by_id = {fn["id"]: fn for fn in functions}
    active_label = function_by_id[selected_function_id]["name"] if selected_function_id in function_by_id else "-"
    parcels = []
    clearances = []
    for parcel in patchwork.get("parcels", []):
        fn = parcel["function"]
        parcels.append({
            "id": fn["id"],
            "name": fn["name"],
            "color": _function_color(fn),
            "points": _component_points(parcel["display_geometry"]),
            "center": [round(float(parcel["display_geometry"].centroid.x), 2), round(float(parcel["display_geometry"].centroid.y), 2)],
            "actual_area_m2": round(float(parcel["actual_area_m2"]), 1),
            "target_area_m2": round(float(parcel["target_area_m2"]), 1),
            "status": parcel["status"],
        })
        if _is_building_function(fn) and patchwork.get("building_spacing_m", 0.0) > 0:
            clearances.append({"id": fn["id"], "points": _component_points(parcel.get("clearance_geometry", parcel["geometry"]))})

    missing = []
    for item in patchwork.get("missing", []):
        if item.get("optional"):
            continue
        geom = item.get("placeholder_geometry", Polygon())
        if geom.is_empty:
            continue
        fn = item["function"]
        missing.append({
            "id": fn["id"],
            "name": fn["name"],
            "points": _component_points(geom),
            "center": [round(float(geom.centroid.x), 2), round(float(geom.centroid.y), 2)],
        })

    road_payload = []
    for segment in patchwork.get("road_network", {}).get("segments", []):
        centerline = segment.get("centerline")
        centerline_points = []
        if centerline is not None and not centerline.is_empty:
            centerline_points = [[round(float(x), 2), round(float(y), 2)] for x, y in centerline.coords]
        road_payload.append({
            "id": segment["id"],
            "function_id": segment.get("function_id", segment.get("kind", "road")),
            "function_name": segment.get("function_name", segment.get("kind", "Straße")),
            "access_id": segment.get("access_id", "-"),
            "need": segment.get("need", segment.get("access_type", "both")),
            "width_m": round(float(segment["width_m"]), 1),
            "length_m": round(float(segment["length_m"]), 1),
            "area_m2": round(float(segment["area_m2"]), 1),
            "points": _component_points(segment.get("corridor", Polygon())),
            "centerline": centerline_points,
        })

    access_payload = []
    for access in access_points:
        (sx, sy), (ex, ey) = _access_edge_segment(access)
        access_type = access.get("access_type", "both")
        label = ACCESS_TYPE_LABELS.get(access_type, ACCESS_TYPE_LABELS["both"])
        width_m = _access_width_m(access_type)
        access_payload.append({
            "id": access["id"],
            "point": [round(float(access["point"][0]), 2), round(float(access["point"][1]), 2)],
            "segment": [[round(float(sx), 2), round(float(sy), 2)], [round(float(ex), 2), round(float(ey), 2)]],
            "label": f"{access['id']} · {label} · {width_m:.1f} m",
            "color": ACCESS_TYPE_COLORS.get(access_type, ACCESS_TYPE_COLORS["both"]),
        })

    return {
        "bounds": {"minx": minx - pad, "miny": miny - pad, "maxx": maxx + pad, "maxy": maxy + pad},
        "site_polygon": [[round(float(x), 2), round(float(y), 2)] for x, y in list(polygon.exterior.coords)],
        "build_boundary": _component_points(patchwork["build_boundary"]),
        "functions": [
            {
                "id": fn["id"],
                "name": fn["name"],
                "kind": fn["kind"],
                "priority": _priority_label(fn.get("priority", "-")),
                "area_m2": round(float(fn["area_m2"]), 1),
                "color": _function_color(fn),
                "chip_size_px": _function_chip_scale_px(fn),
                "generator": _geometry_generator_label(fn),
            }
            for fn in functions
        ],
        "placements": {
            fid: {"anchor": [round(float(value["anchor"][0]), 2), round(float(value["anchor"][1]), 2)], "order": value.get("order", 0)}
            for fid, value in placements.items()
            if fid in function_by_id
        },
        "selected_function_id": selected_function_id,
        "active_label": active_label,
        "parcels": parcels,
        "clearances": clearances,
        "missing": missing,
        "access_points": access_payload,
        "roads": road_payload,
        "road_summary": {
            "segments": len(road_payload),
            "total_area_m2": round(float(patchwork.get("road_network", {}).get("total_area_m2", 0.0)), 1),
            "hard_ok": bool(patchwork.get("road_network", {}).get("hard_ok", True)),
        },
        "area_summary": _area_summary_rows(functions, patchwork),
    }


def _base_function_name(name: str) -> str:
    head, sep, tail = str(name).rpartition(" ")
    return head if sep and tail.isdigit() else str(name)


def _area_summary_rows(functions: list[dict[str, Any]], patchwork: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for fn in functions:
        key = str(fn.get("key", fn["id"]))
        row = grouped.setdefault(key, {"function": _base_function_name(fn["name"]), "required_m2": 0.0, "realized_m2": 0.0})
        row["required_m2"] += float(fn.get("area_m2", 0.0))
    for parcel in patchwork.get("parcels", []):
        fn = parcel["function"]
        key = str(fn.get("key", fn["id"]))
        row = grouped.setdefault(key, {"function": _base_function_name(fn["name"]), "required_m2": 0.0, "realized_m2": 0.0})
        row["realized_m2"] += float(parcel.get("actual_area_m2", 0.0))
    rows = []
    for row in grouped.values():
        required = float(row["required_m2"])
        realized = float(row["realized_m2"])
        diff = realized - required
        diff_pct = diff / required * 100.0 if required > 0 else 0.0
        rows.append({
            "function": row["function"],
            "required_m2": round(required, 1),
            "realized_m2": round(realized, 1),
            "diff_m2": round(diff, 1),
            "diff_pct": round(diff_pct, 1),
        })
    return rows


def _function_rows(functions: list[dict[str, Any]], patchwork: dict[str, Any], placements: dict[str, Any]) -> list[dict[str, str]]:
    optimized = {parcel["function"]["id"]: parcel for parcel in patchwork["parcels"]}
    missing = {item["function"]["id"]: item for item in patchwork.get("missing", [])}
    rows = []
    for fn in functions:
        parcel = optimized.get(fn["id"])
        is_placed = fn["id"] in placements
        if parcel:
            status = parcel["status"]
            actual = f"{parcel['actual_area_m2']:.0f}"
            coverage = f"{parcel['coverage_pct']:.0f} %"
            distance = f"{parcel.get('anchor_gap_m', parcel['center_distance_m']):.1f} m"
        elif fn["id"] in missing:
            status = missing[fn["id"]].get("status", "nicht platzierbar")
            actual = "0"
            coverage = "0 %"
            distance = "-"
        else:
            status = "Platzhalter fehlt" if not is_placed else "wartet"
            actual = "-"
            coverage = "-"
            distance = "-"
        rows.append({
            "Funktion": fn["name"],
            "Prio": _priority_label(fn.get("priority", "-")),
            "Typ": FUNCTION_KIND_LABELS.get(fn["kind"], fn["kind"]),
            "Generator": _geometry_generator_label(fn),
            "Form": _shape_label(fn),
            "Flucht": _alignment_label_for_function(fn),
            "Soll m²": f"{fn['area_m2']:.0f}",
            "Platzhalter": "gesetzt" if is_placed else "offen",
            "Ist m²": actual,
            "Deckung": coverage,
            "Abstand": distance,
            "Status": status,
        })
    return rows


def render_site_figure(site_id: str, access_points: list[dict[str, Any]], patchwork: dict[str, Any], click_mode: str, functions: list[dict[str, Any]], placements: dict[str, Any], selected_function_id: str | None) -> go.Figure:
    site = DEMO_SITES[site_id]
    polygon = _site_polygon(site_id)
    minx, miny, maxx, maxy = polygon.bounds
    pad = max(12.0, max(maxx - minx, maxy - miny) * 0.12)
    poly_x = [p[0] for p in site.polygon] + [site.polygon[0][0]]
    poly_y = [p[1] for p in site.polygon] + [site.polygon[0][1]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=poly_x, y=poly_y, mode="lines", fill="toself", fillcolor="#E8EEE8", line={"color": "#1F2937", "width": 2}, hoverinfo="skip", showlegend=False, name="Grundstück"))
    bx, by = _polygon_points(patchwork["build_boundary"])
    if bx:
        fig.add_trace(go.Scatter(x=bx, y=by, mode="lines", line={"color": "#64748B", "width": 2, "dash": "dash"}, hovertemplate="Baugrenze<extra></extra>", showlegend=False, name="Baugrenze"))
    function_by_id = {fn["id"]: fn for fn in functions}
    active_name = function_by_id[selected_function_id]["name"] if selected_function_id and selected_function_id in function_by_id else "Funktion"
    for segment in patchwork.get("road_network", {}).get("segments", []):
        xs, ys = _polygon_points(segment.get("corridor", Polygon()))
        if xs:
            fig.add_trace(go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="toself",
                fillcolor="rgba(71,85,105,0.20)",
                line={"color": "rgba(51,65,85,0.72)", "width": 1},
                hovertemplate=f"Straße {segment['id']}<br>{segment.get('kind', segment.get('function_name', 'Trasse'))}<br>Breite {segment['width_m']:.1f} m<br>Länge {segment['length_m']:.1f} m<extra></extra>",
                showlegend=False,
                name=f"{segment['id']}_corridor",
            ))
        centerline = segment.get("centerline")
        if centerline is not None and not centerline.is_empty:
            coords = list(centerline.coords)
            fig.add_trace(go.Scatter(
                x=[float(x) for x, _ in coords],
                y=[float(y) for _, y in coords],
                mode="lines",
                line={"color": "rgba(15,23,42,0.50)", "width": 1, "dash": "dash"},
                hoverinfo="skip",
                showlegend=False,
                name=f"{segment['id']}_centerline",
            ))

    if click_mode != "Zufahrt setzen":
        samples = _sample_interior(site_id)
        fig.add_trace(go.Scatter(
            x=[p[0] for p in samples],
            y=[p[1] for p in samples],
            mode="markers",
            marker={"size": 26, "color": "rgba(17,24,39,0.01)", "line": {"width": 0}},
            customdata=[["function_target", ""] for _ in samples],
            hovertemplate=(f"{active_name}<br>nächster Rasterpunkt<br>x=%{{x:.1f}} m<br>y=%{{y:.1f}} m<extra></extra>" if selected_function_id and selected_function_id in function_by_id else "Platzhalter hier platzieren<br>x=%{x:.1f} m<br>y=%{y:.1f} m<extra></extra>"),
            showlegend=False,
            name="Klickfläche Funktion",
        ))
    for parcel in patchwork["parcels"]:
        fn = parcel["function"]
        color = _function_color(fn)
        xs, ys = _polygon_points(parcel["display_geometry"])
        if xs:
            opacity = 0.32 if parcel["status"] == "reduziert" else 0.48
            dash = "dot" if parcel["status"] == "reduziert" else "solid"
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=color, opacity=opacity, line={"color": color, "width": 1.6, "dash": dash}, hovertemplate=f"{fn['name']}<br>{parcel['actual_area_m2']:.0f} / {fn['area_m2']:.0f} m²<br>{parcel['status']}<extra></extra>", showlegend=False, name=fn["name"]))
            click_points = _sample_geometry(parcel["display_geometry"], spacing_m=5.0)
            fig.add_trace(go.Scatter(
                x=[p[0] for p in click_points],
                y=[p[1] for p in click_points],
                mode="markers",
                marker={"size": 28, "color": "rgba(17,24,39,0.01)", "line": {"width": 0}},
                customdata=[["function_rect", fn["id"]] for _ in click_points],
                hovertemplate=f"{fn['name']} auswählen<extra></extra>",
                showlegend=False,
                name=f"{fn['id']}_rect_click",
            ))
            cx, cy = parcel["display_geometry"].centroid.coords[0]
            fig.add_trace(go.Scatter(x=[cx], y=[cy], mode="text", text=[f"{fn['name']}<br>{parcel['actual_area_m2']:.0f} m²"], textfont={"color": "#111827", "size": 12}, hoverinfo="skip", showlegend=False, name=f"{fn['id']}_label"))
        ax, ay = parcel["anchor"]
        is_active = fn["id"] == selected_function_id
        fig.add_trace(go.Scatter(
            x=[ax],
            y=[ay],
            mode="markers",
            marker=_function_chip_marker(fn, is_active),
            customdata=[["function_anchor", fn["id"]]],
            hovertemplate=f"Platzhalter {fn['name']}<br>auswählen und neu platzieren<extra></extra>",
            showlegend=False,
            name=f"{fn['id']}_anchor",
        ))
    for item in patchwork.get("missing", []):
        if item.get("optional"):
            continue
        fn = item["function"]
        color = "#B91C1C"
        xs, ys = _polygon_points(item.get("placeholder_geometry", Polygon()))
        if xs:
            fig.add_trace(go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="toself",
                fillcolor="rgba(185,28,28,0.08)",
                line={"color": color, "width": 2, "dash": "dash"},
                hovertemplate=f"{fn['name']}<br>nicht platzierbar<extra></extra>",
                showlegend=False,
                name=f"{fn['id']}_missing_placeholder",
            ))
            cx, cy = item.get("placeholder_geometry", Polygon()).centroid.coords[0]
            fig.add_trace(go.Scatter(
                x=[cx],
                y=[cy],
                mode="text",
                text=[f"{fn['name']}<br>nicht platzierbar"],
                textfont={"color": color, "size": 12},
                hoverinfo="skip",
                showlegend=False,
                name=f"{fn['id']}_missing_label",
            ))

    placed_parcel_ids = {parcel["function"]["id"] for parcel in patchwork["parcels"]}
    for function_id, placement in placements.items():
        fn = function_by_id.get(function_id)
        if not fn or function_id in placed_parcel_ids:
            continue
        ax, ay = placement["anchor"]
        color = _function_color(fn)
        fig.add_trace(go.Scatter(
            x=[ax],
            y=[ay],
            mode="markers+text",
            marker=_function_chip_marker(fn, function_id == selected_function_id),
            customdata=[["function_anchor", function_id]],
            text=[fn["name"]],
            textposition="top right",
            textfont={"color": color, "size": 12},
            hovertemplate=f"Platzhalter {fn['name']}<br>auswählen und neu platzieren<extra></extra>",
            showlegend=False,
            name=f"{fn['id']}_anchor_pending",
        ))
    clearance_color = "rgba(31,41,55,0.28)"
    for parcel in patchwork["parcels"]:
        if not _is_building_function(parcel["function"]) or patchwork.get("building_spacing_m", 0.0) <= 0:
            continue
        xs, ys = _polygon_points(parcel.get("clearance_geometry", parcel["geometry"]))
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"color": clearance_color, "width": 1, "dash": "dot"}, hovertemplate=f"Abstandspuffer {parcel['function']['name']}<extra></extra>", showlegend=False, name=f"{parcel['function']['id']}_clearance"))

    if selected_function_id and selected_function_id in function_by_id:
        fig.add_annotation(
            x=0.01,
            y=0.99,
            xref="paper",
            yref="paper",
            text=f"Aktiv: {active_name}",
            showarrow=False,
            align="left",
            bgcolor="rgba(255,255,255,0.86)",
            bordercolor="#CBD5E1",
            borderwidth=1,
            font={"size": 13, "color": "#111827"},
        )
    if click_mode == "Zufahrt setzen":
        samples = _sample_boundary(site_id)
        fig.add_trace(go.Scatter(x=[p[0] for p in samples], y=[p[1] for p in samples], mode="markers", marker={"size": 18, "color": "rgba(37,99,235,0.01)", "line": {"width": 0}}, customdata=[["access_target", ""] for _ in samples], hovertemplate="Zufahrt hier setzen<br>x=%{x:.1f} m<br>y=%{y:.1f} m<extra></extra>", showlegend=False, name="Klickfläche Zufahrt"))
    for access in access_points:
        x, y = access["point"]
        access_type = access.get("access_type", "both")
        label = ACCESS_TYPE_LABELS.get(access_type, ACCESS_TYPE_LABELS["both"])
        width_m = _access_width_m(access_type)
        color = ACCESS_TYPE_COLORS.get(access_type, ACCESS_TYPE_COLORS["both"])
        (sx, sy), (ex, ey) = _access_edge_segment(access)
        fig.add_trace(go.Scatter(x=[sx, ex], y=[sy, ey], mode="lines", line={"color": color, "width": 10}, hovertemplate=f"{access['id']} · {label}<br>Breite {width_m:.1f} m<extra></extra>", showlegend=False, name=access["id"]))
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="text", text=[f"{access['id']} · {label} · {width_m:.1f} m"], textposition="top right", textfont={"color": color, "size": 14}, hoverinfo="skip", showlegend=False, name=f"{access['id']}_label"))
    fig.update_layout(height=720, margin={"l": 10, "r": 10, "t": 10, "b": 10}, paper_bgcolor="#F8FAFC", plot_bgcolor="#F8FAFC", dragmode=False, clickmode="event+select", xaxis={"range": [minx - pad, maxx + pad], "scaleanchor": "y", "showgrid": False, "zeroline": False, "visible": False}, yaxis={"range": [miny - pad, maxy + pad], "showgrid": False, "zeroline": False, "visible": False})
    return fig


st.set_page_config(page_title="Traffic & Trassen Lab", layout="wide")

site_options = list(DEMO_SITES)
with st.sidebar:
    st.header("Projekt")
    site_id = st.selectbox("Grundstück", site_options, format_func=lambda key: DEMO_SITES[key].name)
    usage = st.selectbox("Nutzung", list(USAGE_LABELS), format_func=lambda key: USAGE_LABELS[key])
    workspace_mode = st.radio("Arbeitsmodus", ["Zufahrten", "Funktionen", "Optimierung", "Details"], horizontal=False)

    function_settings = _function_settings(usage)
    defaults = USAGE_DEFAULTS[usage]
    with st.expander("Verkehr", expanded=workspace_mode == "Zufahrten"):
        pkw_level = st.select_slider("PKW-Aufkommen", options=list(TRAFFIC_LEVEL_LABELS), value=defaults["pkw"], format_func=lambda key: TRAFFIC_LEVEL_LABELS[key])
        lkw_level = st.select_slider("LKW-Aufkommen", options=list(TRAFFIC_LEVEL_LABELS), value=defaults["lkw"], format_func=lambda key: TRAFFIC_LEVEL_LABELS[key])
        separation = st.radio("Verkehrsführung", list(SEPARATION_LABELS), index=1 if defaults["separate"] else 0, format_func=lambda key: SEPARATION_LABELS[key])
        st.caption("Breitenannahmen: PKW 3,5 m · LKW 7,5 m · PKW+LKW 7,5 m")

    with st.expander("Erschließung", expanded=workspace_mode == "Optimierung"):
        planner_mode = "variants"
        st.caption("Berechnung: Varianten + Scoring")
        road_options = {
            "planner": planner_mode,
            "flow": st.selectbox("Verkehrsführung", list(ROAD_FLOW_LABELS), index=0, format_func=lambda key: ROAD_FLOW_LABELS[key], key=f"road_flow_{site_id}_{usage}"),
            "network": st.selectbox("Netztyp", list(ROAD_NETWORK_LABELS), index=0, format_func=lambda key: ROAD_NETWORK_LABELS[key], key=f"road_network_{site_id}_{usage}"),
            "service": st.selectbox("LKW-Andienung", list(ROAD_SERVICE_LABELS), index=0, format_func=lambda key: ROAD_SERVICE_LABELS[key], key=f"road_service_{site_id}_{usage}"),
            "parking": st.selectbox("PKW-Stellplätze", list(ROAD_PARKING_LABELS), index=0, format_func=lambda key: ROAD_PARKING_LABELS[key], key=f"road_parking_{site_id}_{usage}"),
            "objective": st.selectbox("Optimierungsziel", list(ROAD_OBJECTIVE_LABELS), index=0, format_func=lambda key: ROAD_OBJECTIVE_LABELS[key], key=f"road_objective_{site_id}_{usage}"),
        }
        calculate_roads_clicked = st.button("Erschließung berechnen", key=f"calculate_roads_{site_id}_{usage}", use_container_width=True)
        if st.button("Erschließung zurücksetzen", key=f"reset_roads_{site_id}_{usage}", use_container_width=True):
            _road_plan_store().pop(site_id, None)
            st.rerun()

    with st.expander("Funktionen", expanded=workspace_mode == "Funktionen"):
        active_function_keys = _function_keys_for_usage(usage)
        available_function_keys = [key for key in FUNCTION_LIBRARY if key not in active_function_keys]
        if available_function_keys:
            add_cols = st.columns([1.4, 0.8])
            add_key = add_cols[0].selectbox(
                "Funktion aus Bibliothek",
                available_function_keys,
                format_func=lambda key: f"{FUNCTION_LIBRARY[key]['name']} · {FUNCTION_LIBRARY[key].get('category', '')}",
                key=f"add_function_key_{usage}",
            )
            if add_cols[1].button("Hinzufügen", key=f"add_function_button_{usage}", use_container_width=True):
                _add_function_to_usage(usage, add_key)
                st.rerun()
        reset_cols = st.columns([1, 1])
        reset_cols[0].caption(f"Aktive Funktionen: {len(active_function_keys)}")
        if reset_cols[1].button("Szenario zurücksetzen", key=f"reset_functions_{usage}", use_container_width=True):
            _reset_usage_functions(usage)
            st.rerun()
        manual_geometry = st.checkbox("Form/Flucht manuell anpassen", value=False, key=f"manual_geometry_{usage}")
        for template in _function_templates_for_usage(usage):
            item = function_settings[template["key"]]
            with st.container(border=True):
                title_cols = st.columns([1.0, 0.5])
                title_cols[0].markdown(f"**{template['name']}**")
                if title_cols[1].button("Entfernen", key=f"remove_{usage}_{template['key']}", use_container_width=True):
                    _remove_function_from_usage(usage, template["key"])
                    st.rerun()
                st.caption(f"{template.get('category', FUNCTION_KIND_LABELS.get(template['kind'], 'Funktion'))} · Bibliothek: {template['key']}")
                cols = st.columns([0.8, 1.0])
                current_priority = str(item.get("priority", "optional"))
                if current_priority not in PRIORITY_OPTIONS:
                    current_priority = "optional" if current_priority == "99" else "10"
                item["priority"] = cols[0].selectbox(
                    "Prio",
                    PRIORITY_OPTIONS,
                    index=PRIORITY_OPTIONS.index(current_priority),
                    format_func=lambda value: "optional" if value == "optional" else value,
                    key=f"prio_{usage}_{template['key']}",
                )
                item["count"] = cols[1].slider("Anzahl", 0, 4, int(item["count"]), key=f"count_{usage}_{template['key']}")
                item["area"] = st.slider("Fläche je Einheit m²", 100, 6000, int(item["area"]), 50, key=f"area_{usage}_{template['key']}")
                if manual_geometry:
                    advanced_cols = st.columns([1, 1])
                    current_shape = str(item.get("shape", "auto"))
                    if current_shape not in SHAPE_PREFERENCE_LABELS:
                        current_shape = "auto"
                    item["shape"] = advanced_cols[0].selectbox(
                        "Form",
                        list(SHAPE_PREFERENCE_LABELS),
                        index=list(SHAPE_PREFERENCE_LABELS).index(current_shape),
                        format_func=lambda key: SHAPE_PREFERENCE_LABELS[key],
                        key=f"shape_{usage}_{template['key']}",
                    )
                    current_alignment = str(item.get("alignment", "auto"))
                    if current_alignment not in ALIGNMENT_LABELS:
                        current_alignment = "auto"
                    item["alignment"] = advanced_cols[1].selectbox(
                        "Flucht",
                        list(ALIGNMENT_LABELS),
                        index=list(ALIGNMENT_LABELS).index(current_alignment),
                        format_func=lambda key: ALIGNMENT_LABELS[key],
                        key=f"alignment_{usage}_{template['key']}",
                    )
                else:
                    item["shape"] = "auto"
                    item["alignment"] = "auto"

    with st.expander("Optimierung", expanded=workspace_mode == "Optimierung"):
        building_setback = st.slider("Baugrenzen-Offset", 0.0, 20.0, 8.0, 0.5)
        building_spacing = st.slider("Mindestabstand Gebäude-Gebäude", 0.0, 20.0, 5.0, 0.5)
        equalize_repeated = st.toggle("Gleiche Funktionen gleich groß halten", value=True, key="traffic_equalize_repeated")
        use_drag_plan = st.toggle("Canvas-Editor nutzen", value=True, key="traffic_use_drag_plan")
        if st.button("Funktionsplatzhalter zurücksetzen", use_container_width=True):
            _clear_function_placements(site_id)
            st.rerun()

    if workspace_mode == "Details":
        with st.expander("Debug", expanded=True):
            building_setback = st.slider("Baugrenzen-Offset", 0.0, 20.0, 8.0, 0.5, key="debug_setback")
            building_spacing = st.slider("Mindestabstand Gebäude-Gebäude", 0.0, 20.0, 5.0, 0.5, key="debug_spacing")
            equalize_repeated = st.toggle("Gleiche Funktionen gleich groß halten", value=True, key="debug_equalize")
            use_drag_plan = st.toggle("Canvas-Editor nutzen", value=True, key="debug_canvas")
    elif workspace_mode != "Optimierung":
        building_setback = 8.0
        building_spacing = 5.0

click_mode = "Zufahrt setzen" if workspace_mode == "Zufahrten" else "Funktion platzieren"

access_points = _normalize_access_points(site_id)
traffic_requirements = _derive_traffic_requirements(usage, pkw_level, lkw_level, separation, access_points)
functions = _build_function_instances(usage, function_settings)
placements = _placement_store().get(site_id, {})
all_points_set = _all_functions_placed(functions, placements)
road_options = locals().get("road_options", {"flow": "auto", "network": "auto", "service": "auto", "parking": "auto", "objective": "balanced"})
calculate_roads_clicked = bool(locals().get("calculate_roads_clicked", False))
road_signature = _road_plan_signature(site_id, usage, functions, placements, access_points, road_options, building_setback, building_spacing, equalize_repeated)
road_store = _road_plan_store()
if calculate_roads_clicked and all_points_set and access_points:
    road_store[site_id] = {"signature": road_signature, "options": dict(road_options), "patchwork": None}
elif calculate_roads_clicked:
    road_store.pop(site_id, None)
road_plan = road_store.get(site_id, {})
road_calculated = bool(road_plan.get("signature") == road_signature)
active_road_options = road_plan.get("options", road_options) if road_calculated else road_options
patchwork = _build_patchwork(site_id, functions, building_setback, building_spacing, equalize_repeated, access_points) if all_points_set else _empty_patchwork(site_id, building_setback, building_spacing, equalize_repeated)
variant_scores: list[dict[str, Any]] = []
if road_calculated and access_points and all_points_set and active_road_options.get("planner") == "variants":
    cached_patchwork = road_plan.get("patchwork")
    if isinstance(cached_patchwork, dict):
        patchwork = cached_patchwork
        variant_scores = list(patchwork.get("variant_scores", []))
    else:
        variants = generate_variant_candidates(globals(), site_id, functions, access_points, building_setback, building_spacing, equalize_repeated)
        if variants:
            _best_score, patchwork = variants[0]
            variant_scores = [score_to_dict(score) for score, _candidate_patch in variants]
            patchwork = {**patchwork, "variant_scores": variant_scores}
            road_store[site_id] = {"signature": road_signature, "options": dict(active_road_options), "patchwork": patchwork}
elif road_calculated and access_points:
    patchwork = _with_road_network(site_id, access_points, patchwork, functions, building_setback, active_road_options)
else:
    patchwork = {**patchwork, "road_network": {"segments": [], "total_area_m2": 0.0, "hard_ok": True, "strategy": "not_calculated"}}
unplaced = [fn for fn in functions if fn["id"] not in placements]
all_function_ids = [fn["id"] for fn in functions]
selected_function_id = None
if functions:
    default_id = unplaced[0]["id"] if unplaced else functions[0]["id"]
    active_function_id = st.session_state.get("traffic_lab_active_function_id")
    if active_function_id not in all_function_ids:
        active_function_id = default_id
        st.session_state.traffic_lab_active_function_id = active_function_id
    selected_function_id = active_function_id

site = DEMO_SITES[site_id]
active_status_label = next((fn["name"] for fn in functions if fn["id"] == selected_function_id), "-")
status_items = [
    ("Grundstück", site.name),
    ("Fläche", f"{_site_area(site_id):.0f} m²"),
    ("Funktionen", f"{len(functions) - len(unplaced)}/{len(functions)}"),
    ("Zufahrten", str(len(access_points))),
    ("Erschließung", "berechnet" if road_calculated else "offen"),
    ("Aktiv", active_status_label),
]
status_html = "".join(
    f'<div class="lab-status-item"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'
    for label, value in status_items
)
st.markdown(
    f"""
<style>
.lab-header {{ display: flex; align-items: center; justify-content: space-between; gap: 24px; margin: 0 0 12px; }}
.lab-title {{ font-size: 42px; line-height: 1.06; font-weight: 760; color: #262a36; white-space: nowrap; }}
.lab-status {{ display: grid; grid-template-columns: repeat(6, minmax(74px, 1fr)); gap: 8px; width: min(760px, 58vw); }}
.lab-status-item {{ min-width: 0; border: 1px solid #e2e8f0; border-radius: 7px; padding: 6px 8px; background: #fff; }}
.lab-status-item span {{ display: block; color: #64748b; font-size: 11px; line-height: 1.1; margin-bottom: 3px; }}
.lab-status-item strong {{ display: block; color: #111827; font-size: 16px; line-height: 1.2; font-weight: 680; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
@media (max-width: 1100px) {{ .lab-header {{ align-items: flex-start; flex-direction: column; }} .lab-status {{ width: 100%; grid-template-columns: repeat(2, minmax(0, 1fr)); }} .lab-title {{ font-size: 34px; }} }}
.lab-notice {{ margin: 4px 0 14px; border-radius: 7px; padding: 8px 12px; font-size: 14px; line-height: 1.35; }}
.lab-notice.info {{ background: #eff6ff; color: #1d4ed8; }}
.lab-notice.success {{ background: #ecfdf5; color: #047857; }}
.lab-notice.warning {{ background: #fff7ed; color: #c2410c; }}
</style>
<div class="lab-header"><div class="lab-title">Traffic &amp; Trassen Lab</div><div class="lab-status">{status_html}</div></div>
""",
    unsafe_allow_html=True,
)


def _lab_notice(message: str, kind: str = "info") -> None:
    st.markdown(f'<div class="lab-notice {kind}">{escape(message)}</div>', unsafe_allow_html=True)


if workspace_mode == "Zufahrten":
    if not access_points:
        _lab_notice("Noch keine Zufahrt gesetzt. Im Lageplan auf die Grundstückskante klicken.", "info")
    with st.expander("Zufahrten bearbeiten", expanded=bool(access_points)):
        for access in access_points:
            x, y = access["point"]
            cols = st.columns([1.0, 1.5, 0.8])
            current_type = access.get("access_type", "both")
            width_m = _access_width_m(current_type)
            cols[0].markdown(f"**{access['id']}** · {x:.1f}/{y:.1f} m · {width_m:.1f} m")
            selected_type = cols[1].selectbox("Typ", list(ACCESS_TYPE_LABELS), index=list(ACCESS_TYPE_LABELS).index(current_type), format_func=lambda key: ACCESS_TYPE_LABELS[key], key=f"type_{site_id}_{access['id']}", label_visibility="collapsed")
            if selected_type != current_type:
                _update_access_type(site_id, access["id"], selected_type)
                st.rerun()
            if cols[2].button("Löschen", key=f"delete_{site_id}_{access['id']}"):
                _delete_access(site_id, access["id"])
                st.rerun()
    if not traffic_requirements["pkw_ok"]:
        _lab_notice("PKW-Zufahrt fehlt.", "warning")
    if not traffic_requirements["lkw_ok"]:
        _lab_notice("LKW-Zufahrt fehlt.", "warning")
elif workspace_mode == "Funktionen":
    if functions and not all_points_set:
        _lab_notice(f"Noch {len(unplaced)} Platzhalter platzieren. Anzahl und Flächen können links unter 'Funktionen' weiter angepasst werden.", "info")
    elif functions:
        if road_calculated:
            _lab_notice("Alle Platzhalter platziert. Erschließung ist berechnet.", "success")
        else:
            _lab_notice("Alle Platzhalter platziert. Links unter 'Erschließung' Anforderungen wählen und berechnen.", "info")
elif workspace_mode == "Optimierung":
    if all_points_set:
        reduced = [p for p in patchwork["parcels"] if p["status"] == "reduziert"]
        missing = [m for m in patchwork.get("missing", []) if not m.get("optional")]
        if not road_calculated:
            _lab_notice("Erschließung noch nicht berechnet. Links Anforderungen wählen und 'Erschließung berechnen' drücken.", "info")
        elif not reduced and not missing:
            _lab_notice("Alle Pflichtflächen vollständig abgebildet und Erschließung berechnet.", "success")
        else:
            _lab_notice("Einige Flächen wurden reduziert oder sind nicht platzierbar.", "warning")
    else:
        _lab_notice("Optimierung startet nach Platzierung aller Platzhalter.", "info")
elif workspace_mode == "Details":
    with st.expander("Details anzeigen", expanded=False):
        st.dataframe(_traffic_requirement_rows(traffic_requirements), width="stretch", hide_index=True)
        st.dataframe(_function_rows(functions, patchwork, placements), width="stretch", hide_index=True)

header_cols = st.columns([1.2, 2.2])
header_cols[0].subheader("Lageplan")
active_label = next((fn["name"] for fn in functions if fn["id"] == selected_function_id), "-")
header_cols[1].caption(f"Modus: {workspace_mode} · Aktiv: {active_label}")
if patchwork.get("variant_scores") and workspace_mode == "Optimierung":
    with st.expander("Variantenbewertung", expanded=True):
        st.dataframe(
            [
                {
                    "Variante": item["skeleton"],
                    "Score": item["score"],
                    "OK": "ja" if item["hard_ok"] else "nein",
                    "IST %": item["realized_pct"],
                    "Straße %": item["road_area_pct"],
                    "Abstand m": item["max_road_distance_m"],
                    "Hinweise": ", ".join(item["warnings"]),
                }
                for item in patchwork["variant_scores"]
            ],
            hide_index=True,
            width="stretch",
        )
if click_mode == "Funktion platzieren" and use_drag_plan:
    drag_event = _drag_plan_component(
        payload=_drag_plan_payload(site_id, access_points, patchwork, functions, placements, selected_function_id),
        key=f"canvas_plan_{site_id}_{usage}",
        default=None,
    )
    with st.expander("Klassischen Lageplan anzeigen", expanded=False):
        st.plotly_chart(
            render_site_figure(site_id, access_points, patchwork, click_mode, functions, placements, selected_function_id),
            key=f"canvas_fallback_plan_{site_id}_{usage}_{selected_function_id}",
            config={"displayModeBar": False, "scrollZoom": False},
        )
    if isinstance(drag_event, dict):
        action = drag_event.get("action") or drag_event.get("type")
        function_id = drag_event.get("function_id") or drag_event.get("id")
        event_token = drag_event.get("event_id") or str(drag_event)
        token = f"canvas:{site_id}:{event_token}"
        if function_id in all_function_ids and st.session_state.get("last_drag_plan_event") != token:
            st.session_state.last_drag_plan_event = token
            if action == "select_function":
                st.session_state.traffic_lab_active_function_id = function_id
                st.rerun()
            if action == "place_function":
                point = (float(drag_event.get("x", 0.0)), float(drag_event.get("y", 0.0)))
                snapped_point = _nearest_sample(point, _sample_interior(site_id))
                was_unplaced = function_id not in placements
                _place_function(site_id, function_id, snapped_point)
                st.session_state.traffic_lab_active_function_id = _next_unplaced_function_id(functions, placements, function_id) if was_unplaced else function_id
                st.rerun()
else:
    selection = st.plotly_chart(render_site_figure(site_id, access_points, patchwork, click_mode, functions, placements, selected_function_id), key=f"site_anchor_plan_{site_id}_{click_mode}_{selected_function_id}", on_select="rerun", selection_mode="points", config={"displayModeBar": False, "scrollZoom": False})
    event = _selected_plot_point(selection)
    if event is not None:
        point = event["point"]
        event_kind = event.get("kind")
        event_id = event.get("id")
        token = f"{click_mode}:{site_id}:{event_kind}:{event_id}:{point[0]:.2f}:{point[1]:.2f}:{selected_function_id}"
        if st.session_state.get("last_plan_selection") != token:
            st.session_state.last_plan_selection = token
            if click_mode == "Zufahrt setzen" and event_kind == "access_target":
                _add_access(site_id, point)
                st.rerun()
            if click_mode == "Funktion platzieren" and event_kind in {"function_anchor", "function_rect"} and event_id in all_function_ids:
                st.session_state.traffic_lab_active_function_id = event_id
                st.rerun()
            if click_mode == "Funktion platzieren" and event_kind in {"function_target", None} and selected_function_id:
                snapped_point = _nearest_sample(point, _sample_interior(site_id))
                was_unplaced = selected_function_id not in placements
                _place_function(site_id, selected_function_id, snapped_point)
                if was_unplaced:
                    st.session_state.traffic_lab_active_function_id = _next_unplaced_function_id(functions, placements, selected_function_id)
                st.rerun()

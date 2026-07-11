from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

SKELETON_TYPES = ("u_spange", "row_dividers", "access_edge", "entry_spine", "edge_loop")


@dataclass(frozen=True)
class VariantScore:
    variant_id: str
    skeleton: str
    score: float
    hard_ok: bool
    parcels: int
    roads: int
    realized_pct: float
    weighted_shortfall: float
    road_area_m2: float
    road_area_pct: float
    max_road_distance_m: float
    max_deep_overlap_m2: float
    warnings: tuple[str, ...]


def score_to_dict(score: VariantScore) -> dict[str, Any]:
    return asdict(score)


CONNECTOR_WIDTHS_M = {
    "office": 3.5,
    "parking": 3.5,
    "security": 3.5,
    "tech": 5.0,
    "prod": 7.5,
    "warehouse": 7.5,
    "hall": 7.5,
    "yard": 7.5,
    "dc": 7.5,
}
CONNECTOR_FRONTAGE_M = {
    "office": 3.5,
    "parking": 3.5,
    "security": 3.5,
    "tech": 5.0,
    "prod": 6.0,
    "warehouse": 6.0,
    "hall": 8.0,
    "yard": 7.5,
    "dc": 8.0,
}


def _priority_weight(ns: dict[str, Any], priority: Any) -> float:
    value = ns["_priority_value"](priority)
    if value <= 1:
        return 7.0
    if value == 2:
        return 4.5
    if value == 3:
        return 2.5
    if value == 4:
        return 1.5
    return 1.0


def _base_function_name(ns: dict[str, Any], function: dict[str, Any]) -> str:
    return str(ns["_base_function_name"](function.get("name", function.get("id", "Funktion"))))


def _area_metrics(ns: dict[str, Any], functions: list[dict[str, Any]], parcels: list[dict[str, Any]]) -> tuple[float, float, list[str]]:
    grouped: dict[str, dict[str, Any]] = {}
    for function in functions:
        if function.get("priority") == "optional":
            continue
        key = str(function.get("key", function["id"]))
        row = grouped.setdefault(key, {"required": 0.0, "realized": 0.0, "priority": function.get("priority", 99), "name": _base_function_name(ns, function)})
        row["required"] += float(function.get("area_m2", 0.0))
        if ns["_priority_value"](function.get("priority", 99)) < ns["_priority_value"](row["priority"]):
            row["priority"] = function.get("priority", 99)
    for parcel in parcels:
        function = parcel["function"]
        key = str(function.get("key", function["id"]))
        row = grouped.setdefault(key, {"required": 0.0, "realized": 0.0, "priority": function.get("priority", 99), "name": _base_function_name(ns, function)})
        row["realized"] += float(parcel.get("actual_area_m2", 0.0))

    required_total = sum(float(row["required"]) for row in grouped.values())
    realized_total = sum(min(float(row["realized"]), float(row["required"])) for row in grouped.values())
    realized_pct = 100.0 if required_total <= 0.0 else realized_total / required_total * 100.0
    weighted_shortfall = 0.0
    warnings: list[str] = []
    for row in grouped.values():
        required = float(row["required"])
        realized = float(row["realized"])
        if required <= 0.0:
            continue
        coverage = realized / required * 100.0
        shortfall = max(0.0, 100.0 - coverage)
        weighted_shortfall += shortfall * shortfall * _priority_weight(ns, row["priority"])
        floor = 70.0 if ns["_priority_value"](row["priority"]) <= 1 else 55.0 if ns["_priority_value"](row["priority"]) == 2 else 35.0
        if coverage + 0.1 < floor:
            warnings.append(f"low-area:{row['name']}:{coverage:.0f}%")
    return realized_pct, weighted_shortfall, warnings


def _clip_long_line(site_polygon: Any, a: tuple[float, float], b: tuple[float, float]) -> LineString:
    line = LineString([a, b])
    clipped = line.intersection(site_polygon)
    if clipped.is_empty:
        return line
    if clipped.geom_type == "LineString":
        return clipped
    lines = [geom for geom in getattr(clipped, "geoms", []) if geom.geom_type == "LineString"]
    return max(lines, key=lambda item: item.length) if lines else line


def _axis_from_access(site_polygon: Any, access: dict[str, Any]) -> tuple[float, float]:
    ax, ay = float(access["point"][0]), float(access["point"][1])
    minx, miny, maxx, maxy = site_polygon.bounds
    distances = {
        "north": abs(ay - maxy),
        "south": abs(ay - miny),
        "east": abs(ax - maxx),
        "west": abs(ax - minx),
    }
    side = min(distances, key=distances.get)
    if side == "north":
        return (0.0, -1.0)
    if side == "south":
        return (0.0, 1.0)
    if side == "east":
        return (-1.0, 0.0)
    return (1.0, 0.0)


def _line_through(site_polygon: Any, point: tuple[float, float], axis: tuple[float, float]) -> LineString:
    minx, miny, maxx, maxy = site_polygon.bounds
    span = max(maxx - minx, maxy - miny) * 3.0
    ax, ay = axis
    a = (point[0] - ax * span, point[1] - ay * span)
    b = (point[0] + ax * span, point[1] + ay * span)
    return _clip_long_line(site_polygon, a, b)


def _entry_line(site_polygon: Any, access: dict[str, Any]) -> LineString:
    start = (float(access["point"][0]), float(access["point"][1]))
    axis = _axis_from_access(site_polygon, access)
    return _line_through(site_polygon, start, axis)


def _center_cross_line(site_polygon: Any, access: dict[str, Any]) -> LineString:
    center = site_polygon.representative_point()
    axis = _axis_from_access(site_polygon, access)
    perp = (-axis[1], axis[0])
    return _line_through(site_polygon, (float(center.x), float(center.y)), perp)


def _placement_points(ns: dict[str, Any], site_id: str, functions: list[dict[str, Any]]) -> list[tuple[float, float]]:
    placements = ns["_placement_store"]().get(site_id, {})
    points: list[tuple[float, float]] = []
    for function in functions:
        placement = placements.get(function.get("id"))
        if not placement:
            continue
        anchor = placement.get("anchor")
        if not anchor:
            continue
        points.append((float(anchor[0]), float(anchor[1])))
    return points


def _best_cross_position(site_polygon: Any, bounds: tuple[float, float, float, float], orientation: str, low: float, high: float, preferred: float) -> float:
    minx, miny, maxx, maxy = bounds
    low, high = sorted((float(low), float(high)))
    if high - low <= 0.1:
        return preferred
    best_value = preferred
    best_score = float("-inf")
    samples = max(3, int((high - low) / 1.0) + 1)
    for index in range(samples):
        value = low + (high - low) * index / max(1, samples - 1)
        if orientation == "horizontal":
            line = _clip_long_line(site_polygon, (minx, value), (maxx, value))
            available_span = max(1.0, maxx - minx)
        else:
            line = _clip_long_line(site_polygon, (value, miny), (value, maxy))
            available_span = max(1.0, maxy - miny)
        length_ratio = min(1.0, float(line.length) / available_span)
        center_penalty = abs(value - preferred) / max(1.0, high - low)
        score = length_ratio * 100.0 - center_penalty * 12.0
        if score > best_score:
            best_value = value
            best_score = score
    return best_value


def _polygonal_part(geom: Any) -> Any:
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type in {"Polygon", "MultiPolygon"}:
        return geom
    parts = []
    for part in getattr(geom, "geoms", []):
        if part.geom_type in {"Polygon", "MultiPolygon"}:
            parts.append(part)
    if not parts:
        return geom
    result = parts[0]
    for part in parts[1:]:
        result = result.union(part)
    return result


def _candidate_skeletons(ns: dict[str, Any], site_id: str) -> tuple[str, ...]:
    polygon = ns["_site_polygon"](site_id)
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    aspect = max(width, height) / max(1.0, min(width, height))
    vertex_count = len(list(polygon.exterior.coords))
    if aspect >= 2.2:
        return ("row_dividers", "edge_loop", "entry_spine")
    if vertex_count > 6:
        return ("row_dividers", "entry_spine", "edge_loop")
    return ("u_spange", "row_dividers", "entry_spine")


def _row_divider_lines(ns: dict[str, Any], site_id: str, access: dict[str, Any], functions: list[dict[str, Any]], setback_m: float) -> list[tuple[str, LineString, float]]:
    site_polygon = ns["_site_polygon"](site_id)
    build_boundary = ns["_build_boundary"](site_id, setback_m)
    points = _placement_points(ns, site_id, functions)
    if len(points) < 2:
        return [("spine", _entry_line(site_polygon, access), 7.5)]
    axis = _axis_from_access(site_polygon, access)
    vertical_entry = abs(axis[1]) >= abs(axis[0])
    minx, miny, maxx, maxy = build_boundary.bounds
    lines: list[tuple[str, LineString, float]] = []
    if vertical_entry:
        values = sorted({round(y, 2) for _x, y in points})
        dividers = [(a + b) / 2.0 for a, b in zip(values, values[1:]) if abs(b - a) >= 10.0]
        divider_pairs = [(a, b, (a + b) / 2.0) for a, b in zip(values, values[1:]) if abs(b - a) >= 10.0]
        if not divider_pairs:
            divider_pairs = [(min(values), max(values), sum(values) / len(values))]
        for index, (low, high, preferred_y) in enumerate(divider_pairs, start=1):
            y = _best_cross_position(site_polygon, (minx, miny, maxx, maxy), "horizontal", min(max(low, miny + 4.0), maxy - 4.0), min(max(high, miny + 4.0), maxy - 4.0), min(max(preferred_y, miny + 4.0), maxy - 4.0))
            line = _clip_long_line(site_polygon, (minx, y), (maxx, y))
            if line.length > 0.1:
                lines.append((f"divider_{index}", line, 7.5))
        ax = float(access["point"][0])
        line_values = [float(line.coords[0][1]) for _kind, line, _width in lines if line.length > 0.1]
        if line_values:
            target_y = min(line_values) if axis[1] < 0 else max(line_values)
            throat = _clip_long_line(site_polygon, (ax, float(access["point"][1])), (ax, target_y))
            if throat.length > 0.1:
                lines.insert(0, ("throat", throat, 7.5))
    else:
        values = sorted({round(x, 2) for x, _y in points})
        dividers = [(a + b) / 2.0 for a, b in zip(values, values[1:]) if abs(b - a) >= 10.0]
        divider_pairs = [(a, b, (a + b) / 2.0) for a, b in zip(values, values[1:]) if abs(b - a) >= 10.0]
        if not divider_pairs:
            divider_pairs = [(min(values), max(values), sum(values) / len(values))]
        for index, (low, high, preferred_x) in enumerate(divider_pairs, start=1):
            x = _best_cross_position(site_polygon, (minx, miny, maxx, maxy), "vertical", min(max(low, minx + 4.0), maxx - 4.0), min(max(high, minx + 4.0), maxx - 4.0), min(max(preferred_x, minx + 4.0), maxx - 4.0))
            line = _clip_long_line(site_polygon, (x, miny), (x, maxy))
            if line.length > 0.1:
                lines.append((f"divider_{index}", line, 7.5))
        ay = float(access["point"][1])
        line_values = [float(line.coords[0][0]) for _kind, line, _width in lines if line.length > 0.1]
        if line_values:
            target_x = min(line_values) if axis[0] < 0 else max(line_values)
            throat = _clip_long_line(site_polygon, (float(access["point"][0]), ay), (target_x, ay))
            if throat.length > 0.1:
                lines.insert(0, ("throat", throat, 7.5))
    return lines


def _edge_loop_line(ns: dict[str, Any], site_id: str, setback_m: float) -> LineString:
    boundary = ns["_build_boundary"](site_id, max(2.0, setback_m / 2.0))
    return LineString(boundary.exterior.coords)



def _access_edge_line(ns: dict[str, Any], site_id: str, access: dict[str, Any], setback_m: float) -> LineString:
    site_polygon = ns["_site_polygon"](site_id)
    boundary = ns["_build_boundary"](site_id, max(2.0, setback_m / 2.0))
    minx, miny, maxx, maxy = boundary.bounds
    ax, ay = float(access["point"][0]), float(access["point"][1])
    site_minx, site_miny, site_maxx, site_maxy = site_polygon.bounds
    distances = {
        "north": abs(ay - site_maxy),
        "south": abs(ay - site_miny),
        "east": abs(ax - site_maxx),
        "west": abs(ax - site_minx),
    }
    side = min(distances, key=distances.get)
    if side == "north":
        line = LineString([(minx, maxy), (maxx, maxy)])
    elif side == "south":
        line = LineString([(minx, miny), (maxx, miny)])
    elif side == "east":
        line = LineString([(maxx, miny), (maxx, maxy)])
    else:
        line = LineString([(minx, miny), (minx, maxy)])
    clipped = line.intersection(site_polygon)
    if clipped.is_empty:
        return line
    if clipped.geom_type == "LineString":
        return clipped
    lines = [geom for geom in getattr(clipped, "geoms", []) if geom.geom_type == "LineString"]
    return max(lines, key=lambda item: item.length) if lines else line


def _access_throat_to_edge(ns: dict[str, Any], site_id: str, access: dict[str, Any], edge_line: LineString) -> LineString:
    site_polygon = ns["_site_polygon"](site_id)
    start = Point(float(access["point"][0]), float(access["point"][1]))
    target = edge_line.interpolate(edge_line.project(start))
    return _clip_long_line(site_polygon, (float(start.x), float(start.y)), (float(target.x), float(target.y)))



def _access_side(ns: dict[str, Any], site_id: str, access: dict[str, Any]) -> str:
    site_polygon = ns["_site_polygon"](site_id)
    ax, ay = float(access["point"][0]), float(access["point"][1])
    minx, miny, maxx, maxy = site_polygon.bounds
    distances = {"north": abs(ay - maxy), "south": abs(ay - miny), "east": abs(ax - maxx), "west": abs(ax - minx)}
    return min(distances, key=distances.get)


def _u_spange_line(ns: dict[str, Any], site_id: str, access: dict[str, Any], setback_m: float) -> LineString:
    site_polygon = ns["_site_polygon"](site_id)
    boundary = ns["_build_boundary"](site_id, max(2.0, setback_m / 2.0))
    minx, miny, maxx, maxy = boundary.bounds
    side = _access_side(ns, site_id, access)
    if side == "north":
        coords = [(minx, miny), (minx, maxy), (maxx, maxy), (maxx, miny)]
    elif side == "south":
        coords = [(minx, maxy), (minx, miny), (maxx, miny), (maxx, maxy)]
    elif side == "east":
        coords = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    else:
        coords = [(maxx, miny), (minx, miny), (minx, maxy), (maxx, maxy)]
    line = LineString(coords)
    clipped = line.intersection(site_polygon)
    if clipped.is_empty:
        return line
    if clipped.geom_type == "LineString":
        return clipped
    lines = [geom for geom in getattr(clipped, "geoms", []) if geom.geom_type == "LineString"]
    return max(lines, key=lambda item: item.length) if lines else line


def build_skeleton_segments(ns: dict[str, Any], site_id: str, access_points: list[dict[str, Any]], skeleton: str, setback_m: float, functions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    site_polygon = ns["_site_polygon"](site_id)
    if not access_points:
        return []
    primary = access_points[0]
    lines: list[tuple[str, LineString, float]] = []
    if skeleton == "access_edge":
        edge = _access_edge_line(ns, site_id, primary, setback_m)
        lines.append(("edge", edge, 7.5))
        throat = _access_throat_to_edge(ns, site_id, primary, edge)
        if throat.length > 0.1:
            lines.append(("throat", throat, 7.5))
    elif skeleton == "u_spange":
        u_line = _u_spange_line(ns, site_id, primary, setback_m)
        lines.append(("u_spange", u_line, 7.5))
        edge = _access_edge_line(ns, site_id, primary, setback_m)
        throat = _access_throat_to_edge(ns, site_id, primary, edge)
        if throat.length > 0.1:
            lines.append(("throat", throat, 7.5))
    elif skeleton == "access_edge_spine":
        edge = _access_edge_line(ns, site_id, primary, setback_m)
        lines.append(("edge", edge, 7.5))
        throat = _access_throat_to_edge(ns, site_id, primary, edge)
        if throat.length > 0.1:
            lines.append(("throat", throat, 7.5))
        lines.append(("spine", _entry_line(site_polygon, primary), 7.5))
    elif skeleton == "service_grid":
        lines.append(("spine", _entry_line(site_polygon, primary), 7.5))
        lines.append(("cross", _center_cross_line(site_polygon, primary), 7.5))
    elif skeleton == "row_dividers":
        lines.extend(_row_divider_lines(ns, site_id, primary, functions or [], setback_m))
    elif skeleton == "entry_spine":
        lines.append(("main", _entry_line(site_polygon, primary), 7.5))
    elif skeleton == "edge_loop":
        lines.append(("loop", _edge_loop_line(ns, site_id, setback_m), 7.5))
    else:
        raise ValueError(f"unknown skeleton: {skeleton}")

    segments: list[dict[str, Any]] = []
    for index, (kind, line, width_m) in enumerate(lines, start=1):
        raw = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
        corridor = _polygonal_part(raw.intersection(site_polygon))
        if corridor.is_empty or line.length <= 0.1:
            continue
        segments.append({
            "id": f"V{index}",
            "kind": "skeleton",
            "skeleton_kind": kind,
            "mode": "both",
            "access_id": primary["id"],
            "access_type": "both",
            "need": "both",
            "function_id": "",
            "function_name": "Erschließung",
            "source_id": primary["id"],
            "target_id": "skeleton",
            "width_m": width_m,
            "centerline": line,
            "corridor": corridor,
            "length_m": float(line.length),
            "area_m2": float(corridor.area),
            "outside_area_m2": float(raw.difference(site_polygon.buffer(0.01)).area),
        })
    return segments


def _road_union(segments: list[dict[str, Any]]) -> Any | None:
    union = None
    for segment in segments:
        geom = segment.get("corridor")
        if geom is None or geom.is_empty:
            continue
        union = geom if union is None else union.union(geom)
    return union


def _parcel_road_frontage(parcel: dict[str, Any], road_union: Any | None) -> float:
    if road_union is None or road_union.is_empty:
        return 0.0
    return float(parcel["geometry"].boundary.intersection(road_union.buffer(1.0, cap_style=2, join_style=2)).length)


def _connector_width_m(function: dict[str, Any]) -> float:
    return float(CONNECTOR_WIDTHS_M.get(str(function.get("key", "")), 5.0))


def _connector_frontage_m(function: dict[str, Any]) -> float:
    return float(CONNECTOR_FRONTAGE_M.get(str(function.get("key", "")), 0.0))


def _add_parcel_connectors(site_polygon: Any, segments: list[dict[str, Any]], parcels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments or not parcels:
        return segments
    result = list(segments)
    road_union = _road_union(result)
    if road_union is None or road_union.is_empty:
        return result
    for parcel in parcels:
        function = parcel["function"]
        required_frontage = _connector_frontage_m(function)
        if required_frontage <= 0.0:
            continue
        if _parcel_road_frontage(parcel, road_union) + 0.1 >= required_frontage:
            continue
        parcel_point, road_point = nearest_points(parcel["geometry"].boundary, road_union)
        if parcel_point.distance(road_point) <= 0.05:
            continue
        line = LineString([(float(road_point.x), float(road_point.y)), (float(parcel_point.x), float(parcel_point.y))])
        if line.length <= 0.1:
            continue
        width_m = _connector_width_m(function)
        raw = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
        corridor = _polygonal_part(raw.intersection(site_polygon))
        if corridor.is_empty:
            continue
        result.append({
            "id": f"V{len(result) + 1}",
            "kind": "connector",
            "skeleton_kind": "connector",
            "mode": "both",
            "access_id": segments[0].get("access_id", "Z1"),
            "access_type": "both",
            "need": "both",
            "function_id": function.get("id", ""),
            "function_name": function.get("name", "Funktion"),
            "source_id": "skeleton",
            "target_id": function.get("id", ""),
            "width_m": width_m,
            "centerline": line,
            "corridor": corridor,
            "length_m": float(line.length),
            "area_m2": float(corridor.area),
            "outside_area_m2": float(raw.difference(site_polygon.buffer(0.01)).area),
        })
        road_union = road_union.union(corridor)
    return result


def _skeleton_blockers(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for segment in segments:
        blockers.append({
            "_geometry_blocker": True,
            "id": f"blocker_{segment['id']}",
            "function": {"id": f"road_{segment['id']}", "kind": "road", "priority": 0},
            "geometry": segment["corridor"],
            "strategy_segment": segment,
            "allowed_function_ids": set(),
        })
    return blockers


def _patchwork_with_skeleton(ns: dict[str, Any], site_id: str, functions: list[dict[str, Any]], access_points: list[dict[str, Any]], setback_m: float, spacing_m: float, equalize_repeated: bool, skeleton: str) -> dict[str, Any]:
    skeleton_segments = build_skeleton_segments(ns, site_id, access_points, skeleton, setback_m, functions)
    original_blockers = ns["_road_strategy_blockers"]

    def blockers_with_skeleton(blocker_site_id: str, blocker_access: list[dict[str, Any]], blocker_functions: list[dict[str, Any]], blocker_setback: float) -> list[dict[str, Any]]:
        return _skeleton_blockers(skeleton_segments) + original_blockers(blocker_site_id, blocker_access, blocker_functions, blocker_setback)

    ns["_road_strategy_blockers"] = blockers_with_skeleton
    try:
        patch = ns["_build_patchwork"](site_id, functions, setback_m, spacing_m, equalize_repeated, access_points)
    finally:
        ns["_road_strategy_blockers"] = original_blockers
    patch = dict(patch)
    all_segments = _add_parcel_connectors(ns["_site_polygon"](site_id), skeleton_segments, patch.get("parcels", []))
    patch["road_network"] = {
        "strategy": f"variant_{skeleton}",
        "segments": all_segments,
        "total_area_m2": sum(float(segment["area_m2"]) for segment in all_segments),
        "hard_ok": all(float(segment.get("outside_area_m2", 0.0)) <= 1.0 for segment in all_segments),
    }
    return patch


def _max_road_distance(parcels: list[dict[str, Any]], segments: list[dict[str, Any]]) -> float:
    if not parcels or not segments:
        return 0.0 if not parcels else 999.0
    road_union = None
    for segment in segments:
        corridor = segment["corridor"]
        road_union = corridor if road_union is None else road_union.union(corridor)
    return max(float(parcel["geometry"].distance(road_union)) for parcel in parcels)


def _max_deep_overlap(parcels: list[dict[str, Any]], segments: list[dict[str, Any]]) -> float:
    max_overlap = 0.0
    for segment in segments:
        corridor = segment["corridor"]
        width_m = float(segment.get("width_m", 7.5))
        for parcel in parcels:
            inner = parcel["geometry"].buffer(-max(1.5, min(width_m / 2.0, 4.0)), cap_style=2, join_style=2)
            if inner.is_empty:
                continue
            max_overlap = max(max_overlap, float(corridor.intersection(inner).area))
    return max_overlap


def score_variant(ns: dict[str, Any], site_id: str, functions: list[dict[str, Any]], patch: dict[str, Any], skeleton: str) -> VariantScore:
    parcels = patch.get("parcels", [])
    segments = patch.get("road_network", {}).get("segments", [])
    site_area = float(patch["site_polygon"].area)
    road_area = float(patch.get("road_network", {}).get("total_area_m2", 0.0))
    realized_pct, weighted_shortfall, warnings = _area_metrics(ns, functions, parcels)
    max_distance = _max_road_distance(parcels, segments)
    max_overlap = _max_deep_overlap(parcels, segments)
    missing_required = [item for item in patch.get("missing", []) if not item.get("optional")]
    if missing_required:
        warnings.append("required-missing")
    if max_distance > 18.0:
        warnings.append(f"far-from-road:{max_distance:.0f}m")
    if max_overlap > 1.0:
        warnings.append(f"road-overlaps-function:{max_overlap:.0f}m2")
    if road_area > site_area * 0.22:
        warnings.append("high-road-area")
    road_area_pct = road_area / site_area * 100.0 if site_area > 0 else 0.0
    score = weighted_shortfall + road_area_pct * 180.0 + max(0.0, max_distance - 8.0) * 120.0 + max_overlap * 1000.0 + len(missing_required) * 100_000.0
    hard_ok = not missing_required and max_overlap <= 1.0 and max_distance <= 24.0 and realized_pct >= 60.0 and road_area <= site_area * 0.24
    return VariantScore(
        variant_id=f"{site_id}_{skeleton}",
        skeleton=skeleton,
        score=round(score, 1),
        hard_ok=hard_ok,
        parcels=len(parcels),
        roads=len(segments),
        realized_pct=round(realized_pct, 1),
        weighted_shortfall=round(weighted_shortfall, 1),
        road_area_m2=round(road_area, 1),
        road_area_pct=round(road_area_pct, 1),
        max_road_distance_m=round(max_distance, 1),
        max_deep_overlap_m2=round(max_overlap, 1),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def generate_variant_candidates(ns: dict[str, Any], site_id: str, functions: list[dict[str, Any]], access_points: list[dict[str, Any]], setback_m: float, spacing_m: float, equalize_repeated: bool = True) -> list[tuple[VariantScore, dict[str, Any]]]:
    variants: list[tuple[VariantScore, dict[str, Any]]] = []
    for skeleton in _candidate_skeletons(ns, site_id):
        patch = _patchwork_with_skeleton(ns, site_id, functions, access_points, setback_m, spacing_m, equalize_repeated, skeleton)
        score = score_variant(ns, site_id, functions, patch, skeleton)
        variants.append((score, patch))
    variants.sort(key=lambda item: (not item[0].hard_ok, item[0].score))
    return variants

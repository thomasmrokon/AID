"""Standalone traffic and utility corridor planning lab.

This module is intentionally independent from the main masterplan agent. It
keeps the problem small: site polygon, access points, target zones, candidate
road graphs, scoring and SVG output.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import sqrt
from typing import Any, Iterable

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, unary_union


Point2D = tuple[float, float]


@dataclass(frozen=True)
class LabSite:
    site_id: str
    name: str
    polygon: list[Point2D]
    access_points: list[dict[str, Any]]


DEMO_SITES: dict[str, LabSite] = {
    "compact": LabSite(
        "compact",
        "Kompakt · 96 x 100 m",
        [(0, 0), (96, 0), (96, 100), (0, 100)],
        [{"id": "Z1", "side": "south", "point": (18, 0)}, {"id": "Z2", "side": "north", "point": (76, 100)}],
    ),
    "long": LabSite(
        "long",
        "Langgezogen · 300 x 80 m",
        [(0, 0), (300, 0), (300, 80), (180, 80), (180, 38), (0, 38)],
        [{"id": "Z1", "side": "west", "point": (0, 28)}, {"id": "Z2", "side": "north", "point": (130, 80)}],
    ),
    "irregular": LabSite(
        "irregular",
        "Unregelmäßig · ca. 5 ha",
        [(0, 18), (110, 0), (245, 14), (275, 98), (230, 205), (42, 186), (-28, 92)],
        [{"id": "Z1", "side": "east", "point": (268, 94)}, {"id": "Z2", "side": "south", "point": (96, 5)}],
    ),
}


PROFILE_RULES = {
    "produktion": {"road_width": 9.0, "yard_scale": 0.85, "redundancy": False},
    "logistik": {"road_width": 13.0, "yard_scale": 1.25, "redundancy": False},
    "datacenter": {"road_width": 11.0, "yard_scale": 0.75, "redundancy": True},
}


USAGE_LABELS = {
    "production": "Produktion / Montage",
    "logistics": "Logistik / Distribution",
    "datacenter": "Datacenter / kritische Infrastruktur",
    "mixed": "Gemischter Industriecampus",
}

DELIVERY_LABELS = {
    "low": "niedrig",
    "medium": "mittel",
    "high": "hoch",
    "very_high": "sehr hoch",
}

SEPARATION_LABELS = {
    "shared": "gemeinsame Erschließung möglich",
    "separate_lkw_pkw": "LKW und PKW möglichst trennen",
    "strict": "Besucher, Mitarbeiter und Lieferverkehr klar trennen",
}

REDUNDANCY_LABELS = {
    "none": "nicht erforderlich",
    "preferred": "wünschenswert",
    "required": "zwingend erforderlich",
}

PRIORITY_LABELS = {
    "balanced": "ausgewogen",
    "road_efficiency": "möglichst wenig Verkehrsfläche",
    "robust_access": "robuste und klare Erschließung",
    "rectangular_fields": "große rechteckige Baufelder",
    "future_flexibility": "spätere Erweiterbarkeit",
}


def derive_briefing(requirements: dict[str, Any]) -> dict[str, Any]:
    usage = str(requirements.get("usage") or "logistics")
    delivery = str(requirements.get("delivery") or "medium")
    separation = str(requirements.get("separation") or "separate_lkw_pkw")
    redundancy = str(requirements.get("redundancy") or "none")
    priority = str(requirements.get("priority") or "balanced")

    if usage == "datacenter":
        profile = "datacenter"
    elif usage in {"logistics", "mixed"}:
        profile = "logistik"
    else:
        profile = "produktion"

    lkw_map = {"low": 25, "medium": 70, "high": 140, "very_high": 240}
    emp_map = {"production": 220, "logistics": 140, "datacenter": 80, "mixed": 260}
    lkw_per_day = int(lkw_map.get(delivery, 70))
    employees = int(emp_map.get(usage, 180))

    required_redundancy = redundancy == "required" or usage == "datacenter"
    if required_redundancy:
        preferred_strategy = "loop"
    elif delivery in {"high", "very_high"} or separation == "strict":
        preferred_strategy = "front_spine"
    elif priority == "road_efficiency":
        preferred_strategy = "stich"
    elif priority == "rectangular_fields":
        preferred_strategy = "central_spine"
    else:
        preferred_strategy = "front_spine"

    weights = {
        "connectivity": 1.0,
        "road_efficiency": 1.0,
        "rectangularity": 1.0,
        "parcel_split": 1.0,
    }
    if priority == "road_efficiency":
        weights.update({"road_efficiency": 1.7, "connectivity": 0.9, "rectangularity": 0.8, "parcel_split": 0.8})
    elif priority == "robust_access":
        weights.update({"connectivity": 1.7, "road_efficiency": 0.8, "rectangularity": 0.9, "parcel_split": 1.0})
    elif priority == "rectangular_fields":
        weights.update({"rectangularity": 1.8, "parcel_split": 1.4, "road_efficiency": 0.8})
    elif priority == "future_flexibility":
        weights.update({"parcel_split": 1.7, "rectangularity": 1.4, "connectivity": 1.1, "road_efficiency": 0.8})
    if required_redundancy:
        weights["connectivity"] = max(weights["connectivity"], 1.6)
        weights["road_efficiency"] = min(weights["road_efficiency"], 0.9)
    if separation == "strict":
        weights["connectivity"] = max(weights["connectivity"], 1.4)

    explanations = [
        {
            "Eingabe": "Hauptnutzung",
            "Auswahl": USAGE_LABELS.get(usage, usage),
            "Wirkung im Algorithmus": f"setzt das Nutzungsprofil auf {profile}; dadurch werden Straßenbreite, Andienhofgröße und Redundanzlogik vorbelegt.",
        },
        {
            "Eingabe": "Lieferverkehr",
            "Auswahl": DELIVERY_LABELS.get(delivery, delivery),
            "Wirkung im Algorithmus": f"setzt eine Annahme von ca. {lkw_per_day} LKW-Bewegungen pro Tag; daraus wird die Andienzone skaliert.",
        },
        {
            "Eingabe": "Verkehrstrennung",
            "Auswahl": SEPARATION_LABELS.get(separation, separation),
            "Wirkung im Algorithmus": "erhöht bei strenger Trennung die Bedeutung vollständiger Zielpunkt-Anbindung und bevorzugt klarere Spangen-/Loop-Strukturen.",
        },
        {
            "Eingabe": "Redundanz",
            "Auswahl": REDUNDANCY_LABELS.get(redundancy, redundancy),
            "Wirkung im Algorithmus": "prüft Loop/Ring bevorzugt und wertet einfache Stichlösungen ab, wenn Redundanz zwingend ist.",
        },
        {
            "Eingabe": "Planungspriorität",
            "Auswahl": PRIORITY_LABELS.get(priority, priority),
            "Wirkung im Algorithmus": "setzt die Startgewichtung der Bewertungsfunktion; diese Gewichtung kann anschließend feinjustiert werden.",
        },
    ]

    return {
        "profile": profile,
        "preferred_strategy": preferred_strategy,
        "lkw_per_day": lkw_per_day,
        "employees": employees,
        "setback": 8.0,
        "weights": weights,
        "required_redundancy": required_redundancy,
        "explanations": explanations,
        "summary": {
            "Nutzungsprofil": profile,
            "Strategievorschlag": preferred_strategy,
            "LKW-Bewegungen/Tag": lkw_per_day,
            "Mitarbeiter/Schicht": employees,
            "Redundanz erforderlich": "ja" if required_redundancy else "nein",
        },
    }


def _poly(site: LabSite) -> Polygon:
    return Polygon(site.polygon).buffer(0)


def _coords(geom) -> list[Point2D]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [(round(float(x), 2), round(float(y), 2)) for x, y in geom.exterior.coords[:-1]]
    if geom.geom_type == "MultiPolygon":
        largest = max(geom.geoms, key=lambda g: g.area)
        return [(round(float(x), 2), round(float(y), 2)) for x, y in largest.exterior.coords[:-1]]
    return []


def project_point_to_site_boundary(site: LabSite, point: Point2D) -> dict[str, Any]:
    """Project a clicked point onto the nearest site boundary segment."""
    polygon = _poly(site)
    boundary = polygon.boundary
    clicked = Point(point)
    projected_distance = boundary.project(clicked)
    projected = boundary.interpolate(projected_distance)
    px, py = float(projected.x), float(projected.y)
    coords = list(polygon.exterior.coords)
    best_segment = ((coords[0][0], coords[0][1]), (coords[1][0], coords[1][1]))
    best_distance = float("inf")
    for a, b in zip(coords, coords[1:]):
        segment = LineString([a, b])
        distance = segment.distance(projected)
        if distance < best_distance:
            best_distance = distance
            best_segment = ((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
    (x0, y0), (x1, y1) = best_segment
    dx, dy = x1 - x0, y1 - y0
    length = max(1.0, sqrt(dx * dx + dy * dy))
    return {
        "point": (round(px, 2), round(py, 2)),
        "clicked": (round(float(point[0]), 2), round(float(point[1]), 2)),
        "distance_to_edge_m": round(float(clicked.distance(projected)), 2),
        "segment": [(round(x0, 2), round(y0, 2)), (round(x1, 2), round(y1, 2))],
        "tangent": (round(dx / length, 4), round(dy / length, 4)),
    }


def _side_vector(side: str) -> Point2D:
    return {
        "south": (0.0, 1.0),
        "north": (0.0, -1.0),
        "west": (1.0, 0.0),
        "east": (-1.0, 0.0),
    }.get(side, (0.0, 1.0))


def _inward(pt: Point2D, side: str, distance: float) -> Point2D:
    vx, vy = _side_vector(side)
    return (pt[0] + vx * distance, pt[1] + vy * distance)


def _primary_side(site: LabSite) -> str:
    return str((site.access_points[0] if site.access_points else {}).get("side") or "south")


def _target_zones(site: LabSite, profile: str, lkw_per_day: int, employees: int, setback: float) -> dict[str, Any]:
    poly = _poly(site)
    minx, miny, maxx, maxy = poly.bounds
    width, depth = maxx - minx, maxy - miny
    side = _primary_side(site)
    access = tuple(site.access_points[0]["point"]) if site.access_points else (minx, miny)
    rules = PROFILE_RULES[profile]
    road_width = float(rules["road_width"])
    yard_len = min(max(width, depth) * 0.38, max(34.0, sqrt(poly.area) * 0.42 * rules["yard_scale"] * max(0.7, min(1.6, lkw_per_day / 80))))
    yard_depth = min(min(width, depth) * 0.34, max(16.0, road_width * 2.2))
    car_len = min(max(width, depth) * 0.28, max(24.0, sqrt(poly.area) * 0.22 * max(0.7, min(1.6, employees / 180))))
    car_depth = max(9.0, road_width * 0.9)

    anchor = _inward(access, side, setback + road_width * 1.8)
    if side in {"south", "north"}:
        yard = box(anchor[0] - yard_len / 2, anchor[1] - yard_depth / 2, anchor[0] + yard_len / 2, anchor[1] + yard_depth / 2)
        parking_center = (max(minx + car_len / 2, min(maxx - car_len / 2, anchor[0] + yard_len * 0.45)), anchor[1])
        parking = box(parking_center[0] - car_len / 2, parking_center[1] - car_depth / 2, parking_center[0] + car_len / 2, parking_center[1] + car_depth / 2)
    else:
        yard = box(anchor[0] - yard_depth / 2, anchor[1] - yard_len / 2, anchor[0] + yard_depth / 2, anchor[1] + yard_len / 2)
        parking_center = (anchor[0], max(miny + car_len / 2, min(maxy - car_len / 2, anchor[1] + yard_len * 0.45)))
        parking = box(parking_center[0] - car_depth / 2, parking_center[1] - car_len / 2, parking_center[0] + car_depth / 2, parking_center[1] + car_len / 2)

    buildable = poly.buffer(-setback)
    yard = yard.intersection(buildable)
    parking = parking.intersection(poly)
    security = Point(access).buffer(max(4.0, road_width * 0.55), cap_style=3).intersection(poly.buffer(2))
    infra = _inward(site.access_points[-1]["point"], str(site.access_points[-1].get("side") or side), setback + road_width)
    core = buildable.centroid
    zones = [
        {"id": "AH1", "name": "Andienhof", "kind": "service", "polygon": _coords(yard), "point": tuple(yard.centroid.coords)[0] if not yard.is_empty else anchor},
        {"id": "PKW1", "name": "PKW / Besucher", "kind": "parking", "polygon": _coords(parking), "point": tuple(parking.centroid.coords)[0] if not parking.is_empty else anchor},
        {"id": "PF1", "name": "Pforte", "kind": "security", "polygon": _coords(security), "point": access},
        {"id": "MS1", "name": "Medienknoten", "kind": "infra", "polygon": [], "point": infra},
        {"id": "BF1", "name": "Baufeldkern", "kind": "core", "polygon": [], "point": (core.x, core.y)},
    ]
    return {"zones": zones, "buildable": buildable, "road_width": road_width}


def _orthogonal(a: Point2D, b: Point2D, prefer: str) -> list[LineString]:
    if prefer in {"south", "north"}:
        bend = (a[0], b[1])
    else:
        bend = (b[0], a[1])
    lines = [LineString([a, bend]), LineString([bend, b])]
    return [ln for ln in lines if ln.length > 0.5]


def generate_access_networks(site: LabSite, targets: dict[str, Any], strategies: list[str]) -> list[dict[str, Any]]:
    """Phase 1: generate road-network candidates from site access points.

    A candidate is only a road network at this stage. Utility routes and parcels
    are derived later so they cannot accidentally drive the road geometry.
    """
    poly = _poly(site)
    minx, miny, maxx, maxy = poly.bounds
    side = _primary_side(site)
    zones = {z["id"]: z for z in targets["zones"]}
    access_pts = [tuple(ap["point"]) for ap in site.access_points]
    access = access_pts[0]
    service = zones["AH1"]["point"]
    parking = zones["PKW1"]["point"]
    core = zones["BF1"]["point"]
    road_width = targets["road_width"]
    networks: list[dict[str, Any]] = []

    def add_line(lines: list[LineString], line: LineString) -> None:
        if line.length > road_width * 0.6:
            lines.append(line)

    def add_many(lines: list[LineString], items: Iterable[LineString]) -> None:
        for line in items:
            add_line(lines, line)

    for strategy in strategies:
        lines: list[LineString] = []
        if strategy == "stich":
            add_many(lines, _orthogonal(access, service, side))
            add_many(lines, _orthogonal(service, parking, side))
        elif strategy == "front_spine":
            if side in {"south", "north"}:
                y = service[1]
                x0 = max(minx + road_width, min(access[0], service[0], parking[0]) - road_width * 2)
                x1 = min(maxx - road_width, max(access[0], service[0], parking[0], core[0]) + road_width * 2)
                add_line(lines, LineString([(x0, y), (x1, y)]))
                for pt in access_pts:
                    add_many(lines, _orthogonal(pt, (max(x0, min(x1, pt[0])), y), side))
            else:
                x = service[0]
                y0 = max(miny + road_width, min(access[1], service[1], parking[1]) - road_width * 2)
                y1 = min(maxy - road_width, max(access[1], service[1], parking[1], core[1]) + road_width * 2)
                add_line(lines, LineString([(x, y0), (x, y1)]))
                for pt in access_pts:
                    add_many(lines, _orthogonal(pt, (x, max(y0, min(y1, pt[1]))), side))
        elif strategy == "central_spine":
            if (maxx - minx) >= (maxy - miny):
                y = core[1]
                add_line(lines, LineString([(minx + road_width, y), (maxx - road_width, y)]))
                add_many(lines, _orthogonal(access, (access[0], y), side))
                add_many(lines, _orthogonal(service, (service[0], y), side))
                add_many(lines, _orthogonal(parking, (parking[0], y), side))
            else:
                x = core[0]
                add_line(lines, LineString([(x, miny + road_width), (x, maxy - road_width)]))
                add_many(lines, _orthogonal(access, (x, access[1]), side))
                add_many(lines, _orthogonal(service, (x, service[1]), side))
                add_many(lines, _orthogonal(parking, (x, parking[1]), side))
        elif strategy == "loop":
            loop = targets["buildable"].buffer(-road_width * 0.7)
            if loop.is_empty:
                loop = targets["buildable"]
            coords = list(loop.exterior.coords)
            for idx in range(len(coords) - 1):
                add_line(lines, LineString([coords[idx], coords[idx + 1]]))
            add_many(lines, _orthogonal(access, service, side))
            add_many(lines, _orthogonal(access, parking, side))
        if not lines:
            continue
        road_line = unary_union(lines)
        raw_road_poly = road_line.buffer(road_width / 2, cap_style=2, join_style=2)
        road_poly = raw_road_poly.intersection(poly)
        networks.append({
            "strategy": strategy,
            "road_lines_geom": lines,
            "road_line_geom": road_line,
            "raw_road_polygon_geom": raw_road_poly,
            "road_polygon_geom": road_poly,
            "road_lines": [[(round(x, 2), round(y, 2)) for x, y in ln.coords] for ln in lines],
            "road_polygon": _coords(road_poly),
        })
    return networks


def validate_vehicle_network(network: dict[str, Any], site: LabSite, targets: dict[str, Any], *, redundant: bool) -> dict[str, Any]:
    """Phase 2: hard checks before a network can be scored."""
    site_poly = _poly(site)
    road_poly = network["road_polygon_geom"]
    raw_road_poly = network.get("raw_road_polygon_geom", road_poly)
    road_width = float(targets["road_width"])
    target_points = [z for z in targets["zones"] if z["kind"] in {"service", "parking", "security"}]
    connected = []
    missing = []
    for zone in target_points:
        point = Point(zone["point"])
        ok = road_poly.distance(point) <= road_width * 0.85
        (connected if ok else missing).append(zone["id"])
    outside_area = raw_road_poly.difference(site_poly.buffer(0.01)).area
    inside = outside_area < 1.0
    redundant_ok = (not redundant) or network["strategy"] == "loop"
    dead_end_ok = network["strategy"] != "stich" or not redundant
    hard_ok = bool(inside and not missing and redundant_ok and dead_end_ok)
    checks = [
        {
            "Kriterium": "Straßenfläche liegt im Grundstück",
            "Status": "ok" if inside else "fehlt",
            "Hinweis": "harte geometrische Prüfung" if inside else f"{outside_area:.1f} m² außerhalb",
        },
        {"Kriterium": "Zielpunkte angebunden", "Status": "ok" if not missing else "fehlt", "Hinweis": ", ".join(missing) if missing else ", ".join(connected)},
        {"Kriterium": "Redundanz", "Status": "ok" if redundant_ok else "fehlt", "Hinweis": "Loop erforderlich" if redundant else "nicht gefordert"},
        {"Kriterium": "Sackgasse/Wendeanlage", "Status": "ok" if dead_end_ok else "fehlt", "Hinweis": "Stich bei Redundanz nicht zulässig" if not dead_end_ok else "zulässig"},
    ]
    return {
        "hard_ok": hard_ok,
        "connected_targets": connected,
        "missing_targets": missing,
        "road_outside_area_m2": round(float(outside_area), 1),
        "checks": checks,
    }


def route_utilities_along_network(network: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    """Phase 3: route utilities by snapping to the road network, not diagonally through parcels."""
    zones = {z["id"]: z for z in targets["zones"]}
    infra = Point(zones["MS1"]["point"])
    service = Point(zones["AH1"]["point"])
    road_line = network["road_line_geom"]
    infra_snap = nearest_points(infra, road_line)[1]
    service_snap = nearest_points(service, road_line)[1]

    def connector_lines(a: Point, b: Point) -> list[LineString]:
        ax, ay = a.coords[0]
        bx, by = b.coords[0]
        bend = (ax, by)
        lines = [LineString([(ax, ay), bend]), LineString([bend, (bx, by)])]
        return [line for line in lines if line.length > 0.5]

    connector_geoms = connector_lines(infra, infra_snap) + connector_lines(service, service_snap)
    # The road-axis overlay represents the shared utility corridor along the
    # access network. Only short orthogonal connectors may leave the road corridor.
    utility_lines_geom = connector_geoms + list(network["road_lines_geom"])
    utility_lines = [[(round(x, 2), round(y, 2)) for x, y in ln.coords] for ln in utility_lines_geom if ln.length > 0.5]
    connector_length = sum(line.length for line in connector_geoms)
    return {
        "utility_lines_geom": utility_lines_geom,
        "utility_lines": utility_lines,
        "connector_length_m": round(connector_length, 1),
        "explanation": "Medientrassen werden auf das Straßennetz gesnappt; nur kurze orthogonale Hausanschluss-/Übergabeverbindungen verlassen den Straßenkorridor.",
    }


def split_residual_land_into_parcels(network: dict[str, Any], targets: dict[str, Any], *, min_area_m2: float = 900.0) -> dict[str, Any]:
    """Phase 4: derive parcels only from land left after roads and target zones."""
    residual = targets["buildable"].difference(network["road_polygon_geom"].buffer(0.8))
    for zone in targets["zones"]:
        if zone.get("polygon"):
            residual = residual.difference(Polygon(zone["polygon"]).buffer(0.5))
    residual = residual.buffer(0)
    geoms = list(residual.geoms) if residual.geom_type == "MultiPolygon" else ([] if residual.is_empty else [residual])
    parcels = []
    road_poly = network["road_polygon_geom"]
    for idx, geom in enumerate(sorted(geoms, key=lambda g: g.area, reverse=True), start=1):
        if geom.area < min_area_m2:
            continue
        bbox = box(*geom.bounds)
        access_ok = geom.distance(road_poly) <= 1.5
        parcels.append({
            "id": f"P{idx}",
            "name": f"Parzelle {idx}",
            "area_m2": round(float(geom.area), 1),
            "rectangularity": round(float(geom.area / max(1.0, bbox.area)), 3),
            "access_ok": bool(access_ok),
            "polygon": _coords(geom),
            "centroid": (round(float(geom.centroid.x), 2), round(float(geom.centroid.y), 2)),
        })
    return {
        "parcels": parcels,
        "residual_area_m2": round(float(residual.area), 1),
        "buildable_area_m2": round(float(targets["buildable"].area), 1),
    }


def score_plan_variant(network: dict[str, Any], validation: dict[str, Any], utilities: dict[str, Any], parceling: dict[str, Any], site_poly, targets: dict[str, Any], weights: dict[str, float], redundant: bool) -> dict[str, float]:
    """Phase 5: score only after hard checks and derived parceling."""
    road_poly = network["road_polygon_geom"]
    road_pct = road_poly.area / max(1.0, site_poly.area)
    target_count = len([z for z in targets["zones"] if z["kind"] in {"service", "parking", "security"}])
    connectivity = len(validation["connected_targets"]) / max(1, target_count)
    parcels = parceling["parcels"]
    avg_rect = sum(p["rectangularity"] for p in parcels) / max(1, len(parcels))
    all_access = all(p["access_ok"] for p in parcels) if parcels else False
    raw = (
        42.0
        + connectivity * 26.0 * weights["connectivity"]
        + avg_rect * 22.0 * weights["rectangularity"]
        + min(10.0, len(parcels) * 2.5) * weights["parcel_split"]
        - road_pct * 120.0 * weights["road_efficiency"]
        - utilities["connector_length_m"] * 0.22
    )
    if not validation["hard_ok"]:
        raw -= 28.0
    if parcels and not all_access:
        raw -= 10.0
    if redundant and network["strategy"] == "loop":
        raw += 5.0
    return {
        "score": round(max(0.0, min(100.0, raw)), 1),
        "raw_score": round(raw, 2),
        "road_area_m2": round(road_poly.area, 1),
        "road_area_pct": round(road_pct, 3),
        "connectivity": round(connectivity, 3),
        "rectangularity": round(avg_rect, 3),
        "parcel_count": float(len(parcels)),
        "residual_components": float(len(parcels)),
        "utility_connector_length_m": utilities["connector_length_m"],
        "road_outside_area_m2": validation.get("road_outside_area_m2", 0.0),
        "hard_ok": 1.0 if validation["hard_ok"] else 0.0,
    }


def plan_traffic(
    site_id: str,
    *,
    profile: str = "logistik",
    preferred_strategy: str = "front_spine",
    lkw_per_day: int = 80,
    employees: int = 180,
    setback: float = 8.0,
    weights: dict[str, float] | None = None,
    required_redundancy: bool | None = None,
) -> dict[str, Any]:
    site = DEMO_SITES[site_id]
    profile = profile if profile in PROFILE_RULES else "logistik"
    weights = {
        "connectivity": float((weights or {}).get("connectivity", 1.0)),
        "road_efficiency": float((weights or {}).get("road_efficiency", 1.0)),
        "rectangularity": float((weights or {}).get("rectangularity", 1.0)),
        "parcel_split": float((weights or {}).get("parcel_split", 1.0)),
    }
    targets = _target_zones(site, profile, lkw_per_day, employees, setback)
    site_poly = _poly(site)
    strategies = list(dict.fromkeys([preferred_strategy, "stich", "front_spine", "central_spine", "loop"]))
    redundant = bool(PROFILE_RULES[profile]["redundancy"]) if required_redundancy is None else bool(required_redundancy)
    networks = generate_access_networks(site, targets, strategies)
    candidates: list[dict[str, Any]] = []
    for network in networks:
        validation = validate_vehicle_network(network, site, targets, redundant=redundant)
        utilities = route_utilities_along_network(network, targets)
        parceling = split_residual_land_into_parcels(network, targets)
        metrics = score_plan_variant(network, validation, utilities, parceling, site_poly, targets, weights, redundant)
        candidates.append({
            "strategy": network["strategy"],
            "metrics": metrics,
            "validation": validation,
            "utilities": {k: v for k, v in utilities.items() if k != "utility_lines_geom"},
            "parceling": parceling,
            "road_polygon": network["road_polygon"],
            "road_lines": network["road_lines"],
            "utility_lines": utilities["utility_lines"],
            "parcels": parceling["parcels"],
        })
    candidates.sort(key=lambda item: (item["metrics"]["hard_ok"], item["metrics"]["score"]), reverse=True)
    selected = candidates[0]
    phase_log = [
        {"Phase": "1 Erschließungsnetze", "Ergebnis": f"{len(networks)} Kandidaten erzeugt", "Status": "ok"},
        {"Phase": "2 Fahrzeugnetz prüfen", "Ergebnis": "harte Kriterien geprüft", "Status": "ok" if selected["validation"]["hard_ok"] else "Warnung"},
        {"Phase": "3 Trassen routen", "Ergebnis": selected["utilities"]["explanation"], "Status": "ok"},
        {"Phase": "4 Restflächen parzellieren", "Ergebnis": f"{len(selected['parcels'])} Parzellen aus Restflächen", "Status": "ok" if selected["parcels"] else "Warnung"},
        {"Phase": "5 Varianten bewerten", "Ergebnis": f"{selected['strategy']} mit Score {selected['metrics']['score']}", "Status": "ok"},
    ]
    return {
        "site": {"id": site.site_id, "name": site.name, "polygon": site.polygon, "access_points": site.access_points, "area_m2": round(site_poly.area, 1)},
        "profile": profile,
        "road_width_m": targets["road_width"],
        "targets": targets["zones"],
        "weights": weights,
        "required_redundancy": redundant,
        "phase_log": phase_log,
        "candidates": candidates,
        "selected": selected,
        "svg": render_svg(site, targets, selected),
    }

def render_svg(site: LabSite, targets: dict[str, Any], selected: dict[str, Any]) -> str:
    poly = _poly(site)
    minx, miny, maxx, maxy = poly.bounds
    pad = 22
    view = f"{minx - pad:.1f} {miny - pad:.1f} {(maxx - minx) + 2 * pad:.1f} {(maxy - miny) + 2 * pad:.1f}"

    def pts(items: list[Point2D]) -> str:
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in items)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" aria-label="Traffic Lab">']
    parts.append("<style>text{font-family:Inter,Arial,sans-serif}.label{paint-order:stroke;stroke:white;stroke-width:3px;stroke-linejoin:round}.thin{vector-effect:non-scaling-stroke}</style>")
    parts.append('<defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse"><path d="M0 5 L5 0" stroke="#B9823A" stroke-width=".5"/></pattern></defs>')
    parts.append(f'<polygon points="{pts(site.polygon)}" fill="#E9ECE7" stroke="#1F2933" stroke-width="1.4" class="thin"/>')
    build = targets["buildable"]
    if not build.is_empty:
        parts.append(f'<polygon points="{pts(_coords(build))}" fill="#DDE7EF" stroke="#9BB0C5" opacity=".35" class="thin"/>')
    for parcel in selected.get("parcels", []):
        if parcel.get("polygon"):
            parts.append(f'<polygon points="{pts(parcel["polygon"])}" fill="#DDE7EF" stroke="#42607A" opacity=".34" class="thin"/>')
            cx, cy = parcel["centroid"]
            parts.append(f'<text x="{cx:.2f}" y="{cy + 8:.2f}" font-size="3.6" fill="#1C3557" text-anchor="middle" class="label">{escape(parcel["id"])} · {parcel["area_m2"]:.0f} m²</text>')
    parts.append(f'<polygon points="{pts(selected["road_polygon"])}" fill="url(#hatch)" stroke="#B9823A" opacity=".72" class="thin"/>')
    for line in selected["road_lines"]:
        parts.append(f'<polyline points="{pts(line)}" fill="none" stroke="#A76824" stroke-width="1.1" class="thin"/>')
    for line in selected["utility_lines"]:
        parts.append(f'<polyline points="{pts(line)}" fill="none" stroke="#6554FF" stroke-width=".9" stroke-dasharray="3 2" class="thin"/>')
    colors = {"service": "#E8D3AE", "parking": "#F5F0DC", "security": "#BFD7EA", "infra": "#7B61FF", "core": "#4B5563"}
    label_offsets = {
        "service": (4.0, -6.0),
        "parking": (4.0, 5.0),
        "security": (3.5, -4.5),
        "infra": (3.5, -4.5),
        "core": (4.0, -4.5),
    }
    for zone in targets["zones"]:
        if zone["polygon"]:
            parts.append(f'<polygon points="{pts(zone["polygon"])}" fill="{colors.get(zone["kind"], "#DDD")}" stroke="#4B5563" opacity=".78" class="thin"/>')
        x, y = zone["point"]
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.3" fill="{colors.get(zone["kind"], "#777")}" stroke="white" stroke-width=".7" class="thin"/>')
        dx, dy = label_offsets.get(zone["kind"], (3.0, -3.0))
        parts.append(f'<text x="{x + dx:.2f}" y="{y + dy:.2f}" font-size="3.8" fill="#111827" class="label">{escape(zone["id"])} · {escape(zone["name"])}</text>')
    for ap in site.access_points:
        x, y = ap["point"]
        parts.append(f'<text x="{x + 3:.2f}" y="{y + 5:.2f}" font-size="4" fill="#B91C1C" font-weight="700" class="label">{escape(ap["id"])}</text>')
    parts.append(f'<text x="{minx:.2f}" y="{maxy + 16:.2f}" font-size="6" font-weight="700" fill="#111827">Traffic Lab · {escape(site.name)} · {escape(selected["strategy"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)

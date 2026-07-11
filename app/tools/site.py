"""
AID Demo - reproduzierbare Grundstuecksgenerierung.

Die Presets nutzen feste Seeds: Die Flaechen wirken generiert, bleiben aber
fuer Demo und Vergleich jederzeit identisch.
"""

from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import Any

from shapely.geometry import Polygon, Point


SITE_PRESETS = [
    {
        "id": "A_kompakt",
        "name": "Grundstueck A - kompakt",
        "beschreibung": "Kleines kompaktes Grundstueck fuer Stich- und Hoferschliessung.",
        "seed": 11,
        "shape_type": "compact",
        "target_area_m2": 9600,
        "access_count": 1,
        "preferred_sides": ["north"],
    },
    {
        "id": "B_langgezogen",
        "name": "Grundstueck B - langgezogen",
        "beschreibung": "Mittleres langgezogenes Grundstueck fuer Spine-/Spangenerschliessung.",
        "seed": 23,
        "shape_type": "elongated",
        "target_area_m2": 24000,
        "access_count": 2,
        "preferred_sides": ["west", "south"],
    },
    {
        "id": "C_unregelmaessig",
        "name": "Grundstueck C - unregelmaessig",
        "beschreibung": "Grosses unregelmaessiges Areal fuer Ring, Trassen und mehrere Baufelder.",
        "seed": 37,
        "shape_type": "angled",
        "target_area_m2": 56000,
        "access_count": 2,
        "preferred_sides": ["east", "north"],
    },
]


def get_demo_sites() -> list[dict[str, Any]]:
    """Erzeugt die drei reproduzierbaren Demo-Grundstuecke."""
    return [
        generate_site(
            target_area_m2=preset["target_area_m2"],
            seed=preset["seed"],
            shape_type=preset["shape_type"],
            access_count=preset["access_count"],
            preferred_sides=preset["preferred_sides"],
            site_id=preset["id"],
            name=preset["name"],
            beschreibung=preset["beschreibung"],
        )
        for preset in SITE_PRESETS
    ]


def get_demo_site(site_id: str | None = None) -> dict[str, Any]:
    """Liefert ein Demo-Grundstueck per ID oder das erste Preset."""
    sites = get_demo_sites()
    if not site_id:
        return sites[0]
    for site in sites:
        if site["id"] == site_id:
            return site
    raise ValueError(f"Unbekanntes Grundstueck: {site_id}")


def generate_site(
    *,
    target_area_m2: float,
    seed: int,
    shape_type: str,
    access_count: int,
    preferred_sides: list[str] | None = None,
    site_id: str | None = None,
    name: str | None = None,
    beschreibung: str | None = None,
) -> dict[str, Any]:
    """Generiert ein lokales Meter-Polygon mit Erschliessungspunkten."""
    rng = random.Random(seed)
    coords = _base_polygon(shape_type, target_area_m2, rng)
    coords = _scale_polygon_to_area(coords, target_area_m2)
    coords = _normalize_coords(coords)
    poly = Polygon(coords)
    minx, miny, maxx, maxy = poly.bounds
    width = maxx - minx
    depth = maxy - miny

    access_points = _generate_access_points(
        rng=rng,
        count=access_count,
        preferred_sides=preferred_sides or [],
        width=width,
        depth=depth,
    )

    # Snap each access point to the actual polygon boundary so it lies exactly on the edge
    exterior = poly.exterior
    for ap in access_points:
        pt = Point(float(ap["point"][0]), float(ap["point"][1]))
        snapped = exterior.interpolate(exterior.project(pt))
        ap["point"] = [round(float(snapped.x), 1), round(float(snapped.y), 1)]

    return {
        "id": site_id or f"{shape_type}_{seed}",
        "name": name or f"Grundstueck {seed}",
        "beschreibung": beschreibung or "",
        "seed": seed,
        "shape_type": shape_type,
        "target_area_m2": target_area_m2,
        "area_m2": round(poly.area),
        "width_m": round(width, 1),
        "depth_m": round(depth, 1),
        "polygon": [[round(x, 2), round(y, 2)] for x, y in coords],
        "access_points": access_points,
        "planning": {
            "grz": 0.8,
            "gfz": 2.4,
            "abstandsfaktor": 0.4,
            "max_gebaeudehoehe_m": 12.0,
            "regelgeschoss_hoehe_m": 3.5,
        },
    }


def compute_building_envelope(
    site_geometry: dict[str, Any] | None,
    *,
    grid_m: float = 3.0,
    angle_override: float | None = None,
) -> dict[str, Any] | None:
    """Berechnet ein groesstmoegliches Baufeld-Rechteck entlang der Ausrichtungsachse.

    angle_override: Wenn angegeben, wird diese Achsrichtung (Grad von West-Ost,
    gegen Uhrzeigersinn positiv) statt der geometrischen Hauptachse verwendet.
    Quelle kann die Straßenflucht aus OSM oder ein Nutzerwert sein.
    Fallback-Prioritaet: angle_override > site_geometry["alignment_angle_deg"] > geometrisch.
    """
    if not site_geometry or not site_geometry.get("polygon"):
        return None

    if site_geometry.get("is_building_parcel") or site_geometry.get("interface_type") == "building_parcel":
        width = float(site_geometry.get("width_m") or 0.0)
        depth = float(site_geometry.get("depth_m") or 0.0)
        if width > 0 and depth > 0:
            area = float(site_geometry.get("area_m2") or width * depth)
            return {
                "x": 0.0,
                "y": 0.0,
                "width_m": round(width, 2),
                "depth_m": round(depth, 2),
                "area_m2": round(area, 2),
                "setback_m": 0.0,
                "grz": 1.0,
                "gfz": float((site_geometry.get("planning") or {}).get("gfz", 6.0)),
                "max_gebaeudehoehe_m": float((site_geometry.get("planning") or {}).get("max_gebaeudehoehe_m", 12.0)),
                "max_vollgeschosse": 1,
                "max_footprint_m2": round(area, 2),
                "max_gfa_m2": round(area, 2),
                "limit_grz_m2": round(area, 2),
                "limit_gfz_footprint_m2": round(area, 2),
                "limit_rect_m2": round(area, 2),
                "site_angle_deg": 0.0,
                "site_centroid_x": round(width / 2, 2),
                "site_centroid_y": round(depth / 2, 2),
                "access_edge": _compute_access_edge(site_geometry),
                "rotated_site_south": 0.0,
                "rotated_site_north": round(depth, 2),
            }

    planning = site_geometry.get("planning") or {}
    site_area = float(site_geometry.get("area_m2") or Polygon(site_geometry["polygon"]).area)
    grz = float(planning.get("grz", 0.8))
    gfz = float(planning.get("gfz", 2.4))
    abstandsfaktor = float(planning.get("abstandsfaktor", 0.4))
    max_height = float(planning.get("max_gebaeudehoehe_m", 12.0))
    floor_height = max(2.5, float(planning.get("regelgeschoss_hoehe_m", 3.5)))
    max_floors = max(1, int(max_height // floor_height))
    setback = max(0.0, max_height * abstandsfaktor)

    polygon = Polygon(site_geometry["polygon"])
    cx, cy = polygon.centroid.x, polygon.centroid.y

    # Ausrichtungswinkel bestimmen — drei Quellen, absteigender Vorrang
    if angle_override is not None:
        site_angle_deg = float(angle_override)
    elif "alignment_angle_deg" in site_geometry:
        site_angle_deg = float(site_geometry["alignment_angle_deg"])
    else:
        site_angle_deg = _polygon_principal_angle(polygon)

    # Rotate polygon to align with axes for max-rect search
    if abs(site_angle_deg) > 0.5:
        from shapely.affinity import rotate as _shapely_rotate
        work_poly = _shapely_rotate(polygon, -site_angle_deg, origin=(cx, cy))
    else:
        work_poly = polygon
        site_angle_deg = 0.0

    buildable = work_poly.buffer(-setback)
    if buildable.is_empty:
        buildable = work_poly
        setback = 0.0

    largest = _largest_axis_aligned_rect(buildable, grid_m)
    if not largest:
        return None

    grz_footprint = grz * site_area
    gfz_gfa = gfz * site_area
    gfz_footprint = gfz_gfa / max_floors
    max_footprint = min(largest["area_m2"], grz_footprint, gfz_footprint)

    rot_bounds = buildable.bounds  # (minx, miny, maxx, maxy) in rotated frame

    return {
        **largest,
        "setback_m": round(setback, 2),
        "grz": grz,
        "gfz": gfz,
        "max_gebaeudehoehe_m": max_height,
        "max_vollgeschosse": max_floors,
        "max_footprint_m2": round(max_footprint, 2),
        "max_gfa_m2": round(gfz_gfa, 2),
        "limit_grz_m2": round(grz_footprint, 2),
        "limit_gfz_footprint_m2": round(gfz_footprint, 2),
        "limit_rect_m2": round(largest["area_m2"], 2),
        "site_angle_deg": site_angle_deg,
        "site_centroid_x": round(cx, 2),
        "site_centroid_y": round(cy, 2),
        "access_edge": _compute_access_edge(site_geometry),
        "rotated_site_south": round(rot_bounds[1], 2),
        "rotated_site_north": round(rot_bounds[3], 2),
    }


def _largest_axis_aligned_rect(buildable, grid_m: float) -> dict[str, Any] | None:
    minx, miny, maxx, maxy = buildable.bounds
    cols = max(1, int((maxx - minx) // grid_m))
    rows = max(1, int((maxy - miny) // grid_m))

    cell_area = grid_m * grid_m
    matrix = []
    for r in range(rows):
        row = []
        for c in range(cols):
            cell = Polygon([
                (minx + c * grid_m, miny + r * grid_m),
                (minx + (c + 1) * grid_m, miny + r * grid_m),
                (minx + (c + 1) * grid_m, miny + (r + 1) * grid_m),
                (minx + c * grid_m, miny + (r + 1) * grid_m),
            ])
            # Require ≥90% of cell inside buildable area — prevents Bebauungslinie violations
            coverage = buildable.intersection(cell).area / cell_area
            row.append(coverage >= 0.90)
        matrix.append(row)

    heights = [0] * cols
    best = None
    for r in range(rows):
        for c in range(cols):
            heights[c] = heights[c] + 1 if matrix[r][c] else 0
        stack: list[int] = []
        for c in range(cols + 1):
            h = heights[c] if c < cols else 0
            while stack and h < heights[stack[-1]]:
                top = stack.pop()
                height = heights[top]
                left = stack[-1] + 1 if stack else 0
                width = c - left
                area_cells = width * height
                if best is None or area_cells > best["area_cells"]:
                    best = {
                        "area_cells": area_cells,
                        "col": left,
                        "row": r - height + 1,
                        "cols": width,
                        "rows": height,
                    }
            stack.append(c)

    if not best:
        return None
    x = minx + best["col"] * grid_m
    y = miny + best["row"] * grid_m
    width = best["cols"] * grid_m
    depth = best["rows"] * grid_m
    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "width_m": round(width, 2),
        "depth_m": round(depth, 2),
        "area_m2": round(width * depth, 2),
    }


def _polygon_principal_angle(polygon) -> float:
    """Winkel (Grad) der Hauptachse: laengste Kante des minimum_rotated_rectangle.
    Ergebnis normiert auf (-90, 90]."""
    try:
        rect = polygon.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
        best_angle, best_len = 0.0, 0.0
        for i in range(len(coords) - 1):
            dx = coords[i + 1][0] - coords[i][0]
            dy = coords[i + 1][1] - coords[i][1]
            length = math.hypot(dx, dy)
            if length > best_len:
                best_len = length
                best_angle = math.degrees(math.atan2(dy, dx))
        while best_angle > 90:
            best_angle -= 180
        while best_angle <= -90:
            best_angle += 180
        return round(best_angle, 2)
    except Exception:
        return 0.0


def _compute_access_edge(site_geometry: dict) -> str:
    """Primaere Zugangskante ('south', 'north', 'east', 'west') aus access_points."""
    access_points = (site_geometry or {}).get("access_points") or []
    if not access_points:
        return "south"
    best = max(access_points, key=lambda ap: float(ap.get("width_m", 0)))
    return best.get("side", "south")


def compute_maneuvering_depth(nutzungstyp: str | None = None) -> float:
    """Rangiertiefe in Metern je Nutzungstyp (LKW/Kran 35m, Prod 25m, PKW 8m)."""
    nt = str(nutzungstyp or "").lower()
    if "logistik" in nt or "kranbahn" in nt:
        return 35.0
    if "produktion" in nt:
        return 25.0
    return 8.0


def site_bounds(site_geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    """Extrahiert Breite/Tiefe aus einer Site-Geometrie."""
    if not site_geometry:
        return None
    width = site_geometry.get("width_m")
    depth = site_geometry.get("depth_m")
    if width and depth:
        return float(width), float(depth)
    polygon = site_geometry.get("polygon")
    if not polygon:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return max(xs) - min(xs), max(ys) - min(ys)


def _base_polygon(shape_type: str, target_area_m2: float, rng: random.Random) -> list[tuple[float, float]]:
    if shape_type == "compact":
        aspect = rng.uniform(1.05, 1.25)
        depth = math.sqrt(target_area_m2 / aspect)
        width = target_area_m2 / depth
        return [
            (0, 0),
            (width, 0),
            (width + rng.uniform(-3, 3), depth),
            (rng.uniform(-3, 3), depth + rng.uniform(-2, 2)),
        ]

    if shape_type == "elongated":
        aspect = rng.uniform(2.0, 2.35)
        depth = math.sqrt(target_area_m2 / aspect)
        width = target_area_m2 / depth
        notch = depth * rng.uniform(0.12, 0.18)
        return [
            (0, 0),
            (width, 0),
            (width, depth),
            (width * 0.62, depth),
            (width * 0.62, depth - notch),
            (0, depth - notch),
        ]

    if shape_type == "angled":
        aspect = rng.uniform(1.35, 1.6)
        depth = math.sqrt(target_area_m2 / aspect)
        width = target_area_m2 / depth
        return [
            (0, depth * 0.08),
            (width * 0.82, 0),
            (width, depth * 0.34),
            (width * 0.88, depth),
            (width * 0.18, depth * 0.92),
            (0, depth * 0.62),
        ]

    raise ValueError(f"Unbekannter Zuschnitt: {shape_type}")


def _scale_polygon_to_area(coords: list[tuple[float, float]], target_area_m2: float) -> list[tuple[float, float]]:
    poly = Polygon(coords)
    factor = math.sqrt(target_area_m2 / poly.area)
    return [(x * factor, y * factor) for x, y in coords]


def _normalize_coords(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    minx = min(x for x, _ in coords)
    miny = min(y for _, y in coords)
    normalized = [(x - minx, y - miny) for x, y in coords]
    return _ensure_closed(normalized)


def _ensure_closed(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if coords[0] == coords[-1]:
        return coords
    return coords + [coords[0]]


def _generate_access_points(
    *,
    rng: random.Random,
    count: int,
    preferred_sides: list[str],
    width: float,
    depth: float,
) -> list[dict[str, Any]]:
    sides = deepcopy(preferred_sides)
    for side in ["north", "east", "south", "west"]:
        if len(sides) >= count:
            break
        if side not in sides:
            sides.append(side)

    access_points = []
    for idx, side in enumerate(sides[:count], start=1):
        width_m = rng.choice([6.0, 7.5, 8.0, 10.0])
        if side in {"north", "south"}:
            offset = round(rng.uniform(width * 0.18, width * 0.82), 1)
            point = [offset, depth if side == "north" else 0.0]
        else:
            offset = round(rng.uniform(depth * 0.18, depth * 0.82), 1)
            point = [width if side == "east" else 0.0, offset]
        access_points.append({
            "id": f"Z{idx}",
            "side": side,
            "point": [round(point[0], 1), round(point[1], 1)],
            "width_m": width_m,
        })
    return access_points

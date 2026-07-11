"""
AID Demo – Sprint R: Masterplanung-Agent
=========================================
Erste Planungsmaßstabsebene: Gebäude-Ensemble + Erschließung + Freizonen
auf dem gesamten Grundstück.

Algorithmus: Deterministisch, regelbasiert (kein LLM).

Outputs (dict unter "masterplan"):
  hauptgebaeude     – zentrales Produktionsgebäude (Footprint-Rechteck)
  nebenbauten       – Pforte, Trafostation, Lagerüberdachung
  erschliessung     – LKW-Schleife, PKW-Zufahrt, Rangierzone (Polygon-Punkte)
  freizonen         – Stellplatzfelder, Grünflächen (Liste von Rechtecken)
  flaechenbilanz    – GRZ, GFZ, Versiegelungsgrad etc.
  config            – Eingabeparameter (grz_ziel, nebenbauten_aktiv, …)
"""
from __future__ import annotations

import math
import pathlib
from typing import Any

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_masterplan_rules_cache: dict | None = None


def _load_masterplan_rules() -> dict:
    """Lädt rules_masterplan.yaml (gecacht). Gibt {} zurück wenn nicht verfügbar."""
    global _masterplan_rules_cache
    if _masterplan_rules_cache is not None:
        return _masterplan_rules_cache
    path = _DATA_DIR / "rules_masterplan.yaml"
    if not _YAML_AVAILABLE or not path.exists():
        _masterplan_rules_cache = {}
        return _masterplan_rules_cache
    with open(path, encoding="utf-8") as f:
        _masterplan_rules_cache = _yaml.safe_load(f) or {}
    return _masterplan_rules_cache


def _masterplan_rule_refs(rules: dict, phase: str | None = None) -> list[dict[str, Any]]:
    """Return machine-readable rule references for transparent planning decisions."""
    catalog = rules.get("rule_catalog") or {}
    phases = [str(phase)] if phase else [str(k) for k in catalog.keys()]
    refs: list[dict[str, Any]] = []
    for phase_key in phases:
        entries = catalog.get(phase_key) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ref = {
                "phase": phase_key,
                "id": str(entry.get("id") or ""),
                "title": str(entry.get("title") or entry.get("id") or "Regel"),
                "source_ref": str(entry.get("source_ref") or "Projekt-Regelkatalog"),
                "parameter": str(entry.get("parameter") or ""),
                "value": entry.get("value"),
                "rule_type": str(entry.get("rule_type") or "regel"),
            }
            if entry.get("unit"):
                ref["unit"] = str(entry.get("unit"))
            refs.append(ref)
    return refs


def _masterplan_source_refs(rules: dict) -> list[dict[str, Any]]:
    """Compact source list for decision_log and UI export."""
    refs = []
    seen: set[tuple[str, str]] = set()
    for ref in _masterplan_rule_refs(rules):
        key = (str(ref.get("phase")), str(ref.get("id")))
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            "type": "rule_catalog",
            "phase": ref.get("phase"),
            "id": ref.get("id"),
            "title": ref.get("title"),
            "source_ref": ref.get("source_ref"),
            "parameter": ref.get("parameter"),
            "value": ref.get("value"),
        })
    return refs


# ---------------------------------------------------------------------------
# Standard-Nebenbauten (Funktion → Grundfläche)
# ---------------------------------------------------------------------------

NEBENBAU_TYPEN = {
    "Pforte / Einfahrtskontrolle": {
        "breite_m": 6.0,
        "tiefe_m":  5.0,
        "farbe":    "#4A90D9",
        "prio":     1,  # höchste Priorität, immer platziert
    },
    "Trafostation": {
        "breite_m": 6.0,
        "tiefe_m":  5.0,
        "farbe":    "#E67E22",
        "prio":     2,
    },
    "Lagerüberdachung": {
        "breite_m": 20.0,
        "tiefe_m":   8.0,
        "farbe":    "#7F8C8D",
        "prio":     3,
    },
    "Sozialgebäude": {
        "breite_m": 15.0,
        "tiefe_m":  10.0,
        "farbe":    "#27AE60",
        "prio":     4,
    },
}

# Breite der LKW-Erschließung inkl. Rangieren [m]
LKW_STREIFEN_TIEFE   = 18.0  # 6m Fahrgasse + 12m Rangierfläche
PKW_STREIFEN_TIEFE   = 12.0  # 2 × Parkstreifen à 5m + 2m Fahrgang

# Standardabstand Gebäude → Grundstücksgrenze
ABSTANDSFLAECHE_M = 4.0

# Stellplatz-Maße
SP_BREITE_M = 2.5
SP_TIEFE_M  = 5.0


# ---------------------------------------------------------------------------
# Haupt-Agentenfunktion
# ---------------------------------------------------------------------------

def masterplan_agent(
    site: dict[str, Any],
    *,
    grz_ziel: float = 0.45,
    nebenbauten_aktiv: dict[str, bool] | None = None,
    erschliessung_typ: str = "u_foermig",  # "u_foermig" | "l_foermig" | "gerade"
    geschosse_buero: int = 2,
    briefing: dict[str, Any] | None = None,
    building_targets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Berechnet drei Masterplan-Varianten deterministisch.

    Die oberste Struktur bleibt abwärtskompatibel: Die ausgewählte Variante wird
    weiterhin direkt unter ``masterplan`` gespiegelt. Zusätzlich enthält
    ``masterplan["variants"]`` alle erzeugten Varianten als eigene Planungsstände.
    """
    if nebenbauten_aktiv is None:
        nebenbauten_aktiv = {k: True for k in NEBENBAU_TYPEN}

    rules_mp = _load_masterplan_rules()
    site_w = float(site["width_m"])
    site_d = float(site["depth_m"])
    site_a = float(site["area_m2"])
    access = site.get("access_points") or []
    access_side = _primary_access_side(access, site_w, site_d)
    grundstuecksanalyse = _analyze_site_for_masterplanning(site, access, site_w, site_d, site_a)
    _poly_for_metrics = _polygon_from_site(site)
    if _poly_for_metrics is not None:
        grundstuecksanalyse = _site_geometry_metrics(site, _poly_for_metrics, grundstuecksanalyse)
    grz = max(0.25, min(0.70, grz_ziel))

    variants: list[dict[str, Any]] = []
    for idx, spec in enumerate(_masterplan_variant_specs(grz, erschliessung_typ), start=1):
        variants.append(_generate_masterplan_variant(
            site=site,
            site_w=site_w,
            site_d=site_d,
            site_a=site_a,
            access=access,
            access_side=access_side,
            grundstuecksanalyse=grundstuecksanalyse,
            grz=float(spec["grz"]),
            nebenbauten_aktiv=nebenbauten_aktiv,
            erschliessung_typ=str(spec["erschliessung_typ"]),
            geschosse_buero=geschosse_buero,
            briefing=briefing,
            building_targets=building_targets,
            rules_mp=rules_mp,
            variant_id=str(spec["id"]),
            variant_label=str(spec["label"]),
            variant_focus=str(spec["focus"]),
            parcel_idx=idx,
        ))

    selected = variants[0]
    return {
        "masterplan": {
            "site": site,
            "variants": variants,
            "selected_masterplan_variant_id": selected["id"],
            "building_parcels": selected["building_parcels"],
            "selected_building_parcel_id": selected["selected_building_parcel_id"],
            "building_parcel": selected["building_parcel"],
            "grundstuecksanalyse": grundstuecksanalyse,
            "zonierung": selected["zonierung"],
            "phasenlayer": selected.get("phasenlayer") or {},
            "erschliessungskonzept": selected["erschliessungskonzept"],
            "planning_pipeline": selected["planning_pipeline"],
            "regelquellen": _masterplan_source_refs(rules_mp),
            "hauptgebaeude": selected["hauptgebaeude"],
            "gebaeude": selected["gebaeude"],
            "nebenbauten": selected["nebenbauten"],
            "erschliessung": selected["erschliessung"],
            "freizonen": selected["freizonen"],
            "infrastruktur": selected["infrastruktur"],
            "flaechenbilanz": selected["flaechenbilanz"],
            "score": selected["score"],
            "config": {
                "grz_ziel": grz,
                "nebenbauten_aktiv": nebenbauten_aktiv,
                "erschliessung_typ": erschliessung_typ,
                "access_side": access_side,
                "building_targets": building_targets or {},
                "algorithmus": "polygonal_site_zoning_v2",
                "rules_geladen": bool(rules_mp),
                "rule_catalog_loaded": bool((rules_mp or {}).get("rule_catalog")),
            },
        }
    }


def _masterplan_variant_specs(grz: float, erschliessung_typ: str) -> list[dict[str, Any]]:
    """Standardvarianten fuer die Masterplanung."""
    return [
        {
            "id": "A_LOGISTIK",
            "label": "A Logistikfluss",
            "focus": "Kurze Wege und robuste LKW-Andienung",
            "grz": grz,
            "erschliessung_typ": erschliessung_typ,
        },
        {
            "id": "B_ERWEITERUNG",
            "label": "B Erweiterbarkeit",
            "focus": "Gebäude an eine Seite legen und Erweiterungsreserve freihalten",
            "grz": max(0.25, grz * 0.88),
            "erschliessung_typ": "l_foermig" if erschliessung_typ == "u_foermig" else erschliessung_typ,
        },
        {
            "id": "C_FLAECHENEFFIZIENZ",
            "label": "C Flächeneffizienz",
            "focus": "Hohe Baurechtsausnutzung und kompakter Footprint",
            "grz": min(0.70, grz * 1.10),
            "erschliessung_typ": "u_foermig",
        },
    ]



def _analyze_site_for_masterplanning(site: dict[str, Any], access: list[dict], site_w: float, site_d: float, site_a: float) -> dict[str, Any]:
    """Analysiert Grundstückszuschnitt und Erschließung als Grundlage der Variantenbildung."""
    polygon = site.get("polygon") or [[0, 0], [site_w, 0], [site_w, site_d], [0, site_d]]
    xs = [float(p[0]) for p in polygon]
    ys = [float(p[1]) for p in polygon]
    bbox_w = max(xs) - min(xs) if xs else site_w
    bbox_d = max(ys) - min(ys) if ys else site_d
    bbox_area = max(1.0, bbox_w * bbox_d)
    compactness = max(0.0, min(1.0, site_a / bbox_area))
    long_axis = "x" if bbox_w >= bbox_d else "y"
    aspect = max(bbox_w, bbox_d) / max(1.0, min(bbox_w, bbox_d))
    primary_side = _primary_access_side(access, site_w, site_d)
    secondary_sides = sorted({ap.get("side", primary_side) for ap in access if ap.get("side") != primary_side})
    irregular = compactness < 0.86 or len(polygon) > 4
    return {
        "bbox": {"x": min(xs), "y": min(ys), "width_m": round(bbox_w, 2), "depth_m": round(bbox_d, 2)},
        "compactness": round(compactness, 3),
        "aspect_ratio": round(aspect, 3),
        "long_axis": long_axis,
        "primary_access_side": primary_side,
        "secondary_access_sides": secondary_sides,
        "is_irregular": irregular,
        "access_count": len(access),
    }


def _opposite_side(side: str) -> str:
    return {"south": "north", "north": "south", "west": "east", "east": "west"}.get(side, "north")


def _rect_dict(name: str, x: float, y: float, w: float, d: float, typ: str, farbe: str) -> dict[str, Any]:
    return {
        "name": name,
        "x": round(x, 2),
        "y": round(y, 2),
        "breite_m": round(max(0.0, w), 2),
        "tiefe_m": round(max(0.0, d), 2),
        "flaeche_m2": round(max(0.0, w) * max(0.0, d), 1),
        "typ": typ,
        "farbe": farbe,
    }


def _buildable_rect(site_w: float, site_d: float, margin: float) -> dict[str, float]:
    return {"x": margin, "y": margin, "w": max(1.0, site_w - 2 * margin), "d": max(1.0, site_d - 2 * margin)}


def _polygon_from_site(site: dict[str, Any]):
    try:
        from shapely.geometry import Polygon
        poly = Polygon(site.get("polygon") or [])
        return poly if poly.is_valid and not poly.is_empty and poly.area > 1 else None
    except Exception:
        return None


def _rect_coverage(rect: dict[str, Any], polygon) -> float:
    if polygon is None:
        return 1.0
    try:
        from shapely.geometry import Polygon, box
        if rect.get("polygon"):
            coords = rect.get("polygon") or []
            r = Polygon(coords)
            if not r.is_valid or r.is_empty:
                return 0.0
        else:
            x = float(rect.get("x", 0)); y = float(rect.get("y", 0))
            w = float(rect.get("breite_m", rect.get("width_m", 0))); d = float(rect.get("tiefe_m", rect.get("depth_m", 0)))
            if w <= 0 or d <= 0:
                return 0.0
            r = box(x, y, x + w, y + d)
        return float(polygon.intersection(r).area / max(1.0, r.area))
    except Exception:
        return 1.0


def _largest_buildable_rect_for_site(site: dict[str, Any], margin: float) -> dict[str, Any] | None:
    poly = _polygon_from_site(site)
    if poly is None:
        return None
    try:
        from app.tools.site import _largest_axis_aligned_rect
        buildable = poly.buffer(-max(0.0, margin))
        if buildable.is_empty:
            buildable = poly
        largest = _largest_axis_aligned_rect(buildable, grid_m=3.0)
        if not largest:
            return None
        return _rect_dict(
            "Gebäudeparzelle Hauptgebäude",
            float(largest["x"]),
            float(largest["y"]),
            float(largest["width_m"]),
            float(largest["depth_m"]),
            "building_parcel_candidate",
            "#DDE7EF",
        )
    except Exception:
        return None


def _filter_rects_by_site(rects: list[dict[str, Any]], site: dict[str, Any], *, min_coverage: float = 0.72) -> list[dict[str, Any]]:
    poly = _polygon_from_site(site)
    if poly is None:
        return rects
    out = []
    for rect in rects:
        coverage = _rect_coverage(rect, poly)
        if coverage >= min_coverage:
            item = {**rect, "site_coverage": round(coverage, 3)}
            out.append(item)
    return out


def _sanitize_rect_to_site(rect: dict[str, Any], site: dict[str, Any], fallback: dict[str, Any] | None = None, *, min_coverage: float = 0.60) -> dict[str, Any]:
    poly = _polygon_from_site(site)
    if poly is None or _rect_coverage(rect, poly) >= min_coverage:
        return rect
    if fallback and _rect_coverage(fallback, poly) >= min_coverage:
        return {**rect, "x": fallback["x"], "y": fallback["y"], "breite_m": fallback["breite_m"], "tiefe_m": min(float(rect.get("tiefe_m", fallback["tiefe_m"])), float(fallback["tiefe_m"])), "flaeche_m2": round(float(fallback["breite_m"]) * min(float(rect.get("tiefe_m", fallback["tiefe_m"])), float(fallback["tiefe_m"])), 1), "site_coverage": _rect_coverage(fallback, poly)}
    return rect



def _poly_to_coords(geom) -> list[list[float]]:
    try:
        if geom.is_empty:
            return []
        if geom.geom_type == "MultiPolygon":
            geom = max(list(geom.geoms), key=lambda g: g.area)
        return [[round(float(x), 2), round(float(y), 2)] for x, y in list(geom.exterior.coords)[:-1]]
    except Exception:
        return []


def _zone_from_geom(name: str, geom, typ: str, farbe: str) -> dict[str, Any]:
    minx, miny, maxx, maxy = geom.bounds
    return {
        "name": name,
        "x": round(float(minx), 2),
        "y": round(float(miny), 2),
        "breite_m": round(float(maxx - minx), 2),
        "tiefe_m": round(float(maxy - miny), 2),
        "flaeche_m2": round(float(geom.area), 1),
        "typ": typ,
        "farbe": farbe,
        "polygon": _poly_to_coords(geom),
        "geometry_mode": "polygon_intersection",
    }


def _side_strip_polygon(poly, side: str, depth: float):
    from shapely.geometry import box
    minx, miny, maxx, maxy = poly.bounds
    if side == "south":
        strip = box(minx, miny, maxx, miny + depth)
    elif side == "north":
        strip = box(minx, maxy - depth, maxx, maxy)
    elif side == "west":
        strip = box(minx, miny, minx + depth, maxy)
    else:
        strip = box(maxx - depth, miny, maxx, maxy)
    return poly.intersection(strip)


def _line_to_coords(line) -> list[list[float]]:
    try:
        return [[round(float(x), 2), round(float(y), 2)] for x, y in list(line.coords)]
    except Exception:
        return []


def _fallback_access_point(poly, side: str) -> list[float]:
    minx, miny, maxx, maxy = poly.bounds
    if side == "north":
        return [round((minx + maxx) / 2, 2), round(maxy, 2)]
    if side == "west":
        return [round(minx, 2), round((miny + maxy) / 2, 2)]
    if side == "east":
        return [round(maxx, 2), round((miny + maxy) / 2, 2)]
    return [round((minx + maxx) / 2, 2), round(miny, 2)]


def _site_geometry_metrics(site: dict[str, Any], poly, analysis: dict[str, Any]) -> dict[str, Any]:
    try:
        minx, miny, maxx, maxy = poly.bounds
        hull = poly.convex_hull
        frontage = 0.0
        for ap in site.get("access_points") or []:
            frontage += 8.0
        if frontage <= 0:
            frontage = min(maxx - minx, maxy - miny) * 0.22
        return {
            **analysis,
            "area_m2_exact": round(float(poly.area), 1),
            "perimeter_m": round(float(poly.length), 1),
            "convex_hull_area_m2": round(float(hull.area), 1),
            "concavity_pct": round(max(0.0, 1.0 - float(poly.area) / max(float(hull.area), 1.0)) * 100, 1),
            "frontage_m_estimated": round(frontage, 1),
            "topography": {
                "status": "not_available",
                "slope_mean_pct": None,
                "note": "Topographiedaten sind in dieser Demo noch nicht angebunden; Kennfeld fuer spaetere DGM/DEM-Auswertung.",
            },
        }
    except Exception:
        return {**analysis, "topography": {"status": "not_available"}}


def _build_legal_layer(site: dict[str, Any], poly, analysis: dict[str, Any]) -> dict[str, Any]:
    planning = site.get("planning") or {}
    max_height = float(planning.get("max_gebaeudehoehe_m", 12.0) or 12.0)
    abstandsfaktor = float(planning.get("abstandsfaktor", 0.4) or 0.4)
    setback = max(ABSTANDSFLAECHE_M, max_height * abstandsfaktor)
    buildable = poly.buffer(-setback)
    if buildable.is_empty or buildable.area < poly.area * 0.10:
        setback = ABSTANDSFLAECHE_M
        buildable = poly.buffer(-setback)
    if buildable.is_empty:
        buildable = poly
        setback = 0.0
    baugrenze = _zone_from_geom("Baugrenze", buildable, "baugrenze", "#DDE7EF")
    access_side = analysis.get("primary_access_side", "south")
    access_line_geom = _side_strip_polygon(poly, access_side, max(1.0, setback)).boundary
    return {
        "setback_m": round(setback, 2),
        "buildable_geom": buildable,
        "baugrenze": baugrenze,
        "baulinien": [{"name": "Baulinie / Erschliessungsseite", "side": access_side, "polygon": _poly_to_coords(_side_strip_polygon(poly, access_side, max(1.5, setback * 0.35))), "typ": "baulinie"}],
        "height_zones": [{**baugrenze, "name": f"Gebaeudehoehe max. {max_height:.1f} m", "max_gebaeudehoehe_m": max_height, "typ": "hoehenzone"}],
    }


def _traffic_profile_params(profile: str | None) -> dict[str, Any]:
    key = (profile or "logistik").lower()
    return {
        "anlieferung": {"key": "anlieferung", "base_width_m": 10.0, "pkw_buffer_factor": 0.40, "ring_bias": -8},
        "produktion": {"key": "produktion", "base_width_m": 11.0, "pkw_buffer_factor": 0.42, "ring_bias": -4},
        "logistik": {"key": "logistik", "base_width_m": 13.0, "pkw_buffer_factor": 0.45, "ring_bias": 4},
        "datacenter": {"key": "datacenter", "base_width_m": 12.0, "pkw_buffer_factor": 0.38, "ring_bias": 10},
    }.get(key, {"key": key, "base_width_m": 12.0, "pkw_buffer_factor": 0.42, "ring_bias": 0})


def _traffic_road_width(poly, profile: str | None) -> float:
    minx, miny, maxx, maxy = poly.bounds
    min_dim = max(1.0, min(maxx - minx, maxy - miny))
    area_ref = max(1.0, float(poly.area))
    params = _traffic_profile_params(profile)
    return max(7.0, min(float(params["base_width_m"]), min_dim * 0.16, math.sqrt(area_ref) * 0.12))


def _traffic_decision_preferences(poly, access: list[dict], analysis: dict[str, Any], requested: str, profile: str | None) -> tuple[list[str], list[str]]:
    area = float(poly.area)
    aspect = float(analysis.get("aspect_ratio") or 1.0)
    access_count = len(access or [])
    compactness = float(analysis.get("compactness") or 1.0)
    profile_key = _traffic_profile_params(profile)["key"]
    reasons: list[str] = []

    if area < 12_000:
        size_class = "small"
        reasons.append("Grundstück < 1,2 ha: vollständige Ringerschließung nur bei zwingendem Bedarf.")
    elif area < 30_000:
        size_class = "medium"
        reasons.append("Mittleres Grundstück: Spange oder Spine vor Ring prüfen.")
    else:
        size_class = "large"
        reasons.append("Großes Areal: Ring-/U-Strukturen können sinnvoll sein.")

    if aspect >= 2.0:
        reasons.append("Langgezogenes Grundstück: Längs-Spine ist Kandidat.")
    if compactness < 0.86:
        reasons.append("Unregelmäßiger Zuschnitt: einfache orthogonale Führung bevorzugen.")
    if access_count >= 2:
        reasons.append("Mehrere Zufahrten: Durchfahrt/Spange prüfen.")
    else:
        reasons.append("Eine Zufahrt: Stichhof oder Frontspange bevorzugen.")

    if profile_key == "datacenter":
        if size_class == "large":
            prefs = ["perimeter_ring", "u_loop", "frontspange", "laengs_spine", "stichhof"]
            reasons.append("Datacenter: redundante Umfahrung als Option priorisiert.")
        else:
            prefs = ["frontspange", "stichhof", "u_loop", "laengs_spine", "perimeter_ring"]
            reasons.append("Kleines Datacenter-Grundstück: Service-Spange vor Vollring.")
    elif profile_key == "logistik":
        if size_class == "small":
            prefs = ["frontspange", "stichhof", "laengs_spine", "u_loop", "perimeter_ring"] if access_count >= 2 else ["stichhof", "frontspange", "laengs_spine", "u_loop", "perimeter_ring"]
        elif aspect >= 2.0:
            prefs = ["laengs_spine", "frontspange", "u_loop", "stichhof", "perimeter_ring"]
        else:
            prefs = ["frontspange", "laengs_spine", "u_loop", "stichhof", "perimeter_ring"]
        reasons.append("Logistik: kurze, klare LKW-Führung mit möglichst wenig Flächenverbrauch.")
    else:
        if size_class == "large" and access_count >= 2:
            prefs = ["frontspange", "u_loop", "laengs_spine", "stichhof", "perimeter_ring"]
        elif aspect >= 2.0:
            prefs = ["laengs_spine", "frontspange", "stichhof", "u_loop", "perimeter_ring"]
        else:
            prefs = ["stichhof", "frontspange", "laengs_spine", "u_loop", "perimeter_ring"]
        reasons.append("Produktion/Anlieferung: geringe Verkehrsfläche und klare Andienung bevorzugt.")

    requested_map = {"gerade": "stichhof", "l_foermig": "frontspange", "u_foermig": "u_loop", "ring": "perimeter_ring"}
    requested_strategy = requested_map.get(requested)
    if requested_strategy and requested_strategy in prefs:
        # Wunsch berücksichtigen, aber nur um eine Stufe nach vorne ziehen.
        idx = prefs.index(requested_strategy)
        if idx > 0 and not (size_class == "small" and requested_strategy in {"u_loop", "perimeter_ring"}):
            prefs.pop(idx)
            prefs.insert(max(0, idx - 1), requested_strategy)
            reasons.append(f"Nutzerwunsch {requested}: als Strategie-Kandidat höher gewichtet.")
        elif size_class == "small" and requested_strategy in {"u_loop", "perimeter_ring"}:
            reasons.append(f"Nutzerwunsch {requested} wird wegen kleiner Fläche nicht hart erzwungen.")
    return prefs, reasons


def _traffic_access_points(poly, access: list[dict], side: str) -> list[list[float]]:
    pts: list[list[float]] = []
    for ap in access or []:
        pt = ap.get("point") or []
        if len(pt) >= 2:
            pts.append([float(pt[0]), float(pt[1])])
    return pts or [_fallback_access_point(poly, side)]


def _geom_center(geom) -> list[float]:
    c = geom.centroid
    return [round(float(c.x), 2), round(float(c.y), 2)]


def _largest_polygon_part(geom):
    try:
        if geom.geom_type == "MultiPolygon":
            parts = [g for g in geom.geoms if not g.is_empty]
            return max(parts, key=lambda g: g.area) if parts else geom
    except Exception:
        pass
    return geom


def _box_zone(poly, cx: float, cy: float, w: float, d: float, name: str, typ: str, color: str, clip_geom=None) -> tuple[dict[str, Any] | None, Any | None]:
    from shapely.geometry import box
    geom = box(cx - w / 2, cy - d / 2, cx + w / 2, cy + d / 2)
    geom = geom.intersection(clip_geom or poly)
    geom = _largest_polygon_part(geom)
    if geom.is_empty or geom.area < 12:
        return None, None
    return _zone_from_geom(name, geom, typ, color), geom


def _orthogonal_lines(start: list[float], end: list[float], *, primary_side: str):
    from shapely.geometry import LineString
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    if abs(sx - ex) < 0.5 or abs(sy - ey) < 0.5:
        return [LineString([(sx, sy), (ex, ey)])]
    if primary_side in ("south", "north"):
        bend = (sx, ey)
    else:
        bend = (ex, sy)
    return [LineString([(sx, sy), bend]), LineString([bend, (ex, ey)])]


def _build_functional_target_zones(poly, legal_layer: dict[str, Any], access: list[dict], analysis: dict[str, Any], profile: str | None, road_width: float, requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive target zones before roads are generated.

    This makes traffic planning a network problem: roads connect access points,
    service yards, parking and infrastructure nodes instead of occupying a strip
    first and forcing parcels into the leftover area.
    """
    buildable = legal_layer.get("buildable_geom") or poly
    minx, miny, maxx, maxy = poly.bounds
    bminx, bminy, bmaxx, bmaxy = buildable.bounds
    width, depth = maxx - minx, maxy - miny
    min_dim = max(1.0, min(width, depth))
    side = str(analysis.get("primary_access_side") or "south")
    profile_key = _traffic_profile_params(profile)["key"]
    requirements = requirements or {}
    lkw_movements = max(0, int(requirements.get("lkw_movements_per_day") or 40))
    employee_count = max(0, int(requirements.get("employee_count") or 120))
    visitor_count = max(0, int(requirements.get("visitor_count") or 20))
    access_pts = _traffic_access_points(poly, access, side)
    primary_access = access_pts[0]
    avg_x = sum(pt[0] for pt in access_pts) / max(1, len(access_pts))
    avg_y = sum(pt[1] for pt in access_pts) / max(1, len(access_pts))

    lkw_factor = max(0.75, min(1.65, lkw_movements / 60.0))
    pkw_factor = max(0.70, min(1.80, (employee_count * 0.55 + visitor_count * 0.8) / 95.0))
    service_scale = max(0.65, min(1.65, float(requirements.get("service_scale_factor") or 1.0)))
    parking_scale = max(0.65, min(1.65, float(requirements.get("parking_scale_factor") or 1.0)))
    service_axis_bias = max(-0.5, min(0.5, float(requirements.get("service_axis_bias") or 0.0)))
    parking_axis_bias = max(-0.5, min(0.5, float(requirements.get("parking_axis_bias") or 0.0)))
    service_depth = max(14.0, min(34.0, min_dim * (0.22 if profile_key in {"logistik", "datacenter"} else 0.18) * min(1.25, lkw_factor) * service_scale))
    service_len = max(28.0, min(max(width, depth) * 0.62, math.sqrt(float(poly.area)) * (0.62 if profile_key == "logistik" else 0.48) * lkw_factor * service_scale))
    pkw_depth = max(8.0, min(18.0, road_width * 0.9 * min(1.2, pkw_factor) * parking_scale))
    pkw_len = max(24.0, min(max(width, depth) * 0.42, math.sqrt(float(poly.area)) * 0.34 * pkw_factor * parking_scale))

    if side in ("south", "north"):
        service_y = bminy + service_depth / 2 if side == "south" else bmaxy - service_depth / 2
        service_span = max(0.0, (bmaxx - bminx) - service_len)
        service_x_target = avg_x + service_axis_bias * service_span
        service_x = max(bminx + service_len / 2, min(bmaxx - service_len / 2, service_x_target))
        pkw_y = miny + pkw_depth / 2 if side == "south" else maxy - pkw_depth / 2
        parking_span = max(0.0, (maxx - minx) - pkw_len)
        pkw_x_target = avg_x + parking_axis_bias * parking_span
        pkw_x = max(minx + pkw_len / 2, min(maxx - pkw_len / 2, pkw_x_target))
        sec_w, sec_d = max(8.0, road_width * 1.1), max(8.0, road_width * 1.1)
    else:
        service_x = bminx + service_depth / 2 if side == "west" else bmaxx - service_depth / 2
        service_span = max(0.0, (bmaxy - bminy) - service_len)
        service_y_target = avg_y + service_axis_bias * service_span
        service_y = max(bminy + service_len / 2, min(bmaxy - service_len / 2, service_y_target))
        pkw_x = minx + pkw_depth / 2 if side == "west" else maxx - pkw_depth / 2
        parking_span = max(0.0, (maxy - miny) - pkw_len)
        pkw_y_target = avg_y + parking_axis_bias * parking_span
        pkw_y = max(miny + pkw_len / 2, min(maxy - pkw_len / 2, pkw_y_target))
        sec_w, sec_d = max(8.0, road_width * 1.1), max(8.0, road_width * 1.1)

    zones: list[dict[str, Any]] = []
    geoms: dict[str, Any] = {}
    service_zone, service_geom = _box_zone(poly, service_x, service_y, service_len if side in ("south", "north") else service_depth, service_depth if side in ("south", "north") else service_len, "Andienhof / LKW-Zielzone", "zielzone_andienung", "#E8D3AE", buildable)
    if service_zone:
        zones.append(service_zone); geoms["service_yard"] = service_geom
    pkw_zone, pkw_geom = _box_zone(poly, pkw_x, pkw_y, pkw_len if side in ("south", "north") else pkw_depth, pkw_depth if side in ("south", "north") else pkw_len, "PKW / Besucher-Zielzone", "zielzone_pkw", "#F5F0DC", poly)
    if pkw_zone:
        zones.append(pkw_zone); geoms["parking"] = pkw_geom
    security_zone, security_geom = _box_zone(poly, float(primary_access[0]), float(primary_access[1]), sec_w, sec_d, "Pforte / Einfahrtskontrolle", "zielzone_sicherheit", "#BFD7EA", poly.buffer(2.0))
    if security_zone:
        zones.append(security_zone); geoms["security"] = security_geom

    service_point = _geom_center(service_geom) if service_geom is not None else _geom_center(buildable)
    pkw_point = _geom_center(pkw_geom) if pkw_geom is not None else service_point
    buildable_point = _geom_center(buildable)
    opp = _opposite_side(side)
    infra_point = _fallback_access_point(poly, opp)
    # Pull infrastructure node slightly inside the parcel so the road graph can connect to it.
    if opp == "north":
        infra_point[1] = max(miny, infra_point[1] - road_width * 1.5)
    elif opp == "south":
        infra_point[1] = min(maxy, infra_point[1] + road_width * 1.5)
    elif opp == "east":
        infra_point[0] = max(minx, infra_point[0] - road_width * 1.5)
    else:
        infra_point[0] = min(maxx, infra_point[0] + road_width * 1.5)

    nodes: list[dict[str, Any]] = []
    for idx, pt in enumerate(access_pts, start=1):
        nodes.append({"id": f"Z{idx}", "name": "Zufahrt", "point": [round(pt[0], 2), round(pt[1], 2)], "typ": "access"})
    nodes.extend([
        {"id": "AH1", "name": "Andienhof / LKW", "point": service_point, "typ": "service_yard"},
        {"id": "PKW1", "name": "PKW / Besucher", "point": pkw_point, "typ": "parking"},
        {"id": "BF1", "name": "Baufeld-Zentrum", "point": buildable_point, "typ": "buildable_core"},
        {"id": "MS1", "name": "MS-Trafo / Medien", "point": [round(float(infra_point[0]), 2), round(float(infra_point[1]), 2)], "typ": "infra_node"},
    ])
    return {"zones": zones, "geoms": geoms, "nodes": nodes, "access_points": access_pts, "service_point": service_point, "parking_point": pkw_point, "buildable_point": buildable_point, "infra_point": infra_point}


def _traffic_graph_lines(strategy: str, poly, buildable, analysis: dict[str, Any], target_zones: dict[str, Any], road_width: float):
    from shapely.geometry import LineString
    minx, miny, maxx, maxy = poly.bounds
    bminx, bminy, bmaxx, bmaxy = buildable.bounds
    side = str(analysis.get("primary_access_side") or "south")
    long_axis = str(analysis.get("long_axis") or "x")
    access_pts = target_zones.get("access_points") or [_fallback_access_point(poly, side)]
    primary = access_pts[0]
    service = target_zones.get("service_point") or _geom_center(buildable)
    parking = target_zones.get("parking_point") or service
    infra = target_zones.get("infra_point") or service
    center = target_zones.get("buildable_point") or service
    lines = []

    def add_many(items):
        for ln in items:
            if ln.length > road_width * 0.65:
                lines.append(ln)

    def add_line(points):
        ln = LineString([(float(x), float(y)) for x, y in points])
        if ln.length > road_width * 0.65:
            lines.append(ln)

    if strategy == "stichhof":
        add_many(_orthogonal_lines(primary, service, primary_side=side))
        add_many(_orthogonal_lines(service, parking, primary_side=side))
    elif strategy == "frontspange":
        if side in ("south", "north"):
            y = service[1]
            xs = [pt[0] for pt in access_pts] + [service[0], parking[0]]
            x0 = max(bminx, min(xs) - road_width * 2.5)
            x1 = min(bmaxx, max(xs) + road_width * 2.5)
            if x1 - x0 < max(36.0, road_width * 5):
                mid = (x0 + x1) / 2
                half = min((bmaxx - bminx) / 2, max(24.0, road_width * 4))
                x0, x1 = max(bminx, mid - half), min(bmaxx, mid + half)
            add_line([(x0, y), (x1, y)])
            for pt in access_pts:
                add_many(_orthogonal_lines(pt, [max(x0, min(x1, pt[0])), y], primary_side=side))
        else:
            x = service[0]
            ys = [pt[1] for pt in access_pts] + [service[1], parking[1]]
            y0 = max(bminy, min(ys) - road_width * 2.5)
            y1 = min(bmaxy, max(ys) + road_width * 2.5)
            if y1 - y0 < max(36.0, road_width * 5):
                mid = (y0 + y1) / 2
                half = min((bmaxy - bminy) / 2, max(24.0, road_width * 4))
                y0, y1 = max(bminy, mid - half), min(bmaxy, mid + half)
            add_line([(x, y0), (x, y1)])
            for pt in access_pts:
                add_many(_orthogonal_lines(pt, [x, max(y0, min(y1, pt[1]))], primary_side=side))
    elif strategy == "laengs_spine":
        if long_axis == "x":
            y = center[1]
            add_line([(bminx, y), (bmaxx, y)])
            spine_targets = [[service[0], y], [parking[0], y], [infra[0], y]]
        else:
            x = center[0]
            add_line([(x, bminy), (x, bmaxy)])
            spine_targets = [[x, service[1]], [x, parking[1]], [x, infra[1]]]
        for pt in access_pts:
            target = spine_targets[0]
            add_many(_orthogonal_lines(pt, target, primary_side=side))
        add_many(_orthogonal_lines(service, spine_targets[0], primary_side=side))
        add_many(_orthogonal_lines(parking, spine_targets[1], primary_side=side))
    elif strategy == "u_loop":
        front = _traffic_graph_lines("frontspange", poly, buildable, analysis, target_zones, road_width)
        lines.extend(front)
        if side in ("south", "north"):
            y_back = bmaxy - road_width if side == "south" else bminy + road_width
            x0 = min(pt[0] for pt in access_pts + [service, infra])
            x1 = max(pt[0] for pt in access_pts + [service, infra])
            x0, x1 = max(bminx, x0 - road_width * 2), min(bmaxx, x1 + road_width * 2)
            x_conn = x1 if service[0] < (bminx + bmaxx) / 2 else x0
            add_line([(x0, y_back), (x1, y_back)])
            add_line([(x_conn, service[1]), (x_conn, y_back)])
        else:
            x_back = bmaxx - road_width if side == "west" else bminx + road_width
            y0 = min(pt[1] for pt in access_pts + [service, infra])
            y1 = max(pt[1] for pt in access_pts + [service, infra])
            y0, y1 = max(bminy, y0 - road_width * 2), min(bmaxy, y1 + road_width * 2)
            y_conn = y1 if service[1] < (bminy + bmaxy) / 2 else y0
            add_line([(x_back, y0), (x_back, y1)])
            add_line([(service[0], y_conn), (x_back, y_conn)])
    elif strategy == "perimeter_ring":
        ring = buildable.buffer(-road_width * 0.65)
        if ring.is_empty:
            ring = buildable
        coords = list(ring.exterior.coords)
        for i in range(len(coords) - 1):
            add_line([coords[i], coords[i + 1]])
        for pt in access_pts:
            add_many(_orthogonal_lines(pt, service, primary_side=side))
    return lines


def _traffic_fitness_weights(requirements: dict[str, Any] | None) -> dict[str, float]:
    raw = (requirements or {}).get("traffic_fitness_weights") or {}

    def _weight(name: str, default: float = 1.0) -> float:
        value = raw.get(name, (requirements or {}).get(f"fitness_{name}_weight", default))
        try:
            return max(0.0, min(2.5, float(value)))
        except Exception:
            return default

    return {
        "strategy": _weight("strategy", 1.0),
        "connectivity": _weight("connectivity", 1.0),
        "road_efficiency": _weight("road_efficiency", 1.0),
        "rectangularity": _weight("rectangularity", 1.0),
        "parcel_split": _weight("parcel_split", 1.0),
    }


def _score_traffic_graph_candidate(strategy: str, road_geom, parking_geom, buildable, poly, prefs: list[str], profile: str | None, target_zones: dict[str, Any], road_width: float, weights: dict[str, float] | None = None) -> dict[str, Any]:
    residual = buildable.difference(road_geom.buffer(1.5))
    if parking_geom is not None and not parking_geom.is_empty:
        residual = residual.difference(parking_geom.buffer(0.75))
    road_pct = float(road_geom.area) / max(float(poly.area), 1.0)
    params = _traffic_profile_params(profile)
    preference_bonus = max(0, 24 - (prefs.index(strategy) * 5 if strategy in prefs else 24))
    ring_bonus = float(params.get("ring_bias", 0)) if strategy in {"u_loop", "perimeter_ring"} else 0.0
    target_points = [n["point"] for n in target_zones.get("nodes", []) if n.get("typ") in {"access", "service_yard", "parking", "infra_node"}]
    connected = 0
    for pt in target_points:
        try:
            from shapely.geometry import Point
            if road_geom.distance(Point(float(pt[0]), float(pt[1]))) <= road_width * 0.8:
                connected += 1
        except Exception:
            pass
    connectivity = connected / max(1, len(target_points))
    try:
        components = len(list(residual.geoms)) if residual.geom_type == "MultiPolygon" else (0 if residual.is_empty else 1)
    except Exception:
        components = 1
    largest_rect_ratio = 0.0
    try:
        from app.tools.site import _largest_axis_aligned_rect
        largest = _largest_axis_aligned_rect(residual, grid_m=4.0)
        largest_rect_ratio = float((largest or {}).get("area_m2") or 0) / max(float(poly.area), 1.0)
    except Exception:
        largest_rect_ratio = 0.0
    weights = weights or _traffic_fitness_weights(None)
    # Calibrated score: keep values away from constant 100.0 saturation so
    # users can compare close alternatives in the interactive viewer.
    strategy_term = min(14.0, (preference_bonus + ring_bonus) * 0.55) * weights.get("strategy", 1.0)
    connectivity_term = connectivity * 18.0 * weights.get("connectivity", 1.0)
    connectivity_penalty = max(0.0, 0.8 - connectivity) * 18.0 * weights.get("connectivity", 1.0)
    rectangularity_term = min(16.0, largest_rect_ratio * 32.0) * weights.get("rectangularity", 1.0)
    parcel_split_term = min(7.0, max(0, components - 1) * 2.0) * weights.get("parcel_split", 1.0)
    road_penalty_raw = road_pct * 105.0 + max(0.0, road_pct - 0.12) * 130.0
    if strategy in {"u_loop", "perimeter_ring"} and poly.area < 30_000:
        road_penalty_raw += 14.0
    road_penalty = road_penalty_raw * weights.get("road_efficiency", 1.0)
    raw_score = 42.0 + strategy_term + connectivity_term + rectangularity_term + parcel_split_term - road_penalty - connectivity_penalty
    score = max(0.0, min(100.0, raw_score))
    return {
        "score": round(score, 1),
        "raw_score": round(raw_score, 2),
        "road_area_pct": round(road_pct, 3),
        "connectivity": round(connectivity, 3),
        "residual_components": components,
        "largest_rect_ratio": round(largest_rect_ratio, 3),
        "fitness_weights": {k: round(float(v), 2) for k, v in weights.items()},
        "fitness_terms": {
            "strategy": round(strategy_term, 2),
            "connectivity": round(connectivity_term, 2),
            "connectivity_penalty": round(connectivity_penalty, 2),
            "road_efficiency_penalty": round(road_penalty, 2),
            "rectangularity": round(rectangularity_term, 2),
            "parcel_split": round(parcel_split_term, 2),
        },
    }


def _traffic_candidate_lines(strategy: str, poly, analysis: dict[str, Any], access_pts: list[list[float]], road_width: float):
    from shapely.geometry import LineString
    minx, miny, maxx, maxy = poly.bounds
    side = analysis.get("primary_access_side", "south")
    long_axis = analysis.get("long_axis", "x")
    width = maxx - minx
    depth = maxy - miny
    min_dim = max(1.0, min(width, depth))
    front_offset = max(road_width * 1.25, min_dim * 0.10)
    lines = []

    def add(line):
        if line.length > road_width * 0.75:
            lines.append(line)

    if side in ("south", "north"):
        y_front = miny + front_offset if side == "south" else maxy - front_offset
        y_front = max(miny + road_width * 0.65, min(maxy - road_width * 0.65, y_front))
        avg_x = sum(pt[0] for pt in access_pts) / max(1, len(access_pts))
        if strategy == "stichhof":
            half = min(width * 0.32, max(24.0, width * 0.18))
            x0, x1 = max(minx + road_width * 0.6, avg_x - half), min(maxx - road_width * 0.6, avg_x + half)
            add(LineString([(x0, y_front), (x1, y_front)]))
        elif strategy in ("frontspange", "u_loop"):
            add(LineString([(minx + road_width * 0.6, y_front), (maxx - road_width * 0.6, y_front)]))
        elif strategy == "laengs_spine":
            y_spine = (miny + maxy) / 2 if long_axis == "x" else y_front
            add(LineString([(minx + road_width * 0.6, y_spine), (maxx - road_width * 0.6, y_spine)]))
            y_front = y_spine
        elif strategy == "perimeter_ring":
            y_back = maxy - front_offset if side == "south" else miny + front_offset
            x0, x1 = minx + road_width * 0.8, maxx - road_width * 0.8
            add(LineString([(x0, y_front), (x1, y_front)]))
            add(LineString([(x0, y_back), (x1, y_back)]))
            add(LineString([(x0, y_front), (x0, y_back)]))
            add(LineString([(x1, y_front), (x1, y_back)]))
        for pt in access_pts:
            add(LineString([(pt[0], pt[1]), (pt[0], y_front)]))
        if strategy == "u_loop":
            y_back = maxy - front_offset if side == "south" else miny + front_offset
            y_back = max(miny + road_width * 0.65, min(maxy - road_width * 0.65, y_back))
            x_conn = maxx - road_width * 1.2 if (avg_x < (minx + maxx) / 2) else minx + road_width * 1.2
            add(LineString([(minx + road_width * 0.6, y_back), (maxx - road_width * 0.6, y_back)]))
            add(LineString([(x_conn, y_front), (x_conn, y_back)]))
    else:
        x_front = minx + front_offset if side == "west" else maxx - front_offset
        x_front = max(minx + road_width * 0.65, min(maxx - road_width * 0.65, x_front))
        avg_y = sum(pt[1] for pt in access_pts) / max(1, len(access_pts))
        if strategy == "stichhof":
            half = min(depth * 0.32, max(24.0, depth * 0.18))
            y0, y1 = max(miny + road_width * 0.6, avg_y - half), min(maxy - road_width * 0.6, avg_y + half)
            add(LineString([(x_front, y0), (x_front, y1)]))
        elif strategy in ("frontspange", "u_loop"):
            add(LineString([(x_front, miny + road_width * 0.6), (x_front, maxy - road_width * 0.6)]))
        elif strategy == "laengs_spine":
            x_spine = (minx + maxx) / 2 if long_axis == "y" else x_front
            add(LineString([(x_spine, miny + road_width * 0.6), (x_spine, maxy - road_width * 0.6)]))
            x_front = x_spine
        elif strategy == "perimeter_ring":
            x_back = maxx - front_offset if side == "west" else minx + front_offset
            y0, y1 = miny + road_width * 0.8, maxy - road_width * 0.8
            add(LineString([(x_front, y0), (x_front, y1)]))
            add(LineString([(x_back, y0), (x_back, y1)]))
            add(LineString([(x_front, y0), (x_back, y0)]))
            add(LineString([(x_front, y1), (x_back, y1)]))
        for pt in access_pts:
            add(LineString([(pt[0], pt[1]), (x_front, pt[1])]))
        if strategy == "u_loop":
            x_back = maxx - front_offset if side == "west" else minx + front_offset
            x_back = max(minx + road_width * 0.65, min(maxx - road_width * 0.65, x_back))
            y_conn = maxy - road_width * 1.2 if (avg_y < (miny + maxy) / 2) else miny + road_width * 1.2
            add(LineString([(x_back, miny + road_width * 0.6), (x_back, maxy - road_width * 0.6)]))
            add(LineString([(x_front, y_conn), (x_back, y_conn)]))
    return lines


def _score_traffic_candidate(strategy: str, road_geom, parking_geom, buildable, poly, prefs: list[str], profile: str | None) -> dict[str, Any]:
    residual = buildable.difference(road_geom.buffer(1.5))
    if parking_geom is not None and not parking_geom.is_empty:
        residual = residual.difference(parking_geom.buffer(0.75))
    road_pct = float(road_geom.area) / max(float(poly.area), 1.0)
    preference_bonus = max(0, 18 - (prefs.index(strategy) * 5 if strategy in prefs else 18))
    params = _traffic_profile_params(profile)
    ring_bonus = float(params.get("ring_bias", 0)) if strategy in {"u_loop", "perimeter_ring"} else 0.0
    compact_penalty = max(0.0, road_pct - 0.18) * 120.0
    try:
        components = len(list(residual.geoms)) if residual.geom_type == "MultiPolygon" else (0 if residual.is_empty else 1)
    except Exception:
        components = 1
    component_bonus = min(10.0, max(0, components - 1) * 4.0)
    largest_rect_ratio = 0.0
    try:
        from app.tools.site import _largest_axis_aligned_rect
        largest = _largest_axis_aligned_rect(residual, grid_m=4.0)
        largest_rect_ratio = float((largest or {}).get("area_m2") or 0) / max(float(poly.area), 1.0)
    except Exception:
        largest_rect_ratio = 0.0
    score = 55.0 + preference_bonus + ring_bonus + component_bonus + min(18.0, largest_rect_ratio * 80.0) - road_pct * 95.0 - compact_penalty
    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "road_area_pct": round(road_pct, 3),
        "residual_components": components,
        "largest_rect_ratio": round(largest_rect_ratio, 3),
    }


def _traffic_optimizer_chromosomes(strategies: list[str], requirements: dict[str, Any], profile_key: str, poly_area: float) -> list[dict[str, Any]]:
    """Create a compact deterministic population for transparent optimization.

    The population is intentionally small enough for Streamlit previews, but it
    varies the decisions users normally adjust manually: road topology, service
    yard position, parking position and target-zone scale.
    """
    high_logistics = int(requirements.get("lkw_movements_per_day") or 40) >= 80 or profile_key in {"logistik", "datacenter"}
    many_cars = (int(requirements.get("employee_count") or 120) + int(requirements.get("visitor_count") or 20)) >= 220
    compact_site = float(poly_area or 0) < 18000
    base_service_scale = 1.15 if high_logistics else 1.0
    base_parking_scale = 1.15 if many_cars else 1.0
    if compact_site:
        base_service_scale = min(base_service_scale, 1.0)
        base_parking_scale = min(base_parking_scale, 1.0)

    templates = [
        {"service_axis_bias": 0.0, "parking_axis_bias": 0.0, "service_scale_factor": base_service_scale, "parking_scale_factor": base_parking_scale},
        {"service_axis_bias": -0.35, "parking_axis_bias": 0.35, "service_scale_factor": base_service_scale, "parking_scale_factor": base_parking_scale},
        {"service_axis_bias": 0.35, "parking_axis_bias": -0.35, "service_scale_factor": base_service_scale, "parking_scale_factor": base_parking_scale},
        {"service_axis_bias": -0.25, "parking_axis_bias": -0.25, "service_scale_factor": min(1.55, base_service_scale * 1.12), "parking_scale_factor": max(0.75, base_parking_scale * 0.9)},
        {"service_axis_bias": 0.25, "parking_axis_bias": 0.25, "service_scale_factor": max(0.75, base_service_scale * 0.9), "parking_scale_factor": min(1.55, base_parking_scale * 1.12)},
        {"service_axis_bias": -0.45, "parking_axis_bias": 0.0, "service_scale_factor": min(1.60, base_service_scale * 1.2), "parking_scale_factor": base_parking_scale},
        {"service_axis_bias": 0.45, "parking_axis_bias": 0.0, "service_scale_factor": min(1.60, base_service_scale * 1.2), "parking_scale_factor": base_parking_scale},
    ]
    if profile_key == "datacenter" or requirements.get("required_redundant_access"):
        templates.append({"service_axis_bias": 0.0, "parking_axis_bias": -0.45, "service_scale_factor": base_service_scale, "parking_scale_factor": max(0.75, base_parking_scale * 0.85)})
    if profile_key == "logistik":
        templates.append({"service_axis_bias": 0.0, "parking_axis_bias": 0.45, "service_scale_factor": min(1.65, base_service_scale * 1.25), "parking_scale_factor": max(0.75, base_parking_scale * 0.8)})

    population: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for strategy in strategies:
        for idx, template in enumerate(templates, start=1):
            chromosome = {
                "strategy_type": strategy,
                "generation": 1,
                "variant": idx,
                **template,
            }
            key = (
                chromosome["strategy_type"],
                round(float(chromosome["service_axis_bias"]), 2),
                round(float(chromosome["parking_axis_bias"]), 2),
                round(float(chromosome["service_scale_factor"]), 2),
                round(float(chromosome["parking_scale_factor"]), 2),
            )
            if key in seen:
                continue
            seen.add(key)
            population.append(chromosome)
    return population


def _build_traffic_layer(poly, legal_layer: dict[str, Any], access: list[dict], analysis: dict[str, Any], erschliessung_typ: str, profile: str | None = None, requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    from shapely.ops import unary_union

    profile_key = _traffic_profile_params(profile)["key"]
    road_width = _traffic_road_width(poly, profile_key)
    buildable = legal_layer.get("buildable_geom") or poly
    side = analysis.get("primary_access_side", "south")
    prefs, decision_reasons = _traffic_decision_preferences(poly, access, analysis, erschliessung_typ, profile_key)
    requirements = requirements or {}
    fitness_weights = _traffic_fitness_weights(requirements)
    if requirements.get("required_redundant_access"):
        for forced in ("perimeter_ring", "u_loop"):
            if forced in prefs:
                prefs.remove(forced)
        prefs = ["perimeter_ring", "u_loop"] + prefs
        decision_reasons.append("Redundante Erschließung gefordert: Ring-/U-Struktur wird priorisiert.")

    decision_reasons.append("Zielzonen werden vor der Straße gesetzt: Zufahrt, Andienhof, PKW, Infrastruktur und Baufeldkern.")
    decision_reasons.append("Optimierer erzeugt Varianten aus Strategie, Lage der Zielzonen und Größenfaktoren und bewertet diese über Flächenverbrauch, Konnektivität und rechteckige Restflächen.")
    decision_reasons.append(
        "Fitness-Gewichtung: "
        f"Strategie {fitness_weights['strategy']:.1f}, "
        f"Konnektivität {fitness_weights['connectivity']:.1f}, "
        f"Straßenfläche {fitness_weights['road_efficiency']:.1f}, "
        f"Rechteckigkeit {fitness_weights['rectangularity']:.1f}, "
        f"Teilbarkeit {fitness_weights['parcel_split']:.1f}."
    )

    strategies: list[str] = []
    for name in prefs + ["stichhof", "frontspange", "laengs_spine", "u_loop", "perimeter_ring"]:
        if name not in strategies:
            strategies.append(name)

    population = _traffic_optimizer_chromosomes(strategies, requirements, profile_key, float(poly.area))
    candidates: list[dict[str, Any]] = []
    for chromosome in population:
        strategy = str(chromosome.get("strategy_type") or "stichhof")
        local_requirements = {**requirements, **chromosome}
        target_zones = _build_functional_target_zones(poly, legal_layer, access, analysis, profile_key, road_width, local_requirements)
        parking_geom = target_zones.get("geoms", {}).get("parking")
        lines = _traffic_graph_lines(strategy, poly, buildable, analysis, target_zones, road_width)
        if not lines:
            continue
        road_line = unary_union(lines)
        road_geom = road_line.buffer(road_width / 2, cap_style=2, join_style=2).intersection(poly)
        if road_geom.is_empty or road_geom.area < road_width * 8:
            continue
        p_geom = parking_geom.difference(road_geom.buffer(0.5)).intersection(poly) if parking_geom is not None and not parking_geom.is_empty else None
        metrics = _score_traffic_graph_candidate(strategy, road_geom, p_geom, buildable, poly, prefs, profile_key, target_zones, road_width, fitness_weights)
        # Secondary fitness terms keep the selected option readable and usable.
        score = float(metrics["score"])
        if requirements.get("required_redundant_access") and strategy not in {"u_loop", "perimeter_ring"}:
            score -= 14.0
        if float(metrics.get("road_area_pct") or 0) > 0.28:
            score -= 8.0
        if float(metrics.get("connectivity") or 0) < 0.75:
            score -= 10.0
        score = round(max(0.0, min(100.0, score)), 1)
        metrics = {
            **metrics,
            "score": score,
            "redundancy_adjustment": -14.0 if requirements.get("required_redundant_access") and strategy not in {"u_loop", "perimeter_ring"} else 0.0,
        }
        candidates.append({
            "strategy_type": strategy,
            "score": score,
            "metrics": metrics,
            "chromosome": {
                "generation": int(chromosome.get("generation") or 1),
                "variant": int(chromosome.get("variant") or 1),
                "service_axis_bias": round(float(chromosome.get("service_axis_bias") or 0.0), 2),
                "parking_axis_bias": round(float(chromosome.get("parking_axis_bias") or 0.0), 2),
                "service_scale_factor": round(float(chromosome.get("service_scale_factor") or 1.0), 2),
                "parking_scale_factor": round(float(chromosome.get("parking_scale_factor") or 1.0), 2),
            },
            "road_line_points": [_line_to_coords(ln) for ln in lines],
            "road_zone": _zone_from_geom("Straßenkorridor / LKW-Erschließung", road_geom, "verkehr_lkw", "#D4A96A"),
            "parking_zone": _zone_from_geom("PKW / Besucher", p_geom, "verkehr_pkw", "#F5F0DC") if p_geom is not None and not p_geom.is_empty and p_geom.area > 30 else None,
            "functional_zones": target_zones.get("zones") or [],
            "target_zones": target_zones,
            "traffic_graph": {
                "nodes": target_zones.get("nodes") or [],
                "edges": [{"from": idx, "to": idx + 1, "strategy": strategy, "points": _line_to_coords(ln)} for idx, ln in enumerate(lines, start=1)],
            },
        })

    if not candidates:
        target_zones = _build_functional_target_zones(poly, legal_layer, access, analysis, profile_key, road_width, requirements)
        road_geom = _side_strip_polygon(poly, side, road_width)
        candidates.append({
            "strategy_type": "fallback_edge_strip",
            "score": 0.0,
            "metrics": {"score": 0.0, "road_area_pct": round(float(road_geom.area) / max(float(poly.area), 1.0), 3)},
            "chromosome": {"generation": 0, "variant": 0},
            "road_line_points": [],
            "road_zone": _zone_from_geom("Straßenkorridor / LKW-Erschließung", road_geom, "verkehr_lkw", "#D4A96A"),
            "parking_zone": None,
            "functional_zones": target_zones.get("zones") or [],
            "target_zones": target_zones,
            "traffic_graph": {"nodes": target_zones.get("nodes") or [], "edges": []},
        })

    ranked = sorted(candidates, key=lambda c: float(c.get("score") or 0), reverse=True)
    selected = ranked[0]
    target_zones = selected.get("target_zones") or {}

    infra_nodes = []
    for node in selected.get("traffic_graph", {}).get("nodes") or []:
        if node.get("typ") in {"access", "infra_node", "service_yard"}:
            infra_nodes.append(node)

    candidate_summaries = [
        {
            "strategy_type": c["strategy_type"],
            "score": c["score"],
            "metrics": c.get("metrics") or {},
            "chromosome": c.get("chromosome") or {},
        }
        for c in ranked
    ]
    return {
        "profile": profile_key,
        "road_width_m": round(road_width, 2),
        "strategy_type": selected["strategy_type"],
        "score": selected["score"],
        "optimization_mode": "evolutionary_candidate_search_v1",
        "optimization_population_size": len(population),
        "optimization_evaluated_candidates": len(candidates),
        "fitness_weights": {k: round(float(v), 2) for k, v in fitness_weights.items()},
        "selected_chromosome": selected.get("chromosome") or {},
        "decision_reasons": decision_reasons,
        "candidate_strategies": candidate_summaries,
        "road_line_points": selected.get("road_line_points") or [],
        "road_zone": selected["road_zone"],
        "parking_zone": selected.get("parking_zone"),
        "functional_zones": selected.get("functional_zones") or [],
        "traffic_graph": selected.get("traffic_graph") or {},
        "target_zone_summary": [
            {"name": z.get("name"), "typ": z.get("typ"), "flaeche_m2": z.get("flaeche_m2")}
            for z in selected.get("functional_zones") or []
        ],
        "infra_nodes": infra_nodes,
    }

def _rect_from_largest(largest: dict[str, Any], *, idx: int, typ: str = "building_parcel_candidate") -> dict[str, Any]:
    return _rect_dict(
        f"Parzelle {idx}",
        float(largest["x"]),
        float(largest["y"]),
        float(largest["width_m"]),
        float(largest["depth_m"]),
        typ,
        "#DDE7EF",
    ) | {"rect_score_area_m2": round(float(largest.get("area_m2") or 0), 1)}


def _parcelize_residual_buildable(residual, site: dict[str, Any], count: int, *, gap_m: float = 8.0, grid_m: float = 3.0) -> list[dict[str, Any]]:
    from shapely.geometry import box
    try:
        from app.tools.site import _largest_axis_aligned_rect
    except Exception:
        return []
    work = residual.buffer(0)
    parcels: list[dict[str, Any]] = []
    for idx in range(1, max(1, count) + 1):
        if work.is_empty or work.area < 300:
            break
        largest = _largest_axis_aligned_rect(work, grid_m=grid_m)
        if not largest or float(largest.get("area_m2") or 0) < 300:
            break
        parcel = _rect_from_largest(largest, idx=idx)
        parcels.append(parcel)
        cut = box(parcel["x"], parcel["y"], parcel["x"] + parcel["breite_m"], parcel["y"] + parcel["tiefe_m"]).buffer(gap_m / 2)
        work = work.difference(cut).buffer(0)
    return sorted(parcels, key=lambda p: float(p.get("flaeche_m2") or 0), reverse=True)


def _split_large_parcel(parcel: dict[str, Any], count: int, *, gap_m: float = 8.0) -> list[dict[str, Any]]:
    """Unterteilt ein großes Restrechteck, wenn die Straßen nur eine Restfläche erzeugen."""
    if count <= 1:
        return [parcel]
    x = float(parcel.get("x", 0))
    y = float(parcel.get("y", 0))
    w = float(parcel.get("breite_m", 0))
    d = float(parcel.get("tiefe_m", 0))
    if w <= 0 or d <= 0:
        return [parcel]
    out: list[dict[str, Any]] = []
    if w >= d:
        usable = w - gap_m * (count - 1)
        part_w = usable / count
        if part_w < 18:
            return [parcel]
        for idx in range(count):
            out.append(_rect_dict(f"Parzelle {idx + 1}", x + idx * (part_w + gap_m), y, part_w, d, "building_parcel_candidate", "#DDE7EF") | {"source": "split_residual_max_rect"})
    else:
        usable = d - gap_m * (count - 1)
        part_d = usable / count
        if part_d < 18:
            return [parcel]
        for idx in range(count):
            out.append(_rect_dict(f"Parzelle {idx + 1}", x, y + idx * (part_d + gap_m), w, part_d, "building_parcel_candidate", "#DDE7EF") | {"source": "split_residual_max_rect"})
    return out


def _target_building_specs(site_a: float, grz: float, building_targets: dict[str, Any] | None, variant_id: str) -> dict[str, float]:
    targets = building_targets or {}
    target_area = float(targets.get("main_footprint_m2") or targets.get("hauptgebaeude_flaeche_m2") or 0)
    if target_area <= 0:
        target_area = grz * site_a
    if variant_id == "B_ERWEITERUNG":
        target_area *= 0.92
    elif variant_id == "C_FLAECHENEFFIZIENZ":
        target_area *= 1.04
    target_w = float(targets.get("main_width_m") or targets.get("hauptgebaeude_breite_m") or 0)
    target_d = float(targets.get("main_depth_m") or targets.get("hauptgebaeude_tiefe_m") or 0)
    if target_w <= 0 or target_d <= 0:
        aspect = float(targets.get("main_aspect_ratio") or 1.7)
        target_w = math.sqrt(max(1.0, target_area) * max(0.5, aspect))
        target_d = target_area / max(1.0, target_w)
    return {"area_m2": max(1.0, target_area), "width_m": max(6.0, target_w), "depth_m": max(6.0, target_d)}


def _best_axis_rect_for_target(buildable, target: dict[str, float], grid_m: float = 3.0) -> dict[str, Any] | None:
    """Findet ein innenliegendes Rechteck mit guter Zielgrößen-/Seitenverhältnis-Passung."""
    try:
        from shapely.geometry import box
        minx, miny, maxx, maxy = buildable.bounds
        cols = max(1, int((maxx - minx) // grid_m))
        rows = max(1, int((maxy - miny) // grid_m))
        if cols < 1 or rows < 1:
            return None
        cell_area = grid_m * grid_m
        matrix: list[list[bool]] = []
        for r in range(rows):
            row = []
            for c in range(cols):
                cell = box(minx + c * grid_m, miny + r * grid_m, minx + (c + 1) * grid_m, miny + (r + 1) * grid_m)
                row.append(buildable.intersection(cell).area / cell_area >= 0.90)
            matrix.append(row)
        target_area = float(target["area_m2"])
        target_aspect = float(target["width_m"]) / max(1.0, float(target["depth_m"]))
        best = None
        for r0 in range(rows):
            valid_cols = [True] * cols
            for r1 in range(r0, rows):
                for c in range(cols):
                    valid_cols[c] = valid_cols[c] and matrix[r1][c]
                c = 0
                while c < cols:
                    if not valid_cols[c]:
                        c += 1
                        continue
                    start = c
                    while c < cols and valid_cols[c]:
                        c += 1
                    run = c - start
                    height_cells = r1 - r0 + 1
                    for width_cells in range(1, run + 1):
                        # evaluate only a few horizontal placements to keep runtime bounded
                        for left in {start, start + max(0, (run - width_cells) // 2), start + run - width_cells}:
                            w = width_cells * grid_m
                            d = height_cells * grid_m
                            if w < 18 or d < 18:
                                continue
                            area = w * d
                            area_score = abs(area - target_area) / max(target_area, 1.0)
                            aspect = w / max(d, 1.0)
                            aspect_score = abs(math.log(max(0.2, aspect) / max(0.2, target_aspect)))
                            oversize_penalty = max(0.0, area - target_area) / max(target_area, 1.0) * 0.35
                            score = area_score + 0.45 * aspect_score + oversize_penalty
                            if best is None or score < best["score"]:
                                best = {"score": score, "x": minx + left * grid_m, "y": miny + r0 * grid_m, "width_m": w, "depth_m": d, "area_m2": area}
        if not best:
            return None
        return _rect_dict("Gebäudeparzelle Hauptgebäude", best["x"], best["y"], best["width_m"], best["depth_m"], "building_parcel_candidate", "#DDE7EF") | {"target_match_score": round(float(best["score"]), 3)}
    except Exception:
        return None


def _polygonal_zone_strategy_for_variant(
    *,
    site_w: float,
    site_d: float,
    site_a: float,
    site: dict[str, Any],
    analysis: dict[str, Any],
    building_targets: dict[str, Any] | None,
    variant_id: str,
    grz: float,
    erschliessung_typ: str,
) -> dict[str, Any] | None:
    poly = _polygon_from_site(site)
    if poly is None:
        return None
    try:
        count = max(1, int((building_targets or {}).get("main_building_count") or (building_targets or {}).get("anzahl") or 1))
        legal_layer = _build_legal_layer(site, poly, analysis)
        traffic_profile = str((building_targets or {}).get("traffic_profile") or "logistik")
        traffic_layer = _build_traffic_layer(poly, legal_layer, site.get("access_points") or [], analysis, erschliessung_typ, traffic_profile, building_targets or {})

        buildable = legal_layer.get("buildable_geom") or poly.buffer(-ABSTANDSFLAECHE_M)
        road_geom = None
        if traffic_layer.get("road_zone", {}).get("polygon"):
            from shapely.geometry import Polygon
            road_geom = Polygon(traffic_layer["road_zone"]["polygon"])
        if road_geom is None or road_geom.is_empty:
            road_geom = _side_strip_polygon(poly, analysis.get("primary_access_side", "south"), 20.0)
        parking_geom = None
        if (traffic_layer.get("parking_zone") or {}).get("polygon"):
            from shapely.geometry import Polygon
            parking_geom = Polygon((traffic_layer.get("parking_zone") or {})["polygon"])
        residual = buildable.difference(road_geom.buffer(1.5))
        if parking_geom is not None and not parking_geom.is_empty:
            residual = residual.difference(parking_geom.buffer(0.75))
        try:
            from shapely.geometry import Polygon
            for fz in traffic_layer.get("functional_zones") or []:
                if fz.get("typ") in {"zielzone_andienung", "zielzone_sicherheit"} and fz.get("polygon"):
                    residual = residual.difference(Polygon(fz["polygon"]).buffer(0.75))
        except Exception:
            pass

        reserve_geom = None
        reserve_side = _opposite_side(analysis.get("primary_access_side", "south"))
        reserve_depth = max(12.0, min(32.0, math.sqrt(site_a) * (0.22 if variant_id == "B_ERWEITERUNG" else 0.14)))
        reserve_geom = _side_strip_polygon(residual, reserve_side, reserve_depth)
        if reserve_geom is not None and not reserve_geom.is_empty and reserve_geom.area > max(80.0, site_a * 0.025):
            residual = residual.difference(reserve_geom.buffer(0.5))

        target = _target_building_specs(site_a, grz, building_targets, variant_id)
        parcels = _parcelize_residual_buildable(residual, site, count, gap_m=10.0, grid_m=3.0)
        if len(parcels) < count and parcels:
            split = _split_large_parcel(parcels[0], count, gap_m=10.0)
            if len(split) > len(parcels):
                parcels = split
        if not parcels:
            largest = _largest_buildable_rect_for_site(site, ABSTANDSFLAECHE_M)
            parcels = [largest] if largest else []
        if len(parcels) < count and parcels:
            split = _split_large_parcel(parcels[0], count, gap_m=10.0)
            if len(split) > len(parcels):
                parcels = split
        if not parcels:
            return None
        for idx, parcel in enumerate(parcels, start=1):
            parcel["name"] = f"Gebäudeparzelle {idx}"
            parcel["typ"] = "building_parcel_candidate"
            parcel["source"] = "residual_max_rect"

        zones: list[dict[str, Any]] = []
        zones.extend(traffic_layer.get("functional_zones") or [])
        if traffic_layer.get("road_zone"):
            zones.append(traffic_layer["road_zone"])
        if traffic_layer.get("parking_zone"):
            zones.append(traffic_layer["parking_zone"])
        if reserve_geom is not None and not reserve_geom.is_empty and reserve_geom.area > 20:
            zones.append(_zone_from_geom("Erweiterungsreserve", reserve_geom, "reserve", "#D8E4C8"))
        zones.extend(parcels)

        outdoor_storage = None
        if variant_id == "A_LOGISTIK" and parcels:
            from shapely.geometry import box
            first = parcels[0]
            px, py = float(first["x"]), float(first["y"])
            pw, pd = float(first["breite_m"]), float(first["tiefe_m"])
            side = analysis.get("primary_access_side", "south")
            if side in ("south", "north"):
                candidate = box(px, max(poly.bounds[1], py - 14), px + min(pw, 36), py - 2)
            else:
                candidate = box(max(poly.bounds[0], px - 14), py, px - 2, py + min(pd, 36))
            storage_geom = candidate.intersection(poly).difference(road_geom)
            if not storage_geom.is_empty and storage_geom.area > 35:
                outdoor_storage = _zone_from_geom("Außenlager / Logistikpuffer", storage_geom, "aussenlager", "#C9CDD2")
                zones.append(outdoor_storage)

        selected_strategy = str(traffic_layer.get("strategy_type") or "frontspange")
        route_type = "ring" if selected_strategy in ("u_loop", "perimeter_ring") else ("stich" if selected_strategy == "stichhof" else "loop")
        return {
            "strategy": variant_id,
            "access_side": analysis.get("primary_access_side", "south"),
            "service_side": _opposite_side(analysis.get("primary_access_side", "south")) if variant_id == "B_ERWEITERUNG" else analysis.get("primary_access_side", "south"),
            "route_type": route_type,
            "buildable_rect": _buildable_rect(site_w, site_d, ABSTANDSFLAECHE_M),
            "legal_layer": {k: v for k, v in legal_layer.items() if k != "buildable_geom"},
            "traffic_layer": traffic_layer,
            "primary_parcel_candidate": parcels[0],
            "building_parcel_candidates": parcels,
            "zones": zones,
            "traffic_zone": traffic_layer.get("road_zone") or parcels[0],
            "pkw_zone": traffic_layer.get("parking_zone"),
            "reserve_zone": next((z for z in zones if z.get("typ") == "reserve"), None),
            "outdoor_storage_zone": outdoor_storage,
            "target_footprint_m2": round(target["area_m2"], 1),
            "target_building": target,
            "algorithmus": "polygonal_site_zoning_v2",
        }
    except Exception:
        return None

def _zone_strategy_for_variant(
    *,
    site_w: float,
    site_d: float,
    site_a: float,
    site: dict[str, Any],
    analysis: dict[str, Any],
    building_targets: dict[str, Any] | None,
    variant_id: str,
    grz: float,
    erschliessung_typ: str,
) -> dict[str, Any]:
    """Gliedert das Grundstück in Verkehrs-, Gebäude-, Reserve- und Freizonen."""
    polygonal = _polygonal_zone_strategy_for_variant(
        site_w=site_w, site_d=site_d, site_a=site_a, site=site, analysis=analysis,
        building_targets=building_targets, variant_id=variant_id, grz=grz, erschliessung_typ=erschliessung_typ,
    )
    if polygonal:
        return polygonal
    margin = ABSTANDSFLAECHE_M
    side = analysis.get("primary_access_side", "south")
    buildable = _buildable_rect(site_w, site_d, margin)
    traffic_depth = 22.0 if variant_id == "A_LOGISTIK" else 18.0
    pkw_depth = 12.0
    reserve_depth = max(18.0, min(42.0, (site_d if side in ("south", "north") else site_w) * 0.18))

    zones: list[dict[str, Any]] = []
    if side == "south":
        traffic = _rect_dict("LKW-Erschließung / Rangieren", margin, margin, site_w - 2 * margin, traffic_depth, "verkehr_lkw", "#D4A96A")
        pkw = _rect_dict("PKW / Besucher", margin, traffic["y"] + traffic["tiefe_m"] + 1, site_w - 2 * margin, pkw_depth, "verkehr_pkw", "#F5F0DC")
        if variant_id == "B_ERWEITERUNG":
            reserve = _rect_dict("Erweiterungsreserve", margin, site_d - margin - reserve_depth, site_w - 2 * margin, reserve_depth, "reserve", "#D8E4C8")
            parcel_y0 = pkw["y"] + pkw["tiefe_m"] + 3
            parcel_y1 = reserve["y"] - 4
        else:
            reserve = _rect_dict("Erweiterungsreserve", site_w - margin - max(24, site_w * 0.18), traffic["y"] + traffic["tiefe_m"] + 4, max(24, site_w * 0.18), site_d - traffic["tiefe_m"] - 2 * margin - 8, "reserve", "#D8E4C8")
            parcel_y0 = pkw["y"] + pkw["tiefe_m"] + 3
            parcel_y1 = site_d - margin
    elif side == "north":
        traffic = _rect_dict("LKW-Erschließung / Rangieren", margin, site_d - margin - traffic_depth, site_w - 2 * margin, traffic_depth, "verkehr_lkw", "#D4A96A")
        pkw = _rect_dict("PKW / Besucher", margin, traffic["y"] - pkw_depth - 1, site_w - 2 * margin, pkw_depth, "verkehr_pkw", "#F5F0DC")
        reserve = _rect_dict("Erweiterungsreserve", margin, margin, site_w - 2 * margin, reserve_depth if variant_id == "B_ERWEITERUNG" else max(16, site_d * 0.12), "reserve", "#D8E4C8")
        parcel_y0 = reserve["y"] + reserve["tiefe_m"] + 4 if variant_id == "B_ERWEITERUNG" else margin
        parcel_y1 = pkw["y"] - 3
    elif side == "west":
        traffic = _rect_dict("LKW-Erschließung / Rangieren", margin, margin, traffic_depth, site_d - 2 * margin, "verkehr_lkw", "#D4A96A")
        pkw = _rect_dict("PKW / Besucher", traffic["x"] + traffic["breite_m"] + 1, margin, pkw_depth, site_d - 2 * margin, "verkehr_pkw", "#F5F0DC")
        reserve = _rect_dict("Erweiterungsreserve", site_w - margin - reserve_depth, margin, reserve_depth, site_d - 2 * margin, "reserve", "#D8E4C8")
        parcel_y0, parcel_y1 = margin, site_d - margin
        parcel_x0 = pkw["x"] + pkw["breite_m"] + 4
        parcel_x1 = reserve["x"] - 4 if variant_id == "B_ERWEITERUNG" else site_w - margin
    else:
        traffic = _rect_dict("LKW-Erschließung / Rangieren", site_w - margin - traffic_depth, margin, traffic_depth, site_d - 2 * margin, "verkehr_lkw", "#D4A96A")
        pkw = _rect_dict("PKW / Besucher", traffic["x"] - pkw_depth - 1, margin, pkw_depth, site_d - 2 * margin, "verkehr_pkw", "#F5F0DC")
        reserve = _rect_dict("Erweiterungsreserve", margin, margin, reserve_depth, site_d - 2 * margin, "reserve", "#D8E4C8")
        parcel_y0, parcel_y1 = margin, site_d - margin
        parcel_x0 = reserve["x"] + reserve["breite_m"] + 4 if variant_id == "B_ERWEITERUNG" else margin
        parcel_x1 = pkw["x"] - 4

    if side in ("south", "north"):
        parcel_x0 = margin
        parcel_x1 = site_w - margin
        if variant_id != "B_ERWEITERUNG" and reserve.get("typ") == "reserve" and reserve["breite_m"] > 0 and reserve["x"] > site_w / 2:
            parcel_x1 = min(parcel_x1, reserve["x"] - 4)
    parcel_w = max(24.0, parcel_x1 - parcel_x0)
    parcel_d = max(24.0, parcel_y1 - parcel_y0)
    if variant_id == "C_FLAECHENEFFIZIENZ":
        parcel_w = min(parcel_w, buildable["w"] * 0.92)
        parcel_d = min(parcel_d, buildable["d"] * 0.82)
        parcel_x0 = max(margin, min(parcel_x0 + (parcel_x1 - parcel_x0 - parcel_w) / 2, site_w - margin - parcel_w))
        parcel_y0 = max(margin, min(parcel_y0 + (parcel_y1 - parcel_y0 - parcel_d) / 2, site_d - margin - parcel_d))
    primary_parcel = _rect_dict("Gebäudeparzelle Hauptgebäude", parcel_x0, parcel_y0, parcel_w, parcel_d, "building_parcel_candidate", "#DDE7EF")
    if analysis.get("is_irregular"):
        largest = _largest_buildable_rect_for_site(site, margin)
        if largest and largest.get("breite_m", 0) >= 18 and largest.get("tiefe_m", 0) >= 18:
            primary_parcel = largest

    zones.extend([traffic, pkw, reserve, primary_parcel])
    outdoor_storage = None
    if variant_id == "A_LOGISTIK":
        if side in ("south", "north"):
            outdoor_storage = _rect_dict("Außenlager / Logistikpuffer", primary_parcel["x"], max(margin, primary_parcel["y"] - 16), min(primary_parcel["breite_m"], site_w * 0.35), 12, "aussenlager", "#C9CDD2")
        else:
            outdoor_storage = _rect_dict("Außenlager / Logistikpuffer", max(margin, primary_parcel["x"] - 16), primary_parcel["y"], 12, min(primary_parcel["tiefe_m"], site_d * 0.35), "aussenlager", "#C9CDD2")
        zones.append(outdoor_storage)

    zones = _filter_rects_by_site(zones, site, min_coverage=0.58 if analysis.get("is_irregular") else 0.72)
    if primary_parcel not in zones:
        zones.append(primary_parcel)
    route_type = "ring" if analysis.get("access_count", 0) >= 2 or erschliessung_typ == "u_foermig" else ("stich" if variant_id == "B_ERWEITERUNG" else "loop")
    return {
        "strategy": variant_id,
        "access_side": side,
        "service_side": _opposite_side(side) if variant_id == "B_ERWEITERUNG" else side,
        "route_type": route_type,
        "buildable_rect": buildable,
        "primary_parcel_candidate": primary_parcel,
        "zones": zones,
        "traffic_zone": traffic,
        "pkw_zone": pkw,
        "reserve_zone": reserve,
        "outdoor_storage_zone": outdoor_storage,
        "target_footprint_m2": round(grz * site_a, 1),
    }


def _footprint_in_parcel(target_fp: float, parcel: dict[str, Any], variant_id: str, site_w: float, site_d: float, target_spec: dict[str, float] | None = None) -> tuple[float, float]:
    max_w = max(24.0, float(parcel["breite_m"]) - 4.0)
    max_d = max(24.0, float(parcel["tiefe_m"]) - 4.0)
    if target_spec and float(target_spec.get("width_m", 0)) > 0 and float(target_spec.get("depth_m", 0)) > 0:
        tw = round(float(target_spec["width_m"]) / 6) * 6
        td = round(float(target_spec["depth_m"]) / 6) * 6
        if tw <= max_w and td <= max_d:
            return max(24.0, tw), max(24.0, td)
    aspect_base = max(1.0, min(2.6, max_w / max(1.0, max_d)))
    if variant_id == "A_LOGISTIK":
        aspect = min(2.8, max(1.25, aspect_base * 1.15))
    elif variant_id == "B_ERWEITERUNG":
        aspect = min(3.1, max(1.35, aspect_base * 1.25))
    else:
        aspect = min(2.1, max(1.05, aspect_base * 0.95))
    w = round(math.sqrt(max(1.0, target_fp) * aspect) / 6) * 6
    d = round(max(1.0, target_fp) / max(w, 6) / 6) * 6
    if w > max_w:
        w = round(max_w / 6) * 6
        d = round(target_fp / max(w, 6) / 6) * 6
    if d > max_d:
        d = round(max_d / 6) * 6
        w = round(target_fp / max(d, 6) / 6) * 6
    return max(24.0, min(w, max_w)), max(24.0, min(d, max_d))


def _place_building_in_parcel(parcel: dict[str, Any], w: float, d: float, access_side: str, variant_id: str) -> tuple[float, float]:
    px = float(parcel["x"])
    py = float(parcel["y"])
    pw = float(parcel["breite_m"])
    pd = float(parcel["tiefe_m"])
    inset = 4.0
    if variant_id == "B_ERWEITERUNG":
        if access_side in ("south", "north"):
            x = px + inset
            y = py + (pd - d) / 2
        else:
            x = px + (pw - w) / 2
            y = py + inset
    elif access_side == "south":
        x = px + (pw - w) / 2
        y = py + inset
    elif access_side == "north":
        x = px + (pw - w) / 2
        y = py + pd - d - inset
    elif access_side == "west":
        x = px + inset
        y = py + (pd - d) / 2
    else:
        x = px + pw - w - inset
        y = py + (pd - d) / 2
    return round(max(px + inset, min(x, px + pw - w - inset)), 2), round(max(py + inset, min(y, py + pd - d - inset)), 2)


def _generate_masterplan_variant(
    *,
    site: dict[str, Any],
    site_w: float,
    site_d: float,
    site_a: float,
    access: list[dict],
    access_side: str,
    grundstuecksanalyse: dict[str, Any],
    grz: float,
    nebenbauten_aktiv: dict[str, bool],
    erschliessung_typ: str,
    geschosse_buero: int,
    briefing: dict[str, Any] | None,
    building_targets: dict[str, Any] | None,
    rules_mp: dict,
    variant_id: str,
    variant_label: str,
    variant_focus: str,
    parcel_idx: int,
) -> dict[str, Any]:
    zoning_strategy = _zone_strategy_for_variant(
        site_w=site_w,
        site_d=site_d,
        site_a=site_a,
        site=site,
        analysis=grundstuecksanalyse,
        building_targets=building_targets or {},
        variant_id=variant_id,
        grz=grz,
        erschliessung_typ=erschliessung_typ,
    )
    primary_parcel_candidate = zoning_strategy["primary_parcel_candidate"]
    target_count = max(1, int((building_targets or {}).get("main_building_count") or (building_targets or {}).get("anzahl") or 1))
    parcel_candidates = list(zoning_strategy.get("building_parcel_candidates") or [primary_parcel_candidate])
    explicit_target_fp = float((building_targets or {}).get("main_footprint_m2") or (building_targets or {}).get("hauptgebaeude_flaeche_m2") or 0)
    target_total_fp = float(zoning_strategy.get("target_footprint_m2") or grz * site_a)
    target_fp_each = max(250.0, explicit_target_fp if explicit_target_fp > 0 else target_total_fp / target_count)

    main_buildings: list[dict[str, Any]] = []
    for idx_parcel, parcel_candidate in enumerate(parcel_candidates[:target_count], start=1):
        max_parcel_footprint = max(1.0, float(parcel_candidate["breite_m"]) * float(parcel_candidate["tiefe_m"]) * 0.82)
        target_fp = min(target_fp_each, max_parcel_footprint)
        hg_w, hg_d = _footprint_in_parcel(target_fp, parcel_candidate, variant_id, site_w, site_d, zoning_strategy.get("target_building"))
        hg_x, hg_y = _place_building_in_parcel(parcel_candidate, hg_w, hg_d, access_side, variant_id)
        main_buildings.append({
            "name": "Hauptgebäude (Produktion)" if idx_parcel == 1 else f"Hauptgebäude {idx_parcel} (Produktion)",
            "x": round(hg_x, 2),
            "y": round(hg_y, 2),
            "breite_m": round(hg_w, 2),
            "tiefe_m": round(hg_d, 2),
            "flaeche_m2": round(hg_w * hg_d, 1),
            "farbe": "#1A3A5C" if idx_parcel == 1 else "#244B73",
            "funktion": "produktion",
            "source_parcel": parcel_candidate.get("name"),
        })

    if not main_buildings:
        max_parcel_footprint = max(1.0, primary_parcel_candidate["breite_m"] * primary_parcel_candidate["tiefe_m"] * 0.82)
        target_fp = min(target_fp_each, max_parcel_footprint)
        hg_w, hg_d = _footprint_in_parcel(target_fp, primary_parcel_candidate, variant_id, site_w, site_d, zoning_strategy.get("target_building"))
        hg_x, hg_y = _place_building_in_parcel(primary_parcel_candidate, hg_w, hg_d, access_side, variant_id)
        main_buildings.append({
            "name": "Hauptgebäude (Produktion)", "x": round(hg_x, 2), "y": round(hg_y, 2),
            "breite_m": round(hg_w, 2), "tiefe_m": round(hg_d, 2), "flaeche_m2": round(hg_w * hg_d, 1),
            "farbe": "#1A3A5C", "funktion": "produktion",
        })

    hauptgebaeude = main_buildings[0]
    gebaeude = main_buildings + _generate_secondary_gebaeude(
        site_a=site_a,
        site_w=site_w,
        site_d=site_d,
        hauptgebaeude=hauptgebaeude,
        access_side=access_side,
        variant_id=variant_id,
        briefing=briefing,
    )

    building_parcels = []
    for idx_building, geb in enumerate(gebaeude, start=1):
        parcel = _building_parcel_from_hauptgebaeude(site, geb, parcel_idx=idx_building)
        parcel["id"] = f"{site.get('id', 'site')}_{variant_id}_BP{idx_building:02d}"
        parcel["name"] = f"{variant_label} · {geb.get('name', 'Gebäude')}"
        parcel["masterplan_variant_id"] = variant_id
        parcel["building_name"] = geb.get("name")
        parcel["building_function"] = geb.get("funktion")
        building_parcels.append(parcel)
    building_parcel = building_parcels[0]

    nebenbauten = _place_nebenbauten(
        hauptgebaeude=hauptgebaeude,
        site_w=site_w, site_d=site_d,
        access_side=access_side,
        aktiv=nebenbauten_aktiv,
    )
    erschliessung = _compute_erschliessung(
        hauptgebaeude=hauptgebaeude,
        site_w=site_w, site_d=site_d,
        access_side=access_side,
        access_points=access,
        erschliessung_typ=erschliessung_typ,
    )
    if zoning_strategy.get("algorithmus") in ("polygonal_site_zoning_v2", "phase_based_polygonal_masterplan_v1") and zoning_strategy.get("traffic_zone"):
        tz = zoning_strategy["traffic_zone"]
        traffic_layer = zoning_strategy.get("traffic_layer") or {}
        erschliessung["rangierzone"] = {**tz, "typ": "rangier", "name": "Straßenkorridor / LKW-Erschließung"}
        erschliessung["erschliessungsflaeche_m2"] = round(float(tz.get("flaeche_m2") or 0), 1)
        erschliessung["strassenachsen"] = traffic_layer.get("road_line_points") or []
        if erschliessung["strassenachsen"]:
            erschliessung["lkw_schleife_punkte"] = erschliessung["strassenachsen"][0]
    elif grundstuecksanalyse.get("is_irregular"):
        erschliessung["rangierzone"] = _sanitize_rect_to_site(
            erschliessung.get("rangierzone") or {},
            site,
            zoning_strategy.get("primary_parcel_candidate"),
            min_coverage=0.55,
        )
    freizonen = _compute_freizonen(
        hauptgebaeude=hauptgebaeude,
        nebenbauten=nebenbauten,
        erschliessung=erschliessung,
        site_w=site_w, site_d=site_d,
        access_side=access_side,
    )
    freizonen = _merge_zoning_freizonen(freizonen, zoning_strategy)
    if grundstuecksanalyse.get("is_irregular"):
        freizonen = _filter_rects_by_site(freizonen, site, min_coverage=0.58)
    infrastruktur = _compute_infrastruktur(
        site=site,
        hauptgebaeude=hauptgebaeude,
        nebenbauten=nebenbauten,
        access_points=access,
    )
    if zoning_strategy.get("traffic_layer"):
        infrastruktur["knoten"] = zoning_strategy["traffic_layer"].get("infra_nodes") or []
    flaechenbilanz = _compute_flaechenbilanz(
        site_a=site_a,
        hauptgebaeude=hauptgebaeude,
        gebaeude=gebaeude,
        nebenbauten=nebenbauten,
        erschliessung=erschliessung,
        freizonen=freizonen,
        briefing=briefing,
        geschosse_buero=geschosse_buero,
        rules=rules_mp,
    )
    score = _score_masterplan_variant(flaechenbilanz, infrastruktur, variant_id)
    rule_refs_11 = _masterplan_rule_refs(rules_mp, "1.1")
    rule_refs_12 = _masterplan_rule_refs(rules_mp, "1.2")
    rule_refs_13 = _masterplan_rule_refs(rules_mp, "1.3")
    rule_refs_14 = _masterplan_rule_refs(rules_mp, "1.4")

    return {
        "id": variant_id,
        "label": variant_label,
        "focus": variant_focus,
        "building_parcels": building_parcels,
        "selected_building_parcel_id": building_parcel["id"],
        "building_parcel": building_parcel,
        "grundstuecksanalyse": grundstuecksanalyse,
        "zonierung": zoning_strategy["zones"],
        "phasenlayer": {
            "1.1": {"grundstuecksanalyse": grundstuecksanalyse, "rule_refs": rule_refs_11},
            "1.2": {**(zoning_strategy.get("legal_layer") or {}), "rule_refs": rule_refs_12},
            "1.3": {**(zoning_strategy.get("traffic_layer") or {}), "rule_refs": rule_refs_13},
            "1.4": {"building_parcels": zoning_strategy.get("building_parcel_candidates") or [], "rule_refs": rule_refs_14},
        },
        "erschliessungskonzept": {
            "route_type": zoning_strategy.get("route_type"),
            "strategy_type": (zoning_strategy.get("traffic_layer") or {}).get("strategy_type"),
            "strategy_score": (zoning_strategy.get("traffic_layer") or {}).get("score"),
            "decision_reasons": (zoning_strategy.get("traffic_layer") or {}).get("decision_reasons") or [],
            "candidate_strategies": (zoning_strategy.get("traffic_layer") or {}).get("candidate_strategies") or [],
            "optimization_mode": (zoning_strategy.get("traffic_layer") or {}).get("optimization_mode"),
            "optimization_population_size": (zoning_strategy.get("traffic_layer") or {}).get("optimization_population_size"),
            "optimization_evaluated_candidates": (zoning_strategy.get("traffic_layer") or {}).get("optimization_evaluated_candidates"),
            "fitness_weights": (zoning_strategy.get("traffic_layer") or {}).get("fitness_weights") or {},
            "selected_chromosome": (zoning_strategy.get("traffic_layer") or {}).get("selected_chromosome") or {},
            "access_side": access_side,
            "service_side": zoning_strategy.get("service_side"),
            "verkehrstrennung": "PKW und LKW als getrennte Zonen geführt",
            "rule_refs": rule_refs_13,
        },
        "planning_pipeline": [
            "1 Grundstück analysiert",
            "2 Erschließungskorridor aus Zufahrt und Variante abgeleitet",
            "3 Funktionszonen gebildet",
            "4 Gebäudeparzellen aus bebaubarer Zone erzeugt",
            "5 Varianten nach Ausnutzung, Verkehr, Infrastruktur und Reserve bewertet",
        ],
        "hauptgebaeude": hauptgebaeude,
        "gebaeude": gebaeude,
        "nebenbauten": nebenbauten,
        "erschliessung": erschliessung,
        "freizonen": freizonen,
        "infrastruktur": infrastruktur,
        "flaechenbilanz": flaechenbilanz,
        "score": score,
        "config": {
            "grz_ziel": grz,
            "erschliessung_typ": erschliessung_typ,
            "access_side": access_side,
            "building_targets": building_targets or {},
            "algorithmus": zoning_strategy.get("algorithmus", "polygonal_site_zoning_v2"),
            "rule_catalog_loaded": bool((rules_mp or {}).get("rule_catalog")),
        },
    }





def _generate_additional_main_buildings(
    *,
    primary: dict[str, Any],
    base: dict[str, Any],
    count: int,
    site: dict[str, Any],
) -> list[dict[str, Any]]:
    """Platziert zusätzliche Hallen-Platzhalter innerhalb der Gebäudeparzelle."""
    if count <= 1:
        return []
    poly = _polygon_from_site(site)
    px, py = float(primary["x"]), float(primary["y"])
    pw, pd = float(primary["breite_m"]), float(primary["tiefe_m"])
    bw, bd = float(base["breite_m"]), float(base["tiefe_m"])
    gap = 6.0
    placed = [(float(base["x"]), float(base["y"]), bw, bd)]
    candidates: list[tuple[float, float]] = []
    # Prefer rows parallel to the long parcel direction.
    for row in range(max(1, int(pd // max(bd + gap, 1)))):
        y = py + 4.0 + row * (bd + gap)
        for col in range(max(1, int(pw // max(bw + gap, 1)))):
            x = px + 4.0 + col * (bw + gap)
            candidates.append((x, y))
    out: list[dict[str, Any]] = []
    for x, y in candidates:
        if len(out) >= count - 1:
            break
        if any(not (x + bw + gap <= ox or ox + ow + gap <= x or y + bd + gap <= oy or oy + od + gap <= y) for ox, oy, ow, od in placed):
            continue
        rect = {"x": x, "y": y, "breite_m": bw, "tiefe_m": bd}
        if poly is not None and _rect_coverage(rect, poly) < 0.92:
            continue
        placed.append((x, y, bw, bd))
        idx = len(out) + 2
        out.append({
            "name": f"Hauptgebäude {idx} (Produktion)",
            "x": round(x, 2),
            "y": round(y, 2),
            "breite_m": round(bw, 2),
            "tiefe_m": round(bd, 2),
            "flaeche_m2": round(bw * bd, 1),
            "farbe": "#244B73",
            "funktion": "produktion",
            "placeholder_from_target": True,
        })
    return out


def _merge_zoning_freizonen(freizonen: list[dict[str, Any]], strategy: dict[str, Any]) -> list[dict[str, Any]]:
    """Spiegelt relevante Zonierungsflächen in der Lageplan-Darstellung."""
    out = list(freizonen)
    existing = {(round(float(f.get("x", 0)), 1), round(float(f.get("y", 0)), 1), f.get("typ")) for f in out}
    typ_map = {
        "reserve": ("reserve", "Erweiterungsreserve", "#D8E4C8"),
        "aussenlager": ("aussenlager", "Außenlager / Logistikpuffer", "#C9CDD2"),
    }
    for zone in strategy.get("zones") or []:
        ztyp = zone.get("typ")
        if ztyp not in typ_map:
            continue
        typ, name, color = typ_map[ztyp]
        key = (round(float(zone.get("x", 0)), 1), round(float(zone.get("y", 0)), 1), typ)
        if key in existing:
            continue
        if float(zone.get("breite_m", 0)) < 4 or float(zone.get("tiefe_m", 0)) < 4:
            continue
        out.append({
            "name": name,
            "x": zone.get("x"),
            "y": zone.get("y"),
            "breite_m": zone.get("breite_m"),
            "tiefe_m": zone.get("tiefe_m"),
            "flaeche_m2": zone.get("flaeche_m2"),
            "polygon": zone.get("polygon"),
            "geometry_mode": zone.get("geometry_mode"),
            "typ": "gruen" if ztyp == "reserve" else "aussenlager",
            "farbe": color,
            "source": "masterplan_zoning",
        })
    return out


def _generate_secondary_gebaeude(
    *,
    site_a: float,
    site_w: float,
    site_d: float,
    hauptgebaeude: dict,
    access_side: str,
    variant_id: str,
    briefing: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Erzeugt zusätzliche Gebäude für größere Masterplan-Areale."""
    if site_a < 60_000:
        return []

    margin = ABSTANDSFLAECHE_M
    hx = float(hauptgebaeude["x"])
    hy = float(hauptgebaeude["y"])
    hw = float(hauptgebaeude["breite_m"])
    hd = float(hauptgebaeude["tiefe_m"])

    logistics_area = float((briefing or {}).get("lager_rohstoffe") or 0) + float((briefing or {}).get("lager_fertigwaren") or 0)
    if logistics_area <= 0:
        logistics_area = min(site_a * 0.10, max(1200.0, float(hauptgebaeude["flaeche_m2"]) * 0.28))
    logistics_w = max(30.0, round(math.sqrt(logistics_area * 1.8) / 6) * 6)
    logistics_d = max(24.0, round(logistics_area / logistics_w / 6) * 6)
    logistics_w = min(logistics_w, max(30.0, site_w * 0.32))
    logistics_d = min(logistics_d, max(24.0, site_d * 0.30))

    office_area = float((briefing or {}).get("buero_nuf2") or 0) or min(site_a * 0.035, 1800.0)
    office_w = max(18.0, round(math.sqrt(office_area * 1.3) / 6) * 6)
    office_d = max(12.0, round(office_area / office_w / 6) * 6)
    office_w = min(office_w, max(18.0, site_w * 0.20))
    office_d = min(office_d, max(12.0, site_d * 0.18))

    def _clamp(x: float, y: float, w: float, d: float) -> tuple[float, float]:
        return (
            round(max(margin, min(x, site_w - w - margin)), 2),
            round(max(margin, min(y, site_d - d - margin)), 2),
        )

    if access_side in ("south", "north"):
        log_x, log_y = _clamp(hx + hw + margin * 2, hy, logistics_w, logistics_d)
        if log_x <= hx + hw and hx > logistics_w + margin * 3:
            log_x, log_y = _clamp(hx - logistics_w - margin * 2, hy, logistics_w, logistics_d)
        off_y = margin if access_side == "south" else site_d - office_d - margin
        office_x, office_y = _clamp(margin, off_y, office_w, office_d)
    else:
        log_x, log_y = _clamp(hx, hy + hd + margin * 2, logistics_w, logistics_d)
        if log_y <= hy + hd and hy > logistics_d + margin * 3:
            log_x, log_y = _clamp(hx, hy - logistics_d - margin * 2, logistics_w, logistics_d)
        off_x = margin if access_side == "west" else site_w - office_w - margin
        office_x, office_y = _clamp(off_x, margin, office_w, office_d)

    secondary = [
        {
            "name": "Logistikgebäude",
            "x": log_x,
            "y": log_y,
            "breite_m": round(logistics_w, 2),
            "tiefe_m": round(logistics_d, 2),
            "flaeche_m2": round(logistics_w * logistics_d, 1),
            "farbe": "#335C67",
            "funktion": "logistik",
        },
        {
            "name": "Büro / Sozial",
            "x": office_x,
            "y": office_y,
            "breite_m": round(office_w, 2),
            "tiefe_m": round(office_d, 2),
            "flaeche_m2": round(office_w * office_d, 1),
            "farbe": "#2A9D8F",
            "funktion": "buero_sozial",
        },
    ]
    if variant_id == "C_FLAECHENEFFIZIENZ":
        secondary = secondary[:1]
    return secondary

def _adjust_hauptgebaeude_for_variant(
    variant_id: str,
    x: float,
    y: float,
    w: float,
    d: float,
    site_w: float,
    site_d: float,
    access_side: str,
) -> tuple[float, float]:
    margin = ABSTANDSFLAECHE_M
    if variant_id == "B_ERWEITERUNG":
        if access_side in ("south", "north"):
            x = margin
        elif access_side == "west":
            y = margin
        else:
            y = site_d - d - margin
    elif variant_id == "C_FLAECHENEFFIZIENZ":
        x = (site_w - w) / 2
        y = (site_d - d) / 2
    x = max(margin, min(x, site_w - w - margin))
    y = max(margin, min(y, site_d - d - margin))
    return round(x, 2), round(y, 2)


def _compute_infrastruktur(
    *,
    site: dict[str, Any],
    hauptgebaeude: dict,
    nebenbauten: list[dict],
    access_points: list[dict],
) -> dict[str, Any]:
    """Einfache Medien-Trassen vom Anschluss-/Zufahrtspunkt zu Hauptgebäude und Technik."""
    site_w = float(site.get("width_m") or 0)
    site_d = float(site.get("depth_m") or 0)
    if access_points:
        start = access_points[0].get("point", [site_w / 2, 0])
    else:
        start = [site_w / 2, 0]
    hg_target = [
        float(hauptgebaeude["x"]) + float(hauptgebaeude["breite_m"]) / 2,
        float(hauptgebaeude["y"]) + float(hauptgebaeude["tiefe_m"]) / 2,
    ]
    trassen = []
    media = ["Strom", "Wasser", "Abwasser", "Glasfaser"]
    for idx, medium in enumerate(media):
        offset = idx * 1.2
        p0 = [round(float(start[0]) + offset, 2), round(float(start[1]), 2)]
        p1 = [round(hg_target[0] + offset, 2), round(hg_target[1], 2)]
        length = abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])
        trassen.append({"medium": medium, "punkte": [p0, p1], "laenge_m": round(length, 1)})

    trafo = next((n for n in nebenbauten if n.get("name") == "Trafostation"), None)
    if trafo:
        p1 = [float(trafo["x"]) + float(trafo["breite_m"]) / 2, float(trafo["y"]) + float(trafo["tiefe_m"]) / 2]
        length = abs(p1[0] - float(start[0])) + abs(p1[1] - float(start[1]))
        trassen.append({"medium": "MS-Trafo", "punkte": [start, [round(p1[0], 2), round(p1[1], 2)]], "laenge_m": round(length, 1)})

    return {
        "anschlusspunkt": [round(float(start[0]), 2), round(float(start[1]), 2)],
        "trassen": trassen,
        "trassenlaenge_m": round(sum(float(t["laenge_m"]) for t in trassen), 1),
    }


def _score_masterplan_variant(flaechenbilanz: dict[str, Any], infrastruktur: dict[str, Any], variant_id: str) -> dict[str, Any]:
    grz = float(flaechenbilanz.get("grz") or 0)
    grz_limit = float(flaechenbilanz.get("grz_grenzwert") or 0.6)
    vers = float(flaechenbilanz.get("versiegelungsgrad") or 0)
    sp_pct = min(1.0, float(flaechenbilanz.get("stellplaetze_deckung_pct") or 0) / 100.0)
    infra_len = float(infrastruktur.get("trassenlaenge_m") or 0)
    grz_quality = max(0.0, 1.0 - abs(min(grz, grz_limit) - grz_limit * 0.85) / max(grz_limit, 0.01))
    vers_quality = max(0.0, 1.0 - max(0.0, vers - 0.75) / 0.25)
    infra_quality = max(0.0, 1.0 - infra_len / 2000.0)
    bonus = {"A_LOGISTIK": 0.04, "B_ERWEITERUNG": 0.03, "C_FLAECHENEFFIZIENZ": 0.02}.get(variant_id, 0.0)
    total = (0.32 * grz_quality + 0.26 * vers_quality + 0.22 * sp_pct + 0.20 * infra_quality + bonus) * 100
    return {
        "gesamt": round(min(100.0, total), 1),
        "grz_qualitaet": round(grz_quality * 100, 1),
        "versiegelung": round(vers_quality * 100, 1),
        "stellplaetze": round(sp_pct * 100, 1),
        "infrastruktur": round(infra_quality * 100, 1),
    }

def _building_parcel_from_hauptgebaeude(
    site: dict[str, Any],
    hauptgebaeude: dict[str, Any],
    *,
    parcel_idx: int,
) -> dict[str, Any]:
    """Erzeugt die Schnittstelle Masterplanung -> Gebäude-Layoutplanung.

    Die Layoutplanung erhält nicht mehr das gesamte Grundstück, sondern eine lokal
    genullte Gebäudeparzelle. Das ursprüngliche Grundstück und die Lage innerhalb
    des Masterplans bleiben als Metadaten erhalten.
    """
    width = float(hauptgebaeude.get("breite_m") or 0.0)
    depth = float(hauptgebaeude.get("tiefe_m") or 0.0)
    area = float(hauptgebaeude.get("flaeche_m2") or width * depth)
    parent_x = float(hauptgebaeude.get("x") or 0.0)
    parent_y = float(hauptgebaeude.get("y") or 0.0)

    site_id = str(site.get("id") or "site")
    parcel_id = f"{site_id}_BP{parcel_idx:02d}"

    return {
        "id": parcel_id,
        "name": f"Gebäudeparzelle {parcel_idx} - {site.get('name', 'Masterplan')}",
        "source": "masterplan",
        "interface_type": "building_parcel",
        "is_building_parcel": True,
        "exclude_site_parking": True,
        "parent_site_id": site.get("id"),
        "parent_site_name": site.get("name"),
        "parent_offset_m": [round(parent_x, 2), round(parent_y, 2)],
        "area_m2": round(area, 1),
        "width_m": round(width, 2),
        "depth_m": round(depth, 2),
        "polygon": [[0.0, 0.0], [round(width, 2), 0.0], [round(width, 2), round(depth, 2)], [0.0, round(depth, 2)]],
        "access_points": _project_access_points_to_building_parcel(site, hauptgebaeude),
        "planning": {
            "grz": 1.0,
            "gfz": 6.0,
            "abstandsfaktor": 0.0,
            "max_gebaeudehoehe_m": float((site.get("planning") or {}).get("max_gebaeudehoehe_m", 12.0)),
            "regelgeschoss_hoehe_m": float((site.get("planning") or {}).get("regelgeschoss_hoehe_m", 3.5)),
        },
        "building_envelope": {
            "x": 0.0,
            "y": 0.0,
            "width_m": round(width, 2),
            "depth_m": round(depth, 2),
            "area_m2": round(area, 1),
            "max_footprint_m2": round(area, 1),
            "site_angle_deg": 0.0,
            "access_edge": _primary_access_side(site.get("access_points") or [], float(site.get("width_m") or width), float(site.get("depth_m") or depth)),
        },
    }


def _project_access_points_to_building_parcel(site: dict[str, Any], hauptgebaeude: dict[str, Any]) -> list[dict[str, Any]]:
    """Projiziert Grundstückszufahrten auf die lokale Gebäudeparzelle."""
    width = float(hauptgebaeude.get("breite_m") or 0.0)
    depth = float(hauptgebaeude.get("tiefe_m") or 0.0)
    if width <= 0 or depth <= 0:
        return []

    access_side = _primary_access_side(
        site.get("access_points") or [],
        float(site.get("width_m") or width),
        float(site.get("depth_m") or depth),
    )
    if access_side == "north":
        point = [width / 2, depth]
    elif access_side == "east":
        point = [width, depth / 2]
    elif access_side == "west":
        point = [0.0, depth / 2]
    else:
        point = [width / 2, 0.0]

    return [{
        "id": "MP-A1",
        "side": access_side,
        "point": [round(point[0], 2), round(point[1], 2)],
        "width_m": 8.0,
        "source": "masterplan",
    }]


# ---------------------------------------------------------------------------
# Erschließungsseite bestimmen
# ---------------------------------------------------------------------------

def _primary_access_side(
    access_points: list[dict],
    site_w: float,
    site_d: float,
) -> str:
    """Bestimmt die primäre Erschließungsseite ('south'|'north'|'west'|'east')."""
    if not access_points:
        return "south"
    # Breitester Zugang ist primär
    best = max(access_points, key=lambda ap: float(ap.get("width_m", 0)))
    return best.get("side", "south")


# ---------------------------------------------------------------------------
# Hauptgebäude positionieren
# ---------------------------------------------------------------------------

def _position_hauptgebaeude(
    *,
    hg_w: float, hg_d: float,
    site_w: float, site_d: float,
    access_side: str,
) -> tuple[float, float]:
    """Platziert das Hauptgebäude gegenüber der Erschließungsseite."""
    margin = ABSTANDSFLAECHE_M
    # Horizontal zentriert (unabhängig von Erschließungsseite)
    cx = (site_w - hg_w) / 2

    if access_side == "south":
        # Zufahrt von Süden → Gebäude im Norden des Grundstücks
        y = site_d - hg_d - margin
    elif access_side == "north":
        # Zufahrt von Norden → Gebäude im Süden
        y = margin
    elif access_side == "west":
        # Zufahrt von Westen → Gebäude im Osten
        cx = site_w - hg_w - margin
        y  = (site_d - hg_d) / 2
    elif access_side == "east":
        # Zufahrt von Osten → Gebäude im Westen
        cx = margin
        y  = (site_d - hg_d) / 2
    else:
        y = (site_d - hg_d) / 2

    x = max(margin, min(cx, site_w - hg_w - margin))
    y = max(margin, min(y, site_d - hg_d - margin))
    return round(x, 2), round(y, 2)


# ---------------------------------------------------------------------------
# Nebenbauten
# ---------------------------------------------------------------------------

def _place_nebenbauten(
    *,
    hauptgebaeude: dict,
    site_w: float,
    site_d: float,
    access_side: str,
    aktiv: dict[str, bool],
) -> list[dict]:
    """Platziert Nebenbauten an logischen Positionen (Ecken, Grenzen)."""
    hx = hauptgebaeude["x"]
    hy = hauptgebaeude["y"]
    hw = hauptgebaeude["breite_m"]
    hd = hauptgebaeude["tiefe_m"]
    margin = ABSTANDSFLAECHE_M
    placed: list[dict] = []

    def _add(name: str, x: float, y: float) -> None:
        spec = NEBENBAU_TYPEN[name]
        bw   = spec["breite_m"]
        bd   = spec["tiefe_m"]
        # Grundstücksgrenze einhalten
        x = max(margin * 0.5, min(x, site_w - bw - margin * 0.5))
        y = max(margin * 0.5, min(y, site_d - bd - margin * 0.5))
        placed.append({
            "name":      name,
            "x":         round(x, 2),
            "y":         round(y, 2),
            "breite_m":  bw,
            "tiefe_m":   bd,
            "flaeche_m2": round(bw * bd, 1),
            "farbe":     spec["farbe"],
        })

    # Pforte: nahe primärem Zugang, außen links neben der Einfahrt
    if aktiv.get("Pforte / Einfahrtskontrolle", True):
        if access_side == "south":
            _add("Pforte / Einfahrtskontrolle", margin, margin)
        elif access_side == "north":
            spec = NEBENBAU_TYPEN["Pforte / Einfahrtskontrolle"]
            _add("Pforte / Einfahrtskontrolle", margin, site_d - spec["tiefe_m"] - margin)
        elif access_side == "west":
            _add("Pforte / Einfahrtskontrolle", margin, margin)
        else:  # east
            spec = NEBENBAU_TYPEN["Pforte / Einfahrtskontrolle"]
            _add("Pforte / Einfahrtskontrolle", site_w - spec["breite_m"] - margin, margin)

    # Trafostation: gegenüber Zugang (hinter Gebäude, Ecke)
    if aktiv.get("Trafostation", True):
        spec = NEBENBAU_TYPEN["Trafostation"]
        if access_side == "south":
            _add("Trafostation", site_w - spec["breite_m"] - margin, site_d - spec["tiefe_m"] - margin)
        elif access_side == "north":
            _add("Trafostation", site_w - spec["breite_m"] - margin, margin)
        elif access_side == "west":
            _add("Trafostation", site_w - spec["breite_m"] - margin, site_d - spec["tiefe_m"] - margin)
        else:
            _add("Trafostation", margin, site_d - spec["tiefe_m"] - margin)

    # Lagerüberdachung: seitlich ans Hauptgebäude angebaut (Lagerseite = Ostseite)
    if aktiv.get("Lagerüberdachung", True):
        spec = NEBENBAU_TYPEN["Lagerüberdachung"]
        ub_x = hx + hw + 2.0  # 2m Abstand zum Hauptgebäude
        ub_y = hy + (hd - spec["tiefe_m"]) * 0.3
        if ub_x + spec["breite_m"] > site_w - margin:
            ub_x = hx - spec["breite_m"] - 2.0  # Auf die Westseite
        _add("Lagerüberdachung", ub_x, ub_y)

    # Sozialgebäude: nahe Bürobereich (Nordseite vom Gebäude oder freie Seite)
    if aktiv.get("Sozialgebäude", False):
        spec = NEBENBAU_TYPEN["Sozialgebäude"]
        sg_x = hx
        sg_y = hy - spec["tiefe_m"] - 4.0
        if sg_y < margin:
            sg_y = hy + hd + 4.0
        _add("Sozialgebäude", sg_x, sg_y)

    return placed


# ---------------------------------------------------------------------------
# Erschließung
# ---------------------------------------------------------------------------

def _compute_erschliessung(
    *,
    hauptgebaeude: dict,
    site_w: float,
    site_d: float,
    access_side: str,
    access_points: list[dict],
    erschliessung_typ: str,
) -> dict[str, Any]:
    """Berechnet LKW-Schleife, PKW-Zufahrt und Rangierzone."""
    hx = hauptgebaeude["x"]
    hy = hauptgebaeude["y"]
    hw = hauptgebaeude["breite_m"]
    hd = hauptgebaeude["tiefe_m"]
    margin = ABSTANDSFLAECHE_M

    # LKW-Erschließungsstreifen: Seite des Zugangs
    if access_side == "south":
        rang_y    = margin
        rang_h    = max(LKW_STREIFEN_TIEFE, hy - margin - 2)
        rang_x    = margin
        rang_w    = site_w - 2 * margin
        schleife  = _u_schleife(hx, hy, hw, hd, rang_y, rang_y + rang_h, "south", site_w, site_d, margin)
    elif access_side == "north":
        rang_h    = max(LKW_STREIFEN_TIEFE, site_d - (hy + hd) - margin - 2)
        rang_y    = site_d - rang_h - margin
        rang_x    = margin
        rang_w    = site_w - 2 * margin
        schleife  = _u_schleife(hx, hy, hw, hd, rang_y, rang_y + rang_h, "north", site_w, site_d, margin)
    elif access_side == "west":
        rang_w    = max(LKW_STREIFEN_TIEFE, hx - margin - 2)
        rang_x    = margin
        rang_y    = margin
        rang_h    = site_d - 2 * margin
        schleife  = _l_schleife(hx, hy, hw, hd, rang_x, rang_x + rang_w, "west", site_w, site_d, margin)
    else:  # east
        rang_x    = hx + hw + 2
        rang_w    = max(LKW_STREIFEN_TIEFE, site_w - rang_x - margin)
        rang_y    = margin
        rang_h    = site_d - 2 * margin
        schleife  = _l_schleife(hx, hy, hw, hd, rang_x, rang_x + rang_w, "east", site_w, site_d, margin)

    # Rangierzone als Rechteck-Descriptor
    rz_b = round(min(rang_w, site_w - 2 * margin), 2)
    rz_t = round(min(rang_h, LKW_STREIFEN_TIEFE), 2)
    rangierzone = {
        "name":       "Rangierzone (LKW)",
        "x":          round(max(margin, rang_x), 2),
        "y":          round(max(margin, rang_y), 2),
        "breite_m":   rz_b,
        "tiefe_m":    rz_t,
        "flaeche_m2": round(rz_b * rz_t, 1),
        "typ":        "rangier",
        "farbe":      "#E8D5B7",
    }

    erschliessung_flaeche = rangierzone["flaeche_m2"]

    return {
        "lkw_schleife_punkte":   schleife,
        "rangierzone":           rangierzone,
        "erschliessungsflaeche_m2": round(erschliessung_flaeche, 1),
        "access_side":           access_side,
    }


def _u_schleife(
    hx: float, hy: float, hw: float, hd: float,
    rang_y0: float, rang_y1: float,
    side: str,
    site_w: float, site_d: float, margin: float,
) -> list[list[float]]:
    """Erzeugt Punkte einer U-förmigen LKW-Schleife (south/north)."""
    left  = max(margin, hx - 8)
    right = min(site_w - margin, hx + hw + 8)
    if side == "south":
        return [
            [left,  rang_y0], [right, rang_y0],
            [right, rang_y1], [left,  rang_y1], [left, rang_y0],
        ]
    else:  # north
        return [
            [left,  rang_y0], [right, rang_y0],
            [right, rang_y1], [left,  rang_y1], [left, rang_y0],
        ]


def _l_schleife(
    hx: float, hy: float, hw: float, hd: float,
    rang_x0: float, rang_x1: float,
    side: str,
    site_w: float, site_d: float, margin: float,
) -> list[list[float]]:
    """Erzeugt Punkte einer L-förmigen LKW-Schleife (west/east)."""
    bot = max(margin, hy - 8)
    top = min(site_d - margin, hy + hd + 8)
    return [
        [rang_x0, bot], [rang_x1, bot],
        [rang_x1, top], [rang_x0, top], [rang_x0, bot],
    ]


# ---------------------------------------------------------------------------
# Freizonen: Stellplätze + Grünflächen
# ---------------------------------------------------------------------------

def _compute_freizonen(
    *,
    hauptgebaeude: dict,
    nebenbauten: list[dict],
    erschliessung: dict,
    site_w: float,
    site_d: float,
    access_side: str,
) -> list[dict]:
    """Berechnet Stellplatzfelder und Grünflächen aus dem Restgrundstück."""
    freizonen: list[dict] = []
    margin = ABSTANDSFLAECHE_M
    rz = erschliessung["rangierzone"]
    hx = hauptgebaeude["x"]
    hy = hauptgebaeude["y"]
    hw = hauptgebaeude["breite_m"]
    hd = hauptgebaeude["tiefe_m"]

    if access_side == "south":
        # PKW-Stellplätze: südlicher Streifen (nach Rangierzone)
        sp_y = rz["y"] + rz["tiefe_m"] + 1.0
        sp_h = max(PKW_STREIFEN_TIEFE, hy - sp_y - 2.0)
        sp_w = site_w - 2 * margin
        if sp_h > 5:
            freizonen.append(_stellplatzfeld(margin, sp_y, sp_w, sp_h))

        # Grünfläche: verbleibende Ecken
        freizonen.extend(_gruenflaeche_ecken(
            hx, hy, hw, hd, site_w, site_d, margin,
            exclude_south=True,
        ))

    elif access_side == "north":
        sp_y = site_d - margin - PKW_STREIFEN_TIEFE - rz["tiefe_m"] - 1.0
        sp_h = PKW_STREIFEN_TIEFE
        sp_w = site_w - 2 * margin
        if sp_y > margin and sp_h > 5:
            freizonen.append(_stellplatzfeld(margin, sp_y, sp_w, sp_h))
        freizonen.extend(_gruenflaeche_ecken(hx, hy, hw, hd, site_w, site_d, margin))

    elif access_side == "west":
        sp_x = rz["x"] + rz["breite_m"] + 1.0
        sp_w = max(8, hx - sp_x - 2.0)
        sp_h = site_d - 2 * margin
        if sp_w >= 8:
            freizonen.append(_stellplatzfeld(sp_x, margin, sp_w, sp_h))
        freizonen.extend(_gruenflaeche_ecken(hx, hy, hw, hd, site_w, site_d, margin))

    else:  # east
        # Zufahrt von Osten → Gebäude links; Stellplätze zwischen Gebäude und Rangierzone
        rz_left = rz["x"]
        sp_x = hx + hw + 2.0
        sp_w = max(0, rz_left - sp_x - 1.0)
        sp_h = site_d - 2 * margin
        if sp_w >= 8:
            freizonen.append(_stellplatzfeld(sp_x, margin, sp_w, sp_h))
        else:
            # Alternativ: Stellplätze nördlich des Gebäudes
            sp_north_y = hy + hd + 2.0
            sp_north_h = max(0, site_d - margin - sp_north_y)
            sp_north_w = hw
            if sp_north_h >= 8:
                freizonen.append(_stellplatzfeld(hx, sp_north_y, sp_north_w, sp_north_h))
        freizonen.extend(_gruenflaeche_ecken(hx, hy, hw, hd, site_w, site_d, margin))

    return freizonen


def _stellplatzfeld(x: float, y: float, w: float, h: float) -> dict:
    """Beschreibt ein Stellplatzfeld (Rechteck)."""
    n_reihen = max(1, int(h / (SP_TIEFE_M + 0.5)))
    n_plaetze_reihe = max(1, int(w / SP_BREITE_M))
    n_total = n_reihen * n_plaetze_reihe
    return {
        "name":       f"Stellplätze (~{n_total} SP)",
        "x":          round(x, 2),
        "y":          round(y, 2),
        "breite_m":   round(w, 2),
        "tiefe_m":    round(h, 2),
        "flaeche_m2": round(w * h, 1),
        "typ":        "stellplatz",
        "farbe":      "#F5F0DC",
        "anzahl_sp":  n_total,
    }


def _gruenflaeche_ecken(
    hx: float, hy: float, hw: float, hd: float,
    site_w: float, site_d: float, margin: float,
    exclude_south: bool = False,
) -> list[dict]:
    """Erzeugt Grünflächen-Rechtecke an den verbleibenden Rändern."""
    gruen: list[dict] = []
    min_size = 4.0  # Minimum 4m × 4m für eine Grünfläche

    def _add(x: float, y: float, w: float, h: float, label: str) -> None:
        if w >= min_size and h >= min_size:
            gruen.append({
                "name":       label,
                "x":          round(max(margin * 0.5, x), 2),
                "y":          round(max(margin * 0.5, y), 2),
                "breite_m":   round(min(w, site_w - margin), 2),
                "tiefe_m":    round(min(h, site_d - margin), 2),
                "flaeche_m2": round(w * h, 1),
                "typ":        "gruen",
                "farbe":      "#A8D5A2",
            })

    # Norden (über Gebäude)
    north_h = site_d - margin - (hy + hd)
    if north_h >= min_size:
        _add(hx, hy + hd + 1, hw, north_h - 1, "Grünfläche Nord")

    # Westen (links vom Gebäude)
    west_w = hx - margin
    if west_w >= min_size:
        _add(margin, hy, west_w - 1, hd, "Grünfläche West")

    # Osten (rechts vom Gebäude)
    east_x = hx + hw + 1
    east_w = site_w - margin - east_x
    if east_w >= min_size:
        _add(east_x, hy, east_w, hd, "Grünfläche Ost")

    if not exclude_south:
        south_h = hy - margin
        if south_h >= min_size:
            _add(hx, margin, hw, south_h - 1, "Grünfläche Süd")

    return gruen


# ---------------------------------------------------------------------------
# Rechteck-Union (Axis-Aligned)
# ---------------------------------------------------------------------------

def _rect_union_area(rects: list[tuple[float, float, float, float]]) -> float:
    """Berechnet die Fläche der Vereinigung achsenparalleler Rechtecke.

    Methode: Koordinaten-Kompression + Sweep (exakt, O(n²) — für n < 50 ausreichend).
    Jedes Rechteck als (x0, y0, x1, y1).
    """
    if not rects:
        return 0.0

    # Alle x- und y-Koordinaten sammeln und sortieren
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})

    total = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx = (xs[i] + xs[i + 1]) / 2
            cy = (ys[j] + ys[j + 1]) / 2
            # Prüfe ob diese Zelle von mindestens einem Rechteck abgedeckt wird
            covered = any(
                r[0] <= cx <= r[2] and r[1] <= cy <= r[3]
                for r in rects
            )
            if covered:
                total += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return total


def _to_rect(d: dict) -> tuple[float, float, float, float]:
    """Konvertiert ein {x, y, breite_m, tiefe_m}-Dict in (x0, y0, x1, y1)."""
    x0 = float(d.get("x", 0))
    y0 = float(d.get("y", 0))
    return (x0, y0, x0 + float(d.get("breite_m", 0)), y0 + float(d.get("tiefe_m", 0)))


# ---------------------------------------------------------------------------
# LBO-Stellplatznachweis
# ---------------------------------------------------------------------------

def _stellplatz_soll(
    briefing: dict | None,
    hauptgebaeude: dict,
    *,
    rules: dict | None = None,
) -> dict[str, Any]:
    """Berechnet den Stellplatz-Soll aus dem Briefing nach LBO (Orientierungswerte).

    Ohne Briefing: Schätzung aus Gebäudegrundfläche (65% Produktion, 35% Büro).
    Schlüssel kommen aus rules_masterplan.yaml (Fallback: hardcodierte LBO-Werte).
    """
    # Schlüssel aus YAML lesen (Fallback: LBO-Standardwerte)
    sp_cfg = (rules or {}).get("stellplatzschluessel") or {}
    je_prod  = float(sp_cfg.get("produktion_je_100m2", 1)) * 100   # m² je SP
    je_lager = float(sp_cfg.get("lager_je_200m2",     1)) * 200
    je_buero = float(sp_cfg.get("buero_je_30m2",      1)) *  30
    sp_lkw   = int(sp_cfg.get("lkw_stellplatz_min", 2))

    if briefing:
        prod_fp  = float(briefing.get("produktionsflaeche") or 0)
        lager_fp = float(briefing.get("lager_rohstoffe") or 0) + float(briefing.get("lager_fertigwaren") or 0)
        buero_fp = float(briefing.get("buero_nuf2") or 0)
    else:
        hg = float(hauptgebaeude["flaeche_m2"])
        prod_fp  = hg * 0.65
        lager_fp = hg * 0.15
        buero_fp = hg * 0.35

    sp_prod   = math.ceil(prod_fp  / je_prod)
    sp_lager  = math.ceil(lager_fp / je_lager)
    sp_buero  = math.ceil(buero_fp / je_buero)
    sp_gesamt = sp_prod + sp_lager + sp_buero

    return {
        "sp_soll_gesamt":  sp_gesamt,
        "sp_soll_pkw":     sp_prod + sp_lager + sp_buero,
        "sp_soll_lkw":     sp_lkw,
        "sp_soll_aufschl": {
            "produktion":  sp_prod,
            "lager":       sp_lager,
            "buero":       sp_buero,
        },
    }


# ---------------------------------------------------------------------------
# Flächenbilanz
# ---------------------------------------------------------------------------

def _compute_flaechenbilanz(
    *,
    site_a: float,
    hauptgebaeude: dict,
    gebaeude: list[dict] | None = None,
    nebenbauten: list[dict],
    erschliessung: dict,
    freizonen: list[dict],
    geschosse_buero: int,
    briefing: dict | None = None,
    rules: dict | None = None,
) -> dict[str, Any]:
    """Berechnet GRZ, GFZ und Versiegelungsgrad via Rechteck-Union (überlappungskorrigiert)."""

    # ── Einzelflächen (für Tabelle) ─────────────────────────────────────────
    gebaeude = gebaeude or [hauptgebaeude]
    hg_fp      = sum(float(g["flaeche_m2"]) for g in gebaeude)
    nb_fp      = sum(float(n["flaeche_m2"]) for n in nebenbauten)
    erschl_fp  = float(erschliessung["erschliessungsflaeche_m2"])
    rangier_fp = float(erschliessung["rangierzone"]["flaeche_m2"])
    sp_fp      = sum(float(z["flaeche_m2"]) for z in freizonen if z["typ"] == "stellplatz")
    gruen_fp   = sum(float(z["flaeche_m2"]) for z in freizonen if z["typ"] == "gruen")
    aussen_fp  = sum(float(z["flaeche_m2"]) for z in freizonen if z["typ"] == "aussenlager")

    # ── GRZ: Union der Gebäude-Footprints (Hauptgebäude + Nebenbauten) ─────
    gebaeude_rects = [_to_rect(g) for g in gebaeude] + [_to_rect(n) for n in nebenbauten]
    ueberbaut_union = _rect_union_area(gebaeude_rects)
    grz = min(ueberbaut_union / site_a, 1.0)

    # ── GFZ: Geschossfläche (Vereinfachung: 65% Produktion 1G, 35% Büro nG) ──
    produktion_fp   = hg_fp * 0.65
    buero_fp        = hg_fp * 0.35
    geschossflaeche = produktion_fp * 1 + buero_fp * geschosse_buero + nb_fp
    gfz = geschossflaeche / site_a

    # ── Versiegelungsgrad: Union aller versiegelten Flächen ─────────────────
    versiegelt_rects = (
        gebaeude_rects
        + [_to_rect(erschliessung["rangierzone"])]
        + [_to_rect(z) for z in freizonen if z["typ"] in ("stellplatz", "rangier", "aussenlager")]
    )
    versiegelt_union = _rect_union_area(versiegelt_rects)
    versiegelungsgrad = min(versiegelt_union / site_a, 0.99)

    # ── Grenzwerte aus YAML (Fallback: BauNVO-Standardwerte) ───────────────
    grz_cfg = (rules or {}).get("grz") or {}
    bilanz_cfg = (rules or {}).get("flaechenbilanz") or {}
    grz_grenzwert = float(grz_cfg.get("grenzwert_gi", 0.60))
    versieg_ref   = float(bilanz_cfg.get("versiegelung_max_pct", 0.80))

    # ── Stellplatz-Nachweis nach LBO ────────────────────────────────────────
    sp_ist    = sum(z.get("anzahl_sp", 0) for z in freizonen if z["typ"] == "stellplatz")
    sp_nachweis = _stellplatz_soll(briefing, {**hauptgebaeude, "flaeche_m2": hg_fp}, rules=rules)
    sp_soll   = sp_nachweis["sp_soll_gesamt"]
    sp_deckung = round(sp_ist / sp_soll * 100) if sp_soll else 100

    return {
        "grundstueck_m2":        round(site_a, 0),
        "hauptgebaeude_m2":      round(hg_fp, 0),
        "nebenbauten_m2":        round(nb_fp, 0),
        "erschliessung_m2":      round(erschl_fp, 0),
        "rangierzone_m2":        round(rangier_fp, 0),
        "stellplatz_m2":         round(sp_fp, 0),
        "aussenlager_m2":        round(aussen_fp, 0),
        "gruenflaeche_m2":       round(gruen_fp, 0),
        "ueberbaut_m2":          round(ueberbaut_union, 0),
        "geschossflaeche_m2":    round(geschossflaeche, 0),
        "grz":                   round(grz, 3),
        "gfz":                   round(gfz, 3),
        "versiegelungsgrad":     round(versiegelungsgrad, 3),
        "grz_grenzwert":         grz_grenzwert,
        "versiegelungsgrad_ref": versieg_ref,
        "stellplaetze_anzahl":   sp_ist,
        "stellplaetze_soll":     sp_soll,
        "stellplaetze_deckung_pct": sp_deckung,
        "stellplaetze_aufschluessel": sp_nachweis["sp_soll_aufschl"],
    }

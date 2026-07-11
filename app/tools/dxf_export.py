"""
AID Demo – DXF-Export
Exportiert eine Layoutvariante als AutoCAD-DXF (R2010) mit Layer-Struktur.
"""
from __future__ import annotations
import io
import math
from pathlib import Path
from typing import Any


# ACI-Farbnummer je DIN-Kategorie
_DIN_COLOR: dict[str, int] = {
    "NUF 2": 5,   # blau
    "NUF 3": 2,   # gelb
    "NUF 4": 3,   # grün
    "NUF 7": 6,   # magenta
    "TF":    1,   # rot
    "VF":    4,   # cyan
}

_DIN_HATCH: dict[str, tuple[str, float]] = {
    "NUF 2": ("ANSI31", 1.5),
    "NUF 3": ("ANSI31", 1.0),
    "NUF 4": ("ANSI37", 2.0),
    "NUF 7": ("NET",    1.5),
    "TF":    ("ANSI36", 1.0),
    "VF":    ("ANSI31", 4.0),
}

_DIN_LAYER: dict[str, str] = {
    "NUF 2": "GEBAEUDE_NUF2",
    "NUF 3": "GEBAEUDE_NUF3",
    "NUF 4": "GEBAEUDE_NUF4",
    "NUF 7": "GEBAEUDE_NUF7",
    "TF":    "GEBAEUDE_TF",
    "VF":    "GEBAEUDE_VF",
}


def export_layout_to_dxf(
    variant: dict[str, Any],
    site_geometry: dict[str, Any] | None = None,
    briefing: dict[str, Any] | None = None,
) -> bytes:
    """Exportiert eine Layoutvariante als DXF-Datei.

    Args:
        variant:       Varianten-Dict aus PlanningState["variants"][i]
        site_geometry: site_geometry-Dict (optional, für Grundstücksumring)
        briefing:      structured_briefing (optional, für Schriftfeld-Infos)

    Returns:
        DXF-Dateiinhalt als UTF-8-kodierte Bytes.
    """
    import ezdxf
    from ezdxf import colors as dxf_colors

    doc = ezdxf.new(dxfversion="R2010")
    doc.header["$INSUNITS"] = 6  # Meter
    msp = doc.modelspace()

    # ── Layer anlegen ─────────────────────────────────────────────────────────
    layer_defs = [
        ("GRUNDSTUECK",    3, 50, "CONTINUOUS"),
        ("ABSTANDSFLAECHE",3, 13, "DASHED"),
        ("GEBAEUDE_NUF2",  5, 35, "CONTINUOUS"),
        ("GEBAEUDE_NUF3",  2, 35, "CONTINUOUS"),
        ("GEBAEUDE_NUF4",  3, 35, "CONTINUOUS"),
        ("GEBAEUDE_NUF7",  6, 25, "CONTINUOUS"),
        ("GEBAEUDE_TF",    1, 25, "CONTINUOUS"),
        ("GEBAEUDE_VF",    4, 18, "CONTINUOUS"),
        ("RESERVE",        8, 13, "DASHED"),
        ("RASTER",         8, 13, "CONTINUOUS"),
        ("ERSCHLIESSUNG",  1, 25, "CONTINUOUS"),
        ("BESCHRIFTUNG",   7, 18, "CONTINUOUS"),
        ("SCHRIFTFELD",    7, 25, "CONTINUOUS"),
    ]
    for name, color, lw, linetype in layer_defs:
        layer = doc.layers.new(name)
        layer.color = color
        layer.lineweight = lw
        if linetype != "CONTINUOUS":
            try:
                doc.linetypes.get(linetype)
            except Exception:
                doc.linetypes.new(linetype, dxfattribs={"description": linetype,
                                                          "pattern": [0.5, 0.5, -0.25]})
            layer.linetype = linetype

    # ── Grundstück ────────────────────────────────────────────────────────────
    site_geo = site_geometry or variant.get("site_geometry") or {}
    polygon = site_geo.get("polygon", [])
    if polygon:
        pts = [(p[0], p[1]) for p in polygon]
        msp.add_lwpolyline(pts, dxfattribs={"layer": "GRUNDSTUECK", "closed": True})

        # Abstandsfläche (Bauwich)
        planning = site_geo.get("planning", {})
        abstand = float(planning.get("max_gebaeudehoehe_m", 12)) * float(planning.get("abstandsfaktor", 0.4))
        if abstand > 0.5:
            try:
                from shapely.geometry import Polygon as ShapelyPoly
                inner = ShapelyPoly([(p[0], p[1]) for p in polygon]).buffer(-abstand)
                if not inner.is_empty:
                    ix, iy = inner.exterior.xy
                    inner_pts = list(zip(ix, iy))
                    msp.add_lwpolyline(inner_pts, dxfattribs={
                        "layer": "ABSTANDSFLAECHE", "closed": True
                    })
            except ImportError:
                pass  # shapely optional hier

    # ── Zufahrten ─────────────────────────────────────────────────────────────
    for ap in site_geo.get("access_points", []):
        pt = ap.get("point", [0, 0])
        w = float(ap.get("width_m", 7.5))
        side = ap.get("side", "south")
        if side in ("north", "south"):
            pts_ap = [(pt[0] - w/2, pt[1]), (pt[0] + w/2, pt[1])]
        else:
            pts_ap = [(pt[0], pt[1] - w/2), (pt[0], pt[1] + w/2)]
        msp.add_lwpolyline(pts_ap, dxfattribs={"layer": "ERSCHLIESSUNG"})

    # ── Stützenraster ─────────────────────────────────────────────────────────
    raster_x = float(variant.get("raster_x", 18.0))
    raster_y = float(variant.get("raster_y", 12.0))
    env = variant.get("building_envelope") or {}
    env_x = float(env.get("x", 0))
    env_y = float(env.get("y", 0))
    env_w = float(env.get("width_m", variant.get("site_breite", 100)))
    env_d = float(env.get("depth_m", variant.get("site_tiefe", 96)))

    x = env_x
    while x <= env_x + env_w + 0.01:
        y = env_y
        while y <= env_y + env_d + 0.01:
            msp.add_circle((x, y), radius=0.3, dxfattribs={"layer": "RASTER"})
            y += raster_y
        x += raster_x

    # ── Zonen ─────────────────────────────────────────────────────────────────
    zonen = variant.get("zonen", [])
    for zone in zonen:
        x = float(zone.get("x", 0))
        y = float(zone.get("y", 0))
        w = float(zone.get("breite", 1))
        d = float(zone.get("tiefe", 1))
        din = zone.get("din_kategorie", "NUF 3")
        name = zone.get("name", din)
        is_reserve = bool(zone.get("schraffur", False))

        layer = "RESERVE" if is_reserve else _DIN_LAYER.get(din, "GEBAEUDE_NUF3")
        pts_zone = [(x, y), (x+w, y), (x+w, y+d), (x, y+d)]

        # Umriss
        msp.add_lwpolyline(pts_zone, dxfattribs={"layer": layer, "closed": True})

        # Schraffur
        if is_reserve:
            pattern_name, pattern_scale = "ANSI31", 6.0
        else:
            pattern_name, pattern_scale = _DIN_HATCH.get(din, ("ANSI31", 2.0))
        try:
            color = 8 if is_reserve else _DIN_COLOR.get(din, 7)
            hatch = msp.add_hatch(color=color, dxfattribs={"layer": layer})
            hatch.paths.add_polyline_path(pts_zone, is_closed=True)
            hatch.set_pattern_fill(pattern_name, scale=pattern_scale)
            hatch.transparency = 0.7   # 70 % transparent → Raster sichtbar
        except Exception:
            pass  # Hatch-Fehler nicht fatal

        # Beschriftung (Zonenname + Fläche)
        cx, cy = x + w / 2, y + d / 2
        flaeche = zone.get("planned_area_m2") or zone.get("flaeche_m2", w * d)
        label = f"{name}\n{flaeche:.0f} m²"
        msp.add_mtext(label, dxfattribs={
            "layer":         "BESCHRIFTUNG",
            "insert":        (cx, cy),
            "char_height":   max(1.0, min(w, d) * 0.08),
            "attachment_point": 5,   # Middle Center
        })

    # ── Schriftfeld (Plankopf) ────────────────────────────────────────────────
    # Unten rechts im Grundstücks-Bounding-Box
    site_w = float(site_geo.get("width_m", env_w))
    site_d = float(site_geo.get("depth_m", env_d))
    sf_w, sf_h = 80.0, 30.0   # Schriftfeld: 80 m × 30 m (maßstabstreu)
    sf_x = site_w - sf_w
    sf_y = -sf_h - 5.0         # 5 m unterhalb Grundstücks-Südkante

    sf_pts = [(sf_x, sf_y), (sf_x+sf_w, sf_y), (sf_x+sf_w, sf_y+sf_h), (sf_x, sf_y+sf_h)]
    msp.add_lwpolyline(sf_pts, dxfattribs={"layer": "SCHRIFTFELD", "closed": True})
    # Trennlinie horizontal
    msp.add_line((sf_x, sf_y + sf_h/2), (sf_x+sf_w, sf_y + sf_h/2),
                 dxfattribs={"layer": "SCHRIFTFELD"})
    # Trennlinie vertikal bei 60 %
    msp.add_line((sf_x + sf_w*0.6, sf_y), (sf_x + sf_w*0.6, sf_y+sf_h),
                 dxfattribs={"layer": "SCHRIFTFELD"})

    # Texte
    nutzungstyp = (briefing or {}).get("nutzungstyp", "Industriebau")
    variante_name = variant.get("name", "").replace("_", " ")
    texts = [
        (sf_x + 1,          sf_y + sf_h - 3,  2.5, f"PROJEKT: AID Demo – {nutzungstyp}"),
        (sf_x + 1,          sf_y + sf_h/2 - 3, 2.5, f"VARIANTE: {variante_name}"),
        (sf_x + sf_w*0.61,  sf_y + sf_h - 3,  2.0, "INHALT:"),
        (sf_x + sf_w*0.61,  sf_y + sf_h - 6,  2.5, "Lageplan EG"),
        (sf_x + sf_w*0.61,  sf_y + sf_h/2 - 3, 2.0, "ERSTELLT:"),
        (sf_x + sf_w*0.61,  sf_y + sf_h/2 - 6, 2.0, "AID Pipeline"),
    ]
    for tx, ty, th, txt in texts:
        msp.add_text(txt, dxfattribs={"layer": "SCHRIFTFELD",
                                       "insert": (tx, ty),
                                       "height": th})

    # ── Serialisieren ─────────────────────────────────────────────────────────
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def save_layout_dxf(
    variant: dict[str, Any],
    output_path: Path,
    site_geometry: dict[str, Any] | None = None,
    briefing: dict[str, Any] | None = None,
) -> Path:
    """Speichert DXF als Datei. Gibt Pfad zurück."""
    dxf_bytes = export_layout_to_dxf(variant, site_geometry, briefing)
    dxf_path = output_path.with_suffix(".dxf")
    dxf_path.write_bytes(dxf_bytes)
    return dxf_path

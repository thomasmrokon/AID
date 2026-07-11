"""
AID Demo — Layout-Rendering
Erzeugt professionelle Layouts als PNG-Dateien mit matplotlib.
"""

from __future__ import annotations
import math
from pathlib import Path
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyArrow
from matplotlib.lines import Line2D
import numpy as np
from app.tools.geometry import Zone

# ---------------------------------------------------------------------------
# MEP-Konstanten (gespiegelt aus mep.py für drawing-unabhängige Nutzung)
# ---------------------------------------------------------------------------

_GEWERK_FARBEN: dict[str, str] = {
    "elektro_stark":      "#FFD700",
    "daten_it":           "#00BFFF",
    "lueftung_rlt":       "#90EE90",
    "druckluft":          "#FFA07A",
    "wasser_trinkwasser": "#4169E1",
    "abwasser":           "#8B4513",
    "sprinkler":          "#FF6347",
    "kaelte":             "#87CEEB",
    "usv_notstrom":       "#DA70D6",
}
_GEWERK_LABELS: dict[str, str] = {
    "elektro_stark":      "Elektro",
    "daten_it":           "IT",
    "lueftung_rlt":       "RLT",
    "druckluft":          "Druckluft",
    "wasser_trinkwasser": "Wasser",
    "abwasser":           "Abwasser",
    "sprinkler":          "Sprinkler",
    "kaelte":             "Kälte",
    "usv_notstrom":       "USV",
}
# Zeichenpriorität: physisch größte Trasse zuerst
_GEWERK_PRIO = [
    "lueftung_rlt", "druckluft", "kaelte", "sprinkler",
    "wasser_trinkwasser", "abwasser", "elektro_stark", "daten_it",
]


class SiteTransform:
    """Transformiert Koordinaten aus dem rotierten Baufeld-Referenzrahmen in Globalkoordinaten.

    Zonenkoordinaten liegen im rotierten Referenzrahmen (Hauptachse des Grundstuecks
    entlang der X-Achse). Diese Klasse dreht sie zurueck in die globale Anzeigeebene.
    Bei angle_deg == 0 ist die Transformation die Identitaet — rueckwaertskompatibel.
    """

    def __init__(self, angle_deg: float = 0.0, cx: float = 0.0, cy: float = 0.0):
        self.angle_deg = float(angle_deg)
        self.cx = float(cx)
        self.cy = float(cy)
        _a = math.radians(self.angle_deg)
        self._cos = math.cos(_a)
        self._sin = math.sin(_a)

    @property
    def is_rotated(self) -> bool:
        return abs(self.angle_deg) > 0.05

    def pt(self, x: float, y: float) -> tuple[float, float]:
        """Rotiert einen Punkt aus dem rotierten Rahmen in Globalkoordinaten."""
        if not self.is_rotated:
            return float(x), float(y)
        dx, dy = float(x) - self.cx, float(y) - self.cy
        return (
            self.cx + dx * self._cos - dy * self._sin,
            self.cy + dx * self._sin + dy * self._cos,
        )

    def corners(self, x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
        """Vier Ecken eines achsparallelen Rechtecks, transformiert in Globalkoordinaten."""
        return [self.pt(x, y), self.pt(x + w, y), self.pt(x + w, y + h), self.pt(x, y + h)]

    @classmethod
    def from_envelope(cls, envelope: dict | None) -> "SiteTransform":
        if not envelope:
            return cls()
        return cls(
            angle_deg=float(envelope.get("site_angle_deg") or 0.0),
            cx=float(envelope.get("site_centroid_x") or 0.0),
            cy=float(envelope.get("site_centroid_y") or 0.0),
        )

_TRAGWERK_LABELS: dict[str, str] = {
    "stahl":       "Stahlbau",
    "stahlbeton":  "Stahlbetonbau",
    "holz":        "Holzbau",
    "hybrid":      "Hybrid",
}
_LASTKLASSE_LABELS: dict[str, str] = {
    "leicht": "≤5 kN/m²",
    "mittel":  "≤10 kN/m²",
    "schwer":  "≤20 kN/m²",
    "kran":    "Kranbahn",
}


def _load_tragwerk_traufhoehe(typologie: str) -> float | None:
    """Liest Traufhöhe aus rules_tragwerk.yaml für die gewählte Typologie."""
    try:
        p = Path(__file__).parent.parent / "data" / "rules_tragwerk.yaml"
        with open(p, encoding="utf-8") as f:
            rules = yaml.safe_load(f) or {}
        return rules.get("typologien", {}).get(typologie, {}).get("traufhoehe_standard_m")
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Farbpalette
# ---------------------------------------------------------------------------

ZONE_FARBEN: dict[str, str] = {
    # Produktion
    "Wareneingang":         "#5B8DB8",
    "Lager Rohstoffe":      "#F4A261",
    "Lager Fertigwaren":    "#E9C46A",
    "Produktion":           "#2A9D8F",
    "Qualitätssicherung":   "#E76F51",
    "Versand":              "#264653",
    "Büro / Verwaltung":    "#A8DADC",
    "Technik":              "#8D99AE",
    "Sozial":               "#B7E4C7",
    # Logistik
    "Lager":                "#F4A261",
    "Kommissionierung":     "#E9C46A",
    "Retouren":             "#E76F51",
    # Data Center
    "Whitespace IT":        "#2A9D8F",
    "USV / Trafo":          "#8D99AE",
    "Kühlung":              "#5B8DB8",
    "Notstrom":             "#E76F51",
    "NOC":                  "#A8DADC",
    "Staging":              "#F4A261",
    "Einspeisung":          "#264653",
    "Erschließung":         "#C9CDD2",
    "Erschliessung":        "#C9CDD2",
    # Erweiterung / Außenfläche
    "Erweiterungsreserve":  "#F5F5F5",
    "Freifläche":           "#D8E4C8",   # gleiche Farbe wie Site-Polygon → wirkt als Außenanlage
}


def _zone_farbe(name: str, farbe: str) -> str:
    return ZONE_FARBEN.get(name, farbe)


def _legend_label(zone: Zone) -> str:
    planned = zone.planned_area_m2 if zone.planned_area_m2 is not None else zone.gezeichnete_flaeche * zone.floors
    if zone.din_kategorie == "VF":
        return f"{zone.name}: {planned:.0f} m²"
    floors = f" | {zone.floors}G" if zone.floors > 1 else ""
    delta = f" | d {zone.delta_pct:+.0f}%" if getattr(zone, "delta_pct", 0) else ""
    return f"{zone.name}: {planned:.0f} m²{floors}{delta}"


# ---------------------------------------------------------------------------
# Stellplatz-Berechnung
# ---------------------------------------------------------------------------

STELLPLATZ_BREITE = 2.5   # m
STELLPLATZ_TIEFE  = 5.0   # m
FAHRGANG_BREITE   = 6.0   # m (Einbahnverkehr)
STELLPLATZ_REIHE_FLAECH = STELLPLATZ_BREITE * (STELLPLATZ_TIEFE + FAHRGANG_BREITE / 2)  # ~20 m² pro SP


def berechne_stellplaetze(site_area_m2: float, building_footprint_m2: float) -> int:
    """Schätzt mögliche Stellplätze auf der Restfläche nach grober Abzugsregel."""
    remaining = max(0.0, site_area_m2 - building_footprint_m2)
    # ~60 % der Restfläche ist parkierbar (Wege, Bepflanzung, Manövrierraum abgezogen)
    parkierbar = remaining * 0.60
    return max(0, int(parkierbar / STELLPLATZ_REIHE_FLAECH))


# ---------------------------------------------------------------------------
# Typologie-Ableitung
# ---------------------------------------------------------------------------

def _detect_typology(zonen: list[Zone], hint: str | None = None) -> str:
    """Erkennt die tatsächliche Topologie aus den Zonen oder einem Hint.

    hint:  Typologiename aus typology_assignments (bevorzugt, wenn übergeben).
    Fallback-Heuristik: 'block_reserve' wenn Erweiterungsreserve vorhanden,
    sonst 'squarified' (Dreispalten-Columns, aktiver Standard-Algorithmus).
    """
    _valid = {"optimized", "block_reserve", "squarified", "recursive"}
    if hint and hint in _valid:
        return hint
    if any("Erweiterung" in z.name for z in zonen):
        return "block_reserve"
    return "squarified"


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def zeichne_layout(
    variante_name:      str,
    beschreibung:       str,
    zonen:              list[Zone],
    site_breite:        float,
    site_tiefe:         float,
    raster_x:           float,
    raster_y:           float,
    scores:             dict,
    gewichtung:         dict,
    output_path:        Path,
    nutzungstyp:        str = "",
    site_geometry:      dict | None = None,
    topology:           dict | None = None,
    adjacency_weights:  dict | None = None,
    tragwerk_config:      dict | None = None,
    mep_variant_data:     dict | None = None,
    building_envelope:    dict | None = None,
    erschliessungsgraph:  dict | None = None,
    tree_topology:        str | None = None,
    show_optimizer_overlay: bool = False,
    show_legend:          bool = True,   # False → Legende nur als Streamlit-Popover
    show_violations:      bool = True,   # False → Warnungen nur als Streamlit-Popover
    typology_key:         str | None = None,  # Overrides _detect_typology() für Badge
) -> None:
    """Rendert ein Layout als PNG und speichert es unter output_path."""

    fig, ax = plt.subplots(figsize=(15, 10))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#E8EDF0")

    # Koordinatentransformation aus Baufeld-Referenzrahmen → Globalkoordinaten
    tr = SiteTransform.from_envelope(building_envelope)

    # --- Grundstück zeichnen ---
    _draw_site(ax, site_geometry, site_breite, site_tiefe)

    # --- Stützenraster (zonenspezifisch, Stützen an Zonengrenzen) ---
    _draw_grid(ax, zonen, raster_x, raster_y, tr)

    if show_optimizer_overlay and tree_topology:
        _draw_slicing_tree_overlay(ax, zonen, tree_topology, tr)

    # --- Zonen ---
    for zone in zonen:
        _draw_zone(ax, zone, tr)

    # --- Techniktrassen ---
    trassen_laenge = _draw_techniktrassen(ax, zonen, mep_variant_data, tr)

    # --- Erschließungsgraph ---
    if erschliessungsgraph:
        _draw_erschliessungsgraph(ax, zonen, erschliessungsgraph, tr)

    # --- Zonenbeschriftung ---
    for zone in zonen:
        _draw_zone_label(ax, zone, tr)

    # --- Zufahrten ---
    if site_geometry:
        _draw_access_points(ax, site_geometry, site_breite, site_tiefe)

    # --- Stellplätze ---
    building_fp = sum(
        z.breite * z.tiefe
        for z in zonen
        if not z.schraffur and z.din_kategorie != "VF"
    )
    if (site_geometry or {}).get("exclude_site_parking"):
        gezeichnete_stellplaetze = 0
    else:
        site_area = float((site_geometry or {}).get("area_m2") or site_breite * site_tiefe)
        stellplaetze = berechne_stellplaetze(site_area, building_fp)
        gezeichnete_stellplaetze = _draw_parking_info(
            ax, site_geometry, site_breite, site_tiefe, zonen, stellplaetze, tr, building_envelope
        )

    # --- Legende (nur wenn nicht als Streamlit-Popover ausgelagert) ---
    if show_legend:
        _draw_legend(ax, zonen)

    # --- Badges: Typologie + Stellplätze + Techniktrassen ---
    _draw_badges(ax, zonen, site_breite, site_tiefe, gezeichnete_stellplaetze, trassen_laenge, typology_key)

    # --- Nordpfeil ---
    _draw_north_arrow(ax, site_breite, site_tiefe)

    # --- Maßstabsleiste ---
    _draw_scalebar(ax, site_tiefe)

    # --- Regelverletzungen (nur wenn nicht als Streamlit-Popover ausgelagert) ---
    if show_violations:
        verstoesse = scores.get("regelverletzungen", [])
        if verstoesse:
            vtext = "WARNUNG: " + "\nWARNUNG: ".join(verstoesse)
            ax.text(0.02, 0.04, vtext,
                    transform=ax.transAxes,
                    ha="left", va="bottom",
                    fontsize=7, color="#C0392B",
                    bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF3F3",
                              edgecolor="#C0392B", alpha=0.9),
                    zorder=10)

    # --- Titel ---
    empfohlen_tag = "  ★ EMPFOHLEN" if scores.get("empfohlen") else ""
    ax.set_title(
        f"Variante {variante_name}{empfohlen_tag}\n"
        f"{str(nutzungstyp)} — {beschreibung}",
        fontsize=12, fontweight="bold", pad=14,
        color="#222222"
    )

    # --- Achsen — Site-Polygon-Bounds nutzen wenn verfügbar (rotierte Grundstücke) ---
    if site_geometry and site_geometry.get("polygon"):
        from shapely.geometry import Polygon as _SPoly
        try:
            _sp = _SPoly(site_geometry["polygon"])
            _bx0, _by0, _bx1, _by1 = _sp.bounds
            _w, _h = _bx1 - _bx0, _by1 - _by0
            margin = max(8.0, min(_w, _h) * 0.10)
            ax.set_xlim(_bx0 - margin, _bx1 + margin * 2)
            ax.set_ylim(_by0 - margin * 1.2, _by1 + margin)
        except Exception:
            margin = max(8.0, min(site_breite, site_tiefe) * 0.10)
            ax.set_xlim(-margin, site_breite + margin * 2)
            ax.set_ylim(-margin * 1.2, site_tiefe + margin)
    else:
        margin = max(8.0, min(site_breite, site_tiefe) * 0.10)
        ax.set_xlim(-margin, site_breite + margin * 2)
        ax.set_ylim(-margin * 1.2, site_tiefe + margin)
    ax.set_aspect("equal")
    ax.set_xlabel("Breite [m]", fontsize=9)
    ax.set_ylabel("Tiefe [m]", fontsize=9)
    ax.tick_params(labelsize=8)

    # --- Tragwerk-Badge (Sprint 4B) ---
    if tragwerk_config:
        _draw_tragwerk_badge(ax, site_breite, site_tiefe, tragwerk_config)

    # --- MEP-Gewerk-Legende (Sprint 4C, nur wenn Legende im Bild) ---
    if show_legend and mep_variant_data:
        _draw_mep_gewerk_legende(ax, mep_variant_data)

    # --- Funktionsgraph-Overlay (optional) ---
    if topology:
        _draw_graph_overlay(ax, zonen, topology, adjacency_weights)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _draw_erschliessungsgraph(
    ax,
    zonen: list,
    graph: dict,
    tr: "SiteTransform | None" = None,
) -> None:
    """Visualisiert den Erschließungsgraphen über dem Layout.

    direkt-Kanten:   gestrichelt blau zwischen Wandmittelpunkten
    korridor-Kanten: gepunktet orange zwischen Zonen-Zentroiden
    isolierte Zonen: Warnsymbol am Zentroid
    """
    _TOL = 0.5  # m — Toleranz Wanderkennung für Zeichnung
    rotated = tr is not None and tr.is_rotated

    zone_map: dict[str, object] = {z.name: z for z in zonen if hasattr(z, "name")}

    def _pt(x: float, y: float) -> tuple[float, float]:
        return tr.pt(x, y) if rotated else (x, y)

    def _wall_midpoint(a, b) -> tuple[float, float] | None:
        ax0, ax1 = a.x, a.x + a.breite
        ay0, ay1 = a.y, a.y + a.tiefe
        bx0, bx1 = b.x, b.x + b.breite
        by0, by1 = b.y, b.y + b.tiefe
        if abs(ax1 - bx0) < _TOL or abs(bx1 - ax0) < _TOL:
            x_w = ax1 if abs(ax1 - bx0) < _TOL else bx1
            y_w = (max(ay0, by0) + min(ay1, by1)) / 2
            return _pt(x_w, y_w)
        if abs(ay1 - by0) < _TOL or abs(by1 - ay0) < _TOL:
            y_w = ay1 if abs(ay1 - by0) < _TOL else by1
            x_w = (max(ax0, bx0) + min(ax1, bx1)) / 2
            return _pt(x_w, y_w)
        return None

    def _polyline_midpoint(points: list[tuple[float, float]]) -> tuple[float, float]:
        if len(points) < 2:
            return points[0] if points else (0.0, 0.0)

        segments: list[tuple[float, tuple[float, float], tuple[float, float]]] = []
        total = 0.0
        for p0, p1 in zip(points, points[1:]):
            length = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
            if length <= 0:
                continue
            segments.append((length, p0, p1))
            total += length

        if total <= 0:
            return points[len(points) // 2]

        halfway = total / 2
        walked = 0.0
        for length, p0, p1 in segments:
            if walked + length >= halfway:
                t = (halfway - walked) / length
                return (
                    p0[0] + (p1[0] - p0[0]) * t,
                    p0[1] + (p1[1] - p0[1]) * t,
                )
            walked += length
        return segments[-1][2]

    for kante in graph.get("kanten", []):
        za = zone_map.get(kante["von"])
        zb = zone_map.get(kante["nach"])
        if za is None or zb is None:
            continue

        if kante["typ"] == "direkt":
            mid = _wall_midpoint(za, zb)
            if mid:
                ca = _pt(za.x + za.breite / 2, za.y + za.tiefe / 2)
                cb = _pt(zb.x + zb.breite / 2, zb.y + zb.tiefe / 2)
                ax.annotate(
                    "", xy=cb, xytext=ca,
                    arrowprops=dict(
                        arrowstyle="-", color="#5B8FA8",
                        lw=1.2, linestyle="dashed",
                        connectionstyle="arc3,rad=0.0",
                        alpha=0.7,
                    ),
                    zorder=6,
                )
        elif kante["typ"] == "korridor":
            ca = _pt(za.x + za.breite / 2, za.y + za.tiefe / 2)
            cb = _pt(zb.x + zb.breite / 2, zb.y + zb.tiefe / 2)
            pfad_punkte = kante.get("pfad_punkte") or []
            if len(pfad_punkte) >= 2:
                points = [_pt(float(x), float(y)) for x, y in pfad_punkte]
            else:
                points = [ca, cb]

            ax.plot(
                [p[0] for p in points],
                [p[1] for p in points],
                color="#E07B00", lw=1.5, linestyle="--",
                alpha=0.8, zorder=6,
            )
            mx, my = _polyline_midpoint(points)
            pfad_laenge = float(kante.get("pfad_laenge_m") or 0.0)
            ax.text(mx, my, f"~Korridor {pfad_laenge:.0f}m",
                    fontsize=6, color="#E07B00",
                    ha="center", va="center", alpha=0.75, zorder=6)

    for zone_name in graph.get("isolierte_zonen", []):
        z = zone_map.get(zone_name)
        if z:
            cx, cy = _pt(z.x + z.breite / 2, z.y + z.tiefe / 2)
            ax.text(cx, cy + 2, "!", fontsize=10, color="#CC0000",
                    ha="center", va="bottom", fontweight="bold", zorder=7)


def _draw_slicing_tree_overlay(
    ax,
    zonen: list[Zone],
    tree_topology: str,
    tr: SiteTransform | None = None,
) -> None:
    zone_map = {z.name: z for z in zonen if not z.schraffur}
    tree = _parse_slicing_tree(tree_topology)
    if tree is None:
        return

    rotated = tr is not None and tr.is_rotated

    def _pt(x: float, y: float) -> tuple[float, float]:
        return tr.pt(x, y) if rotated else (x, y)

    def _bounds(node) -> tuple[float, float, float, float] | None:
        if isinstance(node, str):
            z = zone_map.get(node)
            if not z:
                return None
            return z.x, z.y, z.x + z.breite, z.y + z.tiefe

        direction, left, right = node
        left_bounds = _bounds(left)
        right_bounds = _bounds(right)
        if not left_bounds or not right_bounds:
            return left_bounds or right_bounds

        lx0, ly0, lx1, ly1 = left_bounds
        rx0, ry0, rx1, ry1 = right_bounds
        x0, y0 = min(lx0, rx0), min(ly0, ry0)
        x1, y1 = max(lx1, rx1), max(ly1, ry1)

        if direction == "V":
            x = (lx1 + rx0) / 2 if lx0 <= rx0 else (rx1 + lx0) / 2
            p0 = _pt(x, y0)
            p1 = _pt(x, y1)
        else:
            y = (ly1 + ry0) / 2 if ly0 <= ry0 else (ry1 + ly0) / 2
            p0 = _pt(x0, y)
            p1 = _pt(x1, y)
        ax.plot(
            [p0[0], p1[0]],
            [p0[1], p1[1]],
            linestyle="--",
            color="#CCCCCC",
            linewidth=0.5,
            alpha=0.5,
            zorder=1,
        )
        return x0, y0, x1, y1

    _bounds(tree)


def _parse_slicing_tree(text: str):
    s = "".join(str(text or "").split())
    if not s:
        return None

    def parse_expr(idx: int):
        if idx >= len(s):
            return None, idx
        if s[idx] in {"H", "V"} and idx + 1 < len(s) and s[idx + 1] == "(":
            direction = s[idx]
            left, idx = parse_expr(idx + 2)
            if idx >= len(s) or s[idx] != "|":
                return None, idx
            right, idx = parse_expr(idx + 1)
            if idx >= len(s) or s[idx] != ")":
                return None, idx
            return (direction, left, right), idx + 1

        start = idx
        while idx < len(s) and s[idx] not in "|)":
            idx += 1
        return s[start:idx], idx

    tree, idx = parse_expr(0)
    if tree is None or idx != len(s):
        return None
    return tree


def zeichne_lageplan_pdf(
    variante_name:      str,
    beschreibung:       str,
    zonen:              list[Zone],
    site_breite:        float,
    site_tiefe:         float,
    raster_x:           float,
    raster_y:           float,
    scores:             dict,
    gewichtung:         dict,
    output_path:        Path,
    nutzungstyp:        str = "",
    site_geometry:      dict | None = None,
    tragwerk_config:    dict | None = None,
    mep_variant_data:   dict | None = None,
    projektname:        str = "AID Demo",
    plannummer:         str = "L-001",
    building_envelope:  dict | None = None,
    typology_key:       str | None = None,
) -> Path:
    """Rendert ein Layout als Vektor-PDF im Format A3 quer mit DIN-Plankopf.

    Gibt den Pfad zur erzeugten PDF-Datei zurück.
    """
    import matplotlib.gridspec as gridspec

    # A3 quer in Zoll (420 × 297 mm)
    fig = plt.figure(figsize=(16.54, 11.69))
    fig.patch.set_facecolor("#FAFAFA")

    gs = gridspec.GridSpec(
        2, 1,
        figure=fig,
        height_ratios=[82, 18],
        hspace=0.02,
    )
    ax_plan = fig.add_subplot(gs[0])
    ax_kopf = fig.add_subplot(gs[1])

    ax_plan.set_facecolor("#E8EDF0")

    # -- Planinhalt (identisch zu zeichne_layout) ----------------------------
    tr_pdf = SiteTransform.from_envelope(building_envelope)
    _draw_site(ax_plan, site_geometry, site_breite, site_tiefe)
    _draw_grid(ax_plan, zonen, raster_x, raster_y, tr_pdf)

    for zone in zonen:
        _draw_zone(ax_plan, zone, tr_pdf)

    trassen_laenge = _draw_techniktrassen(ax_plan, zonen, mep_variant_data, tr_pdf)

    for zone in zonen:
        _draw_zone_label(ax_plan, zone, tr_pdf)

    if site_geometry:
        _draw_access_points(ax_plan, site_geometry, site_breite, site_tiefe)

    building_fp = sum(
        z.breite * z.tiefe
        for z in zonen
        if not z.schraffur and z.din_kategorie != "VF"
    )
    if (site_geometry or {}).get("exclude_site_parking"):
        gezeichnete_stellplaetze = 0
    else:
        site_area = float((site_geometry or {}).get("area_m2") or site_breite * site_tiefe)
        stellplaetze = berechne_stellplaetze(site_area, building_fp)
        gezeichnete_stellplaetze = _draw_parking_info(
            ax_plan, site_geometry, site_breite, site_tiefe, zonen, stellplaetze, tr_pdf, building_envelope
        )

    _draw_legend(ax_plan, zonen)
    _draw_badges(ax_plan, zonen, site_breite, site_tiefe, gezeichnete_stellplaetze, trassen_laenge, typology_key)
    _draw_north_arrow(ax_plan, site_breite, site_tiefe)
    _draw_scalebar(ax_plan, site_tiefe)

    verstoesse = scores.get("regelverletzungen", [])
    if verstoesse:
        vtext = "WARNUNG: " + "\nWARNUNG: ".join(verstoesse)
        ax_plan.text(0.02, 0.04, vtext,
                     transform=ax_plan.transAxes,
                     ha="left", va="bottom", fontsize=7, color="#C0392B",
                     bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF3F3",
                               edgecolor="#C0392B", alpha=0.9),
                     zorder=10)

    if tragwerk_config:
        _draw_tragwerk_badge(ax_plan, site_breite, site_tiefe, tragwerk_config)
    if mep_variant_data:
        _draw_mep_gewerk_legende(ax_plan, mep_variant_data)

    if site_geometry and site_geometry.get("polygon"):
        from shapely.geometry import Polygon as _SPoly2
        try:
            _sp2 = _SPoly2(site_geometry["polygon"])
            _bx0p, _by0p, _bx1p, _by1p = _sp2.bounds
            _wp, _hp = _bx1p - _bx0p, _by1p - _by0p
            margin = max(8.0, min(_wp, _hp) * 0.10)
            ax_plan.set_xlim(_bx0p - margin, _bx1p + margin * 2)
            ax_plan.set_ylim(_by0p - margin * 1.2, _by1p + margin)
        except Exception:
            margin = max(8.0, min(site_breite, site_tiefe) * 0.10)
            ax_plan.set_xlim(-margin, site_breite + margin * 2)
            ax_plan.set_ylim(-margin * 1.2, site_tiefe + margin)
    else:
        margin = max(8.0, min(site_breite, site_tiefe) * 0.10)
        ax_plan.set_xlim(-margin, site_breite + margin * 2)
        ax_plan.set_ylim(-margin * 1.2, site_tiefe + margin)
    ax_plan.set_aspect("equal")
    ax_plan.set_xlabel("Breite [m]", fontsize=8)
    ax_plan.set_ylabel("Tiefe [m]", fontsize=8)
    ax_plan.tick_params(labelsize=7)

    # -- Maßstab berechnen ---------------------------------------------------
    # Grundlage: Planbreite ≈ 14" (A3 minus Rand); site in Metern → mm-Faktor
    plan_width_mm = 340.0  # Nutzbreite des Planfelds auf A3 quer
    site_max_m = max(site_breite, site_tiefe)
    raw_scale = (site_max_m * 1000.0) / plan_width_mm
    # Runden auf nächsthöhere Standardmaßstabstufe
    for std in (100, 200, 250, 500, 750, 1000, 1250, 1500, 2000):
        if raw_scale <= std:
            massstab_zahl = std
            break
    else:
        massstab_zahl = int(round(raw_scale / 100) * 100)
    massstab_str = f"1 : {massstab_zahl}"

    # -- Plankopf ------------------------------------------------------------
    _draw_plankopf(
        ax_kopf,
        projektname=projektname,
        variante_name=variante_name,
        nutzungstyp=nutzungstyp,
        massstab=massstab_str,
        scores=scores,
        plannummer=plannummer,
    )

    # -- Speichern -----------------------------------------------------------
    pdf_path = Path(str(output_path).replace(".png", ".pdf"))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(pdf_path, format="pdf", bbox_inches="tight", dpi=150)
    plt.close(fig)
    return pdf_path


# ---------------------------------------------------------------------------
# Hilfs-Zeichenfunktionen
# ---------------------------------------------------------------------------

def _draw_graph_overlay(
    ax,
    zonen: list[Zone],
    topology: dict,
    adjacency_weights: dict | None = None,
) -> None:
    """Zeichnet den Funktionsgraph als semi-transparentes Overlay auf das Grundriss-Layout."""
    centroids: dict[str, tuple[float, float]] = {
        z.name: z.centroid
        for z in zonen
        if not z.schraffur and z.din_kategorie not in ("VF",)
    }
    edges = topology.get("edges") or []
    weights = adjacency_weights or {}

    _edge_colors = {
        "process":    "#005A8E",
        "betrieb":    "#555555",
        "supervision": "#888888",
        "extern":     "#AAAAAA",
        "personal":   "#E67E22",
    }

    # --- Kanten ---
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src not in centroids or tgt not in centroids:
            continue
        x1, y1 = centroids[src]
        x2, y2 = centroids[tgt]
        key_fwd = f"{src}__{tgt}"
        key_rev = f"{tgt}__{src}"
        w = float(weights.get(key_fwd, weights.get(key_rev, edge.get("weight", 0.5))))
        color = _edge_colors.get(edge.get("kind", ""), "#666666")
        lw = max(1.0, w * 4.5)
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color, lw=lw,
                connectionstyle="arc3,rad=0.08",
                alpha=0.65,
                mutation_scale=12,
            ),
            zorder=18,
        )
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my, f"{w:.1f}", ha="center", va="center",
                fontsize=5.5, color=color, fontweight="bold", zorder=19,
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                          edgecolor="none", alpha=0.75))

    # --- Knoten (weiße Kreise über den Zonenzentren) ---
    for name, (cx, cy) in centroids.items():
        ax.plot(cx, cy, "o", color="white", markersize=9,
                markeredgecolor="#005A8E", markeredgewidth=1.8,
                alpha=0.90, zorder=20)


def _draw_site(ax, site_geometry: dict | None, site_breite: float, site_tiefe: float) -> None:
    """Zeichnet das Grundstück als Polygon (oder Rechteck wenn kein Polygon)."""
    if site_geometry and site_geometry.get("polygon"):
        poly = site_geometry["polygon"]
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        ax.fill(xs, ys, color="#D8E4C8", zorder=0, alpha=0.6)
        ax.plot(xs, ys, color="#5A7A3A", linewidth=2.0, zorder=1)
        # Setback-Linie (gestrichelt) wenn vorhanden
        setback = float((site_geometry.get("planning") or {}).get("abstandsfaktor", 0) or 0)
        max_h = float((site_geometry.get("planning") or {}).get("max_gebaeudehoehe_m", 10) or 10)
        setback_m = max_h * setback
        if setback_m > 0.5:
            from shapely.geometry import Polygon as ShapelyPolygon
            try:
                inner = ShapelyPolygon([(p[0], p[1]) for p in poly]).buffer(-setback_m)
                if not inner.is_empty:
                    ix, iy = inner.exterior.xy
                    ax.plot(list(ix), list(iy), color="#5A7A3A", linewidth=0.8,
                            linestyle="--", zorder=1, alpha=0.6)
            except Exception:
                pass
    else:
        site_rect = mpatches.Rectangle(
            (0, 0), site_breite, site_tiefe,
            linewidth=2, edgecolor="#5A7A3A", facecolor="#D8E4C8", zorder=0, alpha=0.6
        )
        ax.add_patch(site_rect)


# DIN-Kategorie → bevorzugte Stützenspannweite (min, max) in Metern
_SPANNWEITE: dict[str, tuple[float, float]] = {
    "NUF 3": (18.0, 24.0),   # Produktion / Data Center Whitespace
    "NUF 4": (12.0, 18.0),   # Lager, Logistik
    "NUF 2": (6.0,  9.0),    # Büro / Verwaltung
    "NUF 7": (6.0,  9.0),    # Sozial
    "TF":    (9.0,  12.0),   # Technik
    "VF":    (6.0,  6.0),    # Erschließung / Korridor
}


def _spannweite_fuer_zone(z: Zone, raster_x: float, raster_y: float) -> tuple[float, float]:
    lo, hi = _SPANNWEITE.get(z.din_kategorie, (raster_x, raster_y))
    # Snap auf das übergebene Rastermaß — bleibt immer ein Vielfaches
    sx = max(lo, min(hi, raster_x))
    sy = max(lo, min(hi, raster_y))
    return sx, sy


def _draw_grid(ax, zonen: list[Zone], raster_x: float, raster_y: float, tr: SiteTransform | None = None) -> None:
    """Zonenspezifisches Tragwerksraster: Stützen bevorzugt an Zonengrenzen."""
    if not zonen:
        return
    non_hatch = [z for z in zonen if not z.schraffur and z.din_kategorie != "VF"]
    if not non_hatch:
        return

    rotated = tr is not None and tr.is_rotated

    # --- Primärstruktur: Zonengrenzen als Linien ---
    xs_borders: set[float] = set()
    ys_borders: set[float] = set()
    for z in non_hatch:
        xs_borders.update([round(z.x, 1), round(z.x + z.breite, 1)])
        ys_borders.update([round(z.y, 1), round(z.y + z.tiefe, 1)])

    bx0 = min(z.x for z in non_hatch)
    bx1 = max(z.x + z.breite for z in non_hatch)
    by0 = min(z.y for z in non_hatch)
    by1 = max(z.y + z.tiefe for z in non_hatch)

    def _line(x0, y0, x1, y1, **kw):
        if rotated:
            p0, p1 = tr.pt(x0, y0), tr.pt(x1, y1)
            ax.plot([p0[0], p1[0]], [p0[1], p1[1]], **kw)
        else:
            ax.plot([x0, x1], [y0, y1], **kw)

    for xb in xs_borders:
        _line(xb, by0, xb, by1, color="#888888", linewidth=0.8,
              linestyle="-", zorder=2, alpha=0.5)
    for yb in ys_borders:
        _line(bx0, yb, bx1, yb, color="#888888", linewidth=0.8,
              linestyle="-", zorder=2, alpha=0.5)

    # --- Sekundärstruktur: zonenspezifische Zwischenstützen ---
    origin_x = bx0
    origin_y = by0
    for z in non_hatch:
        sx, sy = _spannweite_fuer_zone(z, raster_x, raster_y)
        rel_x0 = z.x - origin_x
        rel_x1 = z.x + z.breite - origin_x
        rel_y0 = z.y - origin_y
        rel_y1 = z.y + z.tiefe - origin_y

        if (z.breite > sx * 1.5) or (z.tiefe > sy * 1.5):
            xi = math.ceil(rel_x0 / sx) * sx
            while xi < rel_x1 - 0.5:
                x_abs = origin_x + xi
                if x_abs not in xs_borders:
                    _line(x_abs, z.y, x_abs, z.y + z.tiefe,
                          color="#CCCCCC", linewidth=0.4, linestyle="--", zorder=2, alpha=0.6)
                xi += sx
            yi = math.ceil(rel_y0 / sy) * sy
            while yi < rel_y1 - 0.5:
                y_abs = origin_y + yi
                if y_abs not in ys_borders:
                    _line(z.x, y_abs, z.x + z.breite, y_abs,
                          color="#CCCCCC", linewidth=0.4, linestyle="--", zorder=2, alpha=0.6)
                yi += sy

    # --- Stützensymbole ○ an allen Rasterkreuzungspunkten ---
    all_xs = sorted(xs_borders)
    all_ys = sorted(ys_borders)
    for xb in all_xs:
        for yb in all_ys:
            gx, gy = tr.pt(xb, yb) if rotated else (xb, yb)
            ax.plot(gx, gy, "o", color="#555555", markersize=3.5,
                    markerfacecolor="white", markeredgewidth=0.8, zorder=4)


# ---------------------------------------------------------------------------
# Techniktrassen
# ---------------------------------------------------------------------------

_TRASSEN_ABSTAND: dict[str, float] = {
    "hoch":    6.0,
    "mittel":  12.0,
    "niedrig": 18.0,
}
_TRASSEN_DICHTE: dict[str, str] = {
    "NUF 3": "hoch",
    "NUF 4": "mittel",
    "NUF 2": "niedrig",
    "NUF 7": "niedrig",
    "TF":    "hoch",
    "VF":    "hoch",
}


def _draw_techniktrassen(ax, zonen: list[Zone], mep_data: dict | None = None, tr: SiteTransform | None = None) -> float:
    """Zeichnet Techniktrassen ausgehend vom Technikraum, farbkodiert nach Gewerken."""
    import math as _math
    TOLEANZ = 1.5   # m – Toleranz für Zonenadjazenz
    _rotated = tr is not None and tr.is_rotated

    def _lp(x0, y0, x1, y1, **kw):
        if _rotated:
            p0, p1 = tr.pt(x0, y0), tr.pt(x1, y1)
            ax.plot([p0[0], p1[0]], [p0[1], p1[1]], **kw)
        else:
            ax.plot([x0, x1], [y0, y1], **kw)

    # Primär-Gewerk-Farbe je Zone aus mep_data
    zone_farbe: dict[str, str] = {}
    if mep_data:
        for mz in mep_data.get("zonen", []):
            gewerke = mz.get("gewerke", {})
            farbe = "#3A7FC1"  # Fallback
            for gw in _GEWERK_PRIO:
                if gw in gewerke:
                    farbe = _GEWERK_FARBEN.get(gw, farbe)
                    break
            zone_farbe[mz.get("zone_name", "")] = farbe

    gesamtlaenge = 0.0
    non_hatch = [z for z in zonen if not z.schraffur]
    erschl     = [z for z in non_hatch if z.din_kategorie == "VF"]
    technik_zonen = [z for z in non_hatch if z.din_kategorie == "TF"]
    produktiv  = [z for z in non_hatch if z.din_kategorie not in ("VF", "TF")]

    # ── Backbone-Koordinaten je Erschließungszone ──────────────────────────
    backbones: list[tuple[float, float, float, float, bool]] = []  # x0,y0,x1,y1,horizontal
    for vf in erschl:
        horiz = vf.breite >= vf.tiefe
        if horiz:
            y_mid = vf.y + vf.tiefe / 2
            backbones.append((vf.x, y_mid, vf.x + vf.breite, y_mid, True))
        else:
            x_mid = vf.x + vf.breite / 2
            backbones.append((x_mid, vf.y, x_mid, vf.y + vf.tiefe, False))

    # Fallback 1: Backbone aus Korridor-Pfadpunkten
    if not backbones and mep_data:
        for kante in mep_data.get("korridor_kanten_mit_pfad", []):
            pts = kante.get("pfad_punkte") or []
            if len(pts) < 2:
                continue
            for i in range(len(pts) - 1):
                x0, y0 = float(pts[i][0]), float(pts[i][1])
                x1, y1 = float(pts[i + 1][0]), float(pts[i + 1][1])
                horiz = abs(y1 - y0) < abs(x1 - x0)
                backbones.append((x0, y0, x1, y1, horiz))

    # Fallback 2 (Sprint P-fix): Optimizer-Variante ohne VF-Erschließungszone.
    # Statt einer synthetischen Mittellinie durch das ganze Gebäude (visuell verwirrend)
    # zeichnen wir ein TF-Stern-Netz: TF-Zentroid → nächste Wandmitte jeder produktiven Zone.
    # Interne Zonentrassen werden danach separat gezeichnet. Early-Return verhindert
    # dass der backbone-basierte Code (Abschnitte unten) zusätzlich läuft.
    if not backbones and technik_zonen and non_hatch:
        for tf in technik_zonen:
            tx, ty = tf.centroid
            # TF-Symbol: kleines Kreuz
            _lp(tx - 1.5, ty, tx + 1.5, ty,
                color="#C0392B", linewidth=2.5, linestyle="-", zorder=5, alpha=0.85,
                solid_capstyle="round")
            _lp(tx, ty - 1.5, tx, ty + 1.5,
                color="#C0392B", linewidth=2.5, linestyle="-", zorder=5, alpha=0.85,
                solid_capstyle="round")
            for z in produktiv:
                zfarbe = zone_farbe.get(z.name, "#3A7FC1")
                # Wandmitten der vier Seiten: wähle die dem TF-Zentroid nächste
                faces = [
                    (z.x + z.breite / 2, z.y),              # Süd
                    (z.x + z.breite / 2, z.y + z.tiefe),    # Nord
                    (z.x,               z.y + z.tiefe / 2), # West
                    (z.x + z.breite,    z.y + z.tiefe / 2), # Ost
                ]
                fx, fy = min(faces, key=lambda p: _math.dist((tx, ty), p))
                _lp(tx, ty, fx, fy,
                    color=zfarbe, linewidth=1.2, linestyle="-", zorder=3, alpha=0.60,
                    solid_capstyle="round")
                gesamtlaenge += _math.dist((tx, ty), (fx, fy))
                # Interne Zonentrassen
                dichte = _TRASSEN_DICHTE.get(z.din_kategorie, "mittel")
                abstand = _TRASSEN_ABSTAND[dichte]
                # B1-Fix: Stub-Verbindung von Wandeintritt zur ersten internen Trasse.
                # Ohne Stub endet die TF-Linie an der Wand, und die gestrichelten Trassen
                # "schweben" abgekoppelt im Zoneninneren.
                TOLEANZ_1 = 1.5  # m — Toleranz für Wandzuordnung
                if abs(fy - z.y) <= TOLEANZ_1:
                    # Eintritt Südwand → kurze vertikale Verbindung zur ersten Trasse
                    first_y = z.y + abstand
                    if first_y < z.y + z.tiefe:
                        _lp(fx, fy, fx, first_y, color=zfarbe, linewidth=1.0,
                            linestyle="-", zorder=3, alpha=0.55, solid_capstyle="round")
                elif abs(fy - (z.y + z.tiefe)) <= TOLEANZ_1:
                    # Eintritt Nordwand → kurze vertikale Verbindung zur letzten Trasse
                    last_y = z.y + z.tiefe - abstand
                    if last_y > z.y:
                        _lp(fx, fy, fx, last_y, color=zfarbe, linewidth=1.0,
                            linestyle="-", zorder=3, alpha=0.55, solid_capstyle="round")
                elif abs(fx - z.x) <= TOLEANZ_1 or abs(fx - (z.x + z.breite)) <= TOLEANZ_1:
                    # Eintritt West-/Ostwand → kurze horizontale Verbindung zur Zonenmitte
                    mid_x = z.x + z.breite / 2
                    _lp(fx, fy, mid_x, fy, color=zfarbe, linewidth=1.0,
                        linestyle="-", zorder=3, alpha=0.55, solid_capstyle="round")
                y = z.y + abstand
                while y < z.y + z.tiefe - abstand * 0.3:
                    _lp(z.x + 1, y, z.x + z.breite - 1, y,
                        color=zfarbe, linewidth=0.5, linestyle=(0, (4, 3)),
                        zorder=3, alpha=0.45)
                    gesamtlaenge += z.breite - 2
                    y += abstand
        return round(gesamtlaenge, 1)  # Early Return: kein backbone-Code danach

    # Fallback 3: Wirklich keine TF-Zone vorhanden → synthetische Mittellinie als letzter Ausweg
    if not backbones and non_hatch:
        xs = [z.x for z in non_hatch] + [z.x + z.breite for z in non_hatch]
        ys = [z.y for z in non_hatch] + [z.y + z.tiefe for z in non_hatch]
        x0_bb, x1_bb = min(xs), max(xs)
        y_mid = (min(ys) + max(ys)) / 2
        backbones.append((x0_bb, y_mid, x1_bb, y_mid, True))

    # ── Stammtrasse: Technikraum → nächster Backbone-Punkt ────────────────
    for tf in technik_zonen:
        tx, ty = tf.centroid
        best_pt = None
        best_dist = float("inf")
        for x0, y0, x1, y1, horiz in backbones:
            if horiz:
                # Backbone ist horizontal bei y = y0
                bx = max(x0, min(x1, tx))
                pt = (bx, y0)
            else:
                by = max(y0, min(y1, ty))
                pt = (x0, by)
            d = _math.dist((tx, ty), pt)
            if d < best_dist:
                best_dist = d
                best_pt = pt
        if best_pt:
            _lp(tx, ty, best_pt[0], best_pt[1],
                color="#C0392B", linewidth=1.8, linestyle="-", zorder=4, alpha=0.75,
                solid_capstyle="round")
            gesamtlaenge += best_dist

    # ── Backbone-Trasse (orange) ───────────────────────────────────────────
    for x0, y0, x1, y1, _ in backbones:
        _lp(x0, y0, x1, y1,
            color="#E07B00", linewidth=2.2, linestyle="-", zorder=3, alpha=0.75,
            solid_capstyle="round")
        gesamtlaenge += _math.dist((x0, y0), (x1, y1))

    # ── Abzweige: Backbone → Zoneneintritt + interne Trassen ──────────────
    for z in produktiv:
        dichte = _TRASSEN_DICHTE.get(z.din_kategorie, "mittel")
        abstand = _TRASSEN_ABSTAND[dichte]

        # Nächsten Backbone-Punkt zur Zone finden
        zx, zy = z.centroid
        entry_pt = None
        best_dist = float("inf")
        for x0, y0, x1, y1, horiz in backbones:
            if horiz:
                # Gemeinsame Oberkante (Zone liegt über VF) oder Unterkante (unter VF)
                shared_x0 = max(z.x, x0)
                shared_x1 = min(z.x + z.breite, x1)
                if shared_x1 > shared_x0 - TOLEANZ:
                    mid_x = (shared_x0 + shared_x1) / 2
                    # Prüfe welche Seite an VF grenzt
                    if abs(z.y - y0) <= TOLEANZ:
                        pt = (mid_x, z.y)
                    elif abs(z.y + z.tiefe - y0) <= TOLEANZ:
                        pt = (mid_x, z.y + z.tiefe)
                    else:
                        # Kürzester Abstand zum Backbone
                        bx = max(x0, min(x1, zx))
                        pt = (bx, y0)
                    d = _math.dist(pt, (mid_x, y0))
                else:
                    bx = max(x0, min(x1, zx))
                    pt = (bx, y0)
                    d = _math.dist((zx, zy), pt)
            else:
                shared_y0 = max(z.y, y0)
                shared_y1 = min(z.y + z.tiefe, y1)
                if shared_y1 > shared_y0 - TOLEANZ:
                    mid_y = (shared_y0 + shared_y1) / 2
                    if abs(z.x - x0) <= TOLEANZ:
                        pt = (z.x, mid_y)
                    elif abs(z.x + z.breite - x0) <= TOLEANZ:
                        pt = (z.x + z.breite, mid_y)
                    else:
                        by = max(y0, min(y1, zy))
                        pt = (x0, by)
                    d = _math.dist(pt, (x0, mid_y))
                else:
                    by = max(y0, min(y1, zy))
                    pt = (x0, by)
                    d = _math.dist((zx, zy), pt)
            if d < best_dist:
                best_dist = d
                entry_pt = pt

        # Abzweig-Linie vom Backbone-Eintritt in die Zone (Farbe je Gewerk)
        zfarbe = zone_farbe.get(z.name, "#3A7FC1")
        if entry_pt:
            ex, ey = entry_pt
            if backbones and backbones[0][4]:  # horizontale Erschließung
                if ey <= z.y + TOLEANZ:
                    inner_y = z.y + z.tiefe
                else:
                    inner_y = z.y
                _lp(ex, ey, ex, inner_y,
                    color=zfarbe, linewidth=1.2, linestyle="-", zorder=3, alpha=0.65,
                    solid_capstyle="round")
                gesamtlaenge += abs(inner_y - ey)
            else:
                if ex <= z.x + TOLEANZ:
                    inner_x = z.x + z.breite
                else:
                    inner_x = z.x
                _lp(ex, ey, inner_x, ey,
                    color=zfarbe, linewidth=1.2, linestyle="-", zorder=3, alpha=0.65,
                    solid_capstyle="round")
                gesamtlaenge += abs(inner_x - ex)

        # Interne Zonentrassen (dashed, density-based, Gewerk-Farbe)
        y = z.y + abstand
        while y < z.y + z.tiefe - abstand * 0.3:
            _lp(z.x + 1, y, z.x + z.breite - 1, y,
                color=zfarbe, linewidth=0.5, linestyle=(0, (4, 3)),
                zorder=3, alpha=0.45)
            gesamtlaenge += z.breite - 2
            y += abstand

    return round(gesamtlaenge, 1)


def _draw_vf_pfeile(ax, zone: Zone, color: str) -> None:
    """Matplotlib-Richtungspfeile entlang der VF-Korridor-Mittelachse (nicht-rotiert)."""
    import matplotlib.patches as mpa
    from matplotlib.patches import FancyArrowPatch

    ARROW_LEN  = 3.0   # m — Pfeillänge
    ARROW_HEAD = 1.2   # m — Pfeilkopfgröße (mutation_scale)
    LW         = 1.0

    if zone.breite >= zone.tiefe:
        # Horizontaler Korridor → Pfeile links→rechts
        y_mid = zone.y + zone.tiefe / 2
        step  = max(8.0, zone.breite / 5)
        x     = zone.x + step * 0.55
        while x + ARROW_LEN < zone.x + zone.breite - 1.5:
            ax.annotate(
                "", xy=(x + ARROW_LEN, y_mid), xytext=(x, y_mid),
                arrowprops=dict(
                    arrowstyle="-|>", color=color, lw=LW,
                    mutation_scale=ARROW_HEAD * 6,
                ),
                zorder=4,
            )
            x += step
    else:
        # Vertikaler Korridor → Pfeile unten→oben
        x_mid = zone.x + zone.breite / 2
        step  = max(8.0, zone.tiefe / 5)
        y     = zone.y + step * 0.55
        while y + ARROW_LEN < zone.y + zone.tiefe - 1.5:
            ax.annotate(
                "", xy=(x_mid, y + ARROW_LEN), xytext=(x_mid, y),
                arrowprops=dict(
                    arrowstyle="-|>", color=color, lw=LW,
                    mutation_scale=ARROW_HEAD * 6,
                ),
                zorder=4,
            )
            y += step


def _draw_vf_pfeile_rotated(ax, zone: Zone, tr, color: str) -> None:
    """Richtungspfeile für rotierte VF-Zone (transformierte Koordinaten)."""
    ARROW_LEN  = 3.0
    ARROW_HEAD = 1.2
    LW         = 1.0

    if zone.breite >= zone.tiefe:
        y_mid = zone.y + zone.tiefe / 2
        step  = max(8.0, zone.breite / 5)
        x     = zone.x + step * 0.55
        while x + ARROW_LEN < zone.x + zone.breite - 1.5:
            p0 = tr.pt(x, y_mid)
            p1 = tr.pt(x + ARROW_LEN, y_mid)
            ax.annotate(
                "", xy=p1, xytext=p0,
                arrowprops=dict(
                    arrowstyle="-|>", color=color, lw=LW,
                    mutation_scale=ARROW_HEAD * 6,
                ),
                zorder=4,
            )
            x += step
    else:
        x_mid = zone.x + zone.breite / 2
        step  = max(8.0, zone.tiefe / 5)
        y     = zone.y + step * 0.55
        while y + ARROW_LEN < zone.y + zone.tiefe - 1.5:
            p0 = tr.pt(x_mid, y)
            p1 = tr.pt(x_mid, y + ARROW_LEN)
            ax.annotate(
                "", xy=p1, xytext=p0,
                arrowprops=dict(
                    arrowstyle="-|>", color=color, lw=LW,
                    mutation_scale=ARROW_HEAD * 6,
                ),
                zorder=4,
            )
            y += step


def _draw_zone(ax, zone: Zone, tr: SiteTransform | None = None) -> None:
    farbe = _zone_farbe(zone.name, zone.farbe)
    rotated = tr is not None and tr.is_rotated

    if zone.din_kategorie == "VF" and not zone.schraffur:
        # VF-Erschließungszone als Korridor darstellen:
        #   Flur-Korridor (farbe="#7EC8E3"): helles Blau, vollfarbig
        #   Standard-Erschließungszone:      warmer Sand-Tint, gestrichelte Kontur
        is_flur_corridor = zone.farbe == "#7EC8E3"
        if is_flur_corridor:
            ec = "#1A6B8A"
            fc = farbe
            ls = "-"
            lw = 1.8
            al = 0.72
            arrow_color = "#0D4F6A"
        else:
            ec = "#9A8A6A"        # sandbraun
            fc = "#F0EAD8"        # sehr heller Warm-Tint (sichtbar auf weiß)
            ls = "--"             # Architekttur-Dash statt Punktlinie
            lw = 1.3
            al = 0.40             # halbtransparent: Korridor erkennbar, aber dezent
            arrow_color = "#8A7A5A"

        if rotated:
            pts = tr.corners(zone.x, zone.y, zone.breite, zone.tiefe)
            ax.add_patch(mpatches.Polygon(
                pts, closed=True, linewidth=lw, edgecolor=ec,
                linestyle=ls, facecolor=fc, alpha=al, zorder=3,
            ))
            # Pfeile entlang der Mittellinie (transformierter Koordinatenraum)
            _draw_vf_pfeile_rotated(ax, zone, tr, arrow_color)
        else:
            ax.add_patch(mpatches.Rectangle(
                (zone.x, zone.y), zone.breite, zone.tiefe,
                linewidth=lw, edgecolor=ec, linestyle=ls,
                facecolor=fc, alpha=al, zorder=3,
            ))
            _draw_vf_pfeile(ax, zone, arrow_color)
        return

    # Freifläche (AF) = Außenanlage: wie Site-Polygon rendern — kein Hatch, hohe Deckkraft
    is_freif = zone.schraffur and zone.din_kategorie == "AF"
    if is_freif:
        alpha = 0.65
        lw    = 0.5
        ec    = "#5A7A3A"   # gleiche Konturfarbe wie Site-Polygon
        hatch = None
    else:
        alpha = 0.22 if zone.schraffur else 0.85
        lw    = 0.8  if zone.schraffur else 1.5
        ec    = "#444444"
        hatch = "////" if zone.schraffur else None

    if rotated:
        pts = tr.corners(zone.x, zone.y, zone.breite, zone.tiefe)
        ax.add_patch(mpatches.Polygon(
            pts, closed=True, linewidth=lw, edgecolor=ec,
            facecolor=farbe, alpha=alpha, zorder=3,
            hatch=hatch,
        ))
    else:
        rect = mpatches.Rectangle(
            (zone.x, zone.y), zone.breite, zone.tiefe,
            linewidth=lw, edgecolor=ec, facecolor=farbe,
            alpha=alpha, zorder=3, hatch=hatch,
        )
        ax.add_patch(rect)


def _draw_zone_label(ax, zone: Zone, tr: SiteTransform | None = None) -> None:
    if zone.schraffur or zone.breite < 8.0 or zone.tiefe < 4.0:
        return
    farbe = _zone_farbe(zone.name, zone.farbe)
    cx_l = zone.x + zone.breite / 2
    cy_l = zone.y + zone.tiefe / 2
    if tr is not None and tr.is_rotated:
        cx_l, cy_l = tr.pt(cx_l, cy_l)
    area_m2 = zone.planned_area_m2 or zone.flaeche_m2
    min_dim = min(zone.breite, zone.tiefe)
    fs = max(5.5, min(9.0, min_dim * 0.50))
    name = zone.name
    if zone.breite < 18 and len(name) > 12:
        name = name.replace(" / ", "\n").replace(" ", "\n", 1)
    label = f"{name}\n{area_m2:.0f} m²"
    if zone.floors > 1:
        label += f"\n{zone.floors}G"
    r, g, b = int(farbe[1:3], 16), int(farbe[3:5], 16), int(farbe[5:7], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    tc = "#222222" if lum > 140 else "#FFFFFF"
    bbox = None
    if zone.din_kategorie != "VF":
        bbox = dict(boxstyle="round,pad=0.12", facecolor=farbe,
                    edgecolor="none", alpha=0.55)
    rotation = (tr.angle_deg if tr is not None and tr.is_rotated else 0)
    ax.text(
        cx_l, cy_l, label,
        ha="center", va="center",
        fontsize=fs, color=tc, fontweight="bold",
        rotation=rotation,
        zorder=5,
        bbox=bbox,
    )


def _draw_access_points(ax, site_geometry: dict, site_breite: float, site_tiefe: float) -> None:
    """Zufahrtspfeile an den Grundstücksgrenzen."""
    for ap in (site_geometry.get("access_points") or []):
        side = ap.get("side", "")
        pt = ap.get("point", [0, 0])
        w = float(ap.get("width_m", 6))
        x, y = float(pt[0]), float(pt[1])
        arrow_len = min(8.0, max(4.0, w * 0.8))

        if side == "south":
            ax.annotate("", xy=(x, y + 1), xytext=(x, y - arrow_len),
                        arrowprops=dict(arrowstyle="->", color="#CC3300", lw=2.0), zorder=8)
            ax.text(x, y - arrow_len - 1.5, f"Zufahrt\n{w:.0f}m",
                    ha="center", va="top", fontsize=6.5, color="#CC3300", fontweight="bold")
        elif side == "north":
            ax.annotate("", xy=(x, y - 1), xytext=(x, y + arrow_len),
                        arrowprops=dict(arrowstyle="->", color="#CC3300", lw=2.0), zorder=8)
            ax.text(x, y + arrow_len + 1.5, f"Zufahrt\n{w:.0f}m",
                    ha="center", va="bottom", fontsize=6.5, color="#CC3300", fontweight="bold")
        elif side == "west":
            ax.annotate("", xy=(x + 1, y), xytext=(x - arrow_len, y),
                        arrowprops=dict(arrowstyle="->", color="#CC3300", lw=2.0), zorder=8)
            ax.text(x - arrow_len - 1.5, y, f"Zufahrt\n{w:.0f}m",
                    ha="right", va="center", fontsize=6.5, color="#CC3300", fontweight="bold")
        elif side == "east":
            ax.annotate("", xy=(x - 1, y), xytext=(x + arrow_len, y),
                        arrowprops=dict(arrowstyle="->", color="#CC3300", lw=2.0), zorder=8)
            ax.text(x + arrow_len + 1.5, y, f"Zufahrt\n{w:.0f}m",
                    ha="left", va="center", fontsize=6.5, color="#CC3300", fontweight="bold")

        # Zufahrtsbreite als farbiger Balken
        if side in {"south", "north"}:
            ax.plot([x - w/2, x + w/2], [y, y], color="#CC3300", linewidth=3, zorder=7, solid_capstyle="butt")
        else:
            ax.plot([x, x], [y - w/2, y + w/2], color="#CC3300", linewidth=3, zorder=7, solid_capstyle="butt")


def _polygon_effective_south(polygon: list, x0: float, x1: float) -> float:
    """Bestimmt die effektive Südgrenze des Polygons im x-Bereich [x0, x1].

    Gibt den maximalen y-Wert der Polygon-Unterseite zurück, der im x-Streifen
    vorkommt — also die konservativste (höchste) Untergrenze für Stellplätze.
    Bei einem achsenparallelen Grundstück ist das 0.0.
    Bei schrägem Rand (z.B. C_unregelmaessig) liegt dieser Wert höher.
    """
    if not polygon or len(polygon) < 3:
        return 0.0
    n = len(polygon)
    ys: list[float] = []
    for i in range(n):
        p0, p1 = polygon[i], polygon[(i + 1) % n]
        xa, ya = float(p0[0]), float(p0[1])
        xb, yb = float(p1[0]), float(p1[1])
        x_lo, x_hi = min(xa, xb), max(xa, xb)
        # Überlappung der Kante mit [x0, x1]?
        if x_hi < x0 - 0.01 or x_lo > x1 + 0.01:
            continue
        dx = xb - xa
        if abs(dx) < 1e-6:
            # Vertikale Kante: nimm das Minimum der beiden y-Werte
            ys.append(min(ya, yb))
        else:
            # Schräge Kante: y bei x=max(x0, x_lo) und x=min(x1, x_hi)
            for x_sample in (max(x0, x_lo), min(x1, x_hi)):
                t = (x_sample - xa) / dx
                ys.append(ya + t * (yb - ya))
    # Von allen y-Werten auf der Unterseite nehmen wir das Maximum
    # (= konservativster Wert = der Rand, der am höchsten liegt)
    south_ys = [y for y in ys if y <= (min(float(p[1]) for p in polygon) + 20)]
    return max(south_ys) if south_ys else 0.0


def _draw_parking_info(
    ax,
    site_geometry: dict | None,
    site_breite: float,
    site_tiefe: float,
    zonen: list[Zone],
    stellplaetze: int,
    tr: SiteTransform | None = None,
    building_envelope: dict | None = None,
) -> int:
    """Zeichnet schematische Stellplatzsymbole auf der Restfläche."""
    if stellplaetze <= 0:
        return 0

    # Restfläche: Grundstück minus Gebäude-BBox
    non_hatch = [z for z in zonen if not z.schraffur and z.din_kategorie != "VF"]
    if not non_hatch:
        return 0
    bx0 = min(z.x for z in non_hatch)
    bx1 = max(z.x + z.breite for z in non_hatch)
    by0 = min(z.y for z in non_hatch)
    by1 = max(z.y + z.tiefe for z in non_hatch)

    avail_w = bx1 - bx0
    sp_per_row = max(1, int(avail_w / STELLPLATZ_BREITE))
    row_height = STELLPLATZ_TIEFE + FAHRGANG_BREITE / 2   # ~8 m pro Reihe

    # Grenzen aus Baufeld-Daten (rotierter Referenzrahmen) oder Fallback auf Site-Tiefe
    site_south = float((building_envelope or {}).get("rotated_site_south") or 0.0)
    site_north = float((building_envelope or {}).get("rotated_site_north") or site_tiefe)

    # B2-Fix: Polygon-genaue Südgrenze im Parking-X-Band.
    # Bei unregelmäßigen Grundstücken liegt die Polygon-Südkante höher als y=0.
    # Wir bestimmen die maximale y-Koordinate der Südkante im x-Bereich [bx0, bx1]
    # und verwenden sie als effektive Untergrenze — so landen keine Parkplätze außerhalb.
    poly_pts = (site_geometry or {}).get("polygon") or []
    if poly_pts:
        site_south = max(site_south, _polygon_effective_south(poly_pts, bx0, bx1))

    south_start = by0 - 1.5
    max_rows_south = 0
    while south_start - max_rows_south * row_height - STELLPLATZ_TIEFE >= site_south:
        max_rows_south += 1

    north_start = by1 + 1.5
    max_rows_north = 0
    while north_start + max_rows_north * row_height + STELLPLATZ_TIEFE <= site_north:
        max_rows_north += 1

    use_north = max_rows_south == 0 and max_rows_north > 0
    if max_rows_south == 0 and max_rows_north == 0:
        return 0

    if use_north:
        n_rows = min(2, max_rows_north)
        max_to_draw = min(stellplaetze, sp_per_row * n_rows)
        row_starts = [north_start]
        if n_rows >= 2:
            row2_y = north_start + STELLPLATZ_TIEFE + FAHRGANG_BREITE
            if row2_y + STELLPLATZ_TIEFE <= site_north:
                row_starts.append(row2_y)
                fahrgang_rect = mpatches.Rectangle(
                    (bx0, north_start + STELLPLATZ_TIEFE), avail_w, FAHRGANG_BREITE,
                    linewidth=0, facecolor="#CCCCCC", alpha=0.4, zorder=1
                )
                ax.add_patch(fahrgang_rect)
    else:
        n_rows = min(2, max_rows_south)
        max_to_draw = min(stellplaetze, sp_per_row * n_rows)
        if n_rows >= 2:
            fahrgang_y = south_start - STELLPLATZ_TIEFE - FAHRGANG_BREITE
            if fahrgang_y >= site_south:
                fahrgang_rect = mpatches.Rectangle(
                    (bx0, fahrgang_y), avail_w, FAHRGANG_BREITE,
                    linewidth=0, facecolor="#CCCCCC", alpha=0.4, zorder=1
                )
                ax.add_patch(fahrgang_rect)
        row_starts = [south_start - STELLPLATZ_TIEFE]
        if n_rows >= 2:
            fahrgang_y = south_start - STELLPLATZ_TIEFE - FAHRGANG_BREITE
            row2_y = fahrgang_y - STELLPLATZ_TIEFE
            if row2_y >= site_south:
                row_starts.append(row2_y)

    rotated = tr is not None and tr.is_rotated
    drawn = 0
    for row_y in row_starts:
        for col in range(sp_per_row):
            if drawn >= max_to_draw:
                break
            sx = bx0 + col * STELLPLATZ_BREITE
            if rotated:
                pts = tr.corners(sx, row_y, STELLPLATZ_BREITE, STELLPLATZ_TIEFE)
                sp_patch = mpatches.Polygon(
                    pts, closed=True,
                    linewidth=0.6, edgecolor="#666666", facecolor="#E0E8F0",
                    alpha=0.7, zorder=2,
                )
            else:
                sp_patch = mpatches.Rectangle(
                    (sx, row_y), STELLPLATZ_BREITE, STELLPLATZ_TIEFE,
                    linewidth=0.6, edgecolor="#666666", facecolor="#E0E8F0",
                    alpha=0.7, zorder=2,
                )
            ax.add_patch(sp_patch)
            drawn += 1
        if drawn >= max_to_draw:
            break
    return drawn


def _draw_legend(ax, zonen: list[Zone]) -> None:
    handles, labels = [], []
    seen = set()
    for zone in zonen:
        if zone.name in seen:
            continue
        seen.add(zone.name)
        farbe = _zone_farbe(zone.name, zone.farbe)
        if zone.din_kategorie == "VF" and not zone.schraffur:
            is_flur = zone.farbe == "#7EC8E3"
            handles.append(mpatches.Patch(
                facecolor=farbe if is_flur else "#F0EAD8",
                edgecolor="#1A6B8A" if is_flur else "#9A8A6A",
                linestyle="-" if is_flur else "--",
                linewidth=1.4,
                alpha=0.72 if is_flur else 0.45,
            ))
        else:
            is_freif_leg = zone.schraffur and zone.din_kategorie == "AF"
            handles.append(mpatches.Patch(
                facecolor=farbe,
                edgecolor="#5A7A3A" if is_freif_leg else "#444444",
                alpha=0.65 if is_freif_leg else (0.85 if not zone.schraffur else 0.25),
                hatch=None if is_freif_leg else ("////" if zone.schraffur else None),
            ))
        labels.append(_legend_label(zone))
    if handles:
        ax.legend(
            handles, labels,
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            frameon=True,
            framealpha=0.95,
            facecolor="white",
            edgecolor="#BBBBBB",
            fontsize=7,
            title="Legende",
            title_fontsize=8,
        )


def _draw_badges(
    ax, zonen: list[Zone], site_breite: float, site_tiefe: float,
    stellplaetze: int, trassen_laenge: float = 0.0,
    typology_key: str | None = None,
) -> None:
    """Typologie-Badge, Stellplatz-Zähler und Techniktrassen-Länge."""
    typo_map = {
        "squarified":    ("Dreispalten-Columns", "Logistik | Halle | Support"),
        "block_reserve": ("Block + Reserve",     "Kompaktblock + Erweiterung"),
        "recursive":     ("Rekursiv",            "Constraint-basierte Teilung"),
        "optimized":     ("KI-Optimiert",        "Scipy Constraint-Optimierung"),
    }
    typo_key = _detect_typology(zonen, hint=typology_key)
    y_badge = site_tiefe + 1.5
    if typo_key:
        tname, tdesc = typo_map.get(typo_key, (typo_key, ""))
        ax.text(
            site_breite - 1, y_badge,
            f"Typologie: {tname}  |  {tdesc}",
            ha="right", va="bottom", fontsize=7.5,
            color="#444444", style="italic",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFDE7",
                      edgecolor="#CCAA00", alpha=0.9),
            zorder=6,
        )
    y2 = y_badge
    if stellplaetze > 0:
        ax.text(
            1, y2,
            f"Stellplätze: ~{stellplaetze} SP (im Grundstück)",
            ha="left", va="bottom", fontsize=7.5,
            color="#1A5276",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#D6EAF8",
                      edgecolor="#1A5276", alpha=0.9),
            zorder=6,
        )
        y2 += 6.5
    if trassen_laenge > 0:
        ax.text(
            1, y2,
            f"Techniktrassen: ~{trassen_laenge:.0f} m",
            ha="left", va="bottom", fontsize=7.5,
            color="#7D4E00",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF3E0",
                      edgecolor="#E07B00", alpha=0.9),
            zorder=6,
        )


def _draw_tragwerk_badge(ax, site_breite: float, site_tiefe: float, tragwerk_config: dict) -> None:
    """Badge: Tragwerktypologie · Traufhöhe · Lastklasse (Sprint 4B)."""
    typ = tragwerk_config.get("typologie", "")
    lastklasse = tragwerk_config.get("lastklasse", "")
    traufhoehe = _load_tragwerk_traufhoehe(typ)

    parts = [_TRAGWERK_LABELS.get(typ, typ)]
    if traufhoehe:
        parts.append(f"h={traufhoehe:.1f} m")
    if lastklasse:
        parts.append(_LASTKLASSE_LABELS.get(lastklasse, lastklasse))

    ax.text(
        site_breite - 1, site_tiefe + 8.5,
        "  |  ".join(parts),
        ha="right", va="bottom", fontsize=7.5,
        color="#1B4F72",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#D6EAF8",
                  edgecolor="#1B4F72", alpha=0.9),
        zorder=6,
    )


def _draw_mep_gewerk_legende(ax, mep_variant_data: dict) -> None:
    """Gewerk-Farbpunkte als kompakte Legende unten links (Sprint 4C)."""
    aktive = mep_variant_data.get("aktive_gewerke", [])
    if not aktive:
        return

    # Legende als zweite ax.legend()-Instanz (add_artist erhält die erste)
    handles = [
        mpatches.Patch(
            facecolor=_GEWERK_FARBEN.get(g, "#AAAAAA"),
            edgecolor="#666666",
            linewidth=0.5,
            label=_GEWERK_LABELS.get(g, g),
        )
        for g in aktive
        if g in _GEWERK_FARBEN
    ]
    if not handles:
        return

    # Vorhandene Zone-Legende sichern, dann MEP-Legende hinzufügen
    existing = ax.get_legend()
    mep_leg = ax.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.0, 0.0),
        fontsize=6,
        title="MEP-Gewerke",
        title_fontsize=6.5,
        framealpha=0.88,
        ncol=2 if len(handles) > 4 else 1,
        handlelength=1.0,
        handleheight=0.8,
    )
    if existing:
        ax.add_artist(existing)  # Zone-Legende wiederherstellen


def _draw_north_arrow(ax, site_breite: float, site_tiefe: float) -> None:
    nx = site_breite + 4
    ax.annotate("", xy=(nx, site_tiefe * 0.92),
                xytext=(nx, site_tiefe * 0.78),
                arrowprops=dict(arrowstyle="->", color="#333333", lw=1.5))
    ax.text(nx, site_tiefe * 0.95, "N",
            ha="center", va="bottom", fontsize=8, fontweight="bold", color="#333333")


def _draw_scalebar(ax, site_tiefe: float) -> None:
    scale_y = -5.5
    scale_len = 20.0
    ax.plot([5, 5 + scale_len], [scale_y, scale_y], color="#333333", lw=2)
    ax.plot([5, 5], [scale_y - 0.8, scale_y + 0.8], color="#333333", lw=1.5)
    ax.plot([5 + scale_len, 5 + scale_len], [scale_y - 0.8, scale_y + 0.8], color="#333333", lw=1.5)
    ax.text(5 + scale_len / 2, scale_y - 2.0, f"{scale_len:.0f} m",
            ha="center", va="top", fontsize=7.5, color="#333333")


def _draw_plankopf(
    ax,
    projektname: str,
    variante_name: str,
    nutzungstyp: str,
    massstab: str,
    scores: dict,
    plannummer: str,
) -> None:
    """Zeichnet den DIN-Plankopf in den unteren Axes-Bereich."""
    import datetime
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    datum = datetime.date.today().strftime("%d.%m.%Y")
    gesamtscore = scores.get("gesamtscore", 0.0)

    felder = [
        ("PROJEKT",     projektname,                    0.00, 0.55),
        ("VARIANTE",    variante_name.replace("_", " "),0.00, 0.00),
        ("NUTZUNG",     nutzungstyp,                    0.22, 0.00),
        ("MASSSTAB",    massstab,                       0.44, 0.00),
        ("DATUM",       datum,                          0.58, 0.00),
        ("PLAN-NR.",    plannummer,                     0.72, 0.00),
        ("GESAMTSCORE", f"{gesamtscore:.1f} / 10",      0.86, 0.00),
    ]

    # Trennlinie oben
    ax.axhline(y=0.92, color="#444444", lw=1.0, xmin=0.0, xmax=1.0)

    for label, value, x, y_extra in felder:
        is_projekt = y_extra > 0.0
        box_x = x
        box_w = 0.22 if is_projekt else 0.14
        box_h = 0.88 if is_projekt else 0.88

        ax.add_patch(mpatches.FancyBboxPatch(
            (box_x + 0.002, 0.04), box_w - 0.004, box_h - 0.04,
            boxstyle="square,pad=0",
            linewidth=0.5, edgecolor="#888888", facecolor="#FFFFFF",
            transform=ax.transAxes,
        ))
        ax.text(
            box_x + 0.005, 0.90, label,
            transform=ax.transAxes,
            ha="left", va="top", fontsize=5.5, color="#888888",
        )
        ax.text(
            box_x + box_w / 2, 0.48, value,
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=8 if not is_projekt else 9,
            fontweight="bold", color="#111111",
            wrap=True,
        )

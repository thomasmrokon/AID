# Sprint 7A – Gemini: Kostenschätzung + DXF-Export

## Kontext

Du arbeitest an einem Python-Projekt (LangGraph + Streamlit) zur Industriebau-Planung.
Deine Aufgabe umfasst **drei Dateien** — keine anderen werden angefasst:

1. `app/data/costs.yaml` — neu erstellen
2. `app/tools/cost.py` — neu erstellen
3. `app/tools/dxf_export.py` — neu erstellen
4. `pyproject.toml` — eine Zeile ergänzen

---

## Datenstruktur (Referenz)

Jede Layoutvariante hat folgende Schlüssel (Auszug):

```python
variant = {
    "name": "A_Materialfluss",
    "zonen": [
        {
            "name": "Produktion",
            "x": 0.0, "y": 4.8,
            "breite": 60.0, "tiefe": 40.0,
            "flaeche_m2": 2400.0,        # Briefing-Anforderung
            "planned_area_m2": 2400.0,   # tatsächlich gezeichnet
            "din_kategorie": "NUF 3",    # NUF 2/3/4/7, TF, VF
            "farbe": "#E8A87C",
            "floors": 1,
            "schraffur": False,          # True = Erweiterungsreserve (nicht einrechnen)
        },
        ...
    ],
    "site_breite": 100.0,
    "site_tiefe": 96.0,
    "site_geometry": {
        "polygon": [[x, y], ...],
        "access_points": [{"id": "Z1", "side": "north", "point": [50, 96], "width_m": 7.5}],
        "area_m2": 9600.0,
        "planning": {"grz": 0.8, "gfz": 2.4, "max_gebaeudehoehe_m": 12.0},
    },
    "building_envelope": {"x": 5.0, "y": 4.8, "width_m": 90.0, "depth_m": 86.0},
    "raster_x": 18.0,
    "raster_y": 12.0,
}

briefing = {
    "nutzungstyp": "Produktion",       # "Produktion" | "Logistik" | "Data Center"
    "bgf_gesamt": 4000.0,
    "kranbahn_erforderlich": False,
    "hochregallager": False,
}
```

---

## Aufgabe 1: `pyproject.toml`

Im `dependencies`-Array ergänzen:

```toml
"ezdxf>=1.1",
```

---

## Aufgabe 2: `app/data/costs.yaml`

Vollständig neu erstellen. Enthält Baukosten-Richtwerte nach DIN-Kategorie und Nutzungstyp sowie Nebenkosten.

```yaml
# Baukosten-Richtwerte für Industriebau (Brutto, inkl. TGA, ohne Grundstück)
# Quelle: Schätzwerte, Kostenkennwerte BKI 2024

din_kategorien:
  NUF 2:   # Büro / Verwaltung
    min_eur_m2: 1400
    mid_eur_m2: 1800
    max_eur_m2: 2300
  NUF 3:   # Produktion / Fertigung
    min_eur_m2: 1100
    mid_eur_m2: 1400
    max_eur_m2: 1900
  NUF 4:   # Lager / Logistik
    min_eur_m2: 700
    mid_eur_m2: 900
    max_eur_m2: 1200
  NUF 7:   # Sozialräume / Sanitär
    min_eur_m2: 1200
    mid_eur_m2: 1600
    max_eur_m2: 2100
  TF:      # Technikfläche
    min_eur_m2: 900
    mid_eur_m2: 1200
    max_eur_m2: 1600
  VF:      # Erschließung / Verkehrsfläche
    min_eur_m2: 400
    mid_eur_m2: 550
    max_eur_m2: 750

# Zuschläge (€/m² auf betroffene Zonen)
zuschlaege:
  kranbahn_nuf3:        180   # €/m² Produktionsfläche wenn Kranbahn
  hochregal_nuf4:       280   # €/m² Lagerfläche wenn Hochregal (Gründung, Höhe)
  mehrgeschossig:        90   # €/m² pro zusätzliches Obergeschoss (ab 2. OG)

# Nebenkosten (Prozent der Baukosten KG 300+400)
nebenkosten:
  planung_honorar_pct:    0.13   # Architekten, Fachplaner (HOAI)
  bauleitung_pct:         0.04
  unvorhergesehenes_pct:  0.10
  aussenanlagen_pct:      0.06   # Erschließung, Parking, Begrünung
  baunebenkosten_pct:     0.05   # Genehmigung, Vermessung, Gutachten
```

---

## Aufgabe 3: `app/tools/cost.py`

Neue Datei. Liest `costs.yaml` und berechnet Kostenschätzung pro Variante.

```python
"""
AID Demo – Kostenschätzung
Berechnet eine grobe Kostenindikation (3 Szenarien) aus Zonen-Footprints.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml


_COSTS_PATH = Path(__file__).parent.parent / "data" / "costs.yaml"
_costs_cache: dict | None = None


def _load_costs() -> dict:
    global _costs_cache
    if _costs_cache is None:
        with open(_COSTS_PATH, encoding="utf-8") as f:
            _costs_cache = yaml.safe_load(f)
    return _costs_cache


def estimate_costs(variant: dict[str, Any], briefing: dict[str, Any]) -> dict[str, Any]:
    """Schätzt Baukosten für eine Layoutvariante (3 Szenarien: min / mid / max).

    Args:
        variant:  Varianten-Dict aus PlanningState["variants"][i]
        briefing: structured_briefing aus PlanningState

    Returns:
        {
            "baukosten_min":      float,   # € Untergrenze
            "baukosten_mid":      float,   # € Mittelwert
            "baukosten_max":      float,   # € Obergrenze
            "nebenkosten_mid":    float,   # € Nebenkosten (auf Mittelwert)
            "gesamtkosten_mid":   float,   # € Gesamt Mittelwert
            "kosten_je_m2_bgf":   float,   # €/m² Brutto-Grundfläche
            "zonen_aufschluesselung": [
                {
                    "zone": str,
                    "din_kategorie": str,
                    "flaeche_m2": float,
                    "kosten_min": float,
                    "kosten_mid": float,
                    "kosten_max": float,
                }
            ],
        }
    """
    costs = _load_costs()
    din_costs = costs.get("din_kategorien", {})
    zuschlaege = costs.get("zuschlaege", {})
    nebenkosten_cfg = costs.get("nebenkosten", {})

    kranbahn = bool(briefing.get("kranbahn_erforderlich", False))
    hochregal = bool(briefing.get("hochregallager", False))

    zonen = variant.get("zonen", [])
    aufschluesselung = []
    total_min = total_mid = total_max = 0.0
    total_bgf = 0.0

    for z in zonen:
        if z.get("schraffur"):          # Erweiterungsreserve überspringen
            continue
        din = z.get("din_kategorie", "NUF 3")
        floors = max(1, int(z.get("floors", 1)))
        footprint = float(z.get("breite", 0)) * float(z.get("tiefe", 0))
        flaeche = footprint * floors      # BGF dieser Zone (mehrgeschossig)

        base = din_costs.get(din, din_costs.get("NUF 3", {}))
        rate_min = float(base.get("min_eur_m2", 800))
        rate_mid = float(base.get("mid_eur_m2", 1100))
        rate_max = float(base.get("max_eur_m2", 1500))

        # Zuschläge
        if din == "NUF 3" and kranbahn:
            zuschl = float(zuschlaege.get("kranbahn_nuf3", 0))
            rate_min += zuschl
            rate_mid += zuschl
            rate_max += zuschl
        if din == "NUF 4" and hochregal:
            zuschl = float(zuschlaege.get("hochregal_nuf4", 0))
            rate_min += zuschl
            rate_mid += zuschl
            rate_max += zuschl
        if floors >= 2:
            og_zuschl = float(zuschlaege.get("mehrgeschossig", 0)) * (floors - 1)
            rate_min += og_zuschl
            rate_mid += og_zuschl
            rate_max += og_zuschl

        k_min = round(flaeche * rate_min, 0)
        k_mid = round(flaeche * rate_mid, 0)
        k_max = round(flaeche * rate_max, 0)

        aufschluesselung.append({
            "zone":          z.get("name", din),
            "din_kategorie": din,
            "flaeche_m2":    round(flaeche, 1),
            "kosten_min":    k_min,
            "kosten_mid":    k_mid,
            "kosten_max":    k_max,
        })
        total_min += k_min
        total_mid += k_mid
        total_max += k_max
        total_bgf += flaeche

    # Nebenkosten auf Mittelwert
    nk_pct = sum([
        float(nebenkosten_cfg.get("planung_honorar_pct", 0.13)),
        float(nebenkosten_cfg.get("bauleitung_pct", 0.04)),
        float(nebenkosten_cfg.get("unvorhergesehenes_pct", 0.10)),
        float(nebenkosten_cfg.get("aussenanlagen_pct", 0.06)),
        float(nebenkosten_cfg.get("baunebenkosten_pct", 0.05)),
    ])
    nebenkosten_mid = round(total_mid * nk_pct, 0)
    gesamtkosten_mid = round(total_mid + nebenkosten_mid, 0)
    kosten_je_m2 = round(gesamtkosten_mid / max(1.0, total_bgf), 0)

    return {
        "baukosten_min":          round(total_min, 0),
        "baukosten_mid":          round(total_mid, 0),
        "baukosten_max":          round(total_max, 0),
        "nebenkosten_mid":        nebenkosten_mid,
        "gesamtkosten_mid":       gesamtkosten_mid,
        "kosten_je_m2_bgf":       kosten_je_m2,
        "nebenkosten_pct":        round(nk_pct, 3),
        "zonen_aufschluesselung": aufschluesselung,
    }
```

---

## Aufgabe 4: `app/tools/dxf_export.py`

Neue Datei. Exportiert eine Layoutvariante als DXF-Datei (AutoCAD 2010).

**Abhängigkeit:** `ezdxf>=1.1` (bereits in pyproject.toml ergänzt).

**Layer-Struktur (DIN ISO 128, Liniengewichte in 1/100 mm):**

| Layer | Farbe (ACI) | Liniengewicht | Beschreibung |
|-------|-------------|----------------|--------------|
| `GRUNDSTUECK` | 3 (grün) | 50 = 0.50 mm | Grundstücksgrenze |
| `ABSTANDSFLAECHE` | 3 | 13 = 0.13 mm | Abstandsfläche gestrichelt |
| `GEBAEUDE_NUF2` | 5 (blau) | 35 = 0.35 mm | Büro/Verwaltung |
| `GEBAEUDE_NUF3` | 2 (gelb) | 35 | Produktion |
| `GEBAEUDE_NUF4` | 3 | 35 | Lager/Logistik |
| `GEBAEUDE_NUF7` | 6 (magenta) | 25 = 0.25 mm | Sozialräume |
| `GEBAEUDE_TF` | 1 (rot) | 25 | Technik |
| `GEBAEUDE_VF` | 4 (cyan) | 18 = 0.18 mm | Erschließung |
| `RESERVE` | 8 (grau) | 13 | Erweiterungsreserve |
| `RASTER` | 8 | 13 | Stützenraster |
| `ERSCHLIESSUNG` | 1 | 25 | Zufahrten |
| `BESCHRIFTUNG` | 7 (weiß/schwarz) | 18 | Zonennamen |
| `SCHRIFTFELD` | 7 | 25 | Plankopf |

**Hatch-Pattern je DIN-Kategorie:**

| DIN | Pattern | Scale |
|-----|---------|-------|
| NUF 2 | `ANSI31` | 1.5 |
| NUF 3 | `ANSI31` | 1.0 |
| NUF 4 | `ANSI37` | 2.0 |
| NUF 7 | `NET` | 1.5 |
| TF | `ANSI36` | 1.0 |
| VF | `ANSI31` | 4.0 (locker) |
| Reserve | `ANSI31` | 6.0 (sehr locker) |

```python
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
```

---

## Verifikation

Kurzes Testskript (nicht speichern, nur lokal ausführen):

```python
# Test 1: Kostenschätzung
from app.tools.cost import estimate_costs
variant_dummy = {
    "zonen": [
        {"name": "Produktion", "breite": 60, "tiefe": 40, "din_kategorie": "NUF 3",
         "floors": 1, "planned_area_m2": 2400, "schraffur": False},
        {"name": "Lager", "breite": 30, "tiefe": 40, "din_kategorie": "NUF 4",
         "floors": 1, "planned_area_m2": 1200, "schraffur": False},
    ]
}
result = estimate_costs(variant_dummy, {"nutzungstyp": "Produktion"})
print(f"Gesamtkosten: {result['gesamtkosten_mid']:,.0f} €")
print(f"€/m² BGF: {result['kosten_je_m2_bgf']:,.0f}")

# Test 2: DXF-Export
from app.tools.dxf_export import export_layout_to_dxf
dxf_bytes = export_layout_to_dxf(variant_dummy)
print(f"DXF-Größe: {len(dxf_bytes)} Bytes")
assert b"SECTION" in dxf_bytes, "DXF-Struktur fehlt"
print("OK")
```

---

## Wichtig: Was du NICHT änderst

- `app/agents/evaluation.py`
- `app/agents/report.py`
- `streamlit_app.py`
- Alle anderen Dateien — Codex übernimmt Drawing + UI

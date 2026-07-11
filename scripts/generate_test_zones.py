"""
Erzeugt Beispiel-Zonendaten als JSON-Dateien für den Grasshopper-Test.
Unabhängig von der LangGraph-Pipeline — kein API-Key erforderlich.

Aufruf: python scripts/generate_test_zones.py
"""
import json
from pathlib import Path

OUT = Path(__file__).parent.parent / "outputs"
OUT.mkdir(exist_ok=True)

# ── Gemeinsame Gebäudeparameter ────────────────────────────────────────────
# Site 90 × 60 m, Raster 18 × 12 m

# ── Variante A — Kamm-Struktur (Prozesskette als Zähne) ───────────────────
ZONES_A = [
    # Prozesskette (oberes Band, tiefe 24 m)
    dict(name="Wareneingang",       x=0,  y=24, breite=18, tiefe=24,
         flaeche_m2=200,  planned_area_m2=432,  din_kategorie="NUF 4",
         farbe="#5B8DB8", schraffur=False, floors=1, delta_m2=232,  delta_pct=116.0),
    dict(name="Lager Rohstoffe",    x=18, y=24, breite=18, tiefe=24,
         flaeche_m2=400,  planned_area_m2=432,  din_kategorie="NUF 4",
         farbe="#F4A261", schraffur=False, floors=1, delta_m2=32,   delta_pct=8.0),
    dict(name="Produktion",         x=36, y=24, breite=27, tiefe=24,
         flaeche_m2=1200, planned_area_m2=648,  din_kategorie="NUF 3",
         farbe="#2A9D8F", schraffur=False, floors=1, delta_m2=-552, delta_pct=-46.0),
    dict(name="Qualitaetssicherung",x=63, y=24, breite=9,  tiefe=24,
         flaeche_m2=120,  planned_area_m2=216,  din_kategorie="NUF 3",
         farbe="#E76F51", schraffur=False, floors=1, delta_m2=96,   delta_pct=80.0),
    dict(name="Lager Fertigwaren",  x=72, y=24, breite=18, tiefe=24,
         flaeche_m2=400,  planned_area_m2=432,  din_kategorie="NUF 4",
         farbe="#E9C46A", schraffur=False, floors=1, delta_m2=32,   delta_pct=8.0),
    # Erschliessung (Rücken)
    dict(name="Erschliessung",      x=0,  y=18, breite=90, tiefe=6,
         flaeche_m2=540,  planned_area_m2=540,  din_kategorie="VF",
         farbe="#C9CDD2", schraffur=False, floors=1, delta_m2=0,    delta_pct=0.0),
    # Support-Band (unteres Band, tiefe 18 m)
    dict(name="Buero / Verwaltung", x=0,  y=0,  breite=36, tiefe=18,
         flaeche_m2=250,  planned_area_m2=1296, din_kategorie="NUF 2",
         farbe="#A8DADC", schraffur=False, floors=2, delta_m2=1046, delta_pct=418.4),
    dict(name="Sozial",             x=36, y=0,  breite=18, tiefe=18,
         flaeche_m2=84,   planned_area_m2=648,  din_kategorie="NUF 7",
         farbe="#B7E4C7", schraffur=False, floors=2, delta_m2=564,  delta_pct=671.4),
    dict(name="Technik",            x=54, y=0,  breite=18, tiefe=18,
         flaeche_m2=168,  planned_area_m2=324,  din_kategorie="TF",
         farbe="#8D99AE", schraffur=False, floors=1, delta_m2=156,  delta_pct=92.9),
    dict(name="Versand",            x=72, y=0,  breite=18, tiefe=18,
         flaeche_m2=200,  planned_area_m2=324,  din_kategorie="NUF 4",
         farbe="#264653", schraffur=False, floors=1, delta_m2=124,  delta_pct=62.0),
]

# ── Variante B — Kompakter Block + Erweiterungsreserve ────────────────────
ZONES_B = [
    dict(name="Wareneingang",       x=0,  y=18, breite=18, tiefe=18,
         flaeche_m2=200,  planned_area_m2=324,  din_kategorie="NUF 4",
         farbe="#5B8DB8", schraffur=False, floors=1, delta_m2=124,  delta_pct=62.0),
    dict(name="Lager Rohstoffe",    x=18, y=18, breite=18, tiefe=18,
         flaeche_m2=400,  planned_area_m2=324,  din_kategorie="NUF 4",
         farbe="#F4A261", schraffur=False, floors=1, delta_m2=-76,  delta_pct=-19.0),
    dict(name="Produktion",         x=36, y=18, breite=18, tiefe=18,
         flaeche_m2=1200, planned_area_m2=324,  din_kategorie="NUF 3",
         farbe="#2A9D8F", schraffur=False, floors=1, delta_m2=-876, delta_pct=-73.0),
    dict(name="Lager Fertigwaren",  x=0,  y=0,  breite=18, tiefe=18,
         flaeche_m2=400,  planned_area_m2=324,  din_kategorie="NUF 4",
         farbe="#E9C46A", schraffur=False, floors=1, delta_m2=-76,  delta_pct=-19.0),
    dict(name="Versand",            x=18, y=0,  breite=18, tiefe=18,
         flaeche_m2=200,  planned_area_m2=324,  din_kategorie="NUF 4",
         farbe="#264653", schraffur=False, floors=1, delta_m2=124,  delta_pct=62.0),
    dict(name="Erschliessung",      x=0,  y=36, breite=54, tiefe=6,
         flaeche_m2=324,  planned_area_m2=324,  din_kategorie="VF",
         farbe="#C9CDD2", schraffur=False, floors=1, delta_m2=0,    delta_pct=0.0),
    dict(name="Buero / Verwaltung", x=0,  y=42, breite=27, tiefe=18,
         flaeche_m2=250,  planned_area_m2=972,  din_kategorie="NUF 2",
         farbe="#A8DADC", schraffur=False, floors=2, delta_m2=722,  delta_pct=288.8),
    dict(name="Sozial",             x=27, y=42, breite=18, tiefe=18,
         flaeche_m2=84,   planned_area_m2=648,  din_kategorie="NUF 7",
         farbe="#B7E4C7", schraffur=False, floors=2, delta_m2=564,  delta_pct=671.4),
    dict(name="Technik",            x=36, y=0,  breite=18, tiefe=18,
         flaeche_m2=168,  planned_area_m2=324,  din_kategorie="TF",
         farbe="#8D99AE", schraffur=False, floors=1, delta_m2=156,  delta_pct=92.9),
    # Erweiterungszone Ost (schraffiert)
    dict(name="Erweiterung ->",     x=54, y=0,  breite=36, tiefe=60,
         flaeche_m2=2160, planned_area_m2=2160, din_kategorie="NUF 4",
         farbe="#F5F5F5", schraffur=True,  floors=1, delta_m2=0,    delta_pct=0.0),
]

# ── Variante C — Kreuzgang-Struktur ───────────────────────────────────────
ZONES_C = [
    # NW-Quadrant: Support
    dict(name="Buero / Verwaltung", x=0,  y=30, breite=30, tiefe=24,
         flaeche_m2=250,  planned_area_m2=1440, din_kategorie="NUF 2",
         farbe="#A8DADC", schraffur=False, floors=2, delta_m2=1190, delta_pct=476.0),
    dict(name="Sozial",             x=0,  y=18, breite=18, tiefe=12,
         flaeche_m2=84,   planned_area_m2=432,  din_kategorie="NUF 7",
         farbe="#B7E4C7", schraffur=False, floors=2, delta_m2=348,  delta_pct=414.3),
    dict(name="Technik",            x=18, y=18, breite=12, tiefe=12,
         flaeche_m2=168,  planned_area_m2=144,  din_kategorie="TF",
         farbe="#8D99AE", schraffur=False, floors=1, delta_m2=-24,  delta_pct=-14.3),
    # NE-Quadrant: Prozess 1. Haelfte
    dict(name="Wareneingang",       x=36, y=30, breite=18, tiefe=24,
         flaeche_m2=200,  planned_area_m2=432,  din_kategorie="NUF 4",
         farbe="#5B8DB8", schraffur=False, floors=1, delta_m2=232,  delta_pct=116.0),
    dict(name="Lager Rohstoffe",    x=54, y=30, breite=18, tiefe=24,
         flaeche_m2=400,  planned_area_m2=432,  din_kategorie="NUF 4",
         farbe="#F4A261", schraffur=False, floors=1, delta_m2=32,   delta_pct=8.0),
    dict(name="Produktion",         x=72, y=30, breite=18, tiefe=24,
         flaeche_m2=1200, planned_area_m2=432,  din_kategorie="NUF 3",
         farbe="#2A9D8F", schraffur=False, floors=1, delta_m2=-768, delta_pct=-64.0),
    # EW-Korridor
    dict(name="Erschliessung",      x=0,  y=24, breite=90, tiefe=6,
         flaeche_m2=540,  planned_area_m2=540,  din_kategorie="VF",
         farbe="#C9CDD2", schraffur=False, floors=1, delta_m2=0,    delta_pct=0.0),
    # SW-Quadrant: Prozess 2. Haelfte
    dict(name="Lager Fertigwaren",  x=0,  y=0,  breite=30, tiefe=18,
         flaeche_m2=400,  planned_area_m2=540,  din_kategorie="NUF 4",
         farbe="#E9C46A", schraffur=False, floors=1, delta_m2=140,  delta_pct=35.0),
    # SE-Quadrant
    dict(name="Qualitaetssicherung",x=36, y=0,  breite=18, tiefe=18,
         flaeche_m2=120,  planned_area_m2=324,  din_kategorie="NUF 3",
         farbe="#E76F51", schraffur=False, floors=1, delta_m2=204,  delta_pct=170.0),
    dict(name="Versand",            x=54, y=0,  breite=36, tiefe=18,
         flaeche_m2=200,  planned_area_m2=648,  din_kategorie="NUF 4",
         farbe="#264653", schraffur=False, floors=1, delta_m2=448,  delta_pct=224.0),
]

VARIANTEN = {
    "A_Materialfluss":   ZONES_A,
    "B_Erweiterbarkeit": ZONES_B,
    "C_Ausgewogen":      ZONES_C,
}

for name, zones in VARIANTEN.items():
    path = OUT / f"zones_{name}.json"
    path.write_text(json.dumps(zones, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Geschrieben: {path}  ({len(zones)} Zonen)")

print("\nFertig. Dateien in:", OUT)

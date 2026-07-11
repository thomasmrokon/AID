"""Quick smoke test: kreuzgang with horizontal NW tiling + drawing."""
import os, sys, io, tempfile
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, '.')
os.environ.setdefault('OPENAI_API_KEY', 'dummy')

from app.agents.layout import _kreuzgang_layout
from app.tools.drawing import zeichne_layout
from app.tools.site import get_demo_site

envelope = {'x': 0.0, 'y': 0.0, 'width_m': 108.0, 'depth_m': 72.0, 'area_m2': 7776.0, 'max_footprint_m2': 7776.0}
zone_roles = {
    'Wareneingang': 'quadrant_SW_1', 'Lager Rohstoffe': 'quadrant_SW_2',
    'Produktion': 'quadrant_NE_1', 'Qualitaetssicherung': 'quadrant_NE_2',
    'Lager Fertigwaren': 'quadrant_SE_1', 'Versand': 'quadrant_SE_2',
    'Buero / Verwaltung': 'quadrant_NW_1', 'Technik': 'quadrant_NW_2', 'Sozial': 'quadrant_NW_3',
}
nodes = [
    {'name': 'Wareneingang', 'area_m2': 800, 'footprint_m2': 800, 'din_kategorie': 'NUF 4', 'farbe': '#5B8DB8', 'floors': 1, 'target_aspect': 1.2, 'breite': 32.0, 'tiefe': 25.0, 'planned_area_m2': 800, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Lager Rohstoffe', 'area_m2': 1200, 'footprint_m2': 1200, 'din_kategorie': 'NUF 4', 'farbe': '#F4A261', 'floors': 1, 'target_aspect': 1.4, 'breite': 41.0, 'tiefe': 29.0, 'planned_area_m2': 1200, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Produktion', 'area_m2': 3000, 'footprint_m2': 3000, 'din_kategorie': 'NUF 3', 'farbe': '#2A9D8F', 'floors': 1, 'target_aspect': 1.7, 'breite': 71.0, 'tiefe': 42.0, 'planned_area_m2': 3000, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Qualitaetssicherung', 'area_m2': 300, 'footprint_m2': 300, 'din_kategorie': 'NUF 3', 'farbe': '#E76F51', 'floors': 1, 'target_aspect': 1.3, 'breite': 20.0, 'tiefe': 15.0, 'planned_area_m2': 300, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Lager Fertigwaren', 'area_m2': 1000, 'footprint_m2': 1000, 'din_kategorie': 'NUF 4', 'farbe': '#E9C46A', 'floors': 1, 'target_aspect': 1.4, 'breite': 37.0, 'tiefe': 27.0, 'planned_area_m2': 1000, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Versand', 'area_m2': 600, 'footprint_m2': 600, 'din_kategorie': 'NUF 4', 'farbe': '#264653', 'floors': 1, 'target_aspect': 1.2, 'breite': 27.0, 'tiefe': 22.0, 'planned_area_m2': 600, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Buero / Verwaltung', 'area_m2': 600, 'footprint_m2': 300, 'din_kategorie': 'NUF 2', 'farbe': '#A8DADC', 'floors': 2, 'target_aspect': 1.6, 'breite': 22.0, 'tiefe': 14.0, 'planned_area_m2': 600, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Technik', 'area_m2': 200, 'footprint_m2': 200, 'din_kategorie': 'TF', 'farbe': '#8D99AE', 'floors': 1, 'target_aspect': 1.2, 'breite': 16.0, 'tiefe': 12.5, 'planned_area_m2': 200, 'delta_m2': 0, 'delta_pct': 0},
    {'name': 'Sozial', 'area_m2': 400, 'footprint_m2': 200, 'din_kategorie': 'NUF 7', 'farbe': '#B7E4C7', 'floors': 2, 'target_aspect': 1.3, 'breite': 16.0, 'tiefe': 12.5, 'planned_area_m2': 400, 'delta_m2': 0, 'delta_pct': 0},
]
topology = {'process_order': ['Wareneingang', 'Lager Rohstoffe', 'Produktion', 'Qualitaetssicherung', 'Lager Fertigwaren', 'Versand']}
s_c = {'process_pull': 1.00, 'compactness': 0.85, 'aspect_bias': 1.00, 'expansion_fraction': 0.20, 'seed': 303, 'edge_pull': 0.80}

f = io.StringIO()
with redirect_stdout(f):
    zones_c = _kreuzgang_layout(nodes=nodes, topology=topology, zone_roles=zone_roles, envelope=envelope, settings=s_c, raster_x=18, raster_y=12)

nw_names = {'Buero / Verwaltung', 'Technik', 'Sozial'}
nw_zones = [z for z in zones_c if z.name in nw_names]
print("NW-Zonen (horizontal):")
for z in nw_zones:
    ratio = max(z.breite, z.tiefe) / max(1, min(z.breite, z.tiefe))
    print(f"  {z.name:25s} {z.breite:.1f} x {z.tiefe:.1f}  ({ratio:.2f}:1)")

site = get_demo_site('C_unregelmaessig')
out = Path(tempfile.gettempdir()) / 'test_kreuzgang_horiz.png'
zeichne_layout(
    variante_name='C_Ausgewogen',
    beschreibung='Kreuzgang mit horizontalen NW-Zonen',
    zonen=zones_c,
    site_breite=108.0,
    site_tiefe=72.0,
    raster_x=18,
    raster_y=12,
    scores={
        'materialfluss_score': 7.2, 'erweiterbarkeit_score': 8.1,
        'tragwerk_score': 7.5, 'gesamtscore': 7.6,
        'regelverletzungen': [], 'empfohlen': True,
    },
    gewichtung={'materialfluss': 0.4, 'erweiterbarkeit': 0.35, 'tragwerk': 0.25},
    output_path=out,
    nutzungstyp='Produktion',
    site_geometry=site,
)
print(f"\nPNG gespeichert: {out}")
print("OK")

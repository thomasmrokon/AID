"""Verify aspect ratio enforcement across all three layout typologies."""
import os, sys, io
from contextlib import redirect_stdout
sys.path.insert(0, '.')
os.environ.setdefault('OPENAI_API_KEY', 'dummy')

from app.agents.layout import _kamm_layout, _block_mit_reserve_layout, _kreuzgang_layout, MAX_ASPECT_RATIO

envelope = {'x': 0.0, 'y': 0.0, 'width_m': 108.0, 'depth_m': 72.0, 'area_m2': 7776.0, 'max_footprint_m2': 7776.0}

zone_roles_kamm = {
    'Wareneingang': 'tooth_1', 'Lager Rohstoffe': 'tooth_2', 'Produktion': 'tooth_3',
    'Qualitaetssicherung': 'tooth_4', 'Lager Fertigwaren': 'tooth_5', 'Versand': 'tooth_6',
    'Buero / Verwaltung': 'spine_1', 'Technik': 'spine_2', 'Sozial': 'spine_3',
}
zone_roles_block_extreme = {
    'Wareneingang': 'block_1', 'Lager Rohstoffe': 'block_2', 'Produktion': 'block_3',
    'Qualitaetssicherung': 'block_4', 'Lager Fertigwaren': 'block_5', 'Versand': 'block_6',
    'Buero / Verwaltung': 'block_7', 'Technik': 'reserve_1', 'Sozial': 'block_8',
}
zone_roles_block_normal = {n: 'block' for n in [
    'Wareneingang', 'Lager Rohstoffe', 'Produktion', 'Qualitaetssicherung',
    'Lager Fertigwaren', 'Versand', 'Buero / Verwaltung', 'Technik', 'Sozial',
]}
zone_roles_kreuzgang = {
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
s_a = {'process_pull': 1.35, 'compactness': 0.45, 'aspect_bias': 1.15, 'expansion_fraction': 0.0, 'seed': 101, 'edge_pull': 0.75}
s_b = {'process_pull': 0.85, 'compactness': 1.25, 'aspect_bias': 0.95, 'expansion_fraction': 0.32, 'seed': 202, 'edge_pull': 0.90}
s_c = {'process_pull': 1.00, 'compactness': 0.85, 'aspect_bias': 1.00, 'expansion_fraction': 0.20, 'seed': 303, 'edge_pull': 0.80}

SKIP = {'Erschließung', 'Erweiterungsreserve'}

def check(name, zones, warn=''):
    print(f'\nVariante {name}')
    bad = []
    for z in zones:
        if z.name in SKIP:
            continue
        ratio = max(z.breite, z.tiefe) / max(1.0, min(z.breite, z.tiefe))
        flag = '  *** EXTREM ***' if ratio > MAX_ASPECT_RATIO else ''
        if flag:
            bad.append(z.name)
        print(f'  {z.name:28s} {z.breite:5.1f} x {z.tiefe:5.1f}  ({ratio:.1f}:1){flag}')
    if warn.strip():
        print(f'  [warn] {warn.strip()}')
    print('  -> OK' if not bad else f'  -> {len(bad)} EXTREM: {bad}')
    return bad

f = io.StringIO()
with redirect_stdout(f):
    zones_a = _kamm_layout(nodes=nodes, topology=topology, zone_roles=zone_roles_kamm, envelope=envelope, settings=s_a, raster_x=18, raster_y=12)
bad_a = check('A kamm (suffix-Rollen)', zones_a, f.getvalue())

f = io.StringIO()
with redirect_stdout(f):
    zones_be = _block_mit_reserve_layout(nodes=nodes, topology=topology, zone_roles=zone_roles_block_extreme, envelope=envelope, settings=s_b, raster_x=18, raster_y=12, freie_fassade_pct=0.32)
bad_be = check('B block_reserve (Technik=reserve, 6 Prozesszonen)', zones_be, f.getvalue())

f = io.StringIO()
with redirect_stdout(f):
    zones_bn = _block_mit_reserve_layout(nodes=nodes, topology=topology, zone_roles=zone_roles_block_normal, envelope=envelope, settings=s_b, raster_x=18, raster_y=12, freie_fassade_pct=0.32)
bad_bn = check('B block_reserve (Normalfall, alle im Block)', zones_bn, f.getvalue())

f = io.StringIO()
with redirect_stdout(f):
    zones_c = _kreuzgang_layout(nodes=nodes, topology=topology, zone_roles=zone_roles_kreuzgang, envelope=envelope, settings=s_c, raster_x=18, raster_y=12)
bad_c = check('C kreuzgang (suffix-Rollen)', zones_c, f.getvalue())

total = len(bad_a) + len(bad_be) + len(bad_bn) + len(bad_c)
print(f'\n=== Gesamt: {total} Zonen mit Seitenverhaeltnis > {MAX_ASPECT_RATIO} ===')

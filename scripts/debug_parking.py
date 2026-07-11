"""Debug: Stellplatz-Grenzen für Demo-Sites."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.tools.site import get_demo_site, compute_building_envelope
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.drawing import berechne_stellplaetze, STELLPLATZ_TIEFE, FAHRGANG_BREITE

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}
ROW_HEIGHT = STELLPLATZ_TIEFE + FAHRGANG_BREITE / 2

for site_id in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site = get_demo_site(site_id)
    env = compute_building_envelope(site)
    state = {'user_input': BASE, 'briefing': BASE, 'site_id': site_id, 'site_geometry': site}
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    print(f'\n=== {site_id} ===')
    print(f'  rotated_site_south={env.get("rotated_site_south")}, rotated_site_north={env.get("rotated_site_north")}')

    for v in state.get('variants', []):
        zonen = v['zonen']
        non_hatch = [z for z in zonen if not z.get('schraffur') and z.get('din_kategorie') != 'VF']
        if not non_hatch:
            continue
        by0 = min(z['y'] for z in non_hatch)
        by1 = max(z['y'] + z['tiefe'] for z in non_hatch)
        bx0 = min(z['x'] for z in non_hatch)
        bx1 = max(z['x'] + z['breite'] for z in non_hatch)

        site_south = float((env or {}).get('rotated_site_south') or 0.0)
        site_north = float((env or {}).get('rotated_site_north') or site.get('depth_m', 100))

        south_start = by0 - 1.5
        max_rows_south = 0
        while south_start - (max_rows_south + 1) * ROW_HEIGHT >= site_south:
            max_rows_south += 1

        north_start = by1 + 1.5
        max_rows_north = 0
        while north_start + (max_rows_north + 1) * ROW_HEIGHT <= site_north:
            max_rows_north += 1

        # First row bottom
        first_row_bottom = south_start - STELLPLATZ_TIEFE if max_rows_south > 0 else None

        building_fp = sum((z['breite'] * z['tiefe']) for z in non_hatch)
        site_area = float(site.get('area_m2', 0) or site.get('width_m', 100) * site.get('depth_m', 100))
        theoretical = berechne_stellplaetze(site_area, building_fp)

        print(f'  {v["name"]:25s}: by0={by0:.1f} by1={by1:.1f} | '
              f'south_start={south_start:.1f} max_rows_S={max_rows_south} | '
              f'north_start={north_start:.1f} max_rows_N={max_rows_north} | '
              f'theoretical={theoretical} SP')
        if first_row_bottom is not None and first_row_bottom < site_south:
            print(f'    !! Erste Reihe Suedseite ({first_row_bottom:.1f}m) unterhalb site_south ({site_south:.1f}m)')

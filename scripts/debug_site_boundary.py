"""Debug site boundaries and building placement."""
import sys; sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.site import get_demo_site, compute_building_envelope
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for sid in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site = get_demo_site(sid)
    envelope = compute_building_envelope(site)

    print(f"\n=== {sid} ===")
    print(f"Site: {site.get('width_m')}x{site.get('depth_m')} m")
    print(f"Site polygon: {site.get('polygon_points', 'NONE')}")
    print(f"Envelope: x=[{envelope['x']:.1f},{envelope['x']+envelope['width_m']:.1f}] y=[{envelope['y']:.1f},{envelope['y']+envelope['depth_m']:.1f}]")

    state = PlanningState(user_input={**BASE, 'grundstueck_id': sid})
    state['site_geometry'] = site
    state['gap_strategy'] = 'sort'
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    for v in state.get('variants', []):
        real = [z for z in v['zonen'] if not z.get('schraffur')]
        if not real:
            continue
        bx1 = min(z['x'] for z in real)
        bx2 = max(z['x']+z['breite'] for z in real)
        by1 = min(z['y'] for z in real)
        by2 = max(z['y']+z['tiefe'] for z in real)

        env_x2 = envelope['x'] + envelope['width_m']
        env_y2 = envelope['y'] + envelope['depth_m']

        overflow_x = max(0, bx2 - env_x2)
        overflow_y = max(0, by2 - env_y2)
        gap_top = env_y2 - by2  # empty space at top
        gap_right = env_x2 - bx2  # empty space at right

        # Check against site polygon too
        site_w = site.get('width_m', 0)
        site_d = site.get('depth_m', 0)
        overflow_site_x = max(0, bx2 - site_w)
        overflow_site_y = max(0, by2 - site_d)

        print(f"  {v['name']:25} building=[{bx1:.1f},{bx2:.1f}]x[{by1:.1f},{by2:.1f}]"
              f" gap_top={gap_top:.1f}m gap_right={gap_right:.1f}m"
              f" overflow_env=({overflow_x:.1f},{overflow_y:.1f})"
              f" overflow_site=({overflow_site_x:.1f},{overflow_site_y:.1f})")

"""Check VF zones and overall layout for gap_strategy=none (Streamlit default)."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
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

site = get_demo_site('A_kompakt')
envelope = compute_building_envelope(site)
state = PlanningState(user_input={**BASE, 'grundstueck_id': 'A_kompakt'})
state['site_geometry'] = site
state['gap_strategy'] = 'none'  # Streamlit default!
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

print(f"Envelope: [{envelope['x']:.1f},{envelope['y']:.1f}] -> [{envelope['x']+envelope['width_m']:.1f},{envelope['y']+envelope['depth_m']:.1f}]")

for v in state.get('variants', []):
    all_zones = v['zonen']
    print(f"\n=== {v['name']} (gap_strategy=none) ===")
    for z in sorted(all_zones, key=lambda z: (z['x'], z['y'])):
        x1, y1 = z['x'], z['y']
        x2, y2 = x1+z['breite'], y1+z['tiefe']
        b, t = z['breite'], z['tiefe']
        ar = max(b, t) / max(min(b, t), 0.01)
        tag = "(VF)" if z.get('din_kategorie') == 'VF' else ""
        tag2 = "(schr)" if z.get('schraffur') else ""
        ar_flag = "!AR!" if ar > 4.01 and not z.get('schraffur') else ""
        print(f"  {z['name']:26} x=[{x1:5.1f},{x2:5.1f}] y=[{y1:5.1f},{y2:5.1f}] {b:.1f}x{t:.1f}m AR={ar:.1f} {tag}{tag2}{ar_flag}")

    real = [z for z in all_zones if not z.get('schraffur')]
    if real:
        bx1 = min(z['x'] for z in real)
        bx2 = max(z['x']+z['breite'] for z in real)
        by1 = min(z['y'] for z in real)
        by2 = max(z['y']+z['tiefe'] for z in real)
        print(f"  => Building BBox: x=[{bx1:.1f},{bx2:.1f}] y=[{by1:.1f},{by2:.1f}]  ({bx2-bx1:.1f}x{by2-by1:.1f}m)")

"""Debug exact zone coordinates to find gap cause."""
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

for sid in ['A_kompakt']:
    site = get_demo_site(sid)
    envelope = compute_building_envelope(site)
    state = PlanningState(user_input={**BASE, 'grundstueck_id': sid})
    state['site_geometry'] = site
    state['gap_strategy'] = 'sort'
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    print(f"Envelope: x=[{envelope['x']:.1f},{envelope['x']+envelope['width_m']:.1f}] y=[{envelope['y']:.1f},{envelope['y']+envelope['depth_m']:.1f}]")
    print(f"  bw={envelope['width_m']:.1f}, bd={envelope['depth_m']:.1f}")

    for v in state.get('variants', []):
        all_zones = v['zonen']
        real = [z for z in all_zones if not z.get('schraffur')]
        schr = [z for z in all_zones if z.get('schraffur')]

        print(f"\n=== {v['name']} ===")
        for z in sorted(all_zones, key=lambda z: (z['x'], z['y'])):
            x1, y1 = z['x'], z['y']
            x2, y2 = x1+z['breite'], y1+z['tiefe']
            tag = "(schr)" if z.get('schraffur') else ""
            print(f"  {z['name']:26} x=[{x1:5.1f},{x2:5.1f}] y=[{y1:5.1f},{y2:5.1f}] {z['breite']:.1f}x{z['tiefe']:.1f}m {tag}")

        if real:
            by1r = min(z['y'] for z in real)
            by2r = max(z['y']+z['tiefe'] for z in real)
            bx1r = min(z['x'] for z in real)
            bx2r = max(z['x']+z['breite'] for z in real)
            print(f"  BBox (real): x=[{bx1r:.1f},{bx2r:.1f}] y=[{by1r:.1f},{by2r:.1f}]")

            # Scanner range
            step = 3.0
            ys = [by1r + step*j for j in range(int((by2r-by1r)/step)+2)]
            print(f"  Scanner y-range: {ys[0]:.1f}..{ys[-1]:.1f} ({len(ys)} steps)")
            extra = [y for y in ys if y > by2r + 0.01]
            print(f"  EXTRA points beyond by2={by2r:.1f}: {extra}")

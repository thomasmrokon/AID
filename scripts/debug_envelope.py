"""Vergleicht rohes vs skaliertes Envelope und zeigt Zeichnungsgrenzen."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.tools.site import get_demo_site, compute_building_envelope
from app.agents.layout import _skaliere_envelope_auf_briefing
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for sid in ['A_kompakt', 'C_unregelmaessig']:
    print(f"\n{'='*60}")
    print(f"Site: {sid}")
    site = get_demo_site(sid)
    raw_env = compute_building_envelope(site)
    print(f"RAW envelope:    x={raw_env['x']:.2f} y={raw_env['y']:.2f}  "
          f"w={raw_env['width_m']:.2f} d={raw_env['depth_m']:.2f}  "
          f"Fläche={raw_env['width_m']*raw_env['depth_m']:.0f} m²")
    print(f"  rechte Kante: {raw_env['x']+raw_env['width_m']:.2f}  "
          f"obere Kante: {raw_env['y']+raw_env['depth_m']:.2f}")

    state = PlanningState(user_input={**BASE, 'grundstueck_id': sid})
    state['site_geometry'] = site
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    nodes = state['topology_diagram']['nodes']
    total_fp = sum(float(n.get('footprint_m2') or n.get('area_m2') or 0) for n in nodes)
    print(f"Summe Knoten-FP: {total_fp:.0f} m²  (× 1.10 = {total_fp*1.10:.0f} m²)")

    scaled = _skaliere_envelope_auf_briefing(raw_env, nodes, 18.0, 12.0)
    print(f"SCALED envelope: x={scaled['x']:.2f} y={scaled['y']:.2f}  "
          f"w={scaled['width_m']:.2f} d={scaled['depth_m']:.2f}  "
          f"Fläche={scaled['width_m']*scaled['depth_m']:.0f} m²")
    print(f"  rechte Kante: {scaled['x']+scaled['width_m']:.2f}  "
          f"obere Kante: {scaled['y']+scaled['depth_m']:.2f}")

    dw = raw_env['width_m'] - scaled['width_m']
    dd = raw_env['depth_m'] - scaled['depth_m']
    print(f"DELTA: Gebäude ist {dw:.1f}m schmaler und {dd:.1f}m flacher als das Baufeld-Envelope")
    print(f"=> Sichtbare Fuge rechts: {dw:.1f}m, oben: {dd:.1f}m")

    # Site polygon bounds
    pts = site.get('polygon', [])
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        print(f"Site-Polygon:    x=[{min(xs):.1f}..{max(xs):.1f}]  y=[{min(ys):.1f}..{max(ys):.1f}]")

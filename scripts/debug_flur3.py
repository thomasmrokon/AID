"""Debug: _squarified_layout_main mit exakter layout_agent-Envelope."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.layout import (
    layout_agent, _squarified_layout_main, _insert_vf_corridors,
    _skaliere_envelope_auf_briefing, _layout_from_topology
)
from app.tools.geometry import Zone, shared_wall
from app.tools.site import get_demo_site, compute_building_envelope, site_bounds
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}
site = get_demo_site('A_kompakt')
state = PlanningState(user_input={**BASE, 'grundstueck_id': 'A_kompakt'})
state['site_geometry'] = site
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))

briefing = state['structured_briefing']
rules    = state['rules']
topo     = state['topology_diagram']
proc_ord = topo.get('process_order', [])

# Gleiche Envelope wie layout_agent
raw_env = compute_building_envelope(site) or {}
env = _skaliere_envelope_auf_briefing(raw_env, briefing)
print(f"Skalierte Envelope: {env['width_m']:.1f} x {env.get('height_m', env.get('depth_m',0)):.1f}")

# _squarified_layout_main direkt aufrufen wie layout_agent
nodes = topo['nodes']
zones = _squarified_layout_main(
    nodes=nodes,
    envelope=env,
    variante_key='A_Materialfluss',
    graph_weights={},
    process_order=proc_ord,
    gap_strategy='corridor',
)
print(f"\nZonen ({len(zones)}):")
for z in sorted(zones, key=lambda z: (round(z.y, 0), round(z.x, 0))):
    is_cor = 'Erschliessung' in z.name
    flag = ' *** KORRIDOR ***' if is_cor else ''
    print(f"  {z.name:30} ({z.breite:.1f}x{z.tiefe:.1f}) @ ({z.x:.1f},{z.y:.1f}){flag}")

print(f"\n--- shared_wall Prüfung ---")
zone_map = {z.name: z for z in zones}
for i in range(len(proc_ord)-1):
    a_name, b_name = proc_ord[i], proc_ord[i+1]
    if a_name not in zone_map or b_name not in zone_map:
        print(f"  FEHLT: {a_name} oder {b_name}")
        continue
    sw = shared_wall(zone_map[a_name], zone_map[b_name])
    status = 'Korridor!' if sw < 0.5 else 'OK'
    print(f"  {a_name[:22]:24} → {b_name[:22]:24}: sw={sw:.2f}m [{status}]")

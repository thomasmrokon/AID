"""Debug topology node fields and envelope scaling."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
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
state['gap_strategy'] = 'sort'
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))

print(f"Envelope before scaling: {envelope['width_m']}x{envelope['depth_m']} = {envelope['width_m']*envelope['depth_m']:.0f}m2")

# Find topology key
topo_keys = [k for k in state.keys() if 'topo' in k.lower() or 'nodes' in k.lower()]
print(f"Topology-related keys: {topo_keys}")

topology = state.get('topology') or {}
nodes = topology.get('nodes', [])
print(f"Nodes found: {len(nodes)}")

if not nodes:
    # Try other keys
    for key in state.keys():
        val = state.get(key)
        if isinstance(val, dict) and 'nodes' in val:
            print(f"Found nodes in key '{key}': {len(val['nodes'])} nodes")
            nodes = val['nodes']
            break

print(f"\nTopology nodes ({len(nodes)}):")
total_fp_area = 0
total_fp_footprint = 0
for n in nodes:
    area = n.get('area_m2', 0) or 0
    fp = n.get('footprint_m2', 0) or 0
    planned = n.get('planned_area_m2', 0) or 0
    floors = n.get('floors', 1) or 1
    fp_calc = area / max(1, floors) if area else 0
    used = fp if fp else area  # what _skaliere uses
    total_fp_area += area
    total_fp_footprint += used
    print(f"  {n['name']:26} area={area:6.0f} footprint={fp:6.0f} planned={planned:6.0f} floors={floors} used={used:.0f} actual_fp={fp_calc:.0f}")

print(f"\nSums:")
print(f"  total_fp_area (area_m2)   = {total_fp_area:.0f} m2")
print(f"  total_fp_footprint (used) = {total_fp_footprint:.0f} m2")
print(f"\nEnvelope area = {envelope['width_m']*envelope['depth_m']:.0f} m2")
print(f"  1.10*1.05 threshold = {total_fp_footprint*1.155:.0f} m2")
print(f"  Would _skaliere shrink? {envelope['width_m']*envelope['depth_m'] > total_fp_footprint*1.155}")

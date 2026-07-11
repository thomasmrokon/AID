"""Debug: Was passiert innerhalb _insert_vf_corridors?"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.layout import layout_agent, _squarified_layout_main, _insert_vf_corridors
from app.tools.geometry import Zone, shared_wall
from app.tools.site import get_demo_site, compute_building_envelope
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

# topology-Nodes holen
topo     = state['topology_diagram']
proc_ord = topo.get('process_order', [])
nodes    = topo['nodes']
env      = compute_building_envelope(site)

print("process_order:", proc_ord)
print(f"Env: {env}")
print()

# _squarified_layout_main aufrufen
zones = _squarified_layout_main(
    nodes=nodes,
    envelope=env,
    variante_key='A_Materialfluss',
    graph_weights={},
    process_order=proc_ord,
    gap_strategy='corridor',
)
print(f"Zonen nach Layout ({len(zones)}):")
for z in sorted(zones, key=lambda z: (round(z.y), round(z.x))):
    is_cor = 'Erschliessung' in z.name
    flag = ' *** KORRIDOR ***' if is_cor else ''
    print(f"  {z.name:30} ({z.breite:.1f}x{z.tiefe:.1f}) @ ({z.x:.1f},{z.y:.1f}){flag}")

# Manuell _insert_vf_corridors Schritt prüfen
print(f"\n--- Prüfung shared_wall entlang Prozesskette ---")
zone_map = {z.name: z for z in zones}
missing_names = [n for n in proc_ord if n not in zone_map]
print(f"Fehlende Prozessknoten in zone_map: {missing_names}")
print()
for i in range(len(proc_ord)-1):
    src_name = proc_ord[i]
    tgt_name = proc_ord[i+1]
    if src_name not in zone_map or tgt_name not in zone_map:
        print(f"  SKIP: {src_name} → {tgt_name} (nicht in zone_map)")
        continue
    a = zone_map[src_name]
    b = zone_map[tgt_name]
    sw = shared_wall(a, b)
    status = 'Korridor nötig!' if sw < 0.5 else 'Wand OK'
    print(f"  {src_name[:22]:24} → {tgt_name[:22]:24}: sw={sw:.2f}m  [{status}]")

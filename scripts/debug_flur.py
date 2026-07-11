"""Debug: Flur-Generator — prüft ob Korridore erzeugt werden."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.layout import layout_agent, _insert_vf_corridors, _squarified_layout_main
from app.tools.geometry import Zone, shared_wall
from app.tools.site import get_demo_site
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

state['gap_strategy'] = 'corridor'
result = layout_agent(state)

v0 = result['variants'][0]
zonen_raw = v0['zonen']
print(f"Zones in Var A: {len(zonen_raw)}")
print(f"Type: {type(zonen_raw[0])}")

# Prozessreihenfolge aus Topology
topo = state.get('topology_diagram', {})
proc_ord = topo.get('process_order', [])
print(f"Process order: {proc_ord}")

# Wandkontakte manuell prüfen (Dicts → shared_wall manuell)
print("\nWandkontakte entlang Prozesskette (A_Materialfluss):")
zone_map = {z['name']: z for z in zonen_raw}
for i in range(len(proc_ord)-1):
    a_name = proc_ord[i]
    b_name = proc_ord[i+1]
    if a_name not in zone_map:
        print(f"  FEHLT: {a_name}")
        continue
    if b_name not in zone_map:
        print(f"  FEHLT: {b_name}")
        continue
    a = zone_map[a_name]
    b = zone_map[b_name]
    # Manuelle Wandkontakt-Berechnung (kein shared_wall auf dicts)
    # Horizontaler Kontakt: rechter Rand a == linker Rand b
    h_contact = max(0, min(a['y'] + a['tiefe'], b['y'] + b['tiefe']) - max(a['y'], b['y']))
    v_contact = max(0, min(a['x'] + a['breite'], b['x'] + b['breite']) - max(a['x'], b['x']))
    h_gap = abs((a['x'] + a['breite']) - b['x']) < 0.5 or abs((b['x'] + b['breite']) - a['x']) < 0.5
    v_gap = abs((a['y'] + a['tiefe']) - b['y']) < 0.5 or abs((b['y'] + b['tiefe']) - a['y']) < 0.5
    wall = h_contact if h_gap else (v_contact if v_gap else 0)
    status = "✓" if wall > 0.5 else "✗ LÜCKE"
    print(f"  {a_name[:20]:22} → {b_name[:20]:22}: Wand={wall:.1f}m {status}")

# Alle Zonen ausgeben
print("\nAlle Zonen in A_Materialfluss:")
for z in sorted(zonen_raw, key=lambda z: (z['y'], z['x'])):
    name = z['name']
    is_corridor = 'Erschliessung' in name
    flag = " ← KORRIDOR" if is_corridor else ""
    print(f"  {name:30} x={z['x']:6.1f} y={z['y']:6.1f} w={z['breite']:6.1f} h={z['tiefe']:6.1f}{flag}")

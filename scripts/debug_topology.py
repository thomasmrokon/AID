"""Diagnose C_unregelmaessig zone AR and typology selection."""
import sys; sys.path.insert(0, '.')
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception: pass
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing  import briefing_agent
from app.agents.rules     import rule_agent
from app.agents.topology  import topology_agent
from app.state import PlanningState

state = PlanningState(user_input={
    'nutzungstyp': 'Produktion',
    'produktionsflaeche': 3000, 'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'A_kompakt',
})
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))

topo = state.get('topology_diagram') or {}
print('=== TOPOLOGY_DIAGRAM NODES ===')
for n in topo.get('nodes', []):
    name = n['name']
    area = n.get('area_m2', 0)
    din  = n.get('din_kategorie', '?')
    farbe = n.get('farbe', '?')
    print(f"  {name:<28}  area={area:>5.0f} m2  din={din}  farbe={farbe}")

print()
print('=== TOPOLOGY_DIAGRAM EDGES ===')
for e in topo.get('edges', []):
    src = e['source']
    tgt = e['target']
    w   = e.get('weight', 0)
    kind = e.get('kind', '?')
    print(f"  {src:<28} -> {tgt:<28}  w={w:.2f}  kind={kind}")

print()
print('=== PROCESS_ORDER ===')
print('  ' + ' -> '.join(topo.get('process_order', [])))

print()
print('=== ALLE STATE-KEYS ===')
for k in sorted(state.keys()):
    v = state.get(k)
    vtype = type(v).__name__
    print(f"  {k:<30} ({vtype})")

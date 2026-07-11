import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.state import PlanningState

state = PlanningState(user_input={
    'nutzungstyp': 'Produktion',
    'produktionsflaeche': 3000,
    'lager_rohstoffe': 600,
    'lager_fertigwaren': 600,
    'wareneingang': 250,
    'versand': 250,
    'qualitaetssicherung': 150,
    'buero_nuf2': 300,
    'kranbahn_erforderlich': False,
    'grundstueck_id': 'B',
})
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))

topo = state['topology_diagram']
print('process_order:', topo.get('process_order', []))
print()
print('nodes:')
for n in topo['nodes']:
    fp = n.get('footprint_m2', n.get('area_m2', 0) / max(1, n.get('floors', 1)))
    print(f"  {n['name']:<25} din={n['din_kategorie']:<8} fp={fp:.0f} area={n.get('area_m2',0):.0f} floors={n.get('floors',1)} access={n.get('access_role','')}")

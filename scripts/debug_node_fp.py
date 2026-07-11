"""Check topology node footprint values."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
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

topo = state['topology_diagram']
print(f"Total nodes: {len(topo['nodes'])}")
total_fp = 0
for n in topo['nodes']:
    fp = n.get('footprint_m2') or n.get('area_m2') or 0
    total_fp += fp
    print(f"  {n['name']:26} footprint={fp:>8.1f}  area={n.get('area_m2', '?'):>8}  cat={n.get('din_kategorie','?'):>6}  role={n.get('role','?')}")
print(f"Total footprint: {total_fp:.1f}")

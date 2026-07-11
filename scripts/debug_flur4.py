"""Debug: Was ist die typology_assignment?"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.layout import layout_agent
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

# Typology assignments aus dem State
typology_assignments = state.get('typology_assignments') or {}
print("Typology Assignments:", typology_assignments)

# Layout ausführen und prüfen
state['gap_strategy'] = 'corridor'
result = layout_agent(state)
state.update(result)

for v in state['variants']:
    print(f"\nVariante: {v['name']}")
    print(f"  typology: {typology_assignments.get(v['name'], 'unbekannt')}")
    zonen = v.get('zonen', [])
    print(f"  Zonen: {len(zonen)}")
    corridors = [z for z in zonen if isinstance(z, dict) and 'Erschliessung' in z.get('name', '')]
    print(f"  Korridore: {len(corridors)}")

"""Debug: Vollständige Pipeline mit strategy_agent — testet Flur-Generator."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing  import briefing_agent
from app.agents.rules     import rule_agent
from app.agents.topology  import topology_agent
from app.agents.strategy  import layout_strategy_agent as strategy_agent
from app.agents.layout    import layout_agent
from app.tools.site       import get_demo_site
from app.state            import PlanningState

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
state.update(strategy_agent(state))

print("Typology Assignments:", state.get('typology_assignments'))

state['gap_strategy'] = 'corridor'
result = layout_agent(state)
state.update(result)

print()
for v in state['variants']:
    zonen = v.get('zonen', [])
    tassign = state.get('typology_assignments', {}).get(v['name'], 'unbekannt')
    corridors = [z for z in zonen if isinstance(z, dict) and 'Erschliessung' in z.get('name', '')]
    print(f"  {v['name']:22} [{tassign:14}]: {len(zonen)} Zonen, {len(corridors)} Korridor(e)")
    for c in corridors:
        print(f"    > {c['name']}")

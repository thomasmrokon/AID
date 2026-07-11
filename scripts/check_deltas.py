"""Check zone area deltas and typology assignments after fixes."""
import sys; sys.path.insert(0, '.')
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception: pass
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing  import briefing_agent
from app.agents.rules     import rule_agent
from app.agents.topology  import topology_agent
from app.agents.strategy  import layout_strategy_agent
from app.agents.layout    import layout_agent
from app.tools.site       import get_demo_site
from app.state            import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for sid in ['A_kompakt', 'C_unregelmaessig']:
    site  = get_demo_site(sid)
    state = PlanningState(user_input={**BASE, 'grundstueck_id': sid})
    state['site_geometry'] = site
    state['gap_strategy']  = 'sort'
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))

    tassign = state.get('typology_assignments', {})
    print(f"\n{'='*55}")
    print(f"Site: {sid}  |  typologies: {tassign}")

    state.update(layout_agent(state))

    for v in state.get('variants', []):
        deltas = []
        for zd in v['zonen']:
            if zd.get('schraffur'):
                continue
            ist  = zd.get('planned_area_m2') or zd['breite'] * zd['tiefe']
            soll = zd['flaeche_m2']
            if soll > 0:
                deltas.append(abs(round((ist - soll) / soll * 100, 1)))
        avg_d = sum(deltas) / len(deltas) if deltas else 0
        max_d = max(deltas) if deltas else 0
        print(f"  {v['name']:25s}: avg_d={avg_d:.1f}%  max_d={max_d:.1f}%")

print("\nDONE.")

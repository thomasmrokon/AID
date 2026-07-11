"""AR-Check für alle Grundstücke mit gap_strategy='sort'."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone
from app.tools.site import get_demo_site
from app.state import PlanningState

BASE_INPUT = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for grundstueck in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site = get_demo_site(grundstueck)
    state = PlanningState(user_input={**BASE_INPUT, 'grundstueck_id': grundstueck})
    state['site_geometry'] = site
    state['gap_strategy'] = 'sort'
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    print(f"\n{grundstueck}:")
    total_violations = 0
    max_ar = 0.0
    for v in state['variants']:
        zonen = [Zone(**z) for z in v['zonen']]
        violations = []
        for z in zonen:
            if z.schraffur or z.din_kategorie == 'VF':
                continue
            ar = max(z.breite, z.tiefe) / max(0.01, min(z.breite, z.tiefe))
            max_ar = max(max_ar, ar)
            if ar > 4.01:
                violations.append(f"{z.name} AR={ar:.2f}")
        total_violations += len(violations)
        status = "OK" if not violations else f"VIOLATION: {', '.join(violations)}"
        print(f"  {v['name']}: {status}")
    print(f"  => Total violations: {total_violations}, max AR: {max_ar:.2f}")

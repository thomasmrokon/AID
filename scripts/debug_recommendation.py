"""Prüft Empfehlung und Scores in der vollständigen Pipeline."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing    import briefing_agent
from app.agents.rules       import rule_agent
from app.agents.topology    import topology_agent
from app.agents.strategy    import layout_strategy_agent
from app.agents.layout      import layout_agent
from app.agents.evaluation  import evaluation_agent
from app.tools.site         import get_demo_site
from app.state              import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for site_id in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    print(f"\n{'='*60}")
    print(f"Site: {site_id}")
    print('='*60)
    site = get_demo_site(site_id)
    state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
    state['site_geometry'] = site
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))
    state.update(evaluation_agent(state))

    evals    = state['evaluations']
    selected = state['selected_variant']
    print(f"\nEmpfehlung: {selected}")
    print()
    for e in sorted(evals, key=lambda x: x['gesamtscore'], reverse=True):
        star = ' ★' if e['variante'] == selected else ''
        print(f"  {e['variante']:22}: {e['gesamtscore']:.2f}"
              f"  (MF={e['materialfluss_score']:.1f} EB={e['erweiterbarkeit_score']:.1f}"
              f" TW={e['tragwerk_score']:.1f}){star}")

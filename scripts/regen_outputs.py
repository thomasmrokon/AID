"""Regenerate output files with current code (A_kompakt, sort strategy)."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.agents.evaluation import evaluation_agent
from app.agents.analyse import analyse_agent
from app.agents.report import report_agent
from app.tools.site import get_demo_site
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'A_kompakt',
}
site = get_demo_site('A_kompakt')

state = PlanningState(user_input=BASE)
state['site_geometry'] = site
state['gap_strategy'] = 'sort'

state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))
state.update(evaluation_agent(state))

try:
    state.update(analyse_agent(state))
except Exception as e:
    print(f"[analyse] Skipped: {e}")

state.update(report_agent(state))

evals = state.get('evaluations', [])
print("\nNew evaluation.json:")
for e in evals:
    print(f"  {e['variante']}: {e['gesamtscore']:.1f} empfohlen={e.get('empfohlen',False)}")
print("\nArtifacts:", list(state.get('artifacts', {}).keys()))
print("DONE.")

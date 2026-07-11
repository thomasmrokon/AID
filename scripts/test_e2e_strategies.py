"""End-to-end pipeline test für alle 4 Gap-Strategien."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.agents.evaluation import evaluation_agent
from app.tools.site import get_demo_site
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'A_kompakt',
}
site = get_demo_site('A_kompakt')

for strat in ['none', 'sort', 'corridor', 'all']:
    state = PlanningState(user_input=BASE)
    state['site_geometry'] = site
    state['gap_strategy'] = strat
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))
    state.update(evaluation_agent(state))
    evals = state.get('evaluations', [])
    gesamtscores = [round(e.get('gesamtscore', 0), 2) for e in evals]
    n_variants = len(state['variants'])
    n_evals = len(evals)
    print(f"{strat:9}: {n_variants} Varianten, {n_evals} Evaluierungen, Scores: {gesamtscores}")

print("DONE — kein Fehler.")

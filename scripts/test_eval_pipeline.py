"""Full pipeline test including evaluation agent."""
import sys
sys.path.insert(0, '.')

from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.agents.evaluation import evaluation_agent
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
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

variants = state.get('variants', [])
print(f"Layout: {len(variants)} Varianten erzeugt")
for v in variants:
    zonen = v.get('zonen', [])
    print(f"  {v['name']}: {len(zonen)} Zonen")

state.update(evaluation_agent(state))

evals = state.get('evaluations', [])
print(f"\nEvaluation: {len(evals)} Varianten bewertet")
for e in evals:
    name = e.get('variante', e.get('name', '?'))
    score = e.get('gesamt_score', e.get('total_score', '?'))
    print(f"  {name}: Score={score}")

print("\nPipeline OK")

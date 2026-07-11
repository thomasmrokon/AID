"""
Regenerate output files with current code — fast version (no Rhino).
Patches rhinoinside/rhino_compute to skip licence-init before importing
report_agent, so the script never hangs on Rhino 8 startup.
"""
import sys
sys.path.insert(0, '.')

# 1. Load .env so LLM agents can use their API keys (or fall back cleanly)
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[init] .env geladen")
except ImportError:
    print("[init] python-dotenv fehlt — LLM-Fallback aktiv")

# 2. Pre-patch rhinoinside so ist_verfuegbar() returns False instantly
import app.tools.rhino_inside_runner as _rir
_rir._available = False          # skip rhinoinside.load() entirely
print("[init] rhinoinside deaktiviert (kein Rhino-8-Startup)")

# 3. Now safe to import everything
from app.agents.briefing  import briefing_agent
from app.agents.rules     import rule_agent
from app.agents.topology  import topology_agent
from app.agents.strategy  import layout_strategy_agent
from app.agents.layout    import layout_agent
from app.agents.evaluation import evaluation_agent
from app.agents.analyse   import analyse_agent
from app.agents.report    import report_agent
from app.tools.site       import get_demo_site
from app.state            import PlanningState

BASE = {
    'nutzungstyp':          'Produktion',
    'produktionsflaeche':   3000,
    'lager_rohstoffe':      600,
    'lager_fertigwaren':    600,
    'wareneingang':         250,
    'versand':              250,
    'qualitaetssicherung':  150,
    'buero_nuf2':           300,
    'kranbahn_erforderlich': False,
    'grundstueck_id':       'A_kompakt',
}

site  = get_demo_site('A_kompakt')
state = PlanningState(user_input=BASE)
state['site_geometry'] = site
state['gap_strategy']  = 'sort'

print("\n--- Pipeline ---")
state.update(briefing_agent(state));         print("[1/7] briefing done")
state.update(rule_agent(state));             print("[2/7] rules done")
state.update(topology_agent(state));         print("[3/7] topology done")
state.update(layout_strategy_agent(state));  print("[4/7] strategy done")
state.update(layout_agent(state));           print("[5/7] layout done")
state.update(evaluation_agent(state));       print("[6/7] evaluation done")

try:
    state.update(analyse_agent(state))
    print("[7a] analyse done")
except Exception as e:
    print(f"[7a] analyse skipped: {e}")

state.update(report_agent(state))
print("[7b] report done")

# Summary
evals = state.get('evaluations', [])
print("\n=== Neue evaluation.json ===")
for e in evals:
    star = " ★" if e.get('empfohlen') else ""
    print(f"  {e['variante']:25s}: {e['gesamtscore']:.2f}{star}  "
          f"(MF={e.get('materialfluss_score', 0):.2f}  "
          f"ER={e.get('erweiterbarkeit_score', 0):.2f}  "
          f"FL={e.get('flaecheneffizienz_score', 0):.2f})")

print(f"\nArtifacts: {list(state.get('artifacts', {}).keys())}")
print("DONE.")

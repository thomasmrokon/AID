"""
Testet ob AR-Fix im Kamm-Layout wirkt.
Erzwingt typology_assignment='kamm' fuer alle Varianten auf C_unregelmaessig.
"""
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
AR_LIMIT = 4.01

for site_id in ['A_kompakt', 'C_unregelmaessig']:
    site  = get_demo_site(site_id)
    state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
    state['site_geometry'] = site
    state['gap_strategy']  = 'sort'

    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))

    # Simulate LLM assigning kamm typology (what the live app does)
    state['typology_assignment'] = {
        'A_Materialfluss':   'kamm',
        'B_Erweiterbarkeit': 'kamm',
        'C_Ausgewogen':      'kamm',
    }

    state.update(layout_agent(state))

    total_violations = 0
    print(f"\n{'='*60}")
    print(f"Site: {site_id} (forced kamm)")
    for v in state.get('variants', []):
        violations = []
        max_ar = 0.0
        for zd in v['zonen']:
            if zd.get('schraffur') or zd.get('din_kategorie') in ('VF',):
                continue
            b, t = zd['breite'], zd['tiefe']
            ar = max(b, t) / max(min(b, t), 0.01)
            max_ar = max(max_ar, ar)
            if ar > AR_LIMIT:
                violations.append((zd['name'], b, t, ar))
        total_violations += len(violations)
        status = "OK" if not violations else f"{len(violations)} VIOLATIONS"
        print(f"  {v['name']:25s}: max_AR={max_ar:.2f}  [{status}]")
        for name, b, t, ar in violations:
            print(f"    VIOLATION  {name:30s}  {b:.1f}x{t:.1f}m  AR={ar:.2f}")

print(f"\nTotal violations: {total_violations}")
if total_violations == 0:
    print("PASS: Alle ARs im Kamm-Layout <= 4.01")
else:
    print("FAIL: AR-Verletzungen vorhanden!")
print("DONE.")

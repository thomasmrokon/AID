"""AR violation check: all 3 Grundstücke × all 4 strategies × 3 variants."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.site import get_demo_site
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

AR_LIMIT = 4.01
total_violations = 0
max_ar_seen = 0.0

for site_id in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    for strat in ['none', 'sort', 'corridor', 'all']:
        site = get_demo_site(site_id)
        state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
        state['site_geometry'] = site
        state['gap_strategy'] = strat
        state.update(briefing_agent(state))
        state.update(rule_agent(state))
        state.update(topology_agent(state))
        state.update(layout_strategy_agent(state))
        state.update(layout_agent(state))

        variants = state.get('variants', [])
        for v in variants:
            for zd in v.get('zonen', []):
                if zd.get('schraffur') or zd.get('din_kategorie') == 'VF':
                    continue
                bw = zd['breite']; td = zd['tiefe']
                ar = max(bw, td) / max(min(bw, td), 0.01)
                max_ar_seen = max(max_ar_seen, ar)
                if ar > AR_LIMIT:
                    total_violations += 1
                    print(f"VIOLATION: {site_id}/{strat}/{v['name']}/{zd['name']}  AR={ar:.2f}  ({bw:.1f}x{td:.1f})")

print(f"\nTotal AR violations: {total_violations}")
print(f"Max AR seen (excl. VF): {max_ar_seen:.2f}")
if total_violations == 0:
    print("PASS: All ARs within limit 4.01")
else:
    print("FAIL: AR violations detected!")

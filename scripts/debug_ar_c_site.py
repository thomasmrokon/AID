"""Diagnose C_unregelmaessig zone AR and typology selection."""
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

    sep = '=' * 60
    print(f"\n{sep}")
    print(f"Site: {site_id}")
    envelope = site.get('envelope') or {}
    print(f"  site area_m2     = {site.get('area_m2')}")
    print(f"  site envelope    = {envelope}")
    typology = state.get('typology_assignment') or {}
    print(f"  typology_assignment:")
    for k, v in (typology.items() if isinstance(typology, dict) else {}.items()):
        print(f"    {k}: {v}")

    state.update(layout_agent(state))

    for v in state.get('variants', []):
        violations = []
        ok_ar = []
        for zd in v['zonen']:
            if zd.get('schraffur') or zd.get('din_kategorie') in ('VF',):
                continue
            b, t = zd['breite'], zd['tiefe']
            ar = max(b, t) / max(min(b, t), 0.01)
            entry = (zd['name'], b, t, ar)
            if ar > AR_LIMIT:
                violations.append(entry)
            else:
                ok_ar.append(entry)
        v_label = f"{v['name']} | {v['site_breite']:.0f}x{v['site_tiefe']:.0f}m"
        print(f"\n  [{v_label}] violations={len(violations)}")
        for name, b, t, ar in violations:
            print(f"    VIOLATION  {name:30s}  {b:.1f}x{t:.1f}m  AR={ar:.2f}")
        if not violations:
            max_ar = max((a for _, _, _, a in ok_ar), default=0.0)
            print(f"    OK — max AR = {max_ar:.2f}")

print("\nDONE.")

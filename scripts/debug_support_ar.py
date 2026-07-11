"""Diagnose support zone AR violations on Grundstück C (unregelmaessig)."""
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
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'C_unregelmaessig',
}
site = get_demo_site('C_unregelmaessig')
print(f"Site: {site.get('name','?')} | buildable_area={site.get('buildable_area_m2','?')}m²")
print(f"Envelope: {site.get('building_envelope', {})}")
print()

state = PlanningState(user_input=BASE)
state['site_geometry'] = site
state['gap_strategy'] = 'none'
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

variants = state.get('variants', [])
briefing = state.get('structured_briefing', {})

print(f"Briefing zones (raw FP):")
for name, fp in briefing.get('flaechenbedarf', {}).items():
    print(f"  {name}: {fp}m²")
print()

for v in variants:
    name = v.get('name', '?')
    meta = v.get('layout_meta', {})
    zonen = v.get('zonen', [])

    print(f"=== {name} ===")
    bw_val = meta.get('building_width', '?')
    bd_val = meta.get('building_depth', '?')
    print(f"  Layout meta: bw={bw_val}, bd={bd_val}, "
          f"sup_w={meta.get('sup_w','?')}, sup_w_min={meta.get('sup_w_min','?')}")
    print(f"  Flächenanpassung: {meta.get('flaechenanpassung_applied','?')}, "
          f"scale={meta.get('scale_factor','?')}")
    print()

    # Print all zones with their dimensions and AR
    for z in sorted(zonen, key=lambda z: z['name']):
        if z.get('schraffur'):
            continue
        bw = z['breite']; td = z['tiefe']
        ar = max(bw, td) / max(min(bw, td), 0.01)
        flag = " *** AR VIOLATION ***" if ar > 4.01 else ""
        print(f"  {z['name']:35s}: {bw:6.1f}w × {td:6.1f}d = {bw*td:7.1f}m²  AR={ar:.2f}{flag}")
    print()

"""Debug detail for remaining AR violations after fix."""
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

cases = [
    ('A_kompakt', 'B_Erweiterbarkeit'),
    ('B_langgezogen', 'B_Erweiterbarkeit'),
    ('C_unregelmaessig', 'A_Materialfluss'),
]

for gid, vname in cases:
    site = get_demo_site(gid)
    state = PlanningState(user_input={**BASE_INPUT, 'grundstueck_id': gid})
    state['site_geometry'] = site
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    v = next((v for v in state['variants'] if v['name'] == vname), None)
    if not v:
        continue
    zonen = [Zone(**z) for z in v['zonen']]
    env = v['building_envelope']
    w, d = env['width_m'], env['depth_m']
    print(f"\n{gid} / {vname}  [{w:.0f}x{d:.0f}m AR={w/d:.2f}]")
    for z in sorted(zonen, key=lambda z: z.flaeche_m2, reverse=True):
        if z.schraffur:
            continue
        ar = max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe))
        flag = ' <<AR!' if ar > 4.0 else ''
        print(f"  {z.name:<25} {z.breite:.1f}x{z.tiefe:.1f}m  AR={ar:.2f}  ({z.flaeche_m2:.0f}m2){flag}")

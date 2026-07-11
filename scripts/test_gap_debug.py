"""Debuggt Zone-Koordinaten für Adjacency-Gap-Analyse."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone, shared_wall
from app.tools.site import get_demo_site
from app.state import PlanningState

BASE_INPUT = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'A_kompakt',
}
site = get_demo_site('A_kompakt')
state = PlanningState(user_input=BASE_INPUT)
state['site_geometry'] = site
state['gap_strategy'] = 'none'
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

topo = state['topology_diagram']
print("Process order:", topo.get('process_order'))

for v in state['variants']:
    name = v['name']
    if name != 'C_Ausgewogen':
        continue
    print(f"\n=== {name} ===")
    zonen = [Zone(**z) for z in v['zonen']]
    zone_map = {z.name: z for z in zonen if not z.schraffur}

    print("\nZone Koordinaten:")
    for z in sorted(zonen, key=lambda z: z.x):
        if not z.schraffur:
            print(f"  {z.name:<28} x={z.x:.1f}..{z.x+z.breite:.1f}  y={z.y:.1f}..{z.y+z.tiefe:.1f}  "
                  f"({z.breite:.1f}x{z.tiefe:.1f}m)")

    print("\nWand-Test LagerR <-> Produktion:")
    lr = zone_map.get('Lager Rohstoffe')
    prod = zone_map.get('Produktion')
    if lr and prod:
        wall = shared_wall(lr, prod)
        print(f"  LagerR right edge: {lr.x + lr.breite:.2f}")
        print(f"  Prod left edge:    {prod.x:.2f}")
        print(f"  LagerR y: {lr.y:.2f} .. {lr.y+lr.tiefe:.2f}")
        print(f"  Prod y:   {prod.y:.2f} .. {prod.y+prod.tiefe:.2f}")
        print(f"  shared_wall = {wall:.2f}")

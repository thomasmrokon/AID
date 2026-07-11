"""Diagnose zone positions for B_Erweiterbarkeit on B_langgezogen."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.site import get_demo_site
from app.tools.geometry import Zone, shared_wall
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'B_langgezogen',
}
site = get_demo_site('B_langgezogen')

for strat in ['none', 'sort']:
    state = PlanningState(user_input=BASE)
    state['site_geometry'] = site
    state['gap_strategy'] = strat
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    topo = state.get('topology_diagram', {})
    topo_edges = [(e['source'], e['target'], float(e.get('weight', 0)))
                  for e in topo.get('edges', []) if float(e.get('weight', 0)) >= 0.5]

    variants = state.get('variants', [])
    for v in variants:
        if v['name'] not in ('B_Erweiterbarkeit',):
            continue
        zonen_dicts = v.get('zonen', [])
        zone_objs = {zd['name']: Zone(
            name=zd['name'], x=zd['x'], y=zd['y'],
            breite=zd['breite'], tiefe=zd['tiefe'],
            flaeche_m2=zd.get('flaeche_m2', zd['breite']*zd['tiefe']),
            din_kategorie=zd['din_kategorie'],
            farbe=zd.get('farbe',''), schraffur=zd.get('schraffur', False)
        ) for zd in zonen_dicts if not zd.get('schraffur')}

        print(f"\n=== {v['name']} | gap_strategy={strat} | B_langgezogen ===")
        for name, z in sorted(zone_objs.items()):
            print(f"  {name:30s}: x=[{z.x:.1f},{z.x+z.breite:.1f}]  y=[{z.y:.1f},{z.y+z.tiefe:.1f}]  {z.breite:.1f}x{z.tiefe:.1f}")

        print(f"\nTopology edges (w>=0.5):")
        for src, tgt, w in topo_edges:
            sw_val = 0.0
            if src in zone_objs and tgt in zone_objs:
                sw_val = shared_wall(zone_objs[src], zone_objs[tgt])
            gap = "GAP" if sw_val < 0.5 else f"wall={sw_val:.1f}m"
            print(f"  {src:30s} -> {tgt:30s}  (w={w:.2f})  [{gap}]")

print("\nDONE.")

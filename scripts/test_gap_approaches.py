"""Testet alle drei Lückenbehandlungs-Ansätze."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone, shared_wall
from app.tools.scoring import berechne_adjacency_gaps
from app.tools.site import get_demo_site
from app.state import PlanningState

BASE_INPUT = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'A_kompakt',
}

site = get_demo_site('A_kompakt')

print("=" * 65)
print("  SHARED_WALL SMOKE TEST")
print("=" * 65)
from app.tools.geometry import Zone as Z
a = Z(name="A", x=0, y=0, breite=10, tiefe=5, flaeche_m2=50, din_kategorie="NUF 3", farbe="#AAA", floors=1, planned_area_m2=50)
b = Z(name="B", x=0, y=5, breite=10, tiefe=5, flaeche_m2=50, din_kategorie="NUF 3", farbe="#AAA", floors=1, planned_area_m2=50)
c = Z(name="C", x=20, y=0, breite=10, tiefe=5, flaeche_m2=50, din_kategorie="NUF 3", farbe="#AAA", floors=1, planned_area_m2=50)
print(f"  A-B wall (expect ~10): {shared_wall(a, b):.1f}")
print(f"  A-C wall (expect 0):   {shared_wall(a, c):.1f}")

for strategy in ["none", "sort", "corridor", "all"]:
    print()
    print("=" * 65)
    print(f"  STRATEGIE: {strategy}")
    print("=" * 65)

    state = PlanningState(user_input=BASE_INPUT)
    state['site_geometry'] = site
    state['gap_strategy'] = strategy
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    topo = state['topology_diagram']

    for v in state['variants']:
        name = v['name']
        zonen = [Zone(**z) for z in v['zonen']]
        gaps = berechne_adjacency_gaps(zonen, topo)
        zone_names = [z.name for z in zonen if not z.schraffur]
        corridors  = [z.name for z in zonen if z.din_kategorie == "VF"]

        print(f"  Variante {name}:")
        print(f"    Zonen gesamt: {len(zone_names)}  |  VF-Korridore: {len(corridors)}")
        if corridors:
            for c in corridors:
                print(f"      + {c}")
        if gaps:
            print(f"    Adjacency-Lücken: {len(gaps)}")
            for src, tgt, w in gaps:
                print(f"      GAP  {src} <-> {tgt}  (w={w:.2f})")
        else:
            print("    Alle Prozess-Kanten haben Wandkontakt. ✓")

print()
print("Done.")

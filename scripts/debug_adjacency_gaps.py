"""Prüft welche Topology-Kanten eine echte gemeinsame Wand haben vs. Flur benötigen."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone
from app.tools.site import get_demo_site
from app.state import PlanningState

TOL = 0.5  # Meter Toleranz für "gemeinsame Wand"

def shared_wall(a: Zone, b: Zone) -> float:
    """Gibt die Länge der gemeinsamen Wand zurück (0 = kein Kontakt)."""
    # a oben / b unten
    if abs((a.y + a.tiefe) - b.y) < TOL:
        overlap = min(a.x+a.breite, b.x+b.breite) - max(a.x, b.x)
        if overlap > TOL: return overlap
    # a unten / b oben
    if abs(a.y - (b.y + b.tiefe)) < TOL:
        overlap = min(a.x+a.breite, b.x+b.breite) - max(a.x, b.x)
        if overlap > TOL: return overlap
    # a rechts / b links
    if abs((a.x + a.breite) - b.x) < TOL:
        overlap = min(a.y+a.tiefe, b.y+b.tiefe) - max(a.y, b.y)
        if overlap > TOL: return overlap
    # a links / b rechts
    if abs(a.x - (b.x + b.breite)) < TOL:
        overlap = min(a.y+a.tiefe, b.y+b.tiefe) - max(a.y, b.y)
        if overlap > TOL: return overlap
    return 0.0

site = get_demo_site('A_kompakt')
state = PlanningState(user_input={
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False, 'grundstueck_id': 'A_kompakt',
})
state['site_geometry'] = site
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

topo = state['topology_diagram']

for v in state['variants']:
    zonen = [Zone(**z) for z in v['zonen']]
    zone_map = {z.name: z for z in zonen if not z.schraffur}
    vname = v['name']

    print(f"\n{'='*65}")
    print(f"Variante: {vname}")
    print()

    # Vollständige Adjazenzmatrix
    print("  Wand-Adjazenz:")
    for z in zonen:
        if z.schraffur: continue
        neighbors = [(b.name, shared_wall(z, b)) for b in zonen
                     if not b.schraffur and b.name != z.name and shared_wall(z, b) > 0]
        nb_str = ', '.join(f"{n}({l:.0f}m)" for n, l in neighbors)
        print(f"    {z.name:<28} | {nb_str or '(isoliert)'}")

    print()
    print("  Topology-Kanten vs. Wand:")
    gaps = []
    for e in topo['edges']:
        src, tgt = e['source'], e['target']
        w = e.get('weight', 0)
        kind = e.get('kind', '?')
        if src not in zone_map or tgt not in zone_map:
            continue
        wall = shared_wall(zone_map[src], zone_map[tgt])
        if w < 0:
            status = "Trennung OK (negativ)"
        elif wall > 0:
            status = f"Wand {wall:.0f}m  OK"
        else:
            status = "!!! KEIN KONTAKT -> Flur noetig"
            if w > 0.3:
                gaps.append((src, tgt, w, kind))
        print(f"    [{kind:10}] w={w:+.2f}  {src:<25} -> {tgt:<25}  {status}")

    if gaps:
        print()
        print("  GAPS mit hohem Gewicht (Flur-Kandidaten):")
        for src, tgt, w, kind in sorted(gaps, key=lambda x: -x[2]):
            print(f"    => {src} <-> {tgt}  (w={w:.2f}, {kind})")
    else:
        print()
        print("  Alle Topology-Kanten haben Wandkontakt.")

"""
Vollständiger Pipeline-Check — alle 3 Sites × 3 Varianten.
Prüft: Fuge, Zonen-Vollständigkeit, AR-Verletzungen, Scores, Empfehlung.
"""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing   import briefing_agent
from app.agents.rules      import rule_agent
from app.agents.topology   import topology_agent
from app.agents.strategy   import layout_strategy_agent
from app.agents.layout     import layout_agent
from app.agents.evaluation import evaluation_agent
from app.tools.geometry    import Zone, shared_wall
from app.tools.site        import get_demo_site, compute_building_envelope
from app.state             import PlanningState

AR_LIM = 4.0   # Seitenverh. Limit (>= ist Violation)
TOL    = 0.5   # Wand-Kontakt Toleranz

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

SITE_IDS = ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']

all_ok = True

for site_id in SITE_IDS:
    print(f"\n{'='*65}")
    print(f"  SITE: {site_id}")
    print('='*65)
    site = get_demo_site(site_id)
    env  = compute_building_envelope(site) or {}
    state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
    state['site_geometry'] = site
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))
    state.update(evaluation_agent(state))

    topo     = state['topology_diagram']
    proc_ord = topo.get('process_order', [])
    node_names = {n['name'] for n in topo['nodes']}

    evals    = state['evaluations']
    selected = state['selected_variant']
    eval_map = {e['variante']: e for e in evals}

    print(f"\n  Empfehlung: {selected}  (Score {eval_map[selected]['gesamtscore']:.2f})")
    for e in sorted(evals, key=lambda x: x['gesamtscore'], reverse=True):
        star = ' ★' if e['variante'] == selected else ''
        print(f"    {e['variante']:22}: {e['gesamtscore']:.2f}"
              f"  MF={e['materialfluss_score']:.1f} EB={e['erweiterbarkeit_score']:.1f}"
              f" TW={e['tragwerk_score']:.1f}{star}")

    for v in state['variants']:
        vname = v['name']
        zonen_raw = v['zonen']
        zonen = [Zone(**z) for z in zonen_raw if not z.get('schraffur')]
        zone_map = {z.name: z for z in zonen}

        issues = []

        # 1. Fuge: Gebäude beginnt an Baufeld-SW-Ecke?
        if zonen:
            x_min = min(z.x for z in zonen)
            y_min = min(z.y for z in zonen)
            dx = round(x_min - env.get('x', 0), 2)
            dy = round(y_min - env.get('y', 0), 2)
            if abs(dx) > 0.5 or abs(dy) > 0.5:
                issues.append(f"FUGE: Gebäude-Offset dx={dx:.1f} dy={dy:.1f} (erwartet 0/0)")

        # 2. Zonen-Vollständigkeit
        zone_namen = {z.name for z in zonen}
        fehlend = node_names - zone_namen - {'Erschließung', 'VF', 'Reserve'}
        # Erweiterungsreserve und Erschließung können fehlen (optional)
        fehlend = {n for n in fehlend if 'Reserve' not in n and 'Erschliessung' not in n}
        if fehlend:
            issues.append(f"ZONEN FEHLEN: {fehlend}")

        # 3. AR-Verletzungen (Seitenverhältnis)
        ar_viols = []
        for z in zonen:
            if z.breite > 0 and z.tiefe > 0:
                ar = max(z.breite, z.tiefe) / min(z.breite, z.tiefe)
                if ar >= AR_LIM:
                    ar_viols.append(f"{z.name}={ar:.2f}")
        if ar_viols:
            issues.append(f"AR-VERLETZUNG: {', '.join(ar_viols)}")

        # 4. Score-Konsistenz: gesamtscore == sum(gew*score)?
        g = v['gewichtung']
        e = eval_map.get(vname, {})
        computed = (g.get('materialfluss', 0) * e.get('materialfluss_score', 0)
                  + g.get('erweiterbarkeit', 0) * e.get('erweiterbarkeit_score', 0)
                  + g.get('tragwerk', 0) * e.get('tragwerk_score', 0))
        diff = abs(computed - e.get('gesamtscore', 0))
        if diff > 0.05:
            issues.append(f"SCORE-INKONSISTENZ: berechnet={computed:.2f} gespeichert={e.get('gesamtscore', 0):.2f}")

        # 5. Lücken in der Prozesskette
        gaps = []
        for i in range(len(proc_ord) - 1):
            a_n, b_n = proc_ord[i], proc_ord[i+1]
            if a_n in zone_map and b_n in zone_map:
                sw = shared_wall(zone_map[a_n], zone_map[b_n])
                if sw < TOL:
                    gaps.append(f"{a_n[:12]}→{b_n[:12]}")
        if gaps:
            issues.append(f"PROZESS-LÜCKEN: {', '.join(gaps)}")

        status = "✅ OK" if not issues else "⚠️ ISSUES"
        print(f"\n  [{status}] {vname}")
        if issues:
            all_ok = False
            for iss in issues:
                print(f"      • {iss}")

print(f"\n{'='*65}")
print(f"  GESAMTERGEBNIS: {'✅ ALLE CHECKS BESTANDEN' if all_ok else '⚠️  ISSUES GEFUNDEN'}")
print('='*65)

"""Diagnose scores and recommendation logic for all 3 Grundstücke."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.agents.evaluation import evaluation_agent
from app.tools.site import get_demo_site
from app.tools.scoring import berechne_adjacency_gaps
from app.tools.geometry import Zone
from app.state import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for site_id in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    for strat in ['none', 'sort']:
        site = get_demo_site(site_id)
        state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
        state['site_geometry'] = site
        state['gap_strategy'] = strat
        state.update(briefing_agent(state))
        state.update(rule_agent(state))
        state.update(topology_agent(state))
        state.update(layout_strategy_agent(state))
        state.update(layout_agent(state))
        state.update(evaluation_agent(state))

        evals = state.get('evaluations', [])
        variants = state.get('variants', [])
        topo = state.get('topology_diagram')

        print(f"\n{'='*70}")
        print(f"Grundstück: {site_id}  |  gap_strategy: {strat}")
        print(f"{'='*70}")

        for ev, var in zip(evals, variants):
            vname = ev.get('variante', '?')
            gs = round(ev.get('gesamtscore', 0), 2)
            mf = round(ev.get('materialfluss_score', 0), 2)
            er = round(ev.get('erweiterbarkeit_score', 0), 2)
            fl = round(ev.get('flaecheneffizienz_score', 0), 2)
            ar_v = ev.get('ar_violations', [])

            # Compute gaps
            zonen_dicts = var.get('zonen', [])
            zone_objs = []
            for zd in zonen_dicts:
                if not zd.get('schraffur'):
                    z = Zone(
                        name=zd['name'], x=zd['x'], y=zd['y'],
                        breite=zd['breite'], tiefe=zd['tiefe'],
                        flaeche_m2=zd.get('flaeche_m2', zd['breite']*zd['tiefe']),
                        din_kategorie=zd['din_kategorie'],
                        farbe=zd.get('farbe',''), schraffur=False
                    )
                    zone_objs.append(z)
            gaps = berechne_adjacency_gaps(zone_objs, topo, min_weight=0.5) if topo else []

            print(f"  {vname:20s}: Gesamt={gs:4.1f}  MF={mf:.2f}  ER={er:.2f}  FL={fl:.2f}  "
                  f"AR-Violations={len(ar_v)}  Gaps={len(gaps)}")
            if ar_v:
                for a in ar_v:
                    print(f"    AR: {a}")
            if gaps:
                for src, tgt, w in gaps:
                    print(f"    Gap: {src} <-> {tgt}  (w={w:.2f})")

print("\n\nDONE.")

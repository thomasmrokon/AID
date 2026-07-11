"""
E2E-Demo-Check: Vollständige Pipeline für alle 3 Sites.
Prüft jeden Agent-Schritt, Layout-Korrektheit, Evaluation,
3D-Viewer, PNG-Export und Report-Generierung.
"""
import sys, io, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from pathlib import Path
from app.agents.briefing   import briefing_agent
from app.agents.rules      import rule_agent
from app.agents.topology   import topology_agent
from app.agents.strategy   import layout_strategy_agent
from app.agents.layout     import layout_agent
from app.agents.evaluation import evaluation_agent
from app.agents.report     import report_agent
from app.tools.site        import get_demo_site
from app.state             import PlanningState
from app.tools.geometry    import Zone

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}
SITES = ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']

out_dir = Path('outputs/e2e')
out_dir.mkdir(parents=True, exist_ok=True)

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

issues: list[str] = []

def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        print(f"  {PASS} {label}")
    else:
        msg = f"{label}" + (f": {detail}" if detail else "")
        print(f"  {FAIL} {msg}")
        issues.append(msg)
    return condition

def warn(label: str, detail: str = ""):
    msg = f"{label}" + (f": {detail}" if detail else "")
    print(f"  {WARN} {msg}")

for site_id in SITES:
    print(f"\n{'='*60}")
    print(f"Site: {site_id}")
    print('='*60)

    try:
        site = get_demo_site(site_id)
        state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
        state['site_geometry'] = site

        # --- Schritt 1: Briefing ---
        print("\n[1] Briefing")
        try:
            state.update(briefing_agent(state))
            sb = state.get('structured_briefing') or {}
            check("structured_briefing vorhanden", bool(sb))
            check("nuf_gesamt > 0", float(sb.get('nuf_gesamt', 0)) > 0,
                  f"nuf_gesamt={sb.get('nuf_gesamt')}")
        except Exception as e:
            check("Briefing-Agent", False, str(e))

        # --- Schritt 2: Rules ---
        print("\n[2] Rules")
        try:
            state.update(rule_agent(state))
            rules = state.get('rules') or {}
            check("rules vorhanden", bool(rules))
            check("rules_hard vorhanden", bool(state.get('rules_hard')))
            check("interpreted_rules vorhanden", bool(state.get('interpreted_rules')))
        except Exception as e:
            check("Rule-Agent", False, str(e))

        # --- Schritt 3: Topology ---
        print("\n[3] Topology")
        try:
            state.update(topology_agent(state))
            topo = state.get('topology_diagram') or {}
            nodes = topo.get('nodes', [])
            edges = topo.get('edges', [])
            check("topology_diagram vorhanden", bool(topo))
            check(f"Knoten vorhanden ({len(nodes)})", len(nodes) >= 5)
            check(f"Kanten vorhanden ({len(edges)})", len(edges) >= 3)
        except Exception as e:
            check("Topology-Agent", False, str(e))

        # --- Schritt 4: Strategy ---
        print("\n[4] Strategy")
        try:
            state.update(layout_strategy_agent(state))
            assign = state.get('typology_assignments') or {}
            check("typology_assignments gesetzt (3 Varianten)",
                  len(assign) == 3, f"Wert: {assign}")
        except Exception as e:
            check("Strategy-Agent", False, str(e))

        # --- Schritt 5: Layout ---
        print("\n[5] Layout")
        try:
            state.update(layout_agent(state))
            variants = state.get('variants') or []
            check(f"3 Varianten generiert", len(variants) == 3,
                  f"nur {len(variants)}")

            for v in variants:
                vname = v['name']
                zonen = v.get('zonen', [])
                non_hatch = [z for z in zonen if not z.get('schraffur')]
                func_zonen = [z for z in non_hatch if z.get('din_kategorie') != 'VF']
                vf_zonen   = [z for z in non_hatch if z.get('din_kategorie') == 'VF']

                # Vollständigkeit
                briefing_keys = ['Produktion', 'Lager Rohstoffe', 'Lager Fertigwaren',
                                  'Wareneingang', 'Versand', 'Büro', 'Qualitätssicherung']
                zone_names = [z['name'] for z in func_zonen]
                missing = [k for k in briefing_keys
                           if not any(k.lower() in n.lower() for n in zone_names)]
                check(f"  {vname}: alle Briefing-Zonen ({len(func_zonen)} Func + {len(vf_zonen)} VF)",
                      len(missing) == 0,
                      f"fehlend: {missing}")

                # Überlappungen
                vf_list = [z for z in non_hatch if z.get('din_kategorie') == 'VF'
                           and z.get('farbe') == '#7EC8E3']
                for f in vf_list:
                    fx1, fy1 = f['x'], f['y']
                    fx2, fy2 = fx1 + f['breite'], fy1 + f['tiefe']
                    for z in func_zonen:
                        zx1, zy1 = z['x'], z['y']
                        zx2, zy2 = zx1 + z['breite'], zy1 + z['tiefe']
                        ox1, ox2 = max(fx1, zx1), min(fx2, zx2)
                        oy1, oy2 = max(fy1, zy1), min(fy2, zy2)
                        if ox2 - ox1 > 0.5 and oy2 - oy1 > 0.5:
                            ov_area = (ox2-ox1)*(oy2-oy1)
                            check(f"  {vname}: kein Flur-Überlapp mit '{z['name']}'",
                                  False, f"{ov_area:.0f} m²")

                # Fuge (Gap zwischen Gebäude und Baufeld)
                raw_env = v.get('site_geometry') or {}
                be = v.get('building_envelope') or {}
                # check Freifläche vorhanden wenn scaled != raw
                frei = [z for z in zonen if z.get('schraffur') and z.get('din_kategorie') == 'AF']
                if frei:
                    total_frei = sum(z['breite']*z['tiefe'] for z in frei)
                    warn(f"  {vname}: Freiflächen-Zonen {len(frei)}× total {total_frei:.0f} m²")

        except Exception as e:
            check("Layout-Agent", False, str(e))
            traceback.print_exc()

        # --- Schritt 6: Evaluation ---
        print("\n[6] Evaluation")
        try:
            state.update(evaluation_agent(state))
            evals = state.get('evaluations') or []
            check(f"3 Evaluations", len(evals) == 3, f"nur {len(evals)}")
            rec = state.get('selected_variant')
            check("Empfehlung (selected_variant) gesetzt", bool(rec), f"Wert: {rec}")

            scores_ok = True
            for ev in evals:
                s = ev.get('gesamt_score', 0)
                if not (0 <= s <= 10):
                    check(f"Score {ev['variante']} im Bereich 0-10", False,
                          f"score={s}")
                    scores_ok = False
            if scores_ok:
                print(f"  {PASS} Alle Scores im Bereich 0-10")

            # AR-Violations
            for ev in evals:
                ar_viols = [r for r in (ev.get('regelverletzungen') or [])
                            if 'Seitenverhältnis' in r]
                if ar_viols:
                    warn(f"  {ev['variante']}: {len(ar_viols)} AR-Verletzung(en)")

        except Exception as e:
            check("Evaluation-Agent", False, str(e))

        # --- Schritt 7: PNG-Export ---
        print("\n[7] PNG-Export")
        try:
            from app.tools.drawing import zeichne_layout
            variants = state.get('variants') or []
            evals    = state.get('evaluations') or []
            eval_map = {e['variante']: e for e in evals}

            for v in variants:
                vname = v['name']
                ev = eval_map.get(vname, {})
                zonen = [Zone(**z) for z in v['zonen']]
                out_path = out_dir / f"{site_id}_{vname}.png"
                try:
                    zeichne_layout(
                        variante_name=vname,
                        beschreibung=v.get('beschreibung', ''),
                        zonen=zonen,
                        site_breite=v['site_breite'],
                        site_tiefe=v['site_tiefe'],
                        raster_x=v.get('raster_x', 18.0),
                        raster_y=v.get('raster_y', 12.0),
                        scores=ev,
                        gewichtung=v.get('gewichtung', {}),
                        output_path=out_path,
                        nutzungstyp='Produktion',
                        site_geometry=v.get('site_geometry'),
                        building_envelope=v.get('building_envelope'),
                        show_legend=False,
                        show_violations=False,
                    )
                    check(f"  PNG {vname}", out_path.exists(),
                          f"Datei fehlt: {out_path}")
                except Exception as e:
                    check(f"  PNG {vname}", False, str(e))
        except Exception as e:
            check("PNG-Export (Import)", False, str(e))

        # --- Schritt 8: 3D-Viewer ---
        print("\n[8] 3D-Viewer")
        try:
            from app.tools.viewer3d import build_3d_figure
            variants = state.get('variants') or []
            for v in variants[:1]:  # nur erste Variante testen
                vname = v['name']
                zonen_3d = [Zone(**z) for z in v['zonen']]
                try:
                    fig = build_3d_figure(
                        zonen=zonen_3d,
                        site_geometry=v.get('site_geometry') or state.get('site_geometry'),
                        raster_x=v.get('raster_x', 18.0),
                        raster_y=v.get('raster_y', 12.0),
                        variante_name=vname,
                    )
                    check(f"  3D-Figure {vname}", fig is not None)
                    n_traces = len(fig.data)
                    check(f"  Traces vorhanden ({n_traces})", n_traces > 0)
                except Exception as e:
                    check(f"  3D-Viewer {vname}", False, str(e))
        except Exception as e:
            check("3D-Viewer (Import)", False, str(e))

        # --- Schritt 9: Report ---
        print("\n[9] Report")
        try:
            state.update(report_agent(state))
            report = state.get('report_markdown', '')
            check("Report generiert", len(report) > 200,
                  f"nur {len(report)} Zeichen")
        except Exception as e:
            check("Report-Agent", False, str(e))

    except Exception as e:
        check(f"SITE {site_id} (kritischer Fehler)", False, str(e))
        traceback.print_exc()

# --- Zusammenfassung ---
print(f"\n{'='*60}")
print("ZUSAMMENFASSUNG")
print('='*60)
if not issues:
    print(f"{PASS} Alle Checks bestanden — Demo-ready!")
else:
    print(f"{FAIL} {len(issues)} Problem(e) gefunden:\n")
    for i, iss in enumerate(issues, 1):
        print(f"  {i:2}. {iss}")

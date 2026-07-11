"""Zeigt alle Lücken/Gaps zwischen Zonen und zwischen Gebäude und Baufeld."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing   import briefing_agent
from app.agents.rules      import rule_agent
from app.agents.topology   import topology_agent
from app.agents.strategy   import layout_strategy_agent
from app.agents.layout     import layout_agent
from app.tools.site        import get_demo_site
from app.state             import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for site_id in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site = get_demo_site(site_id)
    state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
    state['site_geometry'] = site
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    print(f"\n{'='*60}")
    print(f"Site: {site_id}")
    be = site.get('building_envelope') or {}
    env_x  = be.get('x', 0); env_y  = be.get('y', 0)
    env_w  = be.get('width_m', 0); env_h  = be.get('depth_m', 0)
    print(f"  Baufeld (raw):     x={env_x:.1f} y={env_y:.1f}  {env_w:.1f}x{env_h:.1f}m")
    print(f"  Baufeld-Rand:      x={env_x:.1f}..{env_x+env_w:.1f}  y={env_y:.1f}..{env_y+env_h:.1f}")

    for v in state['variants']:
        vname = v['name']
        zonen = v['zonen']
        non_hatch = [z for z in zonen if not z.get('schraffur')]
        all_vis   = [z for z in zonen]  # incl. schraffur

        if not non_hatch:
            continue

        # Bounding Box aller sichtbaren Zonen (inkl. Freifläche)
        all_x0 = min(z['x'] for z in all_vis)
        all_x1 = max(z['x'] + z['breite'] for z in all_vis)
        all_y0 = min(z['y'] for z in all_vis)
        all_y1 = max(z['y'] + z['tiefe'] for z in all_vis)

        # Bounding Box nur Gebäude (nicht schraffur)
        bld_x0 = min(z['x'] for z in non_hatch)
        bld_x1 = max(z['x'] + z['breite'] for z in non_hatch)
        bld_y0 = min(z['y'] for z in non_hatch)
        bld_y1 = max(z['y'] + z['tiefe'] for z in non_hatch)

        frei = [z for z in zonen if z.get('schraffur') and z.get('din_kategorie') == 'AF']
        schr = [z for z in zonen if z.get('schraffur') and z.get('din_kategorie') != 'AF']

        print(f"\n  Variante: {vname}")
        print(f"    Gebäude-BBox:   x={bld_x0:.1f}..{bld_x1:.1f}  y={bld_y0:.1f}..{bld_y1:.1f}"
              f"  ({bld_x1-bld_x0:.1f}x{bld_y1-bld_y0:.1f}m)")
        print(f"    Alle-Zonen-BBox: x={all_x0:.1f}..{all_x1:.1f}  y={all_y0:.1f}..{all_y1:.1f}"
              f"  ({all_x1-all_x0:.1f}x{all_y1-all_y0:.1f}m)")
        print(f"    site_breite={v['site_breite']}  site_tiefe={v['site_tiefe']}")
        print(f"    Freiflächen: {len(frei)}×  Reserve/Schraffur: {len(schr)}×")
        for f in frei:
            print(f"      AF '{f['name']}': x={f['x']:.1f}..{f['x']+f['breite']:.1f}"
                  f"  y={f['y']:.1f}..{f['y']+f['tiefe']:.1f}")

        # Lücke zwischen Gebäude-BBox und Baufeld-Rand
        gap_right = round((env_x + env_w) - bld_x1, 2)
        gap_top   = round((env_y + env_h) - bld_y1, 2)
        gap_left  = round(bld_x0 - env_x, 2)
        gap_bot   = round(bld_y0 - env_y, 2)
        print(f"    Lücken Gebäude->Baufeld:")
        print(f"      Rechts: {gap_right:.1f}m  Oben: {gap_top:.1f}m"
              f"  Links: {gap_left:.1f}m  Unten: {gap_bot:.1f}m")

        # Lücke zwischen Alle-Zonen-BBox und Baufeld-Rand
        fgap_right = round((env_x + env_w) - all_x1, 2)
        fgap_top   = round((env_y + env_h) - all_y1, 2)
        print(f"    Lücken AllZonen->Baufeld (nach Freifläche):")
        print(f"      Rechts: {fgap_right:.1f}m  Oben: {fgap_top:.1f}m")
        if abs(fgap_right) > 0.5 or abs(fgap_top) > 0.5:
            print(f"    *** LUECKE VERBLEIBT ***")
        else:
            print(f"    -> Baufeld vollständig abgedeckt")

        # Interne Lücken zwischen Zonen (Y-Richtung — typisches Problem)
        print(f"    Zonengrenzen (Y-sortiert, nur Gebäude):")
        sorted_z = sorted(non_hatch, key=lambda z: (round(z['y'],1), round(z['x'],1)))
        y_positions = set()
        for z in non_hatch:
            y_positions.add(round(z['y'], 2))
            y_positions.add(round(z['y'] + z['tiefe'], 2))
        y_sorted = sorted(y_positions)
        for i in range(len(y_sorted)-1):
            gap = round(y_sorted[i+1] - y_sorted[i], 2)
            # Welche Zonen enden/starten hier?
            enders   = [z['name'][:12] for z in non_hatch if abs(z['y']+z['tiefe'] - y_sorted[i]) < 0.1]
            starters = [z['name'][:12] for z in non_hatch if abs(z['y'] - y_sorted[i+1]) < 0.1]
            if gap > 0.5:
                print(f"      y={y_sorted[i]:.1f}..{y_sorted[i+1]:.1f}  GAP={gap:.1f}m"
                      f"  nach: {enders}  vor: {starters}")

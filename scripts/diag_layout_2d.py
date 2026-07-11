"""2D-Diagnose: AR, Grundstuecksueberschreitung, Luecken."""
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing  import briefing_agent
from app.agents.rules     import rule_agent
from app.agents.topology  import topology_agent
from app.agents.strategy  import layout_strategy_agent
from app.agents.layout    import layout_agent
from app.tools.site       import get_demo_site, compute_building_envelope
from app.state            import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for sid in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site     = get_demo_site(sid)
    envelope = compute_building_envelope(site)

    state = PlanningState(user_input={**BASE, 'grundstueck_id': sid})
    state['site_geometry'] = site
    state['gap_strategy']  = 'sort'
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    env_x1 = envelope['x'];  env_y1 = envelope['y']
    env_x2 = env_x1 + envelope['width_m']
    env_y2 = env_y1 + envelope['depth_m']

    print(f"\n{'='*70}")
    print(f"Site: {sid}")
    print(f"  Envelope: [{env_x1:.1f},{env_y1:.1f}] -> [{env_x2:.1f},{env_y2:.1f}]  "
          f"{envelope['width_m']:.0f}x{envelope['depth_m']:.0f}m")
    print(f"  Site:     [0,0] -> [{site['width_m']:.0f},{site['depth_m']:.0f}]")

    for v in state.get('variants', []):
        all_zones = v['zonen']
        real      = [z for z in all_zones if not z.get('schraffur')]

        ar_viol, boundary_viol = [], []

        for zd in sorted(all_zones, key=lambda z: (z['y'], z['x'])):
            x1, y1 = zd['x'], zd['y']
            x2, y2 = x1 + zd['breite'], y1 + zd['tiefe']
            b, t   = zd['breite'], zd['tiefe']
            ar     = max(b, t) / max(min(b, t), 0.01)
            flag   = []
            if ar > 4.01 and not zd.get('schraffur'):
                flag.append(f"AR={ar:.2f}!")
            if x1 < env_x1 - 0.3: flag.append(f"W+{env_x1-x1:.1f}")
            if x2 > env_x2 + 0.3: flag.append(f"E+{x2-env_x2:.1f}")
            if y1 < env_y1 - 0.3: flag.append(f"S+{env_y1-y1:.1f}")
            if y2 > env_y2 + 0.3: flag.append(f"N+{y2-env_y2:.1f}")
            if flag:
                (ar_viol if any('AR' in f for f in flag) else boundary_viol).append(
                    f"    {zd['name']:<26} [{x1:.1f},{y1:.1f}]->[{x2:.1f},{y2:.1f}]  {b:.1f}x{t:.1f}m  {' '.join(flag)}"
                )

        # 2D-Luecken im Gebaeude-Bounding-Box
        gap_pts = []
        if real:
            bx1 = min(z['x'] for z in real); by1 = min(z['y'] for z in real)
            bx2 = max(z['x']+z['breite'] for z in real)
            by2 = max(z['y']+z['tiefe']  for z in real)
            step = 3.0
            # +1 extra step to catch boundary; stay strictly within bounding box (clamp to bx2/by2)
            xs = [min(bx1 + step*i, bx2 - 0.01) for i in range(int((bx2-bx1)/step)+1)]
            ys = [min(by1 + step*j, by2 - 0.01) for j in range(int((by2-by1)/step)+1)]
            # Add explicit interior midpoints to catch narrow gaps
            xs = sorted(set([bx1, (bx1+bx2)/2] + xs))
            ys = sorted(set([by1, (by1+by2)/2] + ys))
            for tx in xs:
                for ty in ys:
                    # Only check points strictly inside bounding box
                    if tx >= bx2 or ty >= by2:
                        continue
                    covered = any(
                        z['x'] <= tx < z['x']+z['breite'] and
                        z['y'] <= ty < z['y']+z['tiefe']
                        for z in all_zones
                    )
                    if not covered and len(gap_pts) < 6:
                        gap_pts.append(f"({tx:.0f},{ty:.0f})")

        total_problems = len(ar_viol) + len(boundary_viol) + len(gap_pts)
        status = "OK" if not total_problems else f"FAIL: {total_problems} Probleme"
        print(f"\n  {v['name']}  [{status}]")

        for msg in ar_viol:       print(f"    AR-VERLETZUNG: {msg}")
        for msg in boundary_viol: print(f"    BOUNDARY:      {msg}")
        if gap_pts:
            print(f"    LUECKE:   unkovered points: {gap_pts}")

        if not total_problems:
            # Kompakte Uebersicht
            for zd in sorted(all_zones, key=lambda z: (z['y'], z['x'])):
                x1,y1 = zd['x'],zd['y']
                x2,y2 = x1+zd['breite'],y1+zd['tiefe']
                b,t   = zd['breite'],zd['tiefe']
                ar    = max(b,t)/max(min(b,t),0.01)
                schr  = "R " if zd.get('schraffur') else "  "
                vf    = "VF" if zd.get('din_kategorie')=='VF' else "  "
                print(f"    {schr}{vf} {zd['name']:<26} x={x1:5.1f}..{x2:5.1f}  y={y1:5.1f}..{y2:5.1f}  {b:.0f}x{t:.0f}m  AR={ar:.1f}")

print("\nDONE.")

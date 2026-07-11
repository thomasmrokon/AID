"""Prüft ob Freifläche-Zonen erzeugt werden und das Baufeld vollständig füllen."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing   import briefing_agent
from app.agents.rules      import rule_agent
from app.agents.topology   import topology_agent
from app.agents.strategy   import layout_strategy_agent
from app.agents.layout     import layout_agent
from app.tools.site        import get_demo_site, compute_building_envelope
from app.state             import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

for sid in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    print(f"\n{'='*65}")
    print(f"Site: {sid}")
    site = get_demo_site(sid)
    raw_env = compute_building_envelope(site) or {}
    state = PlanningState(user_input={**BASE, 'grundstueck_id': sid})
    state['site_geometry'] = site
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    result = layout_agent(state)
    state.update(result)

    for v in state['variants']:
        vname = v['name']
        alle_zonen = v['zonen']
        freif = [z for z in alle_zonen if z.get('name', '').startswith('Freif')]
        normzonen = [z for z in alle_zonen if not z.get('schraffur')]

        # Bounding-Box aller Zonen (inkl. Freifläche)
        alle_bz = alle_zonen
        if alle_bz:
            x_min = min(z['x'] for z in alle_bz)
            y_min = min(z['y'] for z in alle_bz)
            x_max = max(z['x'] + z['breite'] for z in alle_bz)
            y_max = max(z['y'] + z['tiefe'] for z in alle_bz)
        else:
            x_min = y_min = x_max = y_max = 0

        raw_x2 = raw_env['x'] + raw_env['width_m']
        raw_y2 = raw_env['y'] + raw_env['depth_m']
        gap_r = round(raw_x2 - x_max, 2)
        gap_t = round(raw_y2 - y_max, 2)
        ok = abs(gap_r) < 0.5 and abs(gap_t) < 0.5
        sym = "✅" if ok else "⚠️"

        print(f"\n  {sym} {vname}: {len(normzonen)} Normalzonen + {len(freif)} Freifläche")
        for f in freif:
            print(f"      Freifläche: x={f['x']:.1f} y={f['y']:.1f} "
                  f"b={f['breite']:.1f} t={f['tiefe']:.1f} "
                  f"({f['breite']*f['tiefe']:.0f} m²)")
        print(f"      Gesamt-BBox: ({x_min:.1f},{y_min:.1f}) → ({x_max:.1f},{y_max:.1f})")
        print(f"      Raw-Env:     ({raw_env['x']:.1f},{raw_env['y']:.1f}) → ({raw_x2:.1f},{raw_y2:.1f})")
        print(f"      Fuge rechts: {gap_r:.1f}m   Fuge oben: {gap_t:.1f}m")

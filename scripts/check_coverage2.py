"""Prüft Coverage aller 3 Varianten auf allen 3 Sites."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing   import briefing_agent
from app.agents.rules      import rule_agent
from app.agents.topology   import topology_agent
from app.agents.strategy   import layout_strategy_agent
from app.agents.layout     import layout_agent, _skaliere_envelope_auf_briefing
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

    nodes = state['topology_diagram']['nodes']
    env = _skaliere_envelope_auf_briefing(raw_env, nodes, 18.0, 12.0)

    print(f"  Raw env:    ({raw_env['x']:.1f},{raw_env['y']:.1f}) → "
          f"({raw_env['x']+raw_env['width_m']:.1f},{raw_env['y']+raw_env['depth_m']:.1f})  "
          f"{raw_env['width_m']:.1f}×{raw_env['depth_m']:.1f} = {raw_env['width_m']*raw_env['depth_m']:.0f} m²")
    print(f"  Scaled env: ({env['x']:.1f},{env['y']:.1f}) → "
          f"({env['x']+env['width_m']:.1f},{env['y']+env['depth_m']:.1f})  "
          f"{env['width_m']:.1f}×{env['depth_m']:.1f} = {env['width_m']*env['depth_m']:.0f} m²")

    for v in state['variants']:
        vname = v['name']
        zonen_raw = [z for z in v['zonen'] if not z.get('schraffur')]
        if not zonen_raw:
            continue
        x_min = min(z['x'] for z in zonen_raw)
        y_min = min(z['y'] for z in zonen_raw)
        x_max = max(z['x'] + z['breite'] for z in zonen_raw)
        y_max = max(z['y'] + z['tiefe'] for z in zonen_raw)
        zone_area = sum(z['breite'] * z['tiefe'] for z in zonen_raw)

        raw_x2 = raw_env['x'] + raw_env['width_m']
        raw_y2 = raw_env['y'] + raw_env['depth_m']
        gap_r = round(raw_x2 - x_max, 2)
        gap_t = round(raw_y2 - y_max, 2)

        ok = abs(gap_r) < 0.5 and abs(gap_t) < 0.5
        sym = "✅" if ok else "⚠️"
        print(f"\n  {sym} {vname}")
        print(f"      Zonen-BBox:  ({x_min:.1f},{y_min:.1f}) → ({x_max:.1f},{y_max:.1f})")
        print(f"      Raw-Env:     ({raw_env['x']:.1f},{raw_env['y']:.1f}) → ({raw_x2:.1f},{raw_y2:.1f})")
        print(f"      Fuge rechts: {gap_r:.1f}m   Fuge oben: {gap_t:.1f}m")
        print(f"      Zone-Fläche: {zone_area:.0f} m²  / Raw-Env: {raw_env['width_m']*raw_env['depth_m']:.0f} m²  "
              f"({zone_area/(raw_env['width_m']*raw_env['depth_m'])*100:.1f}%)")

"""Prüft ob der Envelope vollständig mit Zonen bedeckt ist (keine innere Fuge)."""
import sys, io, math
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

site = get_demo_site('A_kompakt')
state = PlanningState(user_input={**BASE, 'grundstueck_id': 'A_kompakt'})
state['site_geometry'] = site
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
result = layout_agent(state)
state.update(result)

raw_env = compute_building_envelope(site) or {}
nodes   = state['topology_diagram']['nodes']
env = _skaliere_envelope_auf_briefing(raw_env, nodes, 18.0, 12.0)

print(f"Skaliertes Envelope: x={env['x']:.2f} y={env['y']:.2f}  "
      f"w={env['width_m']:.2f} d={env['depth_m']:.2f}  "
      f"Fläche={env['width_m']*env['depth_m']:.0f} m²")

total_node_fp = sum(float(n.get('footprint_m2') or n.get('area_m2') or 0) for n in nodes)
print(f"Summe Knoten-Footprints: {total_node_fp:.0f} m²")
print()

for v in state['variants'][:2]:   # nur A und C prüfen
    vname = v['name']
    zonen_raw = [z for z in v['zonen'] if not z.get('schraffur')]

    # Bounding-Box der Zonen
    x_min = min(z['x'] for z in zonen_raw)
    y_min = min(z['y'] for z in zonen_raw)
    x_max = max(z['x'] + z['breite'] for z in zonen_raw)
    y_max = max(z['y'] + z['tiefe'] for z in zonen_raw)

    env_x2 = env['x'] + env['width_m']
    env_y2 = env['y'] + env['depth_m']

    zone_area = sum(z['breite'] * z['tiefe'] for z in zonen_raw)
    env_area  = env['width_m'] * env['depth_m']

    print(f"{'─'*60}")
    print(f"Variante: {vname}")
    print(f"  Envelope:      ({env['x']:.1f},{env['y']:.1f}) → ({env_x2:.1f},{env_y2:.1f})"
          f"  {env['width_m']:.1f}×{env['depth_m']:.1f} = {env_area:.0f} m²")
    print(f"  Zonen-BBox:    ({x_min:.1f},{y_min:.1f}) → ({x_max:.1f},{y_max:.1f})"
          f"  {x_max-x_min:.1f}×{y_max-y_min:.1f}")
    print(f"  Zonen-Fläche:  {zone_area:.0f} m²  ({zone_area/env_area*100:.1f}% des Envelope)")
    print(f"  Lücke rechts:  {env_x2 - x_max:.1f} m")
    print(f"  Lücke oben:    {env_y2 - y_max:.1f} m")
    print()
    print(f"  Zonenliste (sortiert):")
    for z in sorted(zonen_raw, key=lambda z: (round(z['y']), round(z['x']))):
        print(f"    {z['name']:30} x={z['x']:6.1f}→{z['x']+z['breite']:6.1f}  "
              f"y={z['y']:6.1f}→{z['y']+z['tiefe']:6.1f}  "
              f"({z['breite']:.1f}×{z['tiefe']:.1f})")

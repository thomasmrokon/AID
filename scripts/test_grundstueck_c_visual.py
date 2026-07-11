"""Grundstück C: Polygon-Geometrie, Envelope-Winkel und Layout-Rendering prüfen."""
import sys; sys.path.insert(0, '.')
from pathlib import Path
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone
from app.tools.site import get_demo_site, compute_building_envelope
from app.tools.drawing import zeichne_layout
from app.state import PlanningState

site = get_demo_site('C_unregelmaessig')

print("=== Grundstück C — Polygon ===")
print(f"  shape_type : {site['shape_type']}")
print(f"  area_m2    : {site['area_m2']} m²")
print(f"  width_m    : {site['width_m']} m")
print(f"  depth_m    : {site['depth_m']} m")
print(f"  polygon ({len(site['polygon'])} Punkte):")
for p in site['polygon']:
    print(f"    {p}")
print(f"  access_points:")
for ap in site['access_points']:
    print(f"    {ap}")

env = compute_building_envelope(site)
print()
print("=== Building Envelope ===")
print(f"  site_angle_deg : {env.get('site_angle_deg', 0):.2f}°")
print(f"  x={env['x']:.1f}, y={env['y']:.1f}, width={env['width_m']:.1f}m, depth={env['depth_m']:.1f}m")
print(f"  centroid: ({env.get('site_centroid_x', 0):.1f}, {env.get('site_centroid_y', 0):.1f})")
print(f"  area: {env['area_m2']:.0f} m²  AR={env['width_m']/env['depth_m']:.2f}")

# Layout berechnen
BASE_INPUT = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
    'grundstueck_id': 'C_unregelmaessig',
}
state = PlanningState(user_input=BASE_INPUT)
state['site_geometry'] = site
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

variants = state['variants']
print()
print("=== Layout-Zonen (erste Variante: Ecken in Globalkoordinaten?) ===")
v = variants[0]
zonen = [Zone(**z) for z in v['zonen']]
ev = v['building_envelope']
print(f"  Variante: {v['name']}")
print(f"  Envelope: {ev['width_m']:.0f}x{ev['depth_m']:.0f}m, angle={ev.get('site_angle_deg',0):.2f}°")
print(f"  Zonen x/y Bereiche:")
for z in zonen:
    if not z.schraffur:
        print(f"    {z.name:<25} x={z.x:.1f}..{z.x+z.breite:.1f}  y={z.y:.1f}..{z.y+z.tiefe:.1f}")

# Bilder rendern
out_dir = Path("scripts")
for v in variants:
    zonen = [Zone(**z) for z in v['zonen']]
    env = v['building_envelope']
    fname = out_dir / f"ss_C_{v['name']}.png"
    try:
        zeichne_layout(
            variante_name=v['name'],
            beschreibung=v.get('beschreibung', ''),
            zonen=zonen,
            site_breite=float(site['width_m']),
            site_tiefe=float(site['depth_m']),
            building_envelope=env,
            raster_x=v.get('raster_x', 9.0),
            raster_y=v.get('raster_y', 9.0),
            scores={},
            gewichtung={},
            output_path=fname,
            nutzungstyp='Produktion',
            site_geometry=site,
        )
        print(f"  Gespeichert: {fname}")
    except Exception as e:
        import traceback
        print(f"  Fehler bei {v['name']}: {e}")
        traceback.print_exc()

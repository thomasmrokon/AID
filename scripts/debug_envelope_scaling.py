"""Debug envelope scaling behavior."""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False
from app.tools.site import get_demo_site, compute_building_envelope
from app.agents.layout import _skaliere_envelope_auf_briefing

# Simulate what happens
for sid in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site = get_demo_site(sid)
    envelope = compute_building_envelope(site)
    raster_x, raster_y = 18.0, 12.0

    # Simulate nodes from topology (approximate from BASE)
    nodes = [
        {'name': 'Wareneingang',       'footprint_m2': 250, 'area_m2': 250,  'floors': 1},
        {'name': 'Lager Rohstoffe',    'footprint_m2': 600, 'area_m2': 600,  'floors': 1},
        {'name': 'Produktion',         'footprint_m2': 3000,'area_m2': 3000, 'floors': 1},
        {'name': 'Qualitaetssicherung','footprint_m2': 150, 'area_m2': 150,  'floors': 1},
        {'name': 'Lager Fertigwaren',  'footprint_m2': 600, 'area_m2': 600,  'floors': 1},
        {'name': 'Versand',            'footprint_m2': 250, 'area_m2': 250,  'floors': 1},
        {'name': 'Buero',              'footprint_m2': 150, 'area_m2': 300,  'floors': 2},
        {'name': 'Technik',            'footprint_m2': 309, 'area_m2': 309,  'floors': 1},
        {'name': 'Sozial',             'footprint_m2': 77,  'area_m2': 154,  'floors': 2},
    ]
    total_fp = sum(n['footprint_m2'] for n in nodes)

    env_area = envelope['width_m'] * envelope['depth_m']
    new_env = _skaliere_envelope_auf_briefing(envelope, nodes, raster_x, raster_y)
    new_area = new_env['width_m'] * new_env['depth_m']

    print(f"\n=== {sid} ===")
    print(f"  total_fp = {total_fp} m2")
    print(f"  Envelope before: {envelope['width_m']:.1f}x{envelope['depth_m']:.1f} = {env_area:.0f} m2")
    print(f"  Envelope after:  {new_env['width_m']:.1f}x{new_env['depth_m']:.1f} = {new_area:.0f} m2")
    print(f"  Envelope x: {envelope['x']:.1f} -> {new_env['x']:.1f}   y: {envelope['y']:.1f} -> {new_env['y']:.1f}")
    print(f"  Ratio after/total_fp: {new_area/total_fp:.2f}x")

    # Now simulate _squarified_layout_main internal scaling:
    bx = new_env['x']
    by = new_env['y']
    bw = new_env['width_m']
    bd = new_env['depth_m']
    env_area2 = bw * bd
    orig_bw, orig_bd = envelope['width_m'], envelope['depth_m']

    if env_area2 > total_fp * 1.02:
        scale = math.sqrt(total_fp / env_area2)
        bw2, bd2 = bw * scale, bd * scale
        print(f"  Squarified also scales: {bw:.1f}x{bd:.1f} -> {bw2:.1f}x{bd2:.1f}")
    else:
        bw2, bd2 = bw, bd
        print(f"  Squarified: no further scaling needed")

    # AR correction check
    if bw2 / bd2 < 1.5:
        ideal_bw = math.sqrt(total_fp * 1.6)
        actual_bw = min(ideal_bw, orig_bw)
        actual_bd = total_fp / max(1.0, actual_bw)
        if actual_bd <= orig_bd and (actual_bw / actual_bd) > (bw2 / bd2 + 0.05):
            print(f"  AR correction: {bw2:.1f}x{bd2:.1f} -> {actual_bw:.1f}x{actual_bd:.1f} (ratio {actual_bw/actual_bd:.2f})")
            bw2, bd2 = actual_bw, actual_bd
        else:
            print(f"  AR correction: NOT applied (actual_bd={actual_bd:.1f} > orig_bd={orig_bd:.1f} or AR ok)")

    print(f"  Final building: {bx:.1f} + {bw2:.1f} = {bx+bw2:.1f}  {by:.1f} + {bd2:.1f} = {by+bd2:.1f}")
    print(f"  Gap at top: {new_env['y'] + new_env['depth_m'] - (by + bd2):.1f} m")
    print(f"  Envelope top: {new_env['y'] + new_env['depth_m']:.1f}")

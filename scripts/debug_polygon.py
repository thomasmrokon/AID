"""Check C_unregelmaessig polygon and envelope."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False
from app.tools.site import get_demo_site, compute_building_envelope

for sid in ['A_kompakt', 'C_unregelmaessig']:
    site = get_demo_site(sid)
    envelope = compute_building_envelope(site)

    print(f"\n=== {sid} ===")
    polygon = site.get('polygon')
    if polygon:
        print(f"Polygon ({len(polygon)} pts): {polygon[:5]}...")
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        print(f"  X range: [{min(xs):.1f}, {max(xs):.1f}]")
        print(f"  Y range: [{min(ys):.1f}, {max(ys):.1f}]")

        # Check if envelope corners are within polygon
        from shapely.geometry import Polygon as ShapelyPoly, Point
        poly = ShapelyPoly(polygon)
        env_x = envelope['x']
        env_y = envelope['y']
        env_x2 = env_x + envelope['width_m']
        env_y2 = env_y + envelope['depth_m']
        print(f"Envelope: [{env_x:.1f},{env_y:.1f}] -> [{env_x2:.1f},{env_y2:.1f}]")
        for cx, cy in [(env_x, env_y), (env_x2, env_y), (env_x2, env_y2), (env_x, env_y2)]:
            inside = poly.contains(Point(cx, cy))
            print(f"  Corner ({cx:.1f},{cy:.1f}): {'INSIDE' if inside else 'OUTSIDE!'}")
    else:
        print("No polygon!")

    if envelope:
        print(f"Envelope angle: {envelope.get('site_angle_deg', 0)}°")

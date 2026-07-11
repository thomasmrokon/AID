"""Quick integration test for building placement fix."""
import sys
import inspect
import tempfile
from pathlib import Path

from app.tools.site import get_demo_sites, compute_building_envelope
from app.tools.drawing import zeichne_layout, SiteTransform
from app.tools.geometry import Zone

# Test SiteTransform from envelope
sites = get_demo_sites()
for site in sites:
    env = compute_building_envelope(site)
    tr = SiteTransform.from_envelope(env)
    sn = site["name"]
    print(f"{sn}: angle={tr.angle_deg}, is_rotated={tr.is_rotated}")
    if env and not tr.is_rotated:
        pt_in = (env["x"] + 10, env["y"] + 10)
        pt_out = tr.pt(*pt_in)
        assert abs(pt_out[0] - pt_in[0]) < 0.01 and abs(pt_out[1] - pt_in[1]) < 0.01, (
            f"Identity transform failed: {pt_in} -> {pt_out}"
        )

# Test building_envelope param is present
sig = inspect.signature(zeichne_layout)
assert "building_envelope" in sig.parameters, "building_envelope param missing from zeichne_layout"
print("building_envelope param present in zeichne_layout: OK")

# Test full draw pipeline with real site and envelope
site = sites[0]
env = compute_building_envelope(site)
z = Zone(
    name="Produktion", x=env["x"], y=env["y"], breite=20, tiefe=15,
    flaeche_m2=300, din_kategorie="NUF 3", farbe="#4169E1",
)
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
    tmp_path = Path(tmp.name)
zeichne_layout(
    variante_name="A_Materialfluss", beschreibung="Test",
    zonen=[z], site_breite=site["width_m"], site_tiefe=site["depth_m"],
    raster_x=18, raster_y=12, scores={}, gewichtung={}, output_path=tmp_path,
    site_geometry=site, building_envelope=env,
)
assert tmp_path.exists() and tmp_path.stat().st_size > 10000, "PNG not generated"
tmp_path.unlink()
print("zeichne_layout with building_envelope: OK")

# Test that rotated SiteTransform produces correct corners
import math
tr_rot = SiteTransform(angle_deg=45.0, cx=0.0, cy=0.0)
x1, y1 = tr_rot.pt(1.0, 0.0)
expected_x = math.cos(math.radians(45))
expected_y = math.sin(math.radians(45))
assert abs(x1 - expected_x) < 1e-10 and abs(y1 - expected_y) < 1e-10, (
    f"45-degree rotation failed: got ({x1}, {y1}), expected ({expected_x}, {expected_y})"
)
print("SiteTransform 45° rotation: OK")

print("\nAll placement tests passed!")

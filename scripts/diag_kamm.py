"""Diagnostic: verify spine_h cap + footprint_m2 width allocation fix."""
import sys
sys.path.insert(0, ".")

from app.agents.layout import _with_dimensions, _snap_node_dimensions, _split_band_to_zones

settings = {"aspect_bias": 1.15}  # Variante A
grid = 3.0

nodes_raw = [
    {"name": "Buero",   "area_m2": 250.0, "footprint_m2": 125.0, "floors": 2, "target_aspect": 1.5, "din_kategorie": "NUF 2", "farbe": "#AAA"},
    {"name": "Sozial",  "area_m2":  84.0, "footprint_m2":  42.0, "floors": 2, "target_aspect": 1.5, "din_kategorie": "NUF 7", "farbe": "#BBB"},
    {"name": "Technik", "area_m2": 168.0, "footprint_m2": 168.0, "floors": 1, "target_aspect": 1.5, "din_kategorie": "TF",    "farbe": "#CCC"},
]

print("Snapped fp_i values:")
snapped = []
for n in nodes_raw:
    d = _with_dimensions(n, settings)
    s = _snap_node_dimensions(d, grid, grid)
    fp_m2 = s.get("footprint_m2", s["planned_area_m2"] / max(1, s["floors"]))
    fp_snap = s["planned_area_m2"] / max(1, s["floors"])
    print(f"  {n['name']}: breite={s['breite']:.0f} tiefe={s['tiefe']:.0f} "
          f"fp_briefing={fp_m2:.0f} fp_snap={fp_snap:.0f}")
    snapped.append(s)

spine_fp_briefing = sum(float(n.get("footprint_m2", 0)) for n in nodes_raw)
print(f"\nspine_fp_briefing = {spine_fp_briefing:.0f}")

for bw in [42, 56]:
    max_spine_h = spine_fp_briefing / bw * 1.30
    print(f"\nbw={bw}: max_spine_h_from_fp = {max_spine_h:.2f}m -> snap to {round(max_spine_h/grid)*grid:.0f}m")
    # simulate: original spine_h from fraction (0.15 * say 66m)
    for orig_spine_h in [9, 12]:
        new_spine_h = max(grid * 2, min(orig_spine_h, max_spine_h))
        new_spine_h = round(new_spine_h / grid) * grid
        for order_names in [["Buero", "Sozial", "Technik"], ["Buero", "Technik", "Sozial"]]:
            band = [next(n for n in snapped if n["name"] == nm) for nm in order_names]
            zones = _split_band_to_zones(band, 0, 0, bw, new_spine_h)
            label = f"bw={bw} orig_h={orig_spine_h}->{new_spine_h} {order_names}"
            print(f"  {label}:", end="")
            for z in zones:
                tgt = next(n["area_m2"] for n in nodes_raw if n["name"] == z.name)
                delta_pct = (z.planned_area_m2 - tgt) / tgt * 100
                print(f" {z.name}=w{z.breite:.0f}({delta_pct:+.0f}%)", end="")
            print()

"""Quick test of kamm layout fix — realistic single-zone scenario (no splits)."""
import sys
sys.path.insert(0, ".")

from app.agents.layout import _kamm_layout, _with_dimensions

# Realistic scenario: no zone splits, Produktion = 1 zone
nodes_raw = [
    {"name": "Buero",             "area_m2": 250.0, "footprint_m2": 125.0, "floors": 2, "target_aspect": 1.5, "din_kategorie": "NUF 2", "farbe": "#9B59B6"},
    {"name": "Sozial",            "area_m2":  84.0, "footprint_m2":  42.0, "floors": 2, "target_aspect": 1.5, "din_kategorie": "NUF 7", "farbe": "#F39C12"},
    {"name": "Technik",           "area_m2": 168.0, "footprint_m2": 168.0, "floors": 1, "target_aspect": 1.5, "din_kategorie": "TF",    "farbe": "#95A5A6"},
    {"name": "Wareneingang",      "area_m2": 200.0, "footprint_m2": 200.0, "floors": 1, "target_aspect": 2.0, "din_kategorie": "NUF 4", "farbe": "#E74C3C"},
    {"name": "Produktion",        "area_m2":1200.0, "footprint_m2":1200.0, "floors": 1, "target_aspect": 2.5, "din_kategorie": "NUF 3", "farbe": "#3498DB"},
    {"name": "Lager Rohstoffe",   "area_m2": 400.0, "footprint_m2": 400.0, "floors": 1, "target_aspect": 2.0, "din_kategorie": "NUF 4", "farbe": "#2ECC71"},
    {"name": "Qualitätssicherung","area_m2": 150.0, "footprint_m2": 150.0, "floors": 1, "target_aspect": 1.5, "din_kategorie": "NUF 3", "farbe": "#1ABC9C"},
    {"name": "Lager Fertigwaren", "area_m2": 400.0, "footprint_m2": 400.0, "floors": 1, "target_aspect": 2.0, "din_kategorie": "NUF 4", "farbe": "#27AE60"},
    {"name": "Versand",           "area_m2": 200.0, "footprint_m2": 200.0, "floors": 1, "target_aspect": 2.0, "din_kategorie": "NUF 4", "farbe": "#E67E22"},
]

settings = {"aspect_bias": 1.15, "process_pull": 1.35}

topology = {
    "process_order": ["Wareneingang", "Produktion", "Qualitätssicherung",
                      "Lager Rohstoffe", "Lager Fertigwaren", "Versand"],
    "nodes": nodes_raw,
}

zone_roles = {
    "Buero": "spine", "Sozial": "spine", "Technik": "spine",
    "Wareneingang": "tooth", "Produktion": "tooth",
    "Lager Rohstoffe": "tooth", "Qualitätssicherung": "tooth",
    "Lager Fertigwaren": "tooth", "Versand": "tooth",
}

nodes_dimmed = [_with_dimensions(n, settings) for n in nodes_raw]

# Envelope scaled by _skaliere_envelope_auf_briefing from a ~100×80 site
# total_fp = 125+42+168+200+1200+400+150+400+200 = 2885; mit puffer = 3462
# scale = sqrt(3462/8000)=0.658; new_w≈66m, new_d≈54m
for bw, bd in [(42, 72), (66, 54), (80, 48)]:
    envelope = {"x": 0.0, "y": 0.0, "width_m": float(bw), "depth_m": float(bd),
                "area_m2": float(bw*bd), "max_footprint_m2": float(bw*bd)}
    print(f"\n{'='*60}")
    print(f"Envelope: {bw}m × {bd}m = {bw*bd} m²  (briefing fp+puffer = 3462 m²)")
    try:
        zones = _kamm_layout(
            nodes=nodes_dimmed,
            topology=topology,
            zone_roles=zone_roles,
            envelope=envelope,
            settings=settings,
            raster_x=12.0,
            raster_y=12.0,
        )
        print(f"{'Zone':<24} {'Soll':>6} {'Ist':>6} {'d%':>7} {'Floors':>6} {'W':>5}")
        print("-" * 58)
        total_abs = 0
        for z in zones:
            if z.schraffur:
                continue
            tgt = next((n["area_m2"] for n in nodes_raw if n["name"] == z.name), z.flaeche_m2)
            dp = (z.planned_area_m2 - tgt) / max(1, tgt) * 100
            total_abs += abs(z.planned_area_m2 - tgt)
            print(f"{z.name:<24} {tgt:>6.0f} {z.planned_area_m2:>6.0f} {dp:>+6.1f}% {z.floors:>6} {z.breite:>5.0f}")
        print(f"  Total |delta| = {total_abs:.0f} m²")
    except Exception as e:
        print(f"ERROR: {e}")

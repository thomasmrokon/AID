"""Sprint O: Optimizer Qualitätstest mit A_kompakt."""
import time
from app.tools.site import get_demo_site, compute_building_envelope
from app.agents.layout_optimizer import optimize_layout, OptimizationWeights, TragwerkConstraints

site = get_demo_site("A_kompakt")
env = compute_building_envelope(site)
print(f"Envelope: {env['width_m']}m x {env['depth_m']}m")

nodes = [
    {"name": "Wareneingang",    "area_m2": 300,  "din_kategorie": "NUF 3", "farbe": "#4A90D9", "floors": 1},
    {"name": "Produktion",      "area_m2": 2000, "din_kategorie": "NUF 3", "farbe": "#5B9B6B", "floors": 1},
    {"name": "Lager Rohware",   "area_m2": 500,  "din_kategorie": "NUF 3", "farbe": "#6AB4C8", "floors": 1},
    {"name": "Lager Fertigware","area_m2": 500,  "din_kategorie": "NUF 3", "farbe": "#7BC8E2", "floors": 1},
    {"name": "Versand",         "area_m2": 300,  "din_kategorie": "NUF 3", "farbe": "#4A90D9", "floors": 1},
    {"name": "QS-Labor",        "area_m2": 120,  "din_kategorie": "NUF 4", "farbe": "#F5A623", "floors": 1},
    {"name": "Buero",           "area_m2": 400,  "din_kategorie": "NUF 2", "farbe": "#D0021B", "floors": 2},
    {"name": "Technik",         "area_m2": 150,  "din_kategorie": "TF",    "farbe": "#9B9B9B", "floors": 2},
    {"name": "Sozial",          "area_m2": 200,  "din_kategorie": "NUF 7", "farbe": "#BD10E0", "floors": 2},
]
topology = {
    "nodes": nodes,
    "process_order": ["Wareneingang", "Lager Rohware", "Produktion", "QS-Labor", "Lager Fertigware", "Versand"],
    "adjacency": [],
}
adjacency_weights = {
    "Wareneingang|Lager Rohware": 3.0,
    "Lager Rohware|Produktion": 3.0,
    "Produktion|QS-Labor": 2.0,
    "Produktion|Lager Fertigware": 2.0,
    "Lager Fertigware|Versand": 3.0,
    "Buero|Produktion": 1.5,
    "Technik|Produktion": 1.0,
}

t0 = time.perf_counter()
result = optimize_layout(
    nodes=nodes,
    topology=topology,
    envelope=env,
    adjacency_weights=adjacency_weights,
    weights=OptimizationWeights.for_variant("A_Materialfluss"),
    tragwerk=TragwerkConstraints(),
    n_tree_candidates=6,
    max_iterations=200,
    seed=42,
)
t1 = time.perf_counter()

print(f"Optimizer: {t1-t0:.2f}s, obj={result.objective_value:.4f}, converged={result.converged}")
print(f"Tree: {result.tree_topology}")
print()
max_ar = 0.0
max_delta = 0.0
violations = []
for z in result.zones:
    if not z.schraffur:
        ar = max(z.breite, z.tiefe) / max(0.01, min(z.breite, z.tiefe))
        max_ar = max(max_ar, ar)
        max_delta = max(max_delta, abs(z.delta_pct or 0))
        flag = " <<<" if ar > 4.0 else ""
        print(f"  {z.name:25s}  {z.breite:.1f}m x {z.tiefe:.1f}m  AR={ar:.2f}  delta={z.delta_pct:+.1f}%{flag}")
        if ar > 4.0:
            violations.append(z.name)

print()
print(f"Max AR: {max_ar:.2f} (limit: 4.0)")
print(f"Max area delta: {max_delta:.1f}%")
print(f"AR violations: {violations}")

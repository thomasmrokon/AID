"""Smoke test for the slicing optimizer and its decision metrics."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.layout_optimizer import (  # noqa: E402
    OptimizationWeights,
    TragwerkConstraints,
    optimize_layout,
)


def main() -> None:
    nodes = [
        {
            "name": "Wareneingang",
            "area_m2": 420.0,
            "footprint_m2": 420.0,
            "din_kategorie": "NUF 4",
            "farbe": "#5B8DB8",
            "floors": 1,
        },
        {
            "name": "Produktion",
            "area_m2": 1200.0,
            "footprint_m2": 1200.0,
            "din_kategorie": "NUF 3",
            "farbe": "#2A9D8F",
            "floors": 1,
        },
        {
            "name": "Lager",
            "area_m2": 650.0,
            "footprint_m2": 650.0,
            "din_kategorie": "NUF 4",
            "farbe": "#F4A261",
            "floors": 1,
        },
        {
            "name": "Versand",
            "area_m2": 420.0,
            "footprint_m2": 420.0,
            "din_kategorie": "NUF 4",
            "farbe": "#264653",
            "floors": 1,
        },
        {
            "name": "Buero",
            "area_m2": 360.0,
            "footprint_m2": 180.0,
            "din_kategorie": "NUF 2",
            "farbe": "#A8DADC",
            "floors": 2,
        },
    ]
    topology = {
        "process_order": ["Wareneingang", "Produktion", "Lager", "Versand"],
        "nodes": nodes,
    }
    adjacency_weights = {
        "Wareneingang|Produktion": 1.0,
        "Produktion|Lager": 0.8,
        "Lager|Versand": 1.0,
        "Produktion|Buero": 0.3,
    }
    envelope = {
        "x": 0.0,
        "y": 0.0,
        "width_m": 66.0,
        "depth_m": 48.0,
        "area_m2": 3168.0,
        "rotation_deg": 0.0,
    }

    result = optimize_layout(
        nodes=nodes,
        topology=topology,
        envelope=envelope,
        adjacency_weights=adjacency_weights,
        weights=OptimizationWeights(),
        tragwerk=TragwerkConstraints(raster_x_m=6.0, raster_y_m=6.0),
        n_tree_candidates=12,
        max_iterations=250,
        seed=7,
    )

    assert result.objective_value < 2.0, result.objective_value
    assert result.converged is True
    assert all(z.planned_area_m2 is not None for z in result.zones)
    assert all(0.0 <= d.adjacency_score <= 1.0 for d in result.zone_decisions)

    print(f"objective_value={result.objective_value:.3f} converged={result.converged} iterations={result.iterations}")
    print(f"{'Zone':24s} {'area_delta_pct':>15s} {'adjacency_score':>16s} {'aspect_ratio':>14s}")
    for decision in result.zone_decisions:
        print(
            f"{decision.zone_name:24s} "
            f"{decision.area_delta_pct:15.1f} "
            f"{decision.adjacency_score:16.2f} "
            f"{decision.aspect_ratio:14.2f}"
        )


if __name__ == "__main__":
    main()

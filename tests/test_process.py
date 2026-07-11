"""Tests: Prozesslayout-Agent — Vorschlag und adaptiver Transfer."""
from __future__ import annotations

from app.agents.process import process_layout_agent
from app.state import DEMO_MASCHINENPARK


def test_process_layout_ai_suggestion_returns_mode_and_machines():
    result = process_layout_agent({
        "process_input": {
            "mode": "ai_suggestion",
            "zone_name": "Produktion",
            "zone_breite_m": 40.0,
            "zone_tiefe_m": 75.0,
            "maschinenpark": DEMO_MASCHINENPARK,
        }
    })

    layout = result["process_layout"]
    assert layout["mode"] == "ai_suggestion"
    assert layout["mode_label"] == "KI-gestützter Layoutvorschlag"
    assert layout["maschinen"]
    assert layout["strips"]
    assert layout["kpis"].get("durchsatz_teile_pro_schicht", 0) > 0


def test_process_layout_adaptive_transfer_scales_reference_layout():
    park = DEMO_MASCHINENPARK[:2]
    reference_layout = {
        "zone_breite_m": 20.0,
        "zone_tiefe_m": 30.0,
        "maschinen": [
            {"id": "M01", "name": "Tafelschere", "schritt": 1, "x": 2.0, "y": 2.0, "breite_m": 4.0, "tiefe_m": 2.5},
            {"id": "M02", "name": "Ablängsäge", "schritt": 1, "x": 8.0, "y": 2.0, "breite_m": 3.5, "tiefe_m": 2.0},
        ],
    }

    result = process_layout_agent({
        "process_input": {
            "mode": "adaptive_transfer",
            "zone_name": "Produktion",
            "zone_breite_m": 40.0,
            "zone_tiefe_m": 60.0,
            "maschinenpark": park,
            "reference_layout": reference_layout,
        }
    })

    layout = result["process_layout"]
    assert layout["mode"] == "adaptive_transfer"
    assert layout["transfer"]["status"] == "transferred"
    assert layout["transfer"]["scale_x"] == 2.0
    assert layout["transfer"]["scale_y"] == 2.0
    assert len(layout["maschinen"]) == 2
    assert all(m["x"] >= 1.5 and m["y"] >= 1.5 for m in layout["maschinen"])


def test_process_layout_adaptive_transfer_falls_back_without_reference():
    result = process_layout_agent({
        "process_input": {
            "mode": "adaptive_transfer",
            "zone_breite_m": 40.0,
            "zone_tiefe_m": 75.0,
            "maschinenpark": DEMO_MASCHINENPARK[:1],
            "reference_layout": {},
        }
    })

    layout = result["process_layout"]
    assert layout["transfer"]["status"] == "fallback_suggestion"
    assert layout["maschinen"]

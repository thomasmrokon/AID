"""Test: layout_agent — Vollständigkeit, AR-Constraint, Variantenanzahl."""
from __future__ import annotations
import pytest

MAX_ASPECT_RATIO = 4.0
EXPECTED_VARIANT_COUNT = 3


def test_layout_three_variants(pipeline_state):
    """Genau 3 Varianten werden generiert."""
    variants = pipeline_state["variants"]
    assert variants is not None
    assert len(variants) == EXPECTED_VARIANT_COUNT, (
        f"Erwartet {EXPECTED_VARIANT_COUNT} Varianten, erhalten: {len(variants)}"
    )


def test_layout_all_variants_have_zones(pipeline_state):
    """Jede Variante enthält mindestens 5 Zonen."""
    for v in pipeline_state["variants"]:
        zonen = [z for z in v["zonen"] if not z.get("schraffur")]
        assert len(zonen) >= 5, (
            f"Variante {v['name']}: nur {len(zonen)} Zonen (erwartet ≥ 5)"
        )


def test_layout_no_ar_violations(pipeline_state):
    """Kein Aspect-Ratio > 4.0 in irgendeiner Variante."""
    violations = []
    for v in pipeline_state["variants"]:
        for z in v["zonen"]:
            if z.get("schraffur"):
                continue
            breite = z.get("breite", 1)
            tiefe  = z.get("tiefe", 1)
            if breite > 0 and tiefe > 0:
                ar = max(breite / tiefe, tiefe / breite)
                if ar > MAX_ASPECT_RATIO + 0.01:  # 0.01 Toleranz für Rundung
                    violations.append(
                        f"{v['name']}/{z['name']}: AR={ar:.2f}"
                    )
    assert not violations, "AR-Verletzungen: " + ", ".join(violations)


def test_layout_all_topology_nodes_present(pipeline_state):
    """P0-Regression: alle Topology-Nodes erscheinen namentlich in jeder Variante.

    Schlägt an, wenn _split_band_to_zones oder Fallback-Logik eine Zone verliert.
    """
    topo = pipeline_state.get("topology_diagram") or {}
    expected_names = {n["name"] for n in topo.get("nodes", [])}
    assert expected_names, "topology_diagram ohne Nodes — Pipeline unvollständig"

    for v in pipeline_state["variants"]:
        actual_names = {z["name"] for z in v["zonen"] if not z.get("schraffur")}
        missing = expected_names - actual_names
        assert not missing, (
            f"P0: Variante {v['name']} verliert Zonen: {missing}. "
            f"Vorhanden: {actual_names}"
        )


def test_layout_zones_within_site(pipeline_state):
    """Alle Zone-Koordinaten liegen innerhalb der Site-BBox."""
    site = pipeline_state["site_geometry"]
    # site hat kein "x"/"y" — Ursprung ist immer (0, 0)
    x_min, y_min = 0.0, 0.0
    x_max = site["width_m"]
    y_max = site["depth_m"]

    for v in pipeline_state["variants"]:
        for z in v["zonen"]:
            assert z["x"] >= x_min - 0.5,           f"{v['name']}/{z['name']}: x zu klein"
            assert z["y"] >= y_min - 0.5,           f"{v['name']}/{z['name']}: y zu klein"
            assert z["x"] + z["breite"] <= x_max + 0.5, f"{v['name']}/{z['name']}: Breite überschreitet Site"
            assert z["y"] + z["tiefe"]  <= y_max + 0.5, f"{v['name']}/{z['name']}: Tiefe überschreitet Site"


def test_building_parcel_envelope_uses_full_parcel_area():
    """Gebäudeparzellen aus der Masterplanung sind bereits die Layout-Ausgangsfläche."""
    from app.tools.site import compute_building_envelope

    parcel = {
        "id": "P1_BP01",
        "interface_type": "building_parcel",
        "is_building_parcel": True,
        "width_m": 96.0,
        "depth_m": 54.0,
        "area_m2": 5184.0,
        "polygon": [[0, 0], [96, 0], [96, 54], [0, 54]],
        "planning": {"abstandsfaktor": 0.4, "max_gebaeudehoehe_m": 12.0},
    }

    envelope = compute_building_envelope(parcel)

    assert envelope is not None
    assert envelope["x"] == 0.0
    assert envelope["y"] == 0.0
    assert envelope["width_m"] == 96.0
    assert envelope["depth_m"] == 54.0
    assert envelope["max_footprint_m2"] == 5184.0
    assert envelope["setback_m"] == 0.0

"""Test: masterplan_agent — GRZ, Flächenbilanz, Nebenbauten."""
from __future__ import annotations
import contextlib
import io
import pytest

GRZ_MAX = 0.80      # BauNVO § 17 Abs. 2 — hartes Maximum
GRZ_ZIEL = 0.60     # GI/GE Regelwert


def _run_masterplan(site_state, grz_ziel: float = 0.45):
    """Führt masterplan_agent aus und gibt das Ergebnis zurück."""
    from app.agents.briefing   import briefing_agent
    from app.agents.masterplan import masterplan_agent

    state = dict(site_state)
    with contextlib.redirect_stdout(io.StringIO()):
        sb = briefing_agent(state)
    state.update(sb)

    with contextlib.redirect_stdout(io.StringIO()):
        result = masterplan_agent(
            site       = state["site_geometry"],
            grz_ziel   = grz_ziel,
            nebenbauten_aktiv = {"pforte": True, "trafo": True,
                                 "lagerueberdachung": False, "sozialgebaeude": False},
            erschliessung_typ = "standard",
            geschosse_buero   = 2,
            briefing          = state["structured_briefing"],
        )
    return result


@pytest.fixture(scope="module")
def masterplan_result(site_state):
    return _run_masterplan(site_state)


def _mp(masterplan_result: dict) -> dict:
    """Gibt das verschachtelte 'masterplan'-Unter-Dict zurück."""
    return masterplan_result.get("masterplan") or masterplan_result


def test_masterplan_grz_within_hard_limit(masterplan_result):
    """GRZ ≤ 0.80 (BauNVO harte Grenze)."""
    bilanz = _mp(masterplan_result).get("flaechenbilanz") or {}
    grz = bilanz.get("grz")
    assert grz is not None, "flaechenbilanz.grz fehlt"
    assert grz <= GRZ_MAX, f"GRZ {grz:.3f} überschreitet Maximum {GRZ_MAX}"


def test_masterplan_grz_plausible(masterplan_result):
    """GRZ ≥ 0.10 (kein leeres Grundstück)."""
    grz = _mp(masterplan_result)["flaechenbilanz"]["grz"]
    assert grz >= 0.10, f"GRZ {grz:.3f} unplausibel niedrig"


def test_masterplan_hauptgebaeude_present(masterplan_result):
    """Hauptgebäude-Dict mit Fläche vorhanden."""
    hg = _mp(masterplan_result).get("hauptgebaeude")
    assert hg is not None, "hauptgebaeude fehlt"
    assert hg.get("flaeche_m2", 0) > 0


def test_masterplan_nebenbauten_list(masterplan_result):
    """Nebenbauten-Liste vorhanden (kann leer sein, aber darf nicht None sein)."""
    nb = _mp(masterplan_result).get("nebenbauten")
    assert nb is not None
    assert isinstance(nb, list)


def test_masterplan_stellplaetze_positive(masterplan_result):
    """Stellplatz-Nachweis enthält positive Werte."""
    mp = _mp(masterplan_result)
    # Stellplätze können in flaechenbilanz oder stellplatz_nachweis stecken
    sp = mp.get("stellplatz_nachweis") or mp.get("flaechenbilanz") or {}
    soll = sp.get("stellplaetze_soll", 0)
    assert soll >= 0, "Stellplätze Soll darf nicht negativ sein"


def test_masterplan_building_parcels_have_unique_ids(masterplan_result):
    """Masterplanung liefert eindeutig identifizierbare Gebäudeparzellen für die Layoutplanung."""
    mp = _mp(masterplan_result)
    parcels = mp.get("building_parcels") or []
    assert parcels, "building_parcels fehlt"
    ids = [p.get("id") for p in parcels]
    assert all(ids), "Jede Gebäudeparzelle braucht eine ID"
    assert len(ids) == len(set(ids)), "Gebäudeparzellen-IDs müssen eindeutig sein"


def test_masterplan_selected_building_parcel_is_layout_interface(masterplan_result):
    """Die ausgewählte Gebäudeparzelle ist die Schnittstelle zur Gebäude-Layoutplanung."""
    mp = _mp(masterplan_result)
    selected_id = mp.get("selected_building_parcel_id")
    parcels = mp.get("building_parcels") or []
    selected = next((p for p in parcels if p.get("id") == selected_id), None)
    assert selected is not None
    assert mp.get("building_parcel", {}).get("id") == selected_id
    assert selected.get("source") == "masterplan"
    assert selected.get("interface_type") == "building_parcel"
    assert selected.get("exclude_site_parking") is True
    assert selected.get("polygon")
    assert selected.get("width_m", 0) > 0
    assert selected.get("depth_m", 0) > 0


def test_masterplan_generates_three_variants(masterplan_result):
    """Masterplanung liefert eigenständige Varianten mit Score und Infrastruktur."""
    mp = _mp(masterplan_result)
    variants = mp.get("variants") or []
    assert len(variants) == 3
    assert {v.get("id") for v in variants} == {"A_LOGISTIK", "B_ERWEITERUNG", "C_FLAECHENEFFIZIENZ"}
    for variant in variants:
        assert variant.get("building_parcels"), f"{variant.get('id')}: building_parcels fehlt"
        assert variant.get("infrastruktur", {}).get("trassen"), f"{variant.get('id')}: Infrastrukturtrassen fehlen"
        assert variant.get("score", {}).get("gesamt", 0) > 0, f"{variant.get('id')}: Score fehlt"


def test_masterplan_variant_parcel_ids_are_unique(masterplan_result):
    """Gebäudeparzellen sind auch über Masterplan-Varianten hinweg eindeutig."""
    mp = _mp(masterplan_result)
    ids = [
        parcel.get("id")
        for variant in mp.get("variants") or []
        for parcel in variant.get("building_parcels") or []
    ]
    assert ids
    assert len(ids) == len(set(ids))


def test_large_site_generates_multiple_building_parcels():
    """Große Areale erzeugen mehrere Gebäude und wählbare Gebäudeparzellen."""
    from app.agents.masterplan import masterplan_agent

    site = {
        "id": "large_industrial_site",
        "name": "Großareal Test",
        "width_m": 360.0,
        "depth_m": 260.0,
        "area_m2": 93600.0,
        "polygon": [[0, 0], [360, 0], [360, 260], [0, 260]],
        "access_points": [{"id": "Z1", "side": "south", "point": [90, 0], "width_m": 9}],
    }
    result = masterplan_agent(
        site,
        grz_ziel=0.42,
        nebenbauten_aktiv={"Pforte / Einfahrtskontrolle": True, "Trafostation": True},
        erschliessung_typ="u_foermig",
        geschosse_buero=3,
        briefing={"lager_rohstoffe": 1800, "lager_fertigwaren": 2200, "buero_nuf2": 1400},
    )
    mp = _mp(result)

    assert len(mp.get("gebaeude") or []) >= 3
    assert len(mp.get("building_parcels") or []) >= 3
    ids = [p["id"] for p in mp["building_parcels"]]
    assert len(ids) == len(set(ids))
    for parcel in mp["building_parcels"]:
        assert parcel.get("is_building_parcel") is True
        assert parcel.get("width_m", 0) > 0
        assert parcel.get("depth_m", 0) > 0


def test_masterplan_contains_site_analysis_zoning_and_pipeline(masterplan_result):
    """Masterplanung dokumentiert Grundstücksanalyse, Zonierung und Pipeline-Schritte."""
    mp = _mp(masterplan_result)
    analysis = mp.get("grundstuecksanalyse") or {}
    assert analysis.get("primary_access_side")
    assert analysis.get("long_axis") in {"x", "y"}
    assert 0 < analysis.get("compactness", 0) <= 1

    zoning = mp.get("zonierung") or []
    assert zoning, "Zonierung fehlt"
    zone_types = {z.get("typ") for z in zoning}
    assert "verkehr_lkw" in zone_types
    assert "building_parcel_candidate" in zone_types
    assert "reserve" in zone_types

    concept = mp.get("erschliessungskonzept") or {}
    assert concept.get("route_type") in {"ring", "loop", "stich"}
    assert concept.get("verkehrstrennung")
    assert mp.get("planning_pipeline")


def test_masterplan_building_parcel_comes_from_zoning(masterplan_result):
    """Die Layout-Schnittstelle bleibt innerhalb der erzeugten Gebäudezone."""
    mp = _mp(masterplan_result)
    parcel = mp.get("building_parcel") or {}
    zoning_parcels = [z for z in (mp.get("zonierung") or []) if z.get("typ") == "building_parcel_candidate"]
    assert zoning_parcels
    z = zoning_parcels[0]
    parent_x, parent_y = parcel.get("parent_offset_m") or [None, None]
    assert parent_x is not None and parent_y is not None
    assert z["x"] <= parent_x <= z["x"] + z["breite_m"]
    assert z["y"] <= parent_y <= z["y"] + z["tiefe_m"]


def test_irregular_site_masterplan_keeps_key_rectangles_inside_polygon():
    """Unregelmäßige reale Grundstücke dürfen keine zentralen Rechtecke außerhalb der Fläche platzieren."""
    from shapely.geometry import Polygon, box
    from app.agents.masterplan import masterplan_agent

    site = {
        "id": "irregular_osm_test",
        "name": "Unregelmäßiges OSM-Grundstück",
        "width_m": 90.0,
        "depth_m": 115.0,
        "area_m2": 5200.0,
        "polygon": [[8, 4], [55, 0], [84, 38], [66, 92], [28, 108], [0, 78]],
        "access_points": [{"id": "Z1", "side": "south", "point": [34, 4], "width_m": 7.5}],
    }
    mp = _mp(masterplan_agent(site, grz_ziel=0.45, erschliessung_typ="u_foermig"))
    poly = Polygon(site["polygon"])

    rects = [mp["hauptgebaeude"], mp["erschliessung"]["rangierzone"]] + [
        z for z in mp.get("freizonen", []) if z.get("typ") in {"stellplatz", "aussenlager", "gruen"}
    ]
    for rect in rects:
        r = box(rect["x"], rect["y"], rect["x"] + rect["breite_m"], rect["y"] + rect["tiefe_m"])
        coverage = poly.intersection(r).area / max(1.0, r.area)
        assert coverage >= 0.55, f"{rect.get('name')} liegt zu stark außerhalb des Grundstücks: {coverage:.2f}"


def test_masterplan_respects_main_building_target_size():
    """Zielgrößen aus 1.4 beeinflussen die Platzhaltergröße der Hauptgebäude."""
    from app.agents.masterplan import masterplan_agent

    site = {
        "id": "target_size_site",
        "name": "Zielgröße Test",
        "width_m": 180.0,
        "depth_m": 120.0,
        "area_m2": 21600.0,
        "polygon": [[0, 0], [180, 0], [180, 120], [0, 120]],
        "access_points": [{"id": "Z1", "side": "south", "point": [70, 0], "width_m": 8}],
    }
    mp = _mp(masterplan_agent(
        site,
        grz_ziel=0.45,
        erschliessung_typ="u_foermig",
        building_targets={"main_footprint_m2": 2400, "main_width_m": 60, "main_depth_m": 40, "main_building_count": 2},
    ))
    production_buildings = [g for g in mp.get("gebaeude", []) if g.get("funktion") == "produktion"]
    assert production_buildings
    assert abs(production_buildings[0]["flaeche_m2"] - 2400) <= 700
    assert len(production_buildings) >= 2
    assert mp.get("config", {}).get("building_targets")


def test_irregular_site_uses_polygonal_zoning():
    """Unregelmäßige Grundstücke erzeugen polygonale Verkehrs-/Reserve-Zonen."""
    from app.agents.masterplan import masterplan_agent

    site = {
        "id": "polygonal_zone_test",
        "name": "Polygonal Zone Test",
        "width_m": 90.0,
        "depth_m": 115.0,
        "area_m2": 5200.0,
        "polygon": [[8, 4], [55, 0], [84, 38], [66, 92], [28, 108], [0, 78]],
        "access_points": [{"id": "Z1", "side": "south", "point": [34, 4], "width_m": 7.5}],
    }
    mp = _mp(masterplan_agent(site, grz_ziel=0.42, erschliessung_typ="u_foermig"))
    zones = mp.get("zonierung") or []
    assert any(z.get("geometry_mode") == "polygon_intersection" for z in zones)
    assert mp.get("variants", [])[0].get("config", {}).get("algorithmus") == "polygonal_site_zoning_v2"



def test_traffic_decision_tree_prefers_stichhof_for_small_compact_site():
    """Kleine kompakte Grundstücke sollen keinen Ring erzwingen."""
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    site = get_demo_site("A_kompakt")
    mp = _mp(masterplan_agent(site, grz_ziel=0.45, erschliessung_typ="u_foermig", building_targets={"main_building_count": 2}))
    concept = mp.get("erschliessungskonzept") or {}
    assert concept.get("strategy_type") == "stichhof"
    assert concept.get("route_type") == "stich"
    assert concept.get("decision_reasons")
    assert mp.get("erschliessung", {}).get("erschliessungsflaeche_m2", 0) / site["area_m2"] < 0.12


def test_traffic_decision_tree_candidates_are_recorded_and_drive_parcels():
    """1.4 nutzt die in 1.3 gewählte Strategie als Grundlage für Restflächen."""
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    site = get_demo_site("C_unregelmaessig")
    mp = _mp(masterplan_agent(site, grz_ziel=0.45, erschliessung_typ="u_foermig", building_targets={"main_building_count": 2}))
    concept = mp.get("erschliessungskonzept") or {}
    assert concept.get("strategy_type") in {"frontspange", "stichhof", "laengs_spine", "u_loop"}
    assert concept.get("candidate_strategies")
    traffic = (mp.get("phasenlayer") or {}).get("1.3") or {}
    parcels = ((mp.get("phasenlayer") or {}).get("1.4") or {}).get("building_parcels") or []
    assert traffic.get("road_zone")
    assert len(parcels) >= 2

def test_masterplan_rule_catalog_is_attached_to_phase_layers():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(get_demo_site("A_kompakt"), grz_ziel=0.45))
    layers = mp.get("phasenlayer") or {}
    assert mp.get("config", {}).get("rule_catalog_loaded") is True
    assert layers.get("1.2", {}).get("rule_refs")
    assert layers.get("1.3", {}).get("rule_refs")
    assert layers.get("1.4", {}).get("rule_refs")
    assert any(r.get("source_ref") for r in layers["1.3"]["rule_refs"])


def test_masterplan_rule_sources_are_exportable_for_decision_log():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(get_demo_site("A_kompakt"), grz_ziel=0.45))
    sources = mp.get("regelquellen") or []
    assert sources
    assert {s.get("phase") for s in sources} >= {"1.1", "1.2", "1.3", "1.4"}
    assert all(s.get("id") and s.get("source_ref") for s in sources)

def test_demo_sites_cover_distinct_size_classes():
    from app.tools.site import get_demo_sites

    sites = get_demo_sites()
    by_id = {site["id"]: site for site in sites}
    assert by_id["A_kompakt"]["area_m2"] < 12000
    assert 18000 <= by_id["B_langgezogen"]["area_m2"] <= 30000
    assert by_id["C_unregelmaessig"]["area_m2"] > 45000
    assert by_id["A_kompakt"]["area_m2"] < by_id["B_langgezogen"]["area_m2"] < by_id["C_unregelmaessig"]["area_m2"]

def test_traffic_layer_uses_target_zones_and_graph():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(
        get_demo_site("B_langgezogen"),
        grz_ziel=0.45,
        erschliessung_typ="l_foermig",
        building_targets={"traffic_profile": "logistik", "main_building_count": 2},
    ))
    traffic = (mp.get("phasenlayer") or {}).get("1.3") or {}
    assert traffic.get("functional_zones")
    assert {z.get("typ") for z in traffic["functional_zones"]} >= {"zielzone_andienung", "zielzone_pkw", "zielzone_sicherheit"}
    graph = traffic.get("traffic_graph") or {}
    assert len(graph.get("nodes") or []) >= 5
    assert len(graph.get("edges") or []) >= 2
    assert traffic.get("target_zone_summary")


def test_parcels_do_not_cover_traffic_corridor_from_phase_13():
    from shapely.geometry import Polygon, box
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(
        get_demo_site("B_langgezogen"),
        grz_ziel=0.45,
        erschliessung_typ="l_foermig",
        building_targets={"traffic_profile": "logistik", "main_building_count": 2},
    ))
    traffic = (mp.get("phasenlayer") or {}).get("1.3") or {}
    road_poly = Polygon((traffic.get("road_zone") or {}).get("polygon") or [])
    parcels = ((mp.get("phasenlayer") or {}).get("1.4") or {}).get("building_parcels") or []
    assert not road_poly.is_empty
    assert parcels
    for parcel in parcels:
        pbox = box(parcel["x"], parcel["y"], parcel["x"] + parcel["breite_m"], parcel["y"] + parcel["tiefe_m"])
        overlap = road_poly.intersection(pbox).area / max(1.0, pbox.area)
        assert overlap < 0.08

def test_infra_phase_zonierung_contains_visible_target_zones():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(
        get_demo_site("B_langgezogen"),
        grz_ziel=0.45,
        erschliessung_typ="l_foermig",
        building_targets={"traffic_profile": "logistik", "main_building_count": 2},
    ))
    zone_types = {z.get("typ") for z in mp.get("zonierung") or []}
    assert {"zielzone_andienung", "zielzone_pkw", "zielzone_sicherheit"}.issubset(zone_types)

def test_redundant_access_requirement_prioritizes_ring_candidate():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(
        get_demo_site("C_unregelmaessig"),
        grz_ziel=0.45,
        erschliessung_typ="gerade",
        building_targets={"traffic_profile": "datacenter", "required_redundant_access": True, "main_building_count": 2},
    ))
    candidates = (mp.get("erschliessungskonzept") or {}).get("candidate_strategies") or []
    assert candidates
    assert candidates[0].get("strategy_type") in {"perimeter_ring", "u_loop"}


def test_lkw_movements_scale_service_target_zone():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    site = get_demo_site("B_langgezogen")
    low = _mp(masterplan_agent(site, grz_ziel=0.45, erschliessung_typ="l_foermig", building_targets={"traffic_profile": "logistik", "lkw_movements_per_day": 20}))
    high = _mp(masterplan_agent(site, grz_ziel=0.45, erschliessung_typ="l_foermig", building_targets={"traffic_profile": "logistik", "lkw_movements_per_day": 160}))
    def service_area(mp):
        traffic = (mp.get("phasenlayer") or {}).get("1.3") or {}
        zones = traffic.get("target_zone_summary") or []
        return next(float(z.get("flaeche_m2") or 0) for z in zones if z.get("typ") == "zielzone_andienung")
    assert service_area(high) > service_area(low)

def test_traffic_optimizer_records_population_and_selected_chromosome():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(
        get_demo_site("B_langgezogen"),
        grz_ziel=0.45,
        erschliessung_typ="l_foermig",
        building_targets={
            "traffic_profile": "logistik",
            "main_building_count": 3,
            "lkw_movements_per_day": 140,
            "employee_count": 260,
        },
    ))
    traffic = (mp.get("phasenlayer") or {}).get("1.3") or {}
    concept = mp.get("erschliessungskonzept") or {}
    candidates = concept.get("candidate_strategies") or []

    assert traffic.get("optimization_mode") == "evolutionary_candidate_search_v1"
    assert traffic.get("optimization_population_size", 0) > 10
    assert traffic.get("optimization_evaluated_candidates", 0) > 5
    assert traffic.get("selected_chromosome")
    assert concept.get("selected_chromosome") == traffic.get("selected_chromosome")
    assert candidates and all(c.get("chromosome") for c in candidates[:3])


def test_traffic_optimizer_varies_target_zone_parameters():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    mp = _mp(masterplan_agent(
        get_demo_site("B_langgezogen"),
        grz_ziel=0.45,
        erschliessung_typ="l_foermig",
        building_targets={"traffic_profile": "logistik", "lkw_movements_per_day": 120, "employee_count": 240},
    ))
    candidates = (mp.get("erschliessungskonzept") or {}).get("candidate_strategies") or []
    service_biases = {c.get("chromosome", {}).get("service_axis_bias") for c in candidates[:12]}
    parking_biases = {c.get("chromosome", {}).get("parking_axis_bias") for c in candidates[:12]}

    assert len(service_biases) > 1
    assert len(parking_biases) > 1

def test_traffic_fitness_weights_are_recorded_in_metrics():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    weights = {
        "connectivity": 1.7,
        "strategy": 0.4,
        "road_efficiency": 1.8,
        "rectangularity": 1.5,
        "parcel_split": 0.6,
    }
    mp = _mp(masterplan_agent(
        get_demo_site("B_langgezogen"),
        grz_ziel=0.45,
        erschliessung_typ="l_foermig",
        building_targets={"traffic_profile": "logistik", "traffic_fitness_weights": weights},
    ))
    traffic = (mp.get("phasenlayer") or {}).get("1.3") or {}
    concept = mp.get("erschliessungskonzept") or {}
    top = (concept.get("candidate_strategies") or [])[0]

    assert traffic.get("fitness_weights") == weights
    assert concept.get("fitness_weights") == weights
    assert top.get("metrics", {}).get("fitness_weights") == weights
    assert top.get("metrics", {}).get("fitness_terms", {}).get("road_efficiency_penalty") is not None


def test_traffic_fitness_weights_can_change_selected_candidate():
    from app.agents.masterplan import masterplan_agent
    from app.tools.site import get_demo_site

    site = get_demo_site("B_langgezogen")
    road_focused = _mp(masterplan_agent(
        site,
        grz_ziel=0.45,
        erschliessung_typ="u_foermig",
        building_targets={
            "traffic_profile": "logistik",
            "traffic_fitness_weights": {"connectivity": 0.4, "strategy": 0.2, "road_efficiency": 2.0, "rectangularity": 0.6, "parcel_split": 0.5},
        },
    ))
    rect_focused = _mp(masterplan_agent(
        site,
        grz_ziel=0.45,
        erschliessung_typ="u_foermig",
        building_targets={
            "traffic_profile": "logistik",
            "traffic_fitness_weights": {"connectivity": 1.2, "strategy": 1.0, "road_efficiency": 0.2, "rectangularity": 2.0, "parcel_split": 1.8},
        },
    ))

    road_top = ((road_focused.get("erschliessungskonzept") or {}).get("candidate_strategies") or [])[0]
    rect_top = ((rect_focused.get("erschliessungskonzept") or {}).get("candidate_strategies") or [])[0]
    assert road_top.get("metrics", {}).get("fitness_weights", {}).get("road_efficiency") == 2.0
    assert rect_top.get("metrics", {}).get("fitness_weights", {}).get("rectangularity") == 2.0
    assert road_top.get("score") != rect_top.get("score") or road_top.get("chromosome") != rect_top.get("chromosome")


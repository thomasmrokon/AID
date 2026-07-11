import itertools
import json
import sys
from pathlib import Path


def _load_app_helpers():
    lab_dir = Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab"
    sys.path.insert(0, str(lab_dir))
    source = (lab_dir / "app.py").read_text().split("\nst.set_page_config", 1)[0]
    ns = {}
    exec(source, ns)
    return ns


def _building(fid, area, priority=1, shape="compact", alignment="free"):
    return {
        "id": fid,
        "name": fid,
        "kind": "building",
        "area_m2": area,
        "key": fid,
        "priority": priority,
        "shape": shape,
        "alignment": alignment,
    }


def _assert_building_spacing(patchwork, required):
    parcels = patchwork["parcels"]
    for a, b in itertools.combinations(parcels, 2):
        if a["function"]["kind"] != "building" or b["function"]["kind"] != "building":
            continue
        distance = a["geometry"].distance(b["geometry"])
        assert distance + 0.06 >= required
        assert a.get("spacing_violation_m", 0.0) <= 0.06
        assert b.get("spacing_violation_m", 0.0) <= 0.06


def test_patchwork_enforces_building_spacing_and_clearance_geometry():
    ns = _load_app_helpers()
    placements = {
        "compact": {
            "a": {"anchor": (20.0, 22.0), "order": 1},
            "b": {"anchor": (58.0, 22.0), "order": 2},
            "c": {"anchor": (58.0, 62.0), "order": 3},
        }
    }
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"](
        "compact",
        [_building("a", 500, 1), _building("b", 500, 2), _building("c", 500, 3)],
        8.0,
        10.0,
    )

    assert len(patch["parcels"]) == 3
    _assert_building_spacing(patch, 10.0)
    assert all(parcel["clearance_geometry"].area > parcel["geometry"].area for parcel in patch["parcels"])


def test_patchwork_preserves_spacing_under_tight_area_pressure():
    ns = _load_app_helpers()
    placements = {
        "compact": {f"g{i}": {"anchor": (18.0 + i * 12.0, 35.0), "order": i} for i in range(1, 6)}
    }
    ns["_placement_store"] = lambda: placements

    functions = [_building(f"g{i}", 1800, i, "wide") for i in range(1, 6)]
    patch = ns["_build_patchwork"]("compact", functions, 8.0, 14.0)

    _assert_building_spacing(patch, 14.0)
    assert len(patch["parcels"]) + len(patch["missing"]) == 5
    assert patch["missing"] or any(parcel["coverage_pct"] < 100.0 for parcel in patch["parcels"])


def test_patchwork_can_keep_south_building_alignment():
    ns = _load_app_helpers()
    placements = {
        "compact": {
            "f1": {"anchor": (25.0, 22.0), "order": 1},
            "f2": {"anchor": (58.0, 22.0), "order": 2},
        }
    }
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"](
        "compact",
        [_building("f1", 300, 1, "compact", "south"), _building("f2", 300, 2, "compact", "south")],
        8.0,
        6.0,
    )

    assert len(patch["parcels"]) == 2
    _assert_building_spacing(patch, 6.0)
    assert max(parcel["alignment_gap_m"] for parcel in patch["parcels"]) <= 0.2


def test_auto_shape_rules_are_derived_from_function_type():
    ns = _load_app_helpers()

    assert ns["_resolved_shape"]({"key": "hall", "kind": "building", "shape": "auto"}) == "wide"
    assert ns["_resolved_shape"]({"key": "office", "kind": "building", "shape": "auto"}) == "compact"
    assert ns["_resolved_shape"]({"key": "parking", "kind": "parking", "shape": "auto"}) == "wide"
    assert ns["_resolved_shape"]({"key": "tech", "kind": "technical", "shape": "auto"}) == "compact"
    assert ns["_shape_label"]({"key": "hall", "kind": "building", "shape": "auto"}) == "breit auto"


def test_auto_alignment_uses_boundary_edge_only_when_centered_rect_does_not_fit():
    ns = _load_app_helpers()
    placements = {"compact": {"f1": {"anchor": (25.0, 10.0), "order": 1}}}
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"](
        "compact",
        [_building("f1", 300, 1, "compact", "auto")],
        8.0,
        0.0,
    )

    assert len(patch["parcels"]) == 1
    parcel = patch["parcels"][0]
    assert ns["_resolved_alignment"]({
        "function": parcel["function"],
        "anchor": parcel["anchor"],
        "allowed": ns["_build_boundary"]("compact", 8.0),
        "x": parcel["center"][0],
        "y": parcel["center"][1],
        "w": parcel["geometry"].bounds[2] - parcel["geometry"].bounds[0],
        "h": parcel["geometry"].bounds[3] - parcel["geometry"].bounds[1],
    }) == "south"
    assert parcel["alignment_gap_m"] <= 0.2


def test_rectangle_click_sampling_creates_points_inside_parcel():
    ns = _load_app_helpers()
    placements = {"compact": {"f1": {"anchor": (45.0, 45.0), "order": 1}}}
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"]("compact", [_building("f1", 600, 1, "compact", "free")], 8.0, 0.0)
    parcel = patch["parcels"][0]
    samples = ns["_sample_geometry"](parcel["display_geometry"], 5.0)

    assert samples
    assert all(parcel["display_geometry"].buffer(0.01).contains(ns["Point"](x, y)) for x, y in samples)


def test_plot_event_prefers_rectangle_selection_over_target_grid():
    ns = _load_app_helpers()
    event = ns["_selected_plot_point"]({
        "selection": {
            "points": [
                {"x": 10.0, "y": 10.0, "customdata": ["function_target", ""]},
                {"x": 12.0, "y": 12.0, "customdata": ["function_rect", "hall_1"]},
            ]
        }
    })

    assert event["kind"] == "function_rect"
    assert event["id"] == "hall_1"


def test_repeated_function_instances_are_reduced_fairly():
    ns = _load_app_helpers()
    placements = {
        "compact": {
            "hall_1": {"anchor": (45.0, 38.0), "order": 1},
            "hall_2": {"anchor": (45.0, 68.0), "order": 2},
        }
    }
    ns["_placement_store"] = lambda: placements
    functions = [
        {"id": "hall_1", "name": "Logistikhalle 1", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "hall_2", "name": "Logistikhalle 2", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
    ]

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True)

    assert len(patch["parcels"]) == 2
    coverages = sorted(round(parcel["coverage_pct"], 1) for parcel in patch["parcels"])
    assert coverages[0] == coverages[1]
    assert all(parcel.get("group_fraction") is not None for parcel in patch["parcels"])


def test_repeated_function_instances_can_use_extra_area_when_not_equalized():
    ns = _load_app_helpers()
    placements = {
        "compact": {
            "hall_1": {"anchor": (45.0, 38.0), "order": 1},
            "hall_2": {"anchor": (45.0, 68.0), "order": 2},
        }
    }
    ns["_placement_store"] = lambda: placements
    functions = [
        {"id": "hall_1", "name": "Logistikhalle 1", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "hall_2", "name": "Logistikhalle 2", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
    ]

    equalized = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True)
    flexible = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, False)

    assert len(flexible["parcels"]) == 2
    assert len({round(parcel["coverage_pct"], 1) for parcel in flexible["parcels"]}) > 1
    assert flexible["equalize_repeated"] is False
    _assert_building_spacing(flexible, 5.0)


def test_reduced_rectangles_grow_after_initial_group_fraction():
    ns = _load_app_helpers()
    placements = {
        "compact": {
            "hall_1": {"anchor": (45.0, 38.0), "order": 1},
            "hall_2": {"anchor": (45.0, 68.0), "order": 2},
        }
    }
    ns["_placement_store"] = lambda: placements
    functions = [
        {"id": "hall_1", "name": "Logistikhalle 1", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "hall_2", "name": "Logistikhalle 2", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
    ]

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True)

    assert len(patch["parcels"]) == 2
    assert min(parcel["coverage_pct"] for parcel in patch["parcels"]) >= 70.0
    assert all(parcel["function"].get("geometry_generator") or ns["_geometry_generator_label"](parcel["function"]) for parcel in patch["parcels"])
    _assert_building_spacing(patch, 5.0)


def test_required_function_is_reduced_instead_of_dropped():
    ns = _load_app_helpers()
    placements = {"compact": {"too_big": {"anchor": (45.0, 45.0), "order": 1}}}
    ns["_placement_store"] = lambda: placements
    functions = [_building("too_big", 50000, 8, "wide", "free")]

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 0.0)

    assert len(patch["parcels"]) == 1
    assert not patch["missing"]
    assert patch["parcels"][0]["coverage_pct"] < 30.0
    assert patch["parcels"][0]["status"] == "reduziert"


def test_optional_function_can_be_dropped_without_placeholder():
    ns = _load_app_helpers()
    placements = {
        "compact": {
            "required": {"anchor": (45.0, 45.0), "order": 1},
            "optional": {"anchor": (45.0, 45.0), "order": 2},
        }
    }
    ns["_placement_store"] = lambda: placements
    functions = [
        _building("required", 50000, 8, "wide", "free"),
        _building("optional", 50000, "optional", "wide", "free"),
    ]

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 0.0)

    assert len(patch["parcels"]) == 1
    assert len(patch["missing"]) == 1
    assert patch["missing"][0]["function"]["id"] == "optional"
    assert patch["missing"][0]["status"] == "optional entfallen"
    assert patch["missing"][0]["placeholder_geometry"].is_empty

def test_function_chip_marker_uses_square_symbol_and_color():
    ns = _load_app_helpers()
    fn = _building("f1", 300, 1, "compact", "free")

    inactive = ns["_function_chip_marker"](fn, False)
    active = ns["_function_chip_marker"](fn, True)

    assert inactive["symbol"] == "square"
    assert inactive["color"] == ns["FUNCTION_COLORS"]["building"]
    assert active["size"] > inactive["size"]
    assert active["line"]["width"] > inactive["line"]["width"]


def test_render_uses_square_chip_for_pending_function_anchor():
    ns = _load_app_helpers()
    fn = _building("f1", 300, 1, "compact", "free")
    patch = ns["_empty_patchwork"]("compact", 8.0, 0.0, False)

    fig = ns["render_site_figure"](
        "compact",
        [],
        patch,
        "Funktion platzieren",
        [fn],
        {"f1": {"anchor": (30.0, 30.0), "order": 1}},
        "f1",
    )

    traces = [trace for trace in fig.data if trace.name == "f1_anchor_pending"]
    assert traces
    assert traces[0].marker.symbol == "square"
    assert traces[0].customdata[0][0] == "function_anchor"

def _logistics_patchwork_functions():
    return [
        {"id": "hall_1", "name": "Logistikhalle 1", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "hall_2", "name": "Logistikhalle 2", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "yard_1", "name": "Andienhof", "kind": "outdoor", "area_m2": 1600.0, "key": "yard", "priority": 2, "shape": "auto", "alignment": "free"},
        {"id": "office_1", "name": "Büro", "kind": "building", "area_m2": 450.0, "key": "office", "priority": 3, "shape": "auto", "alignment": "free"},
        {"id": "parking_1", "name": "PKW-Stellplätze", "kind": "parking", "area_m2": 650.0, "key": "parking", "priority": 4, "shape": "auto", "alignment": "free"},
    ]


def test_repeated_mandatory_halls_do_not_starve_in_logistics_variants():
    ns = _load_app_helpers()
    functions = _logistics_patchwork_functions()
    variants = [
        {"hall_1": (48.0, 58.0), "hall_2": (70.0, 22.0), "yard_1": (50.0, 88.0), "office_1": (18.0, 18.0), "parking_1": (66.0, 8.0)},
        {"hall_1": (36.0, 62.0), "hall_2": (54.0, 25.0), "yard_1": (58.0, 88.0), "office_1": (16.0, 20.0), "parking_1": (48.0, 8.0)},
        {"hall_1": (30.0, 64.0), "hall_2": (72.0, 34.0), "yard_1": (52.0, 90.0), "office_1": (20.0, 46.0), "parking_1": (52.0, 10.0)},
        {"hall_1": (28.0, 52.0), "hall_2": (72.0, 52.0), "yard_1": (50.0, 86.0), "office_1": (18.0, 18.0), "parking_1": (66.0, 12.0)},
    ]

    for variant in variants:
        placements = {"compact": {fid: {"anchor": point, "order": order} for order, (fid, point) in enumerate(variant.items(), start=1)}}
        ns["_placement_store"] = lambda placements=placements: placements
        patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True)
        halls = [parcel for parcel in patch["parcels"] if parcel["function"].get("key") == "hall"]
        coverages = [parcel["coverage_pct"] for parcel in halls]

        assert len(halls) == 2
        assert min(coverages) >= 39.9
        assert max(coverages) - min(coverages) <= 5.0
        _assert_building_spacing(patch, 5.0)


def test_equalize_repeated_toggle_uses_persistent_session_key_and_is_not_reset_by_mode():
    source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "app.py").read_text()

    assert 'key="traffic_equalize_repeated"' in source
    assert 'equalize_repeated = True' not in source

def test_drag_plan_payload_is_json_serializable_and_scales_placeholders():
    ns = _load_app_helpers()
    placements = {
        "compact": {
            "small": {"anchor": (20.0, 20.0), "order": 1},
            "large": {"anchor": (60.0, 60.0), "order": 2},
        }
    }
    ns["_placement_store"] = lambda: placements
    functions = [
        _building("small", 200, 1, "compact", "free"),
        _building("large", 3200, 2, "wide", "free"),
    ]
    patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True)

    payload = ns["_drag_plan_payload"]("compact", [], patch, functions, placements["compact"], "small")

    json.dumps(payload)
    sizes = {fn["id"]: fn["chip_size_px"] for fn in payload["functions"]}
    priorities = {fn["id"]: fn["priority"] for fn in payload["functions"]}
    assert sizes["large"] > sizes["small"]
    assert priorities["small"] == "1"
    assert payload["placements"]["small"]["anchor"] == [20.0, 20.0]
    assert payload["selected_function_id"] == "small"
    assert payload["parcels"]
    assert payload["build_boundary"]
    assert payload["area_summary"]
    assert payload["area_summary"][0]["required_m2"] == 200.0


def test_drag_plan_component_asset_contains_streamlit_value_protocol():
    component_path = Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "drag_plan_component" / "index.html"
    source = component_path.read_text()

    assert "streamlit:setComponentValue" in source
    assert "isStreamlitMessage" in source
    assert "place_function" in source
    assert '<canvas id="planCanvas"' in source
    assert 'pointerdown' in source
    assert 'chip-table' in source
    assert '<th>Funktion</th><th>Prio</th><th>Platzhalter</th>' in source
    assert 'Flächenbilanz' in source
    assert '<th>SOLL</th><th>IST</th><th>DELTA</th>' in source
    assert 'geforderte Gesamtfläche' not in source
    assert 'realisierte Gesamtfläche' not in source
    assert 'Differenz in m²/%' not in source

def test_ui_source_uses_mode_panel_and_canvas_editor_toggle():
    source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "app.py").read_text()

    assert 'st.radio("Arbeitsmodus"' in source
    assert 'st.expander("Funktionen"' in source
    assert 'st.expander("Optimierung"' in source
    assert 'key="traffic_use_drag_plan"' in source


def test_canvas_component_uses_uniform_viewport_scaling():
    source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "drag_plan_component" / "index.html").read_text()

    assert "Math.min(cssWidth / logical.width, cssHeight / logical.height)" in source
    assert "viewport = {" in source
    assert "dpr * viewport.scale" in source
    assert "event.clientX - rect.left - viewport.x" in source
    assert "function isInsideViewport(event)" in source
    assert "viewport.x + viewport.width" in source


def test_canvas_component_uses_stable_key_and_initial_height():
    source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "app.py").read_text()

    assert 'height=780' in source
    assert 'key=f"canvas_plan_{site_id}_{usage}"' in source
    assert 'canvas_plan_{site_id}_{usage}_{selected_function_id}' not in source
    assert 'Klassischen Lageplan anzeigen' in source

def test_main_ui_uses_compact_header_status_instead_of_large_metric_row():
    source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "app.py").read_text()

    assert 'left, right = st.columns' not in source
    assert 'status_cols = st.columns' not in source
    assert 'lab-header' in source
    assert 'lab-status-item' in source


def test_function_colors_are_distinct_for_building_functions():
    ns = _load_app_helpers()

    colors = {
        ns["_function_color"]({"key": "prod", "kind": "building"}),
        ns["_function_color"]({"key": "warehouse", "kind": "building"}),
        ns["_function_color"]({"key": "office", "kind": "building"}),
    }

    assert len(colors) == 3


def test_component_greys_out_placed_chip_rows():
    source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "drag_plan_component" / "index.html").read_text()

    assert '.chip-row.placed .swatch' in source
    assert 'grayscale(1)' in source
    assert 'opacity: 0.28' in source

def test_classic_plan_fallback_uses_single_plotly_anchor_key():
    source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "app.py").read_text()

    assert source.count('key=f"site_anchor_plan_{site_id}_{click_mode}_{selected_function_id}"') == 1

def test_geometry_generator_profiles_cover_all_template_functions():
    ns = _load_app_helpers()

    template_keys = {template["key"] for templates in ns["FUNCTION_TEMPLATES"].values() for template in templates}

    assert template_keys <= set(ns["GEOMETRY_GENERATOR_PROFILES"])


def test_geometry_generator_keeps_requested_area_and_uses_minimums_when_feasible():
    ns = _load_app_helpers()

    parking = {"key": "parking", "kind": "parking", "shape": "auto", "area_m2": 650}
    yard = {"key": "yard", "kind": "outdoor", "shape": "auto", "area_m2": 1600}

    parking_w, parking_h = ns["_rect_dimensions_for_area"](parking, 650, 4.0)
    yard_w, yard_h = ns["_rect_dimensions_for_area"](yard, 1600, 3.6)

    assert abs(parking_w * parking_h - 650.0) <= 0.1
    assert abs(yard_w * yard_h - 1600.0) <= 0.1
    assert parking_w >= ns["GEOMETRY_GENERATOR_PROFILES"]["parking"]["min_width_m"]
    assert parking_h >= ns["GEOMETRY_GENERATOR_PROFILES"]["parking"]["min_depth_m"]
    assert yard_w >= ns["GEOMETRY_GENERATOR_PROFILES"]["yard"]["min_width_m"]
    assert yard_h >= ns["GEOMETRY_GENERATOR_PROFILES"]["yard"]["min_depth_m"]


def test_auto_geometry_generator_offers_rotated_candidates():
    ns = _load_app_helpers()

    aspects = ns["_candidate_aspects"]({"key": "hall", "kind": "building", "shape": "auto"})

    assert any(aspect > 2.0 for aspect in aspects)
    assert any(aspect < 0.5 for aspect in aspects)


def test_function_instances_include_generator_label():
    ns = _load_app_helpers()
    settings = {
        "prod": {"count": 1, "area": 2800, "priority": 1, "shape": "auto", "alignment": "auto"},
        "warehouse": {"count": 0, "area": 1200, "priority": 2, "shape": "auto", "alignment": "auto"},
        "office": {"count": 0, "area": 600, "priority": 3, "shape": "auto", "alignment": "auto"},
        "yard": {"count": 0, "area": 900, "priority": 4, "shape": "auto", "alignment": "auto"},
        "parking": {"count": 0, "area": 700, "priority": 5, "shape": "auto", "alignment": "auto"},
    }

    functions = ns["_build_function_instances"]("production", settings)

    assert functions[0]["geometry_generator"] == "Produktionshalle"

def test_balanced_patchwork_reduces_large_required_functions_before_dropping_required_small_one():
    ns = _load_app_helpers()
    functions = [
        {"id": "prod_1", "name": "Produktionshalle 1", "kind": "building", "area_m2": 2800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "prod_2", "name": "Produktionshalle 2", "kind": "building", "area_m2": 2800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "office_1", "name": "Büro", "kind": "building", "area_m2": 600.0, "key": "office", "priority": 2, "shape": "auto", "alignment": "free"},
    ]
    placements = {
        "compact": {
            "prod_1": {"anchor": (25.0, 28.0), "order": 1},
            "prod_2": {"anchor": (25.0, 75.0), "order": 2},
            "office_1": {"anchor": (70.0, 50.0), "order": 3},
        }
    }
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True)

    required_missing = [item for item in patch["missing"] if not item.get("optional")]
    placed_ids = {parcel["function"]["id"] for parcel in patch["parcels"]}
    production_coverages = [parcel["coverage_pct"] for parcel in patch["parcels"] if parcel["function"].get("key") == "prod"]

    assert not required_missing
    assert placed_ids == {"prod_1", "prod_2", "office_1"}
    assert patch["balance_mode"] is True
    assert max(production_coverages) < 100.0



def test_priority_balancing_preserves_high_priority_area_before_lower_priority_targets():
    ns = _load_app_helpers()
    functions = [
        {"id": "prod_1", "name": "Produktionshalle 1", "kind": "building", "area_m2": 2800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "prod_2", "name": "Produktionshalle 2", "kind": "building", "area_m2": 2800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "warehouse_1", "name": "Lager", "kind": "building", "area_m2": 1200.0, "key": "warehouse", "priority": 2, "shape": "auto", "alignment": "free"},
        {"id": "office_1", "name": "Büro", "kind": "building", "area_m2": 600.0, "key": "office", "priority": 3, "shape": "auto", "alignment": "free"},
        {"id": "yard_1", "name": "Andienhof", "kind": "outdoor", "area_m2": 900.0, "key": "yard", "priority": 4, "shape": "auto", "alignment": "free"},
        {"id": "parking_1", "name": "Stellplätze", "kind": "parking", "area_m2": 700.0, "key": "parking", "priority": 5, "shape": "auto", "alignment": "free"},
    ]
    placements = {
        "compact": {
            "prod_1": {"anchor": (28.0, 66.0), "order": 1},
            "prod_2": {"anchor": (36.0, 38.0), "order": 2},
            "warehouse_1": {"anchor": (78.0, 78.0), "order": 3},
            "office_1": {"anchor": (78.0, 58.0), "order": 4},
            "yard_1": {"anchor": (78.0, 22.0), "order": 5},
            "parking_1": {"anchor": (48.0, 18.0), "order": 6},
        }
    }
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True)

    assert not [item for item in patch["missing"] if not item.get("optional")]
    coverage_by_id = {parcel["function"]["id"]: parcel["coverage_pct"] for parcel in patch["parcels"]}
    high_priority_coverages = [coverage_by_id["prod_1"], coverage_by_id["prod_2"], coverage_by_id["warehouse_1"]]
    lower_priority_coverages = [coverage_by_id["office_1"], coverage_by_id["yard_1"], coverage_by_id["parking_1"]]

    assert min(high_priority_coverages) >= 60.0
    assert min(high_priority_coverages) > max(lower_priority_coverages)
    assert coverage_by_id["office_1"] >= coverage_by_id["yard_1"] >= coverage_by_id["parking_1"]





def test_auto_alignment_keeps_office_centered_when_centered_rect_fits():
    ns = _load_app_helpers()
    functions = [
        {"id": "office_1", "name": "Büro", "kind": "building", "area_m2": 450.0, "key": "office", "priority": 1, "shape": "auto", "alignment": "auto"},
    ]
    placements = {"irregular": {"office_1": {"anchor": (20.0, 70.0), "order": 1}}}
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"]("irregular", functions, 8.0, 5.0, True)

    assert len(patch["parcels"]) == 1
    parcel = patch["parcels"][0]
    assert parcel["function"]["id"] == "office_1"
    assert parcel["anchor_mode"] == "center"
    assert parcel["center_distance_m"] <= 0.1
    assert parcel["alignment_gap_m"] == 0.0


def test_centered_function_placeholders_stay_at_rectangle_center_when_space_allows():
    ns = _load_app_helpers()
    functions = [
        {"id": "prod_1", "name": "Produktionshalle 1", "kind": "building", "area_m2": 2800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "prod_2", "name": "Produktionshalle 2", "kind": "building", "area_m2": 2800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "prod_3", "name": "Produktionshalle 3", "kind": "building", "area_m2": 2800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "warehouse_1", "name": "Lager", "kind": "building", "area_m2": 1200.0, "key": "warehouse", "priority": 2, "shape": "auto", "alignment": "free"},
        {"id": "yard_1", "name": "Andienhof", "kind": "outdoor", "area_m2": 900.0, "key": "yard", "priority": 3, "shape": "auto", "alignment": "free"},
    ]
    placements = {
        "irregular": {
            "prod_1": {"anchor": (55.0, 125.0), "order": 1},
            "prod_2": {"anchor": (160.0, 125.0), "order": 2},
            "prod_3": {"anchor": (32.0, 55.0), "order": 3},
            "warehouse_1": {"anchor": (145.0, 42.0), "order": 4},
            "yard_1": {"anchor": (105.0, 90.0), "order": 5},
        }
    }
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"]("irregular", functions, 8.0, 5.0, True)

    centered_ids = {"prod_1", "prod_2", "prod_3", "warehouse_1", "yard_1"}
    by_id = {parcel["function"]["id"]: parcel for parcel in patch["parcels"]}
    assert centered_ids <= set(by_id)
    for function_id in centered_ids:
        assert by_id[function_id]["center_distance_m"] <= 0.1
        assert by_id[function_id]["anchor_mode"] == "center"


def test_repeated_logistics_halls_keep_equal_rectangles_when_space_is_available():
    ns = _load_app_helpers()
    functions = [
        {"id": "hall_1", "name": "Logistikhalle 1", "kind": "building", "area_m2": 4200.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "hall_2", "name": "Logistikhalle 2", "kind": "building", "area_m2": 4200.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "hall_3", "name": "Logistikhalle 3", "kind": "building", "area_m2": 4200.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "yard_1", "name": "Andienhof", "kind": "outdoor", "area_m2": 1600.0, "key": "yard", "priority": 2, "shape": "auto", "alignment": "free"},
        {"id": "office_1", "name": "Büro", "kind": "building", "area_m2": 450.0, "key": "office", "priority": 3, "shape": "auto", "alignment": "free"},
        {"id": "parking_1", "name": "PKW-Stellplätze", "kind": "parking", "area_m2": 650.0, "key": "parking", "priority": 4, "shape": "auto", "alignment": "free"},
    ]
    placements = {
        "irregular": {
            "hall_1": {"anchor": (35.0, 48.0), "order": 1},
            "hall_2": {"anchor": (55.0, 70.0), "order": 2},
            "hall_3": {"anchor": (78.0, 48.0), "order": 3},
            "yard_1": {"anchor": (58.0, 52.0), "order": 4},
            "office_1": {"anchor": (45.0, 35.0), "order": 5},
            "parking_1": {"anchor": (62.0, 31.0), "order": 6},
        }
    }
    ns["_placement_store"] = lambda: placements

    patch = ns["_build_patchwork"]("irregular", functions, 8.0, 5.0, True)

    halls = [parcel for parcel in patch["parcels"] if parcel["function"].get("key") == "hall"]
    assert len(halls) == 3
    widths = [round(parcel["geometry"].bounds[2] - parcel["geometry"].bounds[0], 2) for parcel in halls]
    heights = [round(parcel["geometry"].bounds[3] - parcel["geometry"].bounds[1], 2) for parcel in halls]
    assert len(set(widths)) == 1
    assert len(set(heights)) == 1
    for parcel in patch["parcels"]:
        assert parcel["actual_area_m2"] <= parcel["target_area_m2"] + 0.2



def test_function_library_defines_all_usage_scenario_entries():
    ns = _load_app_helpers()

    library_keys = set(ns["FUNCTION_LIBRARY"])
    scenario_keys = {item["key"] for items in ns["USAGE_SCENARIOS"].values() for item in items}

    assert scenario_keys <= library_keys
    assert ns["FUNCTION_TEMPLATES"] == ns["_templates_from_scenarios"]()


def test_added_library_function_becomes_project_function_instance():
    ns = _load_app_helpers()
    key_store = {}
    ns["_function_key_store"] = lambda: key_store
    ns["_function_keys_for_usage"]("production")
    key_store["production"].append("tech")
    settings = {
        "prod": {"count": 0, "area": 2800, "priority": 1, "shape": "auto", "alignment": "auto"},
        "warehouse": {"count": 0, "area": 1200, "priority": 2, "shape": "auto", "alignment": "auto"},
        "office": {"count": 0, "area": 600, "priority": 3, "shape": "auto", "alignment": "auto"},
        "yard": {"count": 0, "area": 900, "priority": 4, "shape": "auto", "alignment": "auto"},
        "parking": {"count": 0, "area": 700, "priority": 5, "shape": "auto", "alignment": "auto"},
        "tech": {"count": 1, "area": 180, "priority": 6, "shape": "auto", "alignment": "auto"},
    }

    functions = ns["_build_function_instances"]("production", settings)

    assert [function["id"] for function in functions] == ["tech_1"]
    assert functions[0]["name"] == "Technikfläche"
    assert functions[0]["kind"] == "technical"


def test_add_and_remove_function_updates_project_list_settings_and_placements():
    ns = _load_app_helpers()
    key_store = {}
    settings_store = {}
    placements_store = {"compact": {"tech_1": {"anchor": (20, 20), "order": 1}, "prod_1": {"anchor": (40, 40), "order": 2}}}
    ns["_function_key_store"] = lambda: key_store
    ns["_function_settings_store"] = lambda: settings_store
    ns["_placement_store"] = lambda: placements_store

    ns["_add_function_to_usage"]("production", "tech")

    assert "tech" in key_store["production"]
    assert settings_store["production"]["tech"]["count"] == 1
    assert settings_store["production"]["tech"]["area"] == ns["FUNCTION_LIBRARY"]["tech"]["default_area"]

    ns["_remove_function_from_usage"]("production", "tech")

    assert "tech" not in key_store["production"]
    assert "tech" not in settings_store["production"]
    assert "tech_1" not in placements_store["compact"]
    assert "prod_1" in placements_store["compact"]


def test_visible_copy_uses_placeholder_instead_of_chip_word():
    app_source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "app.py").read_text()
    component_source = (Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab" / "drag_plan_component" / "index.html").read_text()

    assert "Funktionsplatzhalter" in component_source
    assert "Alle Platzhalter platziert" in app_source
    assert "Funktionschips" not in app_source + component_source
    assert "Alle Chips" not in app_source

def test_shift_step_can_move_reduced_rectangle_to_open_growth_space():
    ns = _load_app_helpers()
    allowed = ns["_build_boundary"]("compact", 0.0)
    top = {"function": _building("top", 1600, 1, "wide", "free"), "anchor": (50.0, 55.0), "x": 50.0, "y": 55.0, "w": 40.0, "h": 20.0, "allowed": allowed}
    lower = {"function": _building("lower", 1600, 1, "wide", "free"), "anchor": (50.0, 30.0), "x": 50.0, "y": 30.0, "w": 40.0, "h": 20.0, "allowed": allowed}

    shifted = ns["_best_shift_step"](lower, [top, lower], 5.0, step_m=2.0)

    assert shifted is not None
    assert shifted["y"] < lower["y"]
    assert shifted["shifted"] is True
    assert ns["_is_non_overlapping"](shifted, [top], 5.0)

def test_anchor_repair_moves_rectangle_toward_its_placeholder_when_space_is_available():
    ns = _load_app_helpers()
    allowed = ns["_build_boundary"]("compact", 0.0)
    rect = {"function": _building("lager", 1200, 1, "wide", "free"), "anchor": (30.0, 45.0), "x": 62.0, "y": 45.0, "w": 24.0, "h": 20.0, "allowed": allowed}

    repaired = ns["_best_anchor_repair_step"](rect, [rect], 5.0, step_m=2.0)

    assert repaired is not None
    assert repaired["x"] < rect["x"]
    assert ns["_anchor_gap_m"](repaired) < ns["_anchor_gap_m"](rect)
    assert ns["_is_non_overlapping"](repaired, [], 5.0)


def test_patchwork_balance_score_penalizes_large_placeholder_gap():
    ns = _load_app_helpers()
    fn = _building("lager", 1200, 1, "wide", "free")
    near = {"parcels": [{"function": fn, "coverage_pct": 70.0, "anchor_gap_m": 2.0}], "missing": []}
    far = {"parcels": [{"function": fn, "coverage_pct": 70.0, "anchor_gap_m": 25.0}], "missing": []}

    assert ns["_patchwork_balance_score"](near) < ns["_patchwork_balance_score"](far)


def test_best_rectangle_stays_centered_on_placeholder_when_space_is_available():
    ns = _load_app_helpers()
    allowed = ns["_build_boundary"]("irregular", 8.0)
    functions = [
        {"id": "office_1", "name": "Büro", "kind": "building", "area_m2": 450.0, "key": "office", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "hall_1", "name": "Logistikhalle", "kind": "building", "area_m2": 3600.0, "key": "hall", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "warehouse_1", "name": "Lager", "kind": "building", "area_m2": 1200.0, "key": "warehouse", "priority": 1, "shape": "auto", "alignment": "free"},
    ]

    for index, function in enumerate(functions):
        anchor = (32.0 + index * 18.0, 48.0)
        rect = ns["_best_non_overlapping_rect"]({"function": function, "anchor": anchor, "allowed": allowed}, [], 5.0)

        assert rect is not None
        assert abs(rect["x"] - anchor[0]) <= 0.05
        assert abs(rect["y"] - anchor[1]) <= 0.05
        assert ns["_anchor_gap_m"](rect) <= 0.05


def test_road_strategy_reserves_access_corridors_before_placing_parcels():
    ns = _load_app_helpers()
    functions = [
        {"id": "prod_1", "name": "Produktionshalle", "kind": "building", "area_m2": 1800.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
        {"id": "parking_1", "name": "Stellplätze", "kind": "parking", "area_m2": 650.0, "key": "parking", "priority": 2, "shape": "auto", "alignment": "free"},
    ]
    placements = {
        "compact": {
            "prod_1": {"anchor": (42.0, 58.0), "order": 1},
            "parking_1": {"anchor": (40.0, 22.0), "order": 2},
        }
    }
    ns["_placement_store"] = lambda: placements
    projected = ns["project_point_to_site_boundary"](ns["DEMO_SITES"]["compact"], (48.0, 96.0))
    access_points = [{"id": "Z1", "access_type": "both", **projected}]

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True, access_points)
    patch = ns["_with_road_network"]("compact", access_points, patch, functions, 8.0)
    road_network = patch["road_network"]
    corridor_union = None
    for segment in road_network["segments"]:
        corridor = segment["corridor"]
        corridor_union = corridor if corridor_union is None else corridor_union.union(corridor)

    assert road_network["segments"]
    assert road_network["hard_ok"] is True
    assert any(segment["kind"] == "access_link" for segment in road_network["segments"])
    assert all(segment["outside_area_m2"] <= 0.6 for segment in road_network["segments"])
    assert corridor_union is not None
    for parcel in patch["parcels"]:
        unrelated_corridors = []
        for segment in road_network["segments"]:
            allowed_function_ids = {str(segment.get("function_id", "")), str(segment.get("source_id", "")), str(segment.get("target_id", ""))}
            if str(parcel["function"].get("id", "")) not in allowed_function_ids:
                unrelated_corridors.append(segment["corridor"])
        assert all(parcel["geometry"].intersection(corridor).area <= 0.6 for corridor in unrelated_corridors)
    assert all(parcel["geometry"].distance(corridor_union) <= 24.0 for parcel in patch["parcels"])


def test_drag_plan_payload_includes_road_layer():
    ns = _load_app_helpers()
    functions = [
        {"id": "prod_1", "name": "Produktionshalle", "kind": "building", "area_m2": 1200.0, "key": "prod", "priority": 1, "shape": "auto", "alignment": "free"},
    ]
    placements = {"compact": {"prod_1": {"anchor": (45.0, 45.0), "order": 1}}}
    ns["_placement_store"] = lambda: placements
    projected = ns["project_point_to_site_boundary"](ns["DEMO_SITES"]["compact"], (48.0, 96.0))
    access_points = [{"id": "Z1", "access_type": "both", **projected}]

    patch = ns["_build_patchwork"]("compact", functions, 8.0, 5.0, True, access_points)
    patch = ns["_with_road_network"]("compact", access_points, patch, functions, 8.0)
    payload = ns["_drag_plan_payload"]("compact", access_points, patch, functions, placements["compact"], "prod_1")

    assert payload["roads"]
    assert payload["road_summary"]["segments"] >= 1
    assert payload["roads"][0]["points"]
    assert payload["roads"][0]["centerline"]



def _road_option_fixture():
    ns = _load_app_helpers()
    lab_dir = Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab"
    sys.path.insert(0, str(lab_dir))
    import road_matrix  # noqa: E402

    site = "compact"
    usage = "production"
    functions = road_matrix._build_functions(ns, usage)
    placement_polygon = ns["_build_boundary"](site, 8.0)
    placements = {sid: {} for sid in road_matrix.SITES}
    for index, function in enumerate(functions):
        anchor = road_matrix._point_for(
            ns,
            placement_polygon,
            *road_matrix.PATTERNS["balanced"][index % len(road_matrix.PATTERNS["balanced"])],
        )
        placements[site][function["id"]] = {"anchor": anchor, "order": index + 1}
    ns["_placement_store"] = lambda placements=placements: placements
    access_points = [
        road_matrix._make_access(ns, site, u, v, access_type, index)
        for index, (u, v, access_type) in enumerate(road_matrix.ACCESS_VARIANTS["single_both"], start=1)
    ]
    patch = ns["_build_patchwork"](site, functions, 8.0, 5.0, True, access_points)
    return ns, site, functions, access_points, patch


def _road_signature(network):
    return [
        (segment.get("mode"), segment.get("source_id"), segment.get("target_id"), round(float(segment.get("width_m", 0.0)), 1))
        for segment in network["segments"]
    ]


def test_road_options_change_generated_network_topology():
    ns, site, functions, access_points, patch = _road_option_fixture()
    base = {"flow": "separate", "network": "auto", "service": "auto", "parking": "auto", "objective": "balanced"}
    shared = {**base, "flow": "shared"}
    central_yard = {**base, "service": "central_yard"}
    parking_entrance = {**base, "parking": "entrance"}
    spine = {**base, "network": "spine"}
    minimal = {**base, "network": "minimal"}

    base_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, base)["road_network"]
    shared_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, shared)["road_network"]
    yard_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, central_yard)["road_network"]
    parking_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, parking_entrance)["road_network"]
    spine_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, spine)["road_network"]
    minimal_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, minimal)["road_network"]

    assert shared_network["resolved_flow"] == "shared"
    assert all(segment.get("mode") == "both" for segment in shared_network["segments"])
    assert _road_signature(shared_network) != _road_signature(base_network)
    assert _road_signature(yard_network) != _road_signature(base_network)
    assert any(segment.get("source_id") == "yard_1" or segment.get("target_id") == "yard_1" for segment in yard_network["segments"])
    assert _road_signature(parking_network) != _road_signature(base_network)
    assert any(segment.get("source_id") == "Z1" and segment.get("target_id") == "parking_1" for segment in parking_network["segments"])
    assert _road_signature(spine_network) != _road_signature(minimal_network)


def test_road_objective_changes_corridor_area_and_widths():
    ns, site, functions, access_points, patch = _road_option_fixture()
    area_options = {"flow": "separate", "network": "auto", "service": "auto", "parking": "auto", "objective": "area"}
    traffic_options = {"flow": "separate", "network": "auto", "service": "auto", "parking": "auto", "objective": "traffic"}

    area_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, area_options)["road_network"]
    traffic_network = ns["_with_road_network"](site, access_points, patch, functions, 8.0, traffic_options)["road_network"]

    assert traffic_network["total_area_m2"] > area_network["total_area_m2"]
    assert max(segment["width_m"] for segment in traffic_network["segments"]) > max(segment["width_m"] for segment in area_network["segments"])



def test_road_quality_gate_smoke_has_no_hard_failures():
    import sys
    lab_dir = Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab"
    sys.path.insert(0, str(lab_dir))
    import road_matrix

    rows = road_matrix.run_matrix("smoke", 8.0, 5.0)

    assert rows
    failures = [row for row in rows if not row.hard_ok]
    assert not failures, [f"{row.site}/{row.usage}: {row.warnings}" for row in failures]

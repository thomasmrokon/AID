import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1] / "side_projects" / "traffic_trassen_lab"
sys.path.insert(0, str(LAB_DIR))

from shapely.geometry import LineString, Polygon  # noqa: E402

from engine import DEMO_SITES, _target_zones, plan_traffic, validate_vehicle_network  # noqa: E402


def test_lab_returns_candidates_and_svg():
    plan = plan_traffic("long", profile="logistik", preferred_strategy="front_spine")
    assert plan["candidates"]
    assert plan["selected"]["strategy"]
    assert plan["svg"].startswith("<svg")
    assert "<polygon" in plan["svg"]


def test_lab_datacenter_prefers_redundant_loop_when_requested():
    plan = plan_traffic("irregular", profile="datacenter", preferred_strategy="loop")
    assert plan["selected"]["strategy"] == "loop"
    assert plan["selected"]["metrics"]["connectivity"] >= 0.75


def test_lab_weights_can_change_candidate_scores():
    road = plan_traffic("long", profile="logistik", preferred_strategy="loop", weights={"road_efficiency": 2.0, "rectangularity": 0.2, "connectivity": 0.8, "parcel_split": 0.5})
    rect = plan_traffic("long", profile="logistik", preferred_strategy="loop", weights={"road_efficiency": 0.2, "rectangularity": 2.0, "connectivity": 1.0, "parcel_split": 1.5})
    assert road["selected"]["metrics"]["score"] != rect["selected"]["metrics"]["score"] or road["selected"]["strategy"] != rect["selected"]["strategy"]

def test_briefing_derives_explainable_algorithm_inputs():
    from engine import derive_briefing

    briefing = derive_briefing({
        "usage": "datacenter",
        "delivery": "high",
        "separation": "strict",
        "redundancy": "required",
        "priority": "robust_access",
    })

    assert briefing["profile"] == "datacenter"
    assert briefing["preferred_strategy"] == "loop"
    assert briefing["required_redundancy"] is True
    assert briefing["weights"]["connectivity"] >= 1.6
    assert len(briefing["explanations"]) >= 5
    assert all(row.get("Wirkung im Algorithmus") for row in briefing["explanations"])

def test_lab_returns_phase_log_validation_and_parcels():
    plan = plan_traffic("long", profile="logistik", preferred_strategy="front_spine")
    selected = plan["selected"]

    assert len(plan.get("phase_log") or []) == 5
    assert selected.get("validation", {}).get("checks")
    assert selected.get("parcels")
    assert all(parcel["area_m2"] > 0 for parcel in selected["parcels"])


def test_lab_utilities_are_routed_via_network_not_single_diagonal():
    plan = plan_traffic("long", profile="logistik", preferred_strategy="front_spine")
    selected = plan["selected"]

    assert selected["utility_lines"]
    assert len(selected["utility_lines"]) >= len(selected["road_lines"])
    assert selected["utilities"]["connector_length_m"] >= 0


def test_lab_selected_parcels_have_access_to_road():
    plan = plan_traffic("irregular", profile="logistik", preferred_strategy="front_spine")
    parcels = plan["selected"].get("parcels") or []

    assert parcels
    assert all(parcel["access_ok"] for parcel in parcels)



def test_lab_validation_uses_unclipped_road_geometry():
    site = DEMO_SITES["compact"]
    targets = _target_zones(site, "logistik", lkw_per_day=80, employees=180, setback=8.0)
    road_width = targets["road_width"]
    target_y = targets["zones"][0]["point"][1]
    road_line = LineString([(-42.0, target_y), (34.0, target_y)])
    raw_road = road_line.buffer(road_width / 2, cap_style=2, join_style=2)
    clipped_road = raw_road.intersection(Polygon(site.polygon))
    network = {
        "strategy": "front_spine",
        "road_polygon_geom": clipped_road,
        "raw_road_polygon_geom": raw_road,
    }

    validation = validate_vehicle_network(network, site, targets, redundant=False)
    geometry_check = next(row for row in validation["checks"] if row["Kriterium"] == "Straßenfläche liegt im Grundstück")

    assert validation["road_outside_area_m2"] > 1.0
    assert geometry_check["Status"] == "fehlt"
    assert validation["hard_ok"] is False


def test_lab_default_compact_prefers_front_spine_over_short_stich():
    from engine import derive_briefing

    briefing = derive_briefing({
        "usage": "production",
        "delivery": "medium",
        "separation": "separate_lkw_pkw",
        "redundancy": "none",
        "priority": "balanced",
    })
    plan = plan_traffic(
        "compact",
        profile=briefing["profile"],
        preferred_strategy=briefing["preferred_strategy"],
        lkw_per_day=briefing["lkw_per_day"],
        employees=briefing["employees"],
        setback=briefing["setback"],
        weights=briefing["weights"],
        required_redundancy=briefing["required_redundancy"],
    )

    assert plan["selected"]["strategy"] == "front_spine"


def test_lab_utility_lines_are_orthogonal():
    plan = plan_traffic("compact", profile="produktion", preferred_strategy="front_spine")

    for line in plan["selected"]["utility_lines"]:
        for (x0, y0), (x1, y1) in zip(line, line[1:]):
            assert x0 == x1 or y0 == y1


def test_lab_projects_click_to_site_boundary():
    from shapely.geometry import Point, Polygon
    from engine import project_point_to_site_boundary

    site = DEMO_SITES["compact"]
    projected = project_point_to_site_boundary(site, (48.0, 45.0))
    boundary = Polygon(site.polygon).boundary

    assert boundary.distance(Point(projected["point"])) < 0.01
    assert projected["distance_to_edge_m"] > 0
    assert projected["segment"]

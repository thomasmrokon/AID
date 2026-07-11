from app.agents.masterplan import masterplan_agent
from app.tools.site import get_demo_site
from app.tools.svg_masterplan import masterplan_to_svg


def test_masterplan_to_svg_contains_vector_geometry():
    site = get_demo_site()
    result = masterplan_agent(site, grz_ziel=0.55)
    svg = masterplan_to_svg(result["masterplan"])

    assert svg.startswith("<svg")
    assert "<polygon" in svg
    assert "<rect" in svg
    assert "<text" in svg
    assert "viewBox" in svg
    assert "<image" not in svg

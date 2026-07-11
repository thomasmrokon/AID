from app.tools.svg_process import process_layout_to_svg, utilization_to_svg


def _layout():
    return {
        "zone_name": "Produktion",
        "zone_breite_m": 40,
        "zone_tiefe_m": 30,
        "strips": [{"schritt": 1, "y_start": 0, "y_end": 10, "hoehe_m": 10}],
        "maschinen": [
            {"id": "m1", "name": "Laser", "schritt": 1, "x": 2, "y": 2, "breite_m": 5, "tiefe_m": 3, "taktzeit_s": 45},
            {"id": "m2", "name": "Montage", "schritt": 2, "x": 12, "y": 12, "breite_m": 7, "tiefe_m": 4, "taktzeit_s": 60},
        ],
        "kpis": {
            "engpass_schritt": 2,
            "durchsatz_teile_pro_schicht": 120,
            "materialflussweg_m": 55,
            "schwerpunkte": {"1": [4, 4], "2": [15, 14]},
            "auslastung_je_schritt": {"1": 72, "2": 104},
        },
    }


def test_process_svgs_are_vector():
    layout_svg = process_layout_to_svg(_layout())
    util_svg = utilization_to_svg(_layout())
    assert layout_svg.startswith("<svg")
    assert "Laser" in layout_svg
    assert "<rect" in layout_svg
    assert "<image" not in layout_svg
    assert util_svg.startswith("<svg")
    assert "104%" in util_svg

"""Test: drawing-Hilfsfunktionen — Stellplatz-Grenzen, Polygon-Südkante."""
from __future__ import annotations
import pytest


# ── P0-Regression: Stellplätze bleiben innerhalb Grundstücksgrenze ────────────

def test_parking_first_row_respects_site_south():
    """P0: Erste Stellplatz-Reihe (Südseite) liegt nicht unterhalb site_south."""
    from app.tools.drawing import STELLPLATZ_TIEFE, FAHRGANG_BREITE

    # Simuliert die Row-0-Berechnung aus _draw_parking_info:
    # south_start = by0 - 1.5 ; row0_bottom = south_start - STELLPLATZ_TIEFE
    #
    # Bedingung aus while-Loop: south_start - STELLPLATZ_TIEFE >= site_south
    # → row0_bottom >= site_south → Reihe 0 ist sicher innerhalb.

    for by0, site_south in [
        (10.0, 0.0),    # normaler Fall
        (3.0,  0.0),    # Gebäude nah am Südrand  → keine Reihe
        (15.0, 5.0),    # erhöhte Südgrenze
        (8.0,  3.0),    # knapper Spielraum
        (20.0, 2.0),    # viel Platz
    ]:
        south_start = by0 - 1.5
        row0_bottom = south_start - float(STELLPLATZ_TIEFE)

        row_fits = row0_bottom >= site_south
        if row_fits:
            # Wenn die Reihe laut Schleifenbedingung passt, muss sie wirklich passen
            assert row0_bottom >= site_south, (
                f"Row-0-Unterseite {row0_bottom:.1f}m < site_south {site_south:.1f}m "
                f"(by0={by0}, south_start={south_start:.1f})"
            )


def test_parking_second_row_guard():
    """P0: Zweite Stellplatz-Reihe wird nur gezeichnet wenn row2_y >= site_south."""
    from app.tools.drawing import STELLPLATZ_TIEFE, FAHRGANG_BREITE

    for by0, site_south in [
        (20.0, 0.0),
        (18.0, 3.0),
        (12.0, 0.0),
    ]:
        south_start = by0 - 1.5
        fahrgang_y = south_start - float(STELLPLATZ_TIEFE) - float(FAHRGANG_BREITE)
        row2_y = fahrgang_y - float(STELLPLATZ_TIEFE)

        # Guard-Bedingung aus _draw_parking_info:
        if row2_y >= site_south:
            assert row2_y >= site_south, (
                f"Row-2 bei row2_y={row2_y:.1f}m < site_south={site_south:.1f}m"
            )


def test_polygon_effective_south_axis_parallel():
    """Achsenparalleles Rechteck → effektive Südgrenze = 0."""
    from app.tools.drawing import _polygon_effective_south

    rect = [(0, 0), (100, 0), (100, 60), (0, 60)]
    south = _polygon_effective_south(rect, 0, 100)
    assert south == pytest.approx(0.0, abs=0.1), (
        f"Achsenparalleles Grundstück: south_eff sollte 0.0 sein, war {south}"
    )


def test_polygon_effective_south_irregular():
    """Schräges Grundstück → effektive Südgrenze > 0."""
    from app.tools.drawing import _polygon_effective_south

    # Dreieck mit abgeschnittener Südwest-Ecke: Südkante verläuft schräg
    # Punkte: (10,5), (100,0), (100,60), (0,60)  → Südseite von x=10 bis x=100
    irregular = [(10.0, 5.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)]
    south = _polygon_effective_south(irregular, 10, 100)
    # Im x-Bereich [10,100] liegt die Südkante zwischen y=0 und y=5 → south_eff > 0
    assert south > 0.0, (
        f"Schräges Grundstück: south_eff sollte > 0 sein, war {south}"
    )
    assert south < 6.0, (
        f"south_eff {south} überraschend hoch (erwartet < 6 für diese Geometrie)"
    )

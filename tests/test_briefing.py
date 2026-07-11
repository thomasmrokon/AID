"""Test: briefing_agent — Pydantic-Validierung + Struct-Ausgabe."""
from __future__ import annotations
import pytest


def test_briefing_produces_structured_output(pipeline_state):
    """structured_briefing enthält alle Pflichtfelder."""
    sb = pipeline_state["structured_briefing"]
    assert sb is not None, "structured_briefing ist None"
    assert "nutzungstyp"  in sb
    assert "nuf_gesamt"   in sb   # Summe aller Nutzflächen
    assert "bgf_gesamt"   in sb   # Brutto-Grundfläche


def test_briefing_nuf_positive(pipeline_state):
    """NUF gesamt > 0 und plausibel (≤ 50.000 m²)."""
    nuf = pipeline_state["structured_briefing"]["nuf_gesamt"]
    assert nuf > 0
    assert nuf <= 50_000


def test_briefing_bgf_groesser_nuf(pipeline_state):
    """BGF ≥ NUF (Brutto enthält mehr als Netto)."""
    sb  = pipeline_state["structured_briefing"]
    bgf = sb["bgf_gesamt"]
    nuf = sb["nuf_gesamt"]
    assert bgf >= nuf, f"BGF {bgf} < NUF {nuf} — unplausibel"


def test_briefing_nutzungstyp_string(pipeline_state):
    """nutzungstyp ist ein nicht-leerer String."""
    typ = pipeline_state["structured_briefing"]["nutzungstyp"]
    assert isinstance(typ, str) and len(typ) > 0

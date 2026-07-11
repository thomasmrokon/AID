"""Test: rule_agent — YAML-Loading + Regelstruktur."""
from __future__ import annotations
import pytest


def test_rules_not_none(pipeline_state):
    """rule_agent liefert ein Rules-Dict zurück."""
    rules = pipeline_state["rules"]
    assert rules is not None
    assert isinstance(rules, dict)


def test_rules_contains_required_sections(pipeline_state):
    """Mindest-Sektionen im Rules-Dict vorhanden."""
    rules = pipeline_state["rules"]
    for section in ("tragwerk", "logistik", "erweiterbarkeit"):
        assert section in rules, f"Sektion '{section}' fehlt in rules"


def test_rules_conventions_loaded(pipeline_state):
    """rules_conventions wurde aus YAML geladen (nicht None/leer)."""
    rc = pipeline_state.get("rules_conventions")
    assert rc is not None
    assert isinstance(rc, dict)
    assert len(rc) > 0


def test_rules_tragwerk_has_raster(pipeline_state):
    """Tragwerk-Regeln enthalten Stützenraster."""
    tw = pipeline_state["rules"].get("tragwerk", {})
    has_raster = any(
        k in tw for k in ("raster_x_m", "stuetzenraster_x_m", "raster_standard_x_m")
    )
    assert has_raster, f"Kein Stützenraster in Tragwerk-Regeln. Vorhandene Keys: {list(tw.keys())}"

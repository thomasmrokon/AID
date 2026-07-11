"""Test: evaluation_agent — Score-Bereiche + Struktur."""
from __future__ import annotations
import pytest


def test_evaluation_three_results(pipeline_state):
    """Genau 3 Evaluations-Ergebnisse (je Variante)."""
    evals = pipeline_state["evaluations"]
    assert evals is not None
    assert len(evals) == 3


def test_evaluation_scores_in_range(pipeline_state):
    """Alle Scores liegen in [0, 10]."""
    for ev in pipeline_state["evaluations"]:
        for key in ("gesamtscore", "materialfluss_score",
                    "erweiterbarkeit_score", "tragwerk_score"):
            val = ev.get(key)
            assert val is not None, f"{key} fehlt in {ev.get('variante')}"
            assert 0.0 <= val <= 10.0, (
                f"{ev['variante']}.{key} = {val} außerhalb [0,10]"
            )


def test_evaluation_selected_variant_exists(pipeline_state):
    """selected_variant ist eine der 3 Varianten-Namen."""
    selected = pipeline_state["selected_variant"]
    variant_names = {ev["variante"] for ev in pipeline_state["evaluations"]}
    assert selected in variant_names, (
        f"selected_variant '{selected}' nicht in {variant_names}"
    )


def test_evaluation_no_duplicate_variants(pipeline_state):
    """Jede Variante wird genau einmal bewertet."""
    names = [ev["variante"] for ev in pipeline_state["evaluations"]]
    assert len(names) == len(set(names)), "Doppelte Varianten in Evaluation"

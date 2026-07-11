"""
AID Demo – pytest Fixtures (gemeinsam für alle Tests)

pipeline_state:  Führt die deterministische Pipeline durch und cached das Ergebnis.
                 Kein LLM — alle Agenten greifen auf Fallback-Logik zurück.
site_state:      Minimaler State mit Site-Geometrie für Masterplan-Tests.
"""
from __future__ import annotations

import contextlib
import io
import sys
from typing import Any

import pytest

# ── Rhino-Runtime sicher deaktivieren ────────────────────────────────────────
try:
    import app.tools.rhino_inside_runner as _rr
    _rr._available = False
except Exception:
    pass

# ── Minimales Produktions-Briefing (ohne LLM-Felder) ─────────────────────────
BASE_USER_INPUT: dict[str, Any] = {
    "nutzungstyp":            "Produktion",
    "produktionsflaeche":     1800,
    "lager_rohstoffe":        450,
    "lager_fertigwaren":      450,
    "wareneingang":           200,
    "versand":                200,
    "qualitaetssicherung":    100,
    "buero_nuf2":             250,
    "buero_geschosse":        2,
    "technikflaeche_tf":      None,
    "sozialraeume_nuf7":      None,
    "sonderbedingungen":      None,
    "kranbahn_erforderlich":  False,
    "mep_lueftung":           "mechanisch",
    "mep_sprinkler":          False,
    "mep_druckluft":          True,
    "mep_kaelte":             False,
    "mep_usv_notstrom":       False,
    "mep_it_kategorie":       "basis",
    "tragwerk_typologie":     "stahl",
    "tragwerk_lastklasse":    "mittel",
}

SITE_ID = "A_kompakt"


def _quiet(func, *args, **kwargs):
    """Unterdrückt stdout-Ausgaben (print-Statements in Agenten)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


@pytest.fixture(scope="session")
def pipeline_state() -> dict[str, Any]:
    """
    Führt die deterministische Pipeline bis einschließlich Layout und Evaluation durch.
    Scope 'session' → einmalige Ausführung, gecached für alle Tests.
    """
    from app.tools.site import get_demo_site
    from app.agents.briefing   import briefing_agent
    from app.agents.rules      import rule_agent
    from app.agents.topology   import topology_agent
    from app.agents.strategy   import layout_strategy_agent
    from app.agents.layout     import layout_agent
    from app.agents.erschliessung import erschliessungs_agent
    from app.agents.evaluation import evaluation_agent

    site = get_demo_site(SITE_ID)

    state: dict[str, Any] = {
        "user_input":           BASE_USER_INPUT,
        "site_geometry":        site,
        "structured_briefing":  None,
        "rules":                None,
        "rules_conventions":    None,
        "topology_diagram":     None,
        "typology_assignments": None,
        "variants":             None,
        "erschliessungsgraphen": None,
        "evaluations":          None,
        "selected_variant":     None,
        "reasoning_log":        [],
        "planning_decisions":   [],
        "adjacency_weights":    {},
        "zone_splits":          {},
        "gap_strategy":         "balanced",
        "projektziele":         [],
        "split_priority_map":   {},
        "custom_gewichtungen":  None,
        "rule_overrides":       None,
        "rule_change_request":  None,
        "tragwerk_config":      None,
        "mep_anforderungen":    None,
        "mep_trassennetz":      None,
        "llm_used_agents":      [],
        "compliance_issues":    [],
    }

    for agent in [
        briefing_agent,
        rule_agent,
        topology_agent,
        layout_strategy_agent,
        layout_agent,
        erschliessungs_agent,
        evaluation_agent,
    ]:
        result = _quiet(agent, state)
        state.update(result)

    return state


@pytest.fixture(scope="session")
def site_state() -> dict[str, Any]:
    """Minimaler State mit Site für Masterplan-Tests."""
    from app.tools.site import get_demo_site
    site = get_demo_site(SITE_ID)
    return {
        "user_input":          BASE_USER_INPUT,
        "site_geometry":       site,
        "structured_briefing": None,
    }

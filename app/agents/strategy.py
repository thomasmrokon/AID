"""
AID Demo - Layout-Strategy-Agent.

Erzeugt fuer jede Variante:
  - Typologiezuweisung (kamm / block_reserve / kreuzgang)
  - Zonenzuweisung (zone_roles: welche Zone spielt welche Rolle in der Typologie)
  - Dynamische Parameter (process_pull, compactness, aspect_bias)

Liest interpreted_rules aus dem State (Ergebnis des LLM-Planungsrats).
"""

from __future__ import annotations

import copy
import json
import re

from app.state import PlanningState, VARIANTEN_GEWICHTUNGEN


# Erlaubte Typologienamen — muessen mit Layout-Funktionen uebereinstimmen
TYPOLOGIEN = {
    "A_Materialfluss":   "optimized",    # Slicing-Floorplan-Optimizer: Materialfluss A→Z
    "B_Erweiterbarkeit": "block_reserve", # Kompakter Block + schraffierte Erweiterungszone
    "C_Ausgewogen":      "optimized",    # Slicing-Floorplan-Optimizer: ausgewogen
}

# Aktive Typologienamen — nur diese werden vom Layout-Agent verwendet
# kamm + kreuzgang entfernt in Sprint N (erzeugten corridor_y-Fugen, nie in Produktion)
_ALL_TYPOLOGIEN = {"block_reserve", "optimized", "squarified", "recursive"}

# Zonenrollen je Typologie
ROLLEN_BLOCK_RESERVE = {"block", "reserve"}     # Hauptblock + Erweiterungszone


def layout_strategy_agent(state: PlanningState) -> dict:
    """LangGraph-Node: Layoutstrategie + Zonenzuweisung — vollständig deterministisch (Sprint P).

    Begründung für LLM-Entfernung:
    - Typologiezuweisungen sind in TYPOLOGIEN konstant (seit Sprint N); _sanitize_typologies()
      hat LLM-Output bereits vollständig ignoriert.
    - Zone-Rollen sind für alle Optimizer-Varianten leer (Optimizer nutzt adjacency_weights direkt).
    - dynamic_variant_settings entsprechen exakt den Defaults in VARIANT_SETTINGS (layout.py).
    → Kein Informationsgewinn durch LLM-Aufruf, aber Nicht-Determinismus-Risiko.
    """
    fallback_strategy, fallback_roles, fallback_typologies = _fallback(state)
    print("[strategy] Algorithmic (deterministisch) — kein LLM-Aufruf")
    return _build_output(fallback_strategy, fallback_roles, fallback_typologies, state, "fallback")


# ---------------------------------------------------------------------------
# Output zusammenbauen
# ---------------------------------------------------------------------------

def _build_output(
    strategy: dict,
    zone_roles: dict,
    typology_assignments: dict,
    state: PlanningState,
    quelle: str,
    reasoning_log: list | None = None,
    decisions: list | None = None,
) -> dict:
    result: dict = {
        "layout_strategy":      strategy,
        "zone_roles":           zone_roles,
        "typology_assignments": typology_assignments,
        "strategy_decisions":   decisions or strategy.get("decisions", []),
    }
    if reasoning_log is not None:
        result["reasoning_log"] = reasoning_log
    elif quelle == "fallback":
        log = list(state.get("reasoning_log") or [])
        log.append({
            "agent":       "strategy_agent",
            "disziplin":   "System",
            "variante":    "alle",
            "entscheidung": "Fallback aktiviert",
            "begruendung": f"Quelle: {quelle}",
            "regelref":    "TYPOLOGIEN default",
        })
        result["reasoning_log"] = log
    return result


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback(state: PlanningState) -> tuple[dict, dict, dict]:
    topology     = state.get("topology_diagram") or {}
    process_order = topology.get("process_order") or []
    nodes        = topology.get("nodes") or []
    node_names   = {n["name"] for n in nodes}

    process_names = [n for n in process_order if n in node_names]
    support_names = [n["name"] for n in nodes if n["name"] not in set(process_names)]

    # Kamm: Support = spine, Prozess = tooth
    zone_roles_a = {n: "spine" for n in support_names}
    zone_roles_a.update({n: "tooth" for n in process_names})

    # Block+Reserve: alles im Block, keine Reserve-Zone aus Briefing
    zone_roles_b = {n: "block" for n in node_names}

    # Kreuzgang: Prozesskette linear links (SW unten → NW oben), Support rechts (NE)
    zone_roles_c: dict[str, str] = {}
    support_list = list(support_names)
    process_list = list(process_names)
    half = max(1, -(-len(process_list) // 2))  # ceil division
    for i, n in enumerate(process_list):
        zone_roles_c[n] = "quadrant_SW" if i < half else "quadrant_NW"
    for n in support_list:
        zone_roles_c[n] = "quadrant_NE"

    zone_roles = {
        "A_Materialfluss":   {},   # Optimizer: keine Zone-Rollen benötigt
        "B_Erweiterbarkeit": {},   # Optimizer: keine Zone-Rollen benötigt
        "C_Ausgewogen":      {},   # Optimizer: keine Zone-Rollen benötigt
    }

    strategy = _fallback_strategy_dict(process_order)
    return strategy, zone_roles, copy.deepcopy(TYPOLOGIEN)


def _fallback_strategy_dict(process_order: list) -> dict:
    return {
        "global": {
            "primary_axis":    "west_east",
            "grid_priority":   "high",
            "office_position": "south_west",
            "tech_position":   "outer_edge",
        },
        "variants": {
            "A_Materialfluss":   {"typology": "squarified", "support_band": "east",  "process_sequence": process_order},
            "B_Erweiterbarkeit": {"typology": "squarified", "support_band": "south", "process_sequence": process_order},
            "C_Ausgewogen":      {"typology": "squarified", "support_band": "west",  "process_sequence": process_order},
        },
        "dynamic_variant_settings": {
            "A_Materialfluss":   {"process_pull": 1.35, "compactness": 0.45, "aspect_bias": 1.15},
            "B_Erweiterbarkeit": {"process_pull": 0.85, "compactness": 1.25, "aspect_bias": 0.95},
            "C_Ausgewogen":      {"process_pull": 1.00, "compactness": 0.85, "aspect_bias": 1.00},
        },
        "decisions": [],
    }


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

def _sanitize_typologies(raw: dict) -> dict:
    result = copy.deepcopy(TYPOLOGIEN)
    # LLM-Overrides nur für dynamic_variant_settings nutzen — Typologien sind fix.
    # Früher wurden LLM-Typologien (z.B. "kamm" für A) hier übernommen → Fugen-Bug.
    # Jetzt: Typologien immer aus TYPOLOGIEN-Konstante, kein LLM-Override.
    # A_Materialfluss:   squarified (Dreispalten-Columns, kein Korridor)
    # B_Erweiterbarkeit: block_reserve (Kompaktblock + Erweiterungsreserve)
    # C_Ausgewogen:      squarified (Dreispalten-Columns, ausgewogen)
    result["A_Materialfluss"]   = "optimized"
    result["B_Erweiterbarkeit"] = "block_reserve"
    result["C_Ausgewogen"]      = "optimized"
    return result


def _sanitize_zone_roles(raw: dict, node_names: list[str], typology_assignments: dict) -> dict:
    valid_roles = {
        "block_reserve":  ROLLEN_BLOCK_RESERVE,
        "optimized":     set(),   # Optimizer nutzt adjacency_weights, keine Zone-Rollen
        "squarified":    set(),   # Squarified: keine Zone-Rollen benötigt
        "recursive":     set(),
    }
    result: dict = {}
    for variant, roles in raw.items():
        if not isinstance(roles, dict):
            continue
        typ     = typology_assignments.get(variant, "squarified")
        allowed = valid_roles.get(typ, set())
        cleaned: dict[str, str] = {}
        for zone, role in roles.items():
            base_role = role.split("_")[0] if "_" in role else role
            if base_role in allowed or role in allowed:
                cleaned[zone] = role
        result[variant] = cleaned
    return result


def _build_strategy(parsed: dict, fallback: dict) -> dict:
    result = copy.deepcopy(fallback)
    for key in ("global", "variants", "dynamic_variant_settings"):
        if key in parsed and isinstance(parsed[key], dict):
            result[key] = _merge(result.get(key, {}), parsed[key])
    return result


def _merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result


def _parse_json(text: str | None) -> dict:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group())
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}

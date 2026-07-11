"""
AID Demo — Erschließungs-Agent (Sprint B + Sprint C)

Analysiert die Zonen jeder Layout-Variante und erzeugt einen Verbindungsgraphen:
  "direkt"   — Zonen teilen eine gemeinsame Wand >= 0.9 m
  "korridor" — Topologie-Verbindung vorhanden, aber keine gemeinsame Wand;
               Pfad-Geometrie wird via A*-Pathfinder berechnet (Sprint C)

READS:  state["variants"], state["topology_diagram"], state["rules_conventions"]
WRITES: {"erschliessungsgraphen": dict, "reasoning_log": list (append)}
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from app.state import PlanningState
from app.tools.pathfinder import find_corridor_path

_WALL_TOL = 0.1   # m — Toleranz: Wände gelten als berührend
_WALL_MIN = 0.9   # m — Mindestlänge gemeinsame Wand für "direkt"
_DEFAULT_KORRIDOR_BREITE = 6.0


def erschliessungs_agent(state: PlanningState) -> dict[str, Any]:
    """LangGraph-Node: Erschließungsgraph je Variante aufbauen."""
    variants   = state.get("variants") or []
    topo       = state.get("topology_diagram") or {}
    rules_conv = state.get("rules_conventions") or {}

    korridor_breite = float(
        rules_conv
        .get("erschliessung", {})
        .get("erschliessungsbreite_haupt_m", {})
        .get("default", _DEFAULT_KORRIDOR_BREITE)
    )

    topo_weights = _build_topo_weights(topo)
    erschliessungsgraphen: dict[str, dict] = {}
    reasoning_entries: list[dict] = []

    for v in variants:
        variante_name = v.get("name", "")
        zonen_raw     = v.get("zonen", [])

        zonen = [
            z for z in zonen_raw
            if not z.get("schraffur") and z.get("din_kategorie") != "VF"
        ]

        envelope = v.get("building_envelope") or {
            "x":       0.0,
            "y":       0.0,
            "width_m": float(v.get("site_breite", 60.0)),
            "depth_m": float(v.get("site_tiefe",  40.0)),
        }

        zone_map = {z["name"]: z for z in zonen_raw}

        kanten: list[dict] = []
        seen_pairs: set[frozenset] = set()

        for a, b in combinations(zonen, 2):
            pair = frozenset({a["name"], b["name"]})
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            wall_m = _shared_wall(a, b)
            topo_w = topo_weights.get(pair, 0.0)

            if wall_m >= _WALL_MIN:
                kanten.append({
                    "von":               a["name"],
                    "nach":              b["name"],
                    "typ":               "direkt",
                    "shared_wall_m":     round(wall_m, 2),
                    "korridor_breite_m": 0.0,
                    "pfad_punkte":       [],
                    "pfad_laenge_m":     round(wall_m, 2),
                })
            elif topo_w > 0:
                pfad = find_corridor_path(a, b, zonen_raw, envelope)
                kanten.append({
                    "von":               a["name"],
                    "nach":              b["name"],
                    "typ":               "korridor",
                    "shared_wall_m":     0.0,
                    "korridor_breite_m": korridor_breite,
                    "pfad_punkte":       pfad["pfad_punkte"],
                    "pfad_laenge_m":     pfad["pfad_laenge_m"],
                })

        verbundene = {z for k in kanten for z in (k["von"], k["nach"])}
        isolierte  = [z["name"] for z in zonen if z["name"] not in verbundene]

        n_direkt   = sum(1 for k in kanten if k["typ"] == "direkt")
        n_korridor = sum(1 for k in kanten if k["typ"] == "korridor")
        total_korridor_m = sum(
            k.get("pfad_laenge_m", 0) for k in kanten if k["typ"] == "korridor"
        )

        erschliessungsgraphen[variante_name] = {
            "kanten":          kanten,
            "isolierte_zonen": isolierte,
        }

        print(
            f"[erschliessung] {variante_name}: {len(kanten)} Kanten "
            f"({n_direkt} direkt, {n_korridor} Korridor), "
            f"{len(isolierte)} isolierte Zonen · "
            f"Korridor-Länge: {total_korridor_m:.0f} m"
        )

        reasoning_entries.append({
            "agent":    "erschliessung",
            "variante": variante_name,
            "kanten":   len(kanten),
            "direkt":   n_direkt,
            "korridor": n_korridor,
        })

    existing_log = list(state.get("reasoning_log") or [])
    return {
        "erschliessungsgraphen": erschliessungsgraphen,
        "reasoning_log":         existing_log + reasoning_entries,
    }


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _shared_wall(a: dict, b: dict) -> float:
    """Länge der gemeinsamen Wand zwischen zwei Zonen-Dicts (0.0 wenn keine)."""
    ax0, ax1 = float(a["x"]), float(a["x"]) + float(a["breite"])
    ay0, ay1 = float(a["y"]), float(a["y"]) + float(a["tiefe"])
    bx0, bx1 = float(b["x"]), float(b["x"]) + float(b["breite"])
    by0, by1 = float(b["y"]), float(b["y"]) + float(b["tiefe"])

    # Horizontale Berührung: A-rechts → B-links oder B-rechts → A-links
    if abs(ax1 - bx0) < _WALL_TOL or abs(bx1 - ax0) < _WALL_TOL:
        overlap = min(ay1, by1) - max(ay0, by0)
        return max(0.0, overlap)

    # Vertikale Berührung: A-oben → B-unten oder B-oben → A-unten
    if abs(ay1 - by0) < _WALL_TOL or abs(by1 - ay0) < _WALL_TOL:
        overlap = min(ax1, bx1) - max(ax0, bx0)
        return max(0.0, overlap)

    return 0.0


def _build_topo_weights(topo: dict) -> dict[frozenset, float]:
    """Baut {frozenset({zone_a, zone_b}): gewicht} aus topology_diagram."""
    weights: dict[frozenset, float] = {}

    # Format 1: topo["adjacency"] oder topo["kanten"] = {"A__B": weight, ...}
    for raw in (topo.get("adjacency"), topo.get("kanten")):
        if not isinstance(raw, dict):
            continue
        for key, val in raw.items():
            if "__" not in key:
                continue
            parts = key.split("__", 1)
            if len(parts) != 2:
                continue
            try:
                w = float(val)
            except (TypeError, ValueError):
                w = 1.0
            if w > 0:
                fs = frozenset(parts)
                weights[fs] = max(weights.get(fs, 0.0), w)

    # Format 2: topo["edges"] = [{"source": ..., "target": ..., "weight": ...}]
    for edge in topo.get("edges", []):
        src = edge.get("source") or edge.get("from") or edge.get("von")
        tgt = edge.get("target") or edge.get("to")   or edge.get("nach")
        try:
            w = float(edge.get("weight", 1.0) or 1.0)
        except (TypeError, ValueError):
            w = 1.0
        if src and tgt and w > 0:
            fs = frozenset({src, tgt})
            weights[fs] = max(weights.get(fs, 0.0), w)

    return weights

"""
AID Demo - Layout-Agent.

Erzeugt drei Layoutvarianten aus einem graphbasierten Nutzungsdiagramm. Die
Geometrie ist weiterhin deterministisch, aber nicht mehr nur eine lineare
Aneinanderreihung von Rechtecken.
"""

from __future__ import annotations

import math
import random
from copy import deepcopy

from app.state import PlanningState, VARIANTEN_GEWICHTUNGEN, Nutzungstyp, ParameterGewichtung
from app.tools.geometry import Zone, berechne_site_dimensionen
from app.tools.site import compute_building_envelope, site_bounds
from app.agents.layout_recursive import recursive_split_layout, SPLIT_PRESETS


MAX_ASPECT_RATIO = 4.0   # Maximales Seitenverhältnis einer Funktionszone (Erschließung ausgenommen)


def _is_building_parcel_site(site_geometry: dict | None) -> bool:
    return bool(site_geometry and (
        site_geometry.get("is_building_parcel")
        or site_geometry.get("interface_type") == "building_parcel"
    ))

# Speichert OptimizationResult je Variante für das Entscheidungsprotokoll.
# Wird von layout_agent nach _layout_from_topology ausgelesen.
_last_optimization_result: dict = {}

# Zonen, die auf mehrere Geschosse gestapelt werden dürfen (DIN-Kategorie → Max. Geschosse)
STACKABLE_ZONES: dict[str, int] = {
    "NUF 2": 4,   # Büro, Verwaltung
    "NUF 7": 4,   # Sozial, Sanitär
    "TF":    2,   # Technik, Haustechnik
}


def _precheck_capacity(
    nodes: list[dict],
    envelope: dict,
) -> tuple[list[dict], dict | None]:
    """Prüft ob Briefing-Fläche ins Baufeld passt.

    Strategie:
    1. Stackable Zonen auf ≥2G erhöhen → reicht das?
    2. Sonst: Reduktionsfaktor berechnen, alle Flächen skalieren.
    Returns (adjusted_nodes, warning_dict | None).
    """
    max_fp = float(envelope.get("max_footprint_m2") or
                   envelope["width_m"] * envelope["depth_m"])

    original_fp = sum(
        n.get("planned_area_m2", n.get("area_m2", 0)) / max(1, n.get("floors", 1))
        for n in nodes
    )

    if original_fp <= max_fp * 1.05:
        return nodes, None  # Passt — kein Eingriff nötig

    # ── Versuch 1: Stapelung ──────────────────────────────────────────────────
    stacked = deepcopy(nodes)
    stacked_names: list[str] = []
    for n in stacked:
        din = n.get("din_kategorie", "")
        max_fl = STACKABLE_ZONES.get(din, 1)
        if max_fl >= 2 and n.get("floors", 1) < 2:
            n["floors"] = 2
            n["footprint_m2"] = round(n["area_m2"] / 2, 2)
            stacked_names.append(n["name"])

    fp_after_stacking = sum(
        n.get("planned_area_m2", n.get("area_m2", 0)) / max(1, n.get("floors", 1))
        for n in stacked
    )
    if fp_after_stacking <= max_fp * 1.05:
        return stacked, {
            "type": "stacking",
            "original_fp_m2": round(original_fp),
            "adjusted_fp_m2": round(fp_after_stacking),
            "capacity_m2":    round(max_fp),
            "stacked_zones":  stacked_names,
        }

    # ── Versuch 2: Reduktionsfaktor ───────────────────────────────────────────
    # Versuche Stapelung zuerst, dann Reduktion auf Rest
    reduction_factor = max_fp / (fp_after_stacking * 1.05)
    reduced = deepcopy(stacked)
    for n in reduced:
        for key in ("planned_area_m2", "area_m2", "footprint_m2"):
            if key in n and n[key]:
                n[key] = round(float(n[key]) * reduction_factor, 1)
    return reduced, {
        "type": "stacking_and_reduction",
        "original_fp_m2":   round(original_fp),
        "reduction_factor": round(reduction_factor, 2),
        "capacity_m2":      round(max_fp),
        "stacked_zones":    stacked_names,
    }


def _min_band_height_for_aspect(
    nodes: list[dict], band_width: float, grid: float, max_aspect: float = MAX_ASPECT_RATIO
) -> float:
    """Minimale Bandhöhe, damit keine Zone das Seitenverhältnis max_aspect überschreitet."""
    if not nodes or band_width <= 0:
        return 0.0
    def _node_fp(n: dict) -> float:
        return float(n.get("footprint_m2") or n["planned_area_m2"] / max(1, n.get("floors", 1)))
    total_fp = sum(_node_fp(n) for n in nodes)
    if total_fp <= 0:
        return 0.0
    widest_fp = max(_node_fp(n) for n in nodes)
    max_zone_width = band_width * widest_fp / total_fp
    # ceiling-Snap: sicherstellen dass min_height wirklich ausreicht (nicht durch Rundung unterschritten)
    return math.ceil(max_zone_width / (max_aspect * grid)) * grid


VARIANT_SETTINGS = {
    "A_Materialfluss": {
        "seed": 101,
        "expansion_fraction": 0.00,
        "process_pull": 1.35,
        "compactness": 0.45,
        "edge_pull": 0.75,
        "aspect_bias": 1.15,
    },
    "B_Erweiterbarkeit": {
        "seed": 202,
        "expansion_fraction": 0.32,
        "process_pull": 0.85,
        "compactness": 1.25,
        "edge_pull": 0.90,
        "aspect_bias": 0.95,
    },
    "C_Ausgewogen": {
        "seed": 303,
        "expansion_fraction": 0.20,
        "process_pull": 1.00,
        "compactness": 0.85,
        "edge_pull": 0.80,
        "aspect_bias": 1.00,
    },
}


def layout_agent(state: PlanningState) -> dict:
    """LangGraph-Node: Drei graphbasierte Layoutvarianten generieren."""
    briefing = state["structured_briefing"]
    rules = state["rules"]
    nutzungstyp = briefing["nutzungstyp"]
    bgf = briefing["bgf_gesamt"]
    topology = state.get("topology_diagram")
    if not topology:
        raise ValueError("Topology-Diagramm fehlt. Der topology_agent muss vor layout_agent laufen.")
    layout_strategy = state.get("layout_strategy") or {}

    selected_site = state.get("site_geometry")
    bounds = site_bounds(selected_site)
    if bounds:
        site_breite, site_tiefe = bounds
    else:
        site_breite, site_tiefe = berechne_site_dimensionen(bgf, aspekt=1.5)

    raster_x = rules.get("tragwerk", {}).get("raster_standard_x_m", 18)
    raster_y = rules.get("tragwerk", {}).get("raster_standard_y_m", 12)
    if nutzungstyp == Nutzungstyp.PRODUKTION and briefing.get("kranbahn_erforderlich"):
        raster_x = rules["tragwerk"].get("raster_kran_x_m", 24)
    if nutzungstyp == Nutzungstyp.LOGISTIK and briefing.get("hochregallager"):
        raster_x = rules["tragwerk"].get("raster_hochregal_x_m", 24)
    tragwerk_cfg = state.get("tragwerk_config") or {}
    if tragwerk_cfg.get("raster_x_m"):
        raster_x = float(tragwerk_cfg["raster_x_m"])
    if tragwerk_cfg.get("raster_y_m"):
        raster_y = float(tragwerk_cfg["raster_y_m"])

    aktive_gewichtungen = _aktive_gewichtungen(state.get("custom_gewichtungen") or {})
    layout_corrections = state.get("layout_corrections") or {}
    layout_iteration = int(state.get("layout_iteration") or 0)
    zone_roles = state.get("zone_roles") or {}
    typology_assignments = state.get("typology_assignments") or {}
    interpreted_rules = state.get("interpreted_rules") or {}
    split_priority_map = state.get("split_priority_map") or {}
    adjacency_weights = {k: float(v) for k, v in (state.get("adjacency_weights") or {}).items()}
    gap_strategy = str(state.get("gap_strategy") or "none")

    # ── Kapazitäts-Pre-Check (einmalig für alle Varianten) ────────────────────
    _check_envelope = compute_building_envelope(selected_site) or {
        "x": 0.0, "y": 0.0,
        "width_m": site_breite, "depth_m": site_tiefe,
        "area_m2": site_breite * site_tiefe,
        "max_footprint_m2": site_breite * site_tiefe,
    }
    _adjusted_nodes, capacity_warning = _precheck_capacity(
        topology["nodes"], _check_envelope
    )
    if capacity_warning:
        topology = {**topology, "nodes": _adjusted_nodes}

    reasoning_log = list(state.get("reasoning_log") or [])
    planning_decisions = list(state.get("planning_decisions") or [])
    variants = []
    for variante_key, gewichtung in aktive_gewichtungen.items():
        settings = _settings_for_variant(variante_key, rules, layout_strategy, raster_x, raster_y)

        # Variantenspezifische Rastermaße aus interpreted_rules überschreiben
        var_raster_x = raster_x
        var_raster_y = raster_y
        var_interpreted = interpreted_rules.get(variante_key, {})
        if var_interpreted.get("tragwerk"):
            var_raster_x = float(var_interpreted["tragwerk"].get("raster_x_m", raster_x))
            var_raster_y = float(var_interpreted["tragwerk"].get("raster_y_m", raster_y))

        zonen, envelope = _layout_from_topology(
            topology=topology,
            layout_strategy=layout_strategy,
            layout_corrections=layout_corrections,
            site_geometry=selected_site,
            site_breite=site_breite,
            site_tiefe=site_tiefe,
            variante_key=variante_key,
            settings=settings,
            raster_x=var_raster_x,
            raster_y=var_raster_y,
            zone_roles=zone_roles.get(variante_key, {}),
            typology_assignment=typology_assignments.get(variante_key),
            interpreted_rules=var_interpreted,
            split_priority=split_priority_map.get(variante_key),
            graph_weights=adjacency_weights,
            zone_splits={k: max(1, min(4, int(v)))
                         for k, v in (state.get("zone_splits") or {}).items()},
            gap_strategy=gap_strategy,
        )

        # ── Entscheidungsprotokoll: Zonenplatzierung ──────────────────────────
        def _are_adjacent(a: Zone, b: Zone, eps: float = 0.5) -> bool:
            x_overlap = a.x < b.x + b.breite + eps and b.x < a.x + a.breite + eps
            y_touch   = (abs(a.y - (b.y + b.tiefe)) < eps or
                         abs(b.y - (a.y + a.tiefe)) < eps)
            y_overlap = a.y < b.y + b.tiefe + eps and b.y < a.y + a.tiefe + eps
            x_touch   = (abs(a.x - (b.x + b.breite)) < eps or
                         abs(b.x - (a.x + a.breite)) < eps)
            return (x_overlap and y_touch) or (y_overlap and x_touch)

        for zone in zonen:
            adj_names = [
                z2.name for z2 in zonen
                if z2.name != zone.name and _are_adjacent(zone, z2)
            ]
            ist_area = round(zone.breite * zone.tiefe * zone.floors, 1)
            soll_area = zone.flaeche_m2
            delta_pct = round((ist_area - soll_area) / max(1, soll_area) * 100, 1)

            if zone.schraffur:
                planning_decisions.append({
                    "agent":      "layout",
                    "variante":   variante_key,
                    "kategorie":  "Erweiterungsreserve",
                    "zone":       zone.name,
                    "aktion":     f"Reserve {zone.breite:.0f}×{zone.tiefe:.0f} m bei x={zone.x:.0f}/y={zone.y:.0f}",
                    "begruendung": (
                        f"Split-Strategie '{split_priority_map.get(variante_key, '?')}': "
                        f"{round(zone.breite * zone.tiefe):,} m² Erweiterungsreserve freigehalten."
                    ),
                    "wert":       {"area_m2": round(zone.breite * zone.tiefe), "x": zone.x, "y": zone.y},
                    "regel_ref":  "layout.reserve_fraction",
                })
            else:
                adj_str = ", ".join(adj_names) if adj_names else "—"
                planning_decisions.append({
                    "agent":      "layout",
                    "variante":   variante_key,
                    "kategorie":  "Zonenplatzierung",
                    "zone":       zone.name,
                    "aktion":     f"x={zone.x:.0f} m, y={zone.y:.0f} m, {zone.breite:.0f}×{zone.tiefe:.0f} m",
                    "begruendung": (
                        f"DIN {zone.din_kategorie}. "
                        f"Ist: {ist_area:,.0f} m² (Soll: {soll_area:,.0f} m², Δ {delta_pct:+.0f}%). "
                        f"Angrenzend: {adj_str}."
                    ),
                    "wert":       {
                        "area_soll_m2": soll_area,
                        "area_ist_m2":  ist_area,
                        "delta_pct":    delta_pct,
                        "floors":       zone.floors,
                    },
                    "regel_ref":  f"topology.{zone.din_kategorie.lower().replace(' ', '_')}",
                })

        variants.append({
            "name": variante_key,
            "beschreibung": gewichtung.beschreibung,
            "gewichtung": gewichtung.model_dump(),
            "zonen": [_zone_zu_dict(z) for z in zonen],
            "site_breite": site_breite,
            "site_tiefe": site_tiefe,
            "site_geometry": selected_site,
            "building_envelope": envelope,
            "raster_x": var_raster_x,
            "raster_y": var_raster_y,
            "layout_settings": settings,
            "capacity_warning": capacity_warning,
        })
        typology = typology_assignments.get(variante_key, "unbekannt")
        reasoning_log.append({
            "agent":       "layout_agent",
            "disziplin":   "Layout",
            "variante":    variante_key,
            "entscheidung": f"Typologie {typology}: {len(zonen)} Zonen",
            "begruendung": (
                f"Raster {var_raster_x}x{var_raster_y} m, "
                f"Site {site_breite:.0f}x{site_tiefe:.0f} m, Iteration {layout_iteration}"
            ),
            "regelref": f"layout.{typology}",
        })
        print(
            f"[layout] Variante '{variante_key}' generiert - "
            f"{len(zonen)} Zonen, Site {site_breite:.0f}x{site_tiefe:.0f} m, "
            f"Raster {var_raster_x}x{var_raster_y} m, Iteration {layout_iteration}"
        )

    return {"variants": variants, "reasoning_log": reasoning_log, "planning_decisions": planning_decisions}


def _aktive_gewichtungen(custom: dict) -> dict[str, ParameterGewichtung]:
    aktive = {}
    for key, default_g in VARIANTEN_GEWICHTUNGEN.items():
        if key in custom:
            c = custom[key]
            total = c["materialfluss"] + c["erweiterbarkeit"] + c["tragwerk"]
            total = total if total > 0 else 1.0
            aktive[key] = ParameterGewichtung(
                materialfluss=round(c["materialfluss"] / total, 3),
                erweiterbarkeit=round(c["erweiterbarkeit"] / total, 3),
                tragwerk=round(c["tragwerk"] / total, 3),
                beschreibung=default_g.beschreibung,
            )
        else:
            aktive[key] = default_g
    return aktive


def _settings_for_variant(
    variante_key: str,
    rules: dict,
    layout_strategy: dict,
    raster_x: float,
    raster_y: float,
) -> dict:
    settings = deepcopy(VARIANT_SETTINGS[variante_key])
    min_pct = rules.get("erweiterbarkeit", {}).get("freie_ostfassade_min_pct")
    if min_pct and variante_key == "B_Erweiterbarkeit":
        settings["expansion_fraction"] = max(settings["expansion_fraction"], min(0.55, float(min_pct)))
    if min_pct and variante_key == "C_Ausgewogen":
        settings["expansion_fraction"] = max(settings["expansion_fraction"], min(0.35, float(min_pct) * 0.7))
    llm_settings = (layout_strategy.get("dynamic_variant_settings") or {}).get(variante_key) or {}
    for key in ("process_pull", "compactness", "aspect_bias"):
        if key in llm_settings:
            try:
                val = llm_settings[key]
                # Skip range descriptors like "0.6..1.8" that LLM sometimes returns verbatim
                if isinstance(val, str) and ".." in val:
                    continue
                settings[key] = float(val)
            except (TypeError, ValueError):
                pass
    _validate_settings_against_raster(settings, raster_x, raster_y)
    return settings


def _validate_settings_against_raster(settings: dict, raster_x: float, raster_y: float) -> None:
    """Begrenzt LLM-Aspect-Bias auf plausible Tragwerksgeometrien."""
    module_ratio = max(raster_x, raster_y) / max(1.0, min(raster_x, raster_y))
    if module_ratio >= 1.8:
        lo, hi = 0.82, 1.18
    elif module_ratio >= 1.4:
        lo, hi = 0.78, 1.25
    else:
        lo, hi = 0.75, 1.35
    before = float(settings.get("aspect_bias", 1.0))
    after = round(max(lo, min(hi, before)), 3)
    settings["aspect_bias"] = after
    if after != before:
        settings["aspect_bias_note"] = (
            f"LLM aspect_bias {before:.2f} auf {after:.2f} begrenzt "
            f"wegen Stützraster {raster_x:g}x{raster_y:g} m"
        )


def _layout_from_topology(
    *,
    topology: dict,
    layout_strategy: dict,
    layout_corrections: dict,
    site_geometry: dict | None,
    site_breite: float,
    site_tiefe: float,
    variante_key: str,
    settings: dict,
    raster_x: float,
    raster_y: float,
    zone_roles: dict[str, str] | None = None,
    typology_assignment: str | None = None,
    interpreted_rules: dict | None = None,
    split_priority: str | None = None,
    graph_weights: dict | None = None,
    zone_splits: dict[str, int] | None = None,
    gap_strategy: str = "none",
) -> tuple[list[Zone], dict | None]:
    raw_nodes = _maybe_split_nodes(topology["nodes"], zone_splits or {})
    nodes = [_with_dimensions(n, settings) for n in raw_nodes]
    envelope = compute_building_envelope(site_geometry) if site_geometry else None
    if not envelope:
        envelope = {
            "x": 0.0,
            "y": 0.0,
            "width_m": site_breite,
            "depth_m": site_tiefe,
            "area_m2": site_breite * site_tiefe,
            "max_footprint_m2": site_breite * site_tiefe,
        }

    # Raw Envelope vor Skalierung merken (für Freifläche-Zone nach squarified Layout)
    _raw_envelope = dict(envelope)
    _use_full_building_parcel = _is_building_parcel_site(site_geometry)

    # Gebäude auf Briefing-Footprint skalieren — außer die Masterplanung übergibt
    # bereits eine definierte Gebäudeparzelle. Dann ist diese Parzelle die
    # Ausgangsfläche der Layoutplanung und soll vollständig genutzt werden.
    if not _use_full_building_parcel:
        envelope = _skaliere_envelope_auf_briefing(envelope, topology["nodes"], raster_x, raster_y)
    else:
        envelope = {**envelope, "max_footprint_m2": float(envelope.get("area_m2") or envelope["width_m"] * envelope["depth_m"])}

    settings = {**settings, "use_full_building_parcel": _use_full_building_parcel}
    zone_roles = zone_roles or {}
    interpreted_rules = interpreted_rules or {}

    if typology_assignment == "block_reserve":
        freie_fassade_pct = float(
            (interpreted_rules.get("erweiterbarkeit") or {}).get("freie_fassade_min_pct")
            or settings.get("expansion_fraction", 0.30)
        )
        zones = _block_mit_reserve_layout(
            nodes=nodes,
            topology=topology,
            zone_roles=zone_roles,
            envelope=envelope,
            settings=settings,
            raster_x=raster_x,
            raster_y=raster_y,
            freie_fassade_pct=freie_fassade_pct,
        )
    elif typology_assignment == "optimized":
        # Slicing-Floorplan-Optimizer — isotrope Lösung via scipy.optimize
        from app.agents.layout_optimizer import (
            optimize_layout, OptimizationWeights, TragwerkConstraints,
        )
        tragwerk_rules = (interpreted_rules or {}).get("tragwerk") or {}
        tc = TragwerkConstraints.from_interpreted_rules(tragwerk_rules)

        # Für den Optimizer: Envelope exakt auf Briefing-Footprint zuschneiden.
        # Der Slicing-Floorplan hat keine internen Korridore → der 20%-Puffer aus
        # _skaliere_envelope_auf_briefing wäre Flächenverlust.
        # Footprint aus nodes (topology-Knoten haben kein footprint_m2 nach Stapelung,
        # deshalb auch area_m2/floors benutzen falls floors gesetzt ist).
        total_fp = sum(
            float(n.get("footprint_m2") or
                  (n.get("area_m2", 0) / max(1, n.get("floors", 1))))
            for n in topology["nodes"]
        )
        env_area = float(envelope["width_m"]) * float(envelope["depth_m"])
        if (not _use_full_building_parcel) and total_fp > 0 and env_area > total_fp * 1.05:
            scale = math.sqrt(total_fp / env_area)
            opt_w = max(tc.raster_x_m * 4,
                        round(envelope["width_m"] * scale / tc.raster_x_m) * tc.raster_x_m)
            opt_d = max(tc.raster_y_m * 4,
                        math.ceil(total_fp / opt_w / tc.raster_y_m) * tc.raster_y_m)
            # Harte Obergrenze: Optimizer-Envelope darf Raw-Envelope niemals überschreiten.
            # Reihenfolge: erst Minimum anwenden (≥ 4 Raster), dann Limit (≤ raw).
            # Falsch: max(4r, min(d, cap)) → max dominiert wenn 4r > cap.
            # Richtig: min(max(4r, d), cap) → cap überschreibt immer die Mindestgröße.
            max_w = math.floor(_raw_envelope["width_m"]  / tc.raster_x_m) * tc.raster_x_m
            max_d = math.floor(_raw_envelope["depth_m"] / tc.raster_y_m) * tc.raster_y_m
            opt_w = min(max(tc.raster_x_m * 4, opt_w), max_w)
            opt_d = min(max(tc.raster_y_m * 4, opt_d), max_d)
            off_x = max(0.0, (envelope["width_m"] - opt_w) / 2)
            off_y = max(0.0, envelope["depth_m"] - opt_d) * 0.25
            envelope = {
                **envelope,
                "x":       round(envelope["x"] + off_x, 2),
                "y":       round(envelope["y"] + off_y, 2),
                "width_m": opt_w,
                "depth_m": opt_d,
                "area_m2": round(opt_w * opt_d, 2),
            }

        variant_seed = {"A_Materialfluss": 42, "B_Erweiterbarkeit": 137, "C_Ausgewogen": 251}
        result = optimize_layout(
            nodes=nodes,
            topology=topology,
            envelope=envelope,
            adjacency_weights=graph_weights or {},
            weights=OptimizationWeights.for_variant(variante_key),
            tragwerk=tc,
            seed=variant_seed.get(variante_key, 42),
        )
        zones = result.zones
        # Freifläche für den Leerraum zwischen skaliertem Optimizer-Envelope und Baufeld
        zones = _append_freif_zones(zones, envelope, _raw_envelope)
        _last_optimization_result[variante_key] = result
    elif typology_assignment == "squarified":
        # Squarified Treemap — deterministische Flächen, kein Optimizer
        zones = _squarified_layout_main(
            nodes=nodes,
            envelope=envelope,
            variante_key=variante_key,
            graph_weights=graph_weights or {},
            process_order=topology.get("process_order", []),
            gap_strategy=gap_strategy or "none",
        )
        # Freifläche für den Leerraum zwischen Gebäude-Envelope und Baufeld-Grenze
        zones = _append_freif_zones(zones, envelope, _raw_envelope)
    elif typology_assignment == "recursive" or typology_assignment is None:
        # Rekursiver Raumteiler — Preset aus variante_key, Override via split_priority
        zones = recursive_split_layout(
            nodes=nodes,
            topology=topology,
            envelope=envelope,
            graph_weights=graph_weights or {},
            variante_key=variante_key,
            split_priority=split_priority,
            raster_x=raster_x,
            raster_y=raster_y,
        )
    else:
        # Fallback: klassisches Band-Layout (Legacy-Typologien ohne eigenen Branch)
        zones = _sliced_building_layout(
            nodes=nodes,
            topology=topology,
            layout_strategy=layout_strategy,
            layout_corrections=layout_corrections,
            envelope=envelope,
            variante_key=variante_key,
            settings=settings,
            raster_x=raster_x,
            raster_y=raster_y,
        )

    # ── Post-Layout-Validierung: alle Topology-Nodes müssen vorhanden sein ──
    expected = {n["name"] for n in topology["nodes"]}
    actual   = {z.name for z in zones if not z.schraffur}
    missing  = expected - actual
    if missing:
        print(f"[layout] Warnung: Zonen fehlen nach {typology_assignment!r}-Layout: {missing}. "
              "Fallback auf sliced_building_layout.")
        zones = _sliced_building_layout(
            nodes=nodes,
            topology=topology,
            layout_strategy=layout_strategy,
            layout_corrections=layout_corrections,
            envelope=envelope,
            variante_key=variante_key,
            settings=settings,
            raster_x=raster_x,
            raster_y=raster_y,
        )
        # Zweite Prüfung: falls auch Fallback Zonen verliert, fehlende am Ende anfügen
        actual2 = {z.name for z in zones if not z.schraffur}
        still_missing = expected - actual2
        if still_missing:
            _append_missing_zones(zones, nodes, still_missing, envelope, raster_x, raster_y)

    return zones, envelope


def _append_missing_zones(
    zones: list[Zone],
    nodes: list[dict],
    missing_names: set[str],
    envelope: dict,
    raster_x: float,
    raster_y: float,
) -> None:
    """Hängt fehlende Zonen kompakt rechts an die bestehende Zone-Sammlung an."""
    grid = min(raster_x, raster_y) / 2
    if not zones:
        return
    # Fehlende Zonen innerhalb des Envelopes anfügen (gestapelt, von oben links)
    env_right = envelope["x"] + envelope["width_m"]
    env_top   = envelope["y"] + envelope["depth_m"]
    non_hatch = [z for z in zones if not z.schraffur]
    # Finde freien Platz: oberhalb der bestehenden Zonen (Norden) innerhalb Envelope
    x_start = envelope["x"]
    y_base  = max(z.y + z.tiefe for z in non_hatch) if non_hatch else envelope["y"]
    if y_base >= env_top - grid * 2:
        # Kein Platz oben — rechts neben Gebäude anfügen, falls noch Platz
        x_start = max(z.x + z.breite for z in non_hatch) if non_hatch else envelope["x"]
        y_base  = min(z.y for z in non_hatch) if non_hatch else envelope["y"]
    max_h = env_top - y_base
    cursor_y = y_base
    for n in nodes:
        if n["name"] not in missing_names:
            continue
        fp = float(n.get("footprint_m2") or n.get("planned_area_m2") or 36.0)
        w = max(grid * 2, round(math.sqrt(fp) / grid) * grid)
        h = max(grid * 2, min(max_h, round((fp / w) / grid) * grid))
        # Harte Grenze: Zone darf nicht über Envelope-Rand hinaus
        w = min(w, env_right - x_start)
        h = min(h, env_top - cursor_y)
        if w < grid or h < grid:
            continue
        zones.append(Zone(
            name=n["name"],
            x=round(x_start, 2),
            y=round(cursor_y, 2),
            breite=round(w, 2),
            tiefe=round(h, 2),
            flaeche_m2=n.get("area_m2", fp),
            din_kategorie=n.get("din_kategorie", "NUF 3"),
            farbe=n.get("farbe", "#CCCCCC"),
            floors=n.get("floors", 1),
            planned_area_m2=round(w * h * n.get("floors", 1), 2),
        ))
        cursor_y += h
        if cursor_y + grid * 2 > env_top:
            cursor_y = y_base
            x_start += w
            if x_start >= env_right - grid:
                break


_SPLIT_LABELS = ["A", "B", "C", "D"]

def _maybe_split_nodes(nodes: list[dict], zone_splits: dict[str, int]) -> list[dict]:
    """Teilt Nodes mit zone_splits[name] > 1 in gleich große Sub-Nodes auf."""
    if not zone_splits:
        return nodes
    result: list[dict] = []
    for n in nodes:
        count = max(1, min(4, int(zone_splits.get(n["name"], 1))))
        if count <= 1:
            result.append(n)
            continue
        for i in range(count):
            sub = dict(n)
            sub["name"] = f"{n['name']} {_SPLIT_LABELS[i]}"
            for key in ("area_m2", "footprint_m2", "planned_area_m2"):
                if key in sub and sub[key]:
                    sub[key] = round(float(sub[key]) / count, 2)
            result.append(sub)
    return result


def _with_dimensions(node: dict, settings: dict) -> dict:
    n = dict(node)
    area = max(25.0, float(n["footprint_m2"]))
    aspect = max(0.75, min(2.6, float(n.get("target_aspect", 1.5)) * settings["aspect_bias"]))
    width = math.sqrt(area * aspect)
    depth = area / width

    max_ratio = 3.0
    if width / depth > max_ratio:
        width = math.sqrt(area * max_ratio)
        depth = area / width
    elif depth / width > max_ratio:
        depth = math.sqrt(area * max_ratio)
        width = area / depth

    n["breite"] = max(6.0, width)
    n["tiefe"] = max(6.0, depth)
    return n


def _connected_layout(
    *,
    nodes: list[dict],
    topology: dict,
    usable_w: float,
    usable_d: float,
    variante_key: str,
    raster_x: float,
    raster_y: float,
) -> list[Zone]:
    """Packt Nutzungen an eine zusammenhaengende Erschliessungsachse."""
    grid_x = 3.0
    grid_y = 3.0
    circulation_w = max(6.0, _snap(raster_y / 2, grid_y))
    margin = max(6.0, min(raster_x, raster_y) / 2)

    nodes = [_snap_node_dimensions(n, grid_x, grid_y) for n in nodes]
    node_map = {n["name"]: n for n in nodes}
    process_names = [name for name in topology.get("process_order", []) if name in node_map]
    process_nodes = [node_map[name] for name in process_names]
    other_nodes = [n for n in nodes if n["name"] not in process_names]

    corridor_y = _corridor_y(variante_key, usable_d, circulation_w, margin)
    above, below = _split_process_nodes(process_nodes, variante_key)

    zones: list[Zone] = []
    zones += _place_row(
        row=above,
        y=corridor_y + circulation_w,
        side="above",
        usable_w=usable_w,
        margin=margin,
        grid_x=grid_x,
        grid_y=grid_y,
    )
    zones += _place_row(
        row=below,
        y=corridor_y,
        side="below",
        usable_w=usable_w,
        margin=margin,
        grid_x=grid_x,
        grid_y=grid_y,
    )

    zones += _place_service_nodes(
        nodes=other_nodes,
        existing=zones,
        corridor_y=corridor_y,
        circulation_w=circulation_w,
        usable_w=usable_w,
        usable_d=usable_d,
        margin=margin,
        grid_x=grid_x,
        grid_y=grid_y,
    )

    return zones


# ---------------------------------------------------------------------------
# Squarified Treemap Layout (kein Optimizer, deterministische Flächen)
# ---------------------------------------------------------------------------

# DIN-Kategorie → Gruppe für die Streifen-Aufteilung
_DIN_ZU_GRUPPE_SQ: dict[str, str] = {
    "NUF 3": "halle",      # Produktion, Fertigung
    "NUF 4": "logistik",   # Lager, WE, Versand, Kommissionierung
    "NUF 2": "support",    # Büro, Verwaltung
    "NUF 7": "support",    # Sozial, Sanitär
    "TF":    "support",    # Technik
}


def _sq_worst_ar(fps: list[float], strip_dim: float, total_dim: float) -> float:
    s = sum(fps)
    if s <= 0:
        return 999.0
    worst = 0.0
    for fp in fps:
        frac = fp / s
        if strip_dim >= total_dim:
            bw, h_ = strip_dim * frac, total_dim
        else:
            bw, h_ = total_dim, strip_dim * frac
        worst = max(worst, max(bw, h_) / max(0.001, min(bw, h_)))
    return worst


def _sq_strip_place(fps: list[float], x: float, y: float,
                    w: float, h: float) -> list[tuple[float, float, float, float]]:
    if not fps:
        return []
    total = sum(fps)
    if w >= h:
        xc, result = x, []
        for fp in fps:
            cw = w * fp / total
            result.append((xc, y, cw, h))
            xc += cw
        return result
    else:
        yc, result = y, []
        for fp in fps:
            rh = h * fp / total
            result.append((x, yc, w, rh))
            yc += rh
        return result


def _linear_stack_zones(
    items: list[tuple[dict, float]],   # (node_dict, footprint_m2) IN GEWÜNSCHTER REIHENFOLGE
    x: float, y: float, w: float, h: float,
    direction: str = "vertical",
) -> list[tuple[dict, float, float, float, float]]:
    """Lineares Stapeln (kein Squarified). Garantiert Wandkontakt aller Nachbarn.

    direction="vertical"   → Zonen von oben nach unten gestapelt (teilt h auf)
    direction="horizontal" → Zonen von links nach rechts (teilt w auf)
    Die Reihenfolge der Items bleibt erhalten (kein Re-Sortieren!).
    """
    if not items:
        return []
    if len(items) == 1:
        n, fp = items[0]
        return [(n, x, y, w, h)]
    total_fp = sum(fp for _, fp in items)
    if total_fp <= 0:
        return [(n, x, y, w, h / len(items)) for n, _ in items]
    results = []
    cursor = y if direction == "vertical" else x
    for n, fp in items:
        frac = fp / total_fp
        if direction == "vertical":
            zh = h * frac
            results.append((n, x, cursor, w, zh))
            cursor += zh
        else:
            zw = w * frac
            results.append((n, cursor, y, zw, h))
            cursor += zw
    return results


def _sq_layout_zones(
    items: list[tuple[dict, float]],   # (node_dict, footprint_m2)
    x: float, y: float, w: float, h: float,
) -> list[tuple[dict, float, float, float, float]]:
    """Squarified Treemap. Gibt [(node, x, y, breite, tiefe)] zurück."""
    if not items:
        return []
    if len(items) == 1:
        n, fp = items[0]
        return [(n, x, y, w, h)]

    sorted_items = sorted(items, key=lambda t: t[1], reverse=True)
    total_fp = sum(fp for _, fp in sorted_items)
    results: list[tuple[dict, float, float, float, float]] = []
    remaining = list(sorted_items)
    cx, cy, cw, ch = x, y, w, h

    while remaining:
        strip: list[tuple[dict, float]] = []
        strip_fps: list[float] = []
        best_ar = float("inf")

        for item in remaining:
            _, fp = item
            cand_fps = strip_fps + [fp]
            frac = sum(cand_fps) / total_fp
            if cw >= ch:
                ar = _sq_worst_ar(cand_fps, cw * frac, ch)
            else:
                ar = _sq_worst_ar(cand_fps, ch * frac, cw)
            if ar <= best_ar:
                best_ar = ar
                strip.append(item)
                strip_fps.append(fp)
            else:
                break

        strip_fp = sum(fp for _, fp in strip)
        frac = strip_fp / total_fp

        if cw >= ch:
            sw = cw * frac
            for (n, _), pos in zip(strip, _sq_strip_place(strip_fps, cx, cy, sw, ch)):
                results.append((n, pos[0], pos[1], pos[2], pos[3]))
            cx += sw
            cw -= sw
        else:
            sh = ch * frac
            for (n, _), pos in zip(strip, _sq_strip_place(strip_fps, cx, cy, cw, sh)):
                results.append((n, pos[0], pos[1], pos[2], pos[3]))
            cy += sh
            ch -= sh

        total_fp -= strip_fp
        remaining = [it for it in remaining if it not in strip]

    return results


def _squarified_layout_main(
    nodes: list[dict],
    envelope: dict,
    variante_key: str,
    graph_weights: dict,
    process_order: list[str] | None = None,
    gap_strategy: str = "none",
) -> list[Zone]:
    """Drei-Varianten Squarified-Layout für Industriebau.

    Erzeugt deterministisch korrekte Flächen (0% Delta) ohne scipy-Optimizer.
    Verwendet Gruppen-Streifen: Halle | Logistik | Support.

    gap_strategy:
      "none"     — keine Lückenbehandlung (Original-Sortierung nach Adjazenz zur Halle)
      "sort"     — Prozessreihenfolge-Sortierung: pre-Halle links, post-Halle rechts
      "corridor" — Post-Layout Flur-Generator (Approach 3, nach Zonenerzeugung)
      "all"      — sort + corridor kombiniert
    """
    bx = float(envelope.get("x", 0))
    by = float(envelope.get("y", 0))
    bw = float(envelope["width_m"])
    bd = float(envelope["depth_m"])

    def _fp(n: dict) -> float:
        return float(n.get("footprint_m2") or
                     (n.get("planned_area_m2", 0) or n.get("area_m2", 0)) / max(1, n.get("floors", 1)))

    def _area(n: dict) -> float:
        return float(n.get("planned_area_m2") or n.get("area_m2", 0))

    # Nodes in Gruppen aufteilen.
    # Für NUF 3: nur die GRÖSSTE Zone = halle (Produktion), alle anderen = logistik (QS, etc.)
    nuf3_all: list[tuple[dict, float]] = []
    logistik: list[tuple[dict, float]] = []
    support:  list[tuple[dict, float]] = []
    rest:     list[tuple[dict, float]] = []

    for n in nodes:
        din = n.get("din_kategorie", "")
        item = (n, _fp(n))
        if din == "NUF 3":
            nuf3_all.append(item)
        elif din == "NUF 4":
            logistik.append(item)
        elif din in ("NUF 2", "NUF 7", "TF"):
            support.append(item)
        else:
            rest.append(item)  # VF, unbekannte → mit Logistik

    # Größte NUF-3-Zone = Halle; alle weiteren (z.B. QS) → Logistik
    nuf3_all.sort(key=lambda t: t[1], reverse=True)
    halle    = nuf3_all[:1]
    logistik = nuf3_all[1:] + logistik

    fp_hall = sum(fp for _, fp in halle)
    fp_log  = sum(fp for _, fp in logistik) + sum(fp for _, fp in rest)
    fp_sup  = sum(fp for _, fp in support)
    total_fp = fp_hall + fp_log + fp_sup
    if total_fp <= 0:
        return []

    logistik_all = logistik + rest

    # ── Sortierung logistik_all ───────────────────────────────────────────────
    # Standard: nach Adjazenzgewicht zur Halle (Materialfluss-Nähe)
    # "sort" / "all": nach Position in der Prozesskette (pre/post Halle)
    _proc_ord = list(process_order or [])  # z.B. ["Wareneingang", "Lager Rohstoffe", "Produktion", ...]

    if halle:
        halle_name = halle[0][0]["name"]

        def _adj_to_halle(item: tuple[dict, float]) -> float:
            n = item[0]
            return (graph_weights.get(f"{n['name']}|{halle_name}", 0) +
                    graph_weights.get(f"{halle_name}|{n['name']}", 0))

        if gap_strategy in ("sort", "all") and _proc_ord:
            # Prozessketten-Position: Index in process_order (unbekannte → hinten)
            def _proc_pos(item: tuple[dict, float]) -> int:
                name = item[0]["name"]
                try:
                    return _proc_ord.index(name)
                except ValueError:
                    return len(_proc_ord) + 99
            hall_idx = _proc_pos((halle[0][0], 0))
            # pre-Halle: position < hall_idx (sorted ascending → links/oben)
            # post-Halle: position > hall_idx (sorted ascending → erscheinen zuletzt)
            logistik_all = sorted(logistik_all, key=_proc_pos)
        else:
            logistik_all = sorted(logistik_all, key=_adj_to_halle, reverse=True)
    else:
        halle_name = ""

    # Gebäude füllt die gesamte Envelope — kein Skalieren, kein Zentrieren, keine Lücken.

    # Variantenspezifische Streifen-Aufteilung
    placements: list[tuple[dict, float, float, float, float]] = []

    # Gemeinsamer AR-Grenzwert: etwas unter 4.0 als Sicherheitspuffer
    _AR_LIM = 3.5

    # ── Hilfsfunktion: logistik_all in pre/post-Halle aufteilen ─────────────
    def _split_pre_post(items: list[tuple[dict, float]]) -> tuple[list, list]:
        """Teilt logistik_all in pre-Halle (vor Produktion) und post-Halle auf."""
        if not _proc_ord or not halle_name:
            return items, []
        try:
            hall_idx = _proc_ord.index(halle_name)
        except ValueError:
            return items, []
        pre, post = [], []
        for item in items:
            try:
                idx = _proc_ord.index(item[0]["name"])
                (pre if idx < hall_idx else post).append(item)
            except ValueError:
                post.append(item)  # unbekannte Zone → post
        return pre, post

    if variante_key == "A_Materialfluss":
        # Standard: Drei Spalten: Logistik | Halle | Support
        # "sort": Pre-Halle (lin. gestapelt) | Halle | Post-Halle+Support (lin. gestapelt)
        #         Garantiert: WE↔LagerR (linke Spalte), LagerR↔Halle (Spaltenwand),
        #                     Halle↔QS (Spaltenwand), QS↔LagerF↔Versand (rechte Spalte)
        max_sup_fp = max((fp for _, fp in support), default=0.0)
        # Mindestbreite Support-Spalte: größte Zone muss AR ≤ _AR_LIM einhalten.
        # Zonen-Höhe in Vollhöhen-Spalte = bd * max_fp / sum_fp → Breite ≥ Höhe / AR_LIM
        sup_w_min  = bd * max_sup_fp / max(1.0, fp_sup) / _AR_LIM if max_sup_fp > 0 else 0.0

        if gap_strategy in ("sort", "all") and _proc_ord:
            pre_halle, post_halle = _split_pre_post(logistik_all)
            # Prozessketten-Reihenfolge für lineares Stapeln sicherstellen
            def _sort_proc(items):
                return sorted(items, key=lambda it:
                    _proc_ord.index(it[0]["name"]) if it[0]["name"] in _proc_ord else 999)
            pre_sorted  = _sort_proc(pre_halle)
            post_sorted = _sort_proc(post_halle)

            fp_pre  = sum(fp for _, fp in pre_halle)
            fp_post = sum(fp for _, fp in post_halle)
            rem_total = fp_pre + fp_hall + fp_post + fp_sup

            # Vier Spalten: pre(linear) | Halle(sq) | post(linear) | support(sq)
            # Spaltenbreiten proportional zu Fläche; sup_w mindestens sup_w_min
            log_w       = bw * fp_pre  / max(1, rem_total)
            hall_w      = bw * fp_hall / max(1, rem_total)
            post_w_prop = bw * fp_post / max(1, rem_total)
            sup_w       = max(bw - log_w - hall_w - post_w_prop, sup_w_min)
            post_w      = max(bw - log_w - hall_w - sup_w, 1.0)  # Rest für Post-Spalte

            # Pre-Spalte: lineares Stapeln (nur 2 Zonen → immer benachbart).
            placements += _linear_stack_zones(pre_sorted, bx, by, log_w, bd)
            placements += _sq_layout_zones(halle, bx + log_w, by, hall_w, bd)

            # Post-Spalte: QS (erste Zone in Prozessreihenfolge nach Halle) erhält eine
            # Mindesthöhe von post_w/4, damit AR ≤ 4.0 garantiert ist.
            # Alle Post-Zonen teilen die linke Wand mit der Halle (x = bx+log_w+hall_w). ✓
            min_post_fp  = min(fp for _, fp in post_halle) if post_halle else 1.0
            nat_qs_h     = bd * min_post_fp / max(1.0, fp_post)
            qs_h         = min(max(nat_qs_h, post_w / 4.0), bd)
            post_x0      = bx + log_w + hall_w
            qs_zone, *rest_post = post_sorted
            placements.append((qs_zone[0], post_x0, by, post_w, qs_h))
            if rest_post:
                placements += _sq_layout_zones(rest_post, post_x0, by + qs_h,
                                               post_w, max(bd - qs_h, 0.1))
            placements += _sq_layout_zones(support, bx + log_w + hall_w + post_w, by, sup_w, bd)
        else:
            sup_w  = max(bw * fp_sup / total_fp, sup_w_min)
            rem_w  = bw - sup_w
            log_w  = rem_w * fp_log / max(1, fp_log + fp_hall)
            hall_w = rem_w - log_w
            placements += _sq_layout_zones(logistik_all, bx,                by, log_w,  bd)
            placements += _sq_layout_zones(halle,        bx + log_w,        by, hall_w, bd)
            placements += _sq_layout_zones(support,      bx + log_w + hall_w, by, sup_w,  bd)

    elif variante_key == "B_Erweiterbarkeit":
        # Halle oben (volle Breite) | Logistik links unten | Support rechts unten
        # ABER: Falls Halle als horizontaler Streifen AR > _AR_LIM hätte → Column-Orientierung
        hall_d = bd * fp_hall / total_fp
        fp_ls  = fp_log + fp_sup
        hall_ar_as_strip = bw / max(0.01, hall_d)
        if hall_ar_as_strip > _AR_LIM:
            # Orientierung wechseln: Halle als LINKE Spalte (volle Tiefe)
            hall_w  = bw * fp_hall / total_fp
            right_w = bw - hall_w
            log_d   = bd * fp_log / max(1, fp_ls)
            sup_d   = bd - log_d
            placements += _sq_layout_zones(halle, bx, by, hall_w, bd)
            if gap_strategy in ("sort", "all") and _proc_ord and fp_log > 0:
                # Column-Modus sort: horizontale Bänder rechts der Halle.
                # Pre-Halle-Band: letzte Prozesszone (LagerR) direkt adj. zu Halle ✓
                # Post-Halle-Band: erste Prozesszone (QS) direkt adj. zu Halle ✓
                pre_h_cm, post_h_cm = _split_pre_post(logistik_all)
                fp_pre_cm  = sum(fp for _, fp in pre_h_cm)
                fp_post_cm = sum(fp for _, fp in post_h_cm)
                log_pre_d  = log_d * fp_pre_cm  / max(1.0, fp_pre_cm + fp_post_cm)
                log_post_d = log_d - log_pre_d
                # Pre-Halle: umgekehrte Prozessreihenfolge → erste Zone (LagerR) ganz links (adj. Halle)
                pre_rev_cm = sorted(pre_h_cm, key=lambda it:
                    _proc_ord.index(it[0]["name"]) if it[0]["name"] in _proc_ord else 999, reverse=True)
                xc = bx + hall_w
                for n_cm, fp_cm in pre_rev_cm:
                    w_z = right_w * fp_cm / max(1.0, fp_pre_cm)
                    placements.append((n_cm, xc, by, w_z, log_pre_d))
                    xc += w_z
                # Post-Halle: Prozessreihenfolge → erste Zone (QS) ganz links (adj. Halle)
                post_proc_cm = sorted(post_h_cm, key=lambda it:
                    _proc_ord.index(it[0]["name"]) if it[0]["name"] in _proc_ord else 999)
                if post_proc_cm and fp_post_cm > 0:
                    first_fp_cm  = post_proc_cm[0][1]
                    nat_qs_w_cm  = right_w * first_fp_cm / max(1.0, fp_post_cm)
                    qs_w_cm      = min(max(nat_qs_w_cm, log_post_d / 4.0), right_w)
                    qs_n_cm, *rest_cm = post_proc_cm
                    placements.append((qs_n_cm[0], bx + hall_w, by + log_pre_d, qs_w_cm, log_post_d))
                    rem_fp_cm = fp_post_cm - first_fp_cm
                    xc = bx + hall_w + qs_w_cm
                    for n_cm, fp_cm in rest_cm:
                        w_z = (right_w - qs_w_cm) * fp_cm / max(1.0, rem_fp_cm)
                        placements.append((n_cm, xc, by + log_pre_d, w_z, log_post_d))
                        xc += w_z
                placements += _sq_layout_zones(support, bx + hall_w, by + log_d, right_w, sup_d)
            else:
                placements += _sq_layout_zones(logistik_all, bx + hall_w,      by,          right_w, log_d)
                placements += _sq_layout_zones(support,      bx + hall_w,      by + log_d,  right_w, sup_d)
        else:
            rest_d = bd - hall_d
            sup_w  = bw * fp_sup / max(1, fp_ls)
            log_w  = bw - sup_w
            if gap_strategy in ("sort", "all") and _proc_ord:
                # Logistik-Streifen in zwei Sub-Streifen: pre-Halle links, post-Halle rechts.
                # Beide erstrecken sich über die volle Streifen-Höhe (rest_d) →
                # alle Zonen berühren Halles Unterkante (Wandkontakt zu Prod). ✓
                pre_h_b, post_h_b = _split_pre_post(logistik_all)
                fp_pre_b  = sum(fp for _, fp in pre_h_b)
                fp_post_b = sum(fp for _, fp in post_h_b)
                pre_sw    = log_w * fp_pre_b  / max(1.0, fp_pre_b + fp_post_b)
                post_sw   = log_w - pre_sw

                placements += _sq_layout_zones(halle, bx, by, bw, hall_d)
                # Pre-Sub-Streifen: Squarified (WE+LagerR paarweise benachbart, AR-minimal)
                placements += _sq_layout_zones(pre_h_b, bx, by + hall_d, pre_sw, rest_d)

                # Post-Sub-Streifen: QS (erste Prozesszone nach Halle) als fixierte
                # obere Lage für Wandkontakt zu Halle; Rest squarified darunter.
                post_sorted_b = sorted(post_h_b, key=lambda it:
                    _proc_ord.index(it[0]["name"]) if it[0]["name"] in _proc_ord else 999)
                min_post_fp_b = min(fp for _, fp in post_h_b) if post_h_b else 1.0
                nat_qs_h_b    = rest_d * min_post_fp_b / max(1.0, fp_post_b)
                qs_h_b        = min(max(nat_qs_h_b, post_sw / 4.0), rest_d)
                post_x0_b     = bx + pre_sw
                qs_b, *rest_b = post_sorted_b
                placements.append((qs_b[0], post_x0_b, by + hall_d, post_sw, qs_h_b))
                if rest_b:
                    placements += _sq_layout_zones(rest_b, post_x0_b, by + hall_d + qs_h_b,
                                                   post_sw, max(rest_d - qs_h_b, 0.1))
                placements += _sq_layout_zones(support, bx + log_w, by + hall_d, sup_w, rest_d)
            else:
                placements += _sq_layout_zones(halle,        bx,          by,           bw,    hall_d)
                placements += _sq_layout_zones(logistik_all, bx,          by + hall_d,  log_w, rest_d)
                placements += _sq_layout_zones(support,      bx + log_w,  by + hall_d,  sup_w, rest_d)

    else:  # C_Ausgewogen
        # Halle rechts (volle Tiefe) | Alle anderen Zonen links (EINZEL-Spalte, voll Höhe)
        # "sort": Linke Spalte in zwei horizontale Bänder:
        #   - Pre-Halle (oben): Zonen links→rechts in Prozessreihenfolge → letzte Zone adj. Halle
        #   - Post-Halle (unten): Zonen rechts→links → letzte Prozesszone (QS) ganz rechts adj. Halle
        hall_w = bw * fp_hall / total_fp
        left_w = bw - hall_w
        fp_ls  = fp_log + fp_sup
        log_d  = bd * fp_log / max(1, fp_ls)
        sup_d  = bd - log_d

        if gap_strategy in ("sort", "all") and _proc_ord:
            pre_halle, post_halle = _split_pre_post(logistik_all)
            fp_pre  = sum(fp for _, fp in pre_halle)
            fp_post = sum(fp for _, fp in post_halle)
            log_pre_d  = log_d * fp_pre  / max(1.0, fp_pre + fp_post) if (fp_pre + fp_post) > 0 else log_d
            log_post_d = log_d - log_pre_d

            placements += _sq_layout_zones(halle, bx + left_w, by, hall_w, bd)

            # Pre-Halle: links→rechts in Prozessreihenfolge
            # → letzte Zone (LagerR) direkt adj. zur Hallen-Linkswand ✓
            if pre_halle and fp_pre > 0:
                pre_proc_c = sorted(pre_halle, key=lambda it:
                    _proc_ord.index(it[0]["name"]) if it[0]["name"] in _proc_ord else 999)
                xc = bx
                for n_c, fp_c in pre_proc_c:
                    w_z = left_w * fp_c / max(1.0, fp_pre)
                    placements.append((n_c, xc, by, w_z, log_pre_d))
                    xc += w_z

            # Post-Halle: links→rechts in UMGEKEHRTER Prozessreihenfolge
            # → letzte Prozesszone (QS, kleinste) ganz rechts adj. zur Halle, AR-gesichert ✓
            if post_halle and fp_post > 0:
                post_rev_c = sorted(post_halle, key=lambda it:
                    _proc_ord.index(it[0]["name"]) if it[0]["name"] in _proc_ord else 999, reverse=True)
                # post_rev_c = [Versand, LagerF, QS] — QS am Ende → rightmost (adj. Halle)
                qs_n_c  = post_rev_c[-1][0]
                qs_fp_c = post_rev_c[-1][1]
                nat_qs_w_c = left_w * qs_fp_c / max(1.0, fp_post)
                qs_w_c     = min(max(nat_qs_w_c, log_post_d / 4.0), left_w)
                rem_fp_c   = fp_post - qs_fp_c
                xc = bx
                for n_c, fp_c in post_rev_c[:-1]:   # alle außer QS: links→rechts
                    w_z = (left_w - qs_w_c) * fp_c / max(1.0, rem_fp_c)
                    placements.append((n_c, xc, by + log_pre_d, w_z, log_post_d))
                    xc += w_z
                placements.append((qs_n_c, bx + left_w - qs_w_c, by + log_pre_d, qs_w_c, log_post_d))

            placements += _sq_layout_zones(support, bx, by + log_d, left_w, sup_d)
        else:
            placements += _sq_layout_zones(halle,        bx + left_w, by,          hall_w, bd)
            placements += _sq_layout_zones(logistik_all, bx,          by,          left_w, log_d)
            placements += _sq_layout_zones(support,      bx,          by + log_d,  left_w, sup_d)

    # Placements → Zone-Objekte (keine Grid-Snapping, um Flächentreue zu erhalten)
    zones: list[Zone] = []
    for n, zx, zy, zw, zh in placements:
        area = _area(n)
        floors = int(n.get("floors", 1))
        planned = round(zw * zh * floors, 1)
        z = Zone(
            name=n["name"],
            x=round(zx, 2),
            y=round(zy, 2),
            breite=round(zw, 2),
            tiefe=round(zh, 2),
            flaeche_m2=area,
            din_kategorie=n.get("din_kategorie", "NUF 3"),
            farbe=n.get("farbe", "#CCCCCC"),
            floors=floors,
            planned_area_m2=planned,
        )
        z.delta_m2  = round(planned - area, 1)
        z.delta_pct = round((planned - area) / max(1, area) * 100, 1)
        zones.append(z)

    # Approach 3: Post-Layout VF-Korridore für kritische Adjacency-Lücken einfügen
    if gap_strategy in ("corridor", "all") and _proc_ord:
        zones = _insert_vf_corridors(zones, _proc_ord)

    return zones


def _insert_vf_corridors(zones: list[Zone], process_order: list[str]) -> list[Zone]:
    """Approach 3 — Flur-Generator.

    Sucht aufeinanderfolgende Zonen in der Prozesskette, die keine gemeinsame Wand
    haben, und fügt einen schmalen VF-Erschließungskorridor ein.

    Geometrie-Strategie (Sprint I):
    - Der Korridor wird an der Grenze einer der Prozessketten-Zonen platziert.
    - Jede Zone, die mit dem Korridor überlappt, wird um die Korridor-Breite
      zurückgeschoben ("von den Funktionsflächen abgezogen").
    - So entstehen keine überlappenden Zonen — der Korridor hat immer exklusiven Raum.

    Korridor-Breite: 3 m (Mindestgang DIN 18040 / ASR A1.8).
    Farbe: #7EC8E3 (helles Blau) — klar erkennbar, deutlich von Funktionszonen abgesetzt.
    """
    from app.tools.geometry import shared_wall as _sw

    CORRIDOR_W     = 3.0       # m Mindestgang-Breite
    CORRIDOR_COLOR = "#7EC8E3" # helles Blau — klar erkennbar
    MIN_WALL_TOL   = 0.5
    MIN_ZONE_SIZE  = CORRIDOR_W + 2.0  # Mindestgröße damit eine Zone getrimmt werden darf

    def _update_delta(z: Zone) -> None:
        """Aktualisiert delta_m2 / delta_pct nach einer Größenänderung."""
        plan = z.planned_area_m2 or z.flaeche_m2
        if plan and plan > 0:
            new_area = round(z.breite * z.tiefe, 1)
            z.delta_m2  = round(new_area - plan, 1)
            z.delta_pct = round((new_area - plan) / plan * 100, 1)

    def _trim_overlapping(new_zones: list[Zone], cor: Zone) -> None:
        """Schiebt jede Zone, die mit dem Korridor überlappt, um die Korridor-Dicke zurück.

        Erkennt vier Fälle anhand der gemeinsamen Kante:
          ↑ Zone beginnt an Korridor-Unterkante → Zone nach oben schieben (tiefe -)
          ↓ Zone endet  an Korridor-Oberkante  → Zone von oben kürzen   (tiefe -)
          → Zone beginnt an Korridor-Linkkante  → Zone nach rechts schieben (breite -)
          ← Zone endet  an Korridor-Rechtkante  → Zone von rechts kürzen   (breite -)
        """
        cx1, cx2 = cor.x, cor.x + cor.breite
        cy1, cy2 = cor.y, cor.y + cor.tiefe
        TOL = 0.5

        for z in new_zones:
            if z is cor or z.schraffur:
                continue
            # Überlappungs-Rechteck
            ox1 = max(cx1, z.x);       ox2 = min(cx2, z.x + z.breite)
            oy1 = max(cy1, z.y);       oy2 = min(cy2, z.y + z.tiefe)
            if ox2 - ox1 < 0.1 or oy2 - oy1 < 0.1:
                continue  # keine Überlappung

            # Fall 1: Zone startet an Korridor-Unterkante (z.y ≈ cor.y)
            if abs(z.y - cy1) < TOL and z.tiefe >= MIN_ZONE_SIZE:
                z.y     = round(z.y    + cor.tiefe, 2)
                z.tiefe = round(z.tiefe - cor.tiefe, 2)
                _update_delta(z)
                print(f"  [flur-trim] '{z.name}' nach oben verschoben um {cor.tiefe:.1f}m")
            # Fall 2: Zone endet an Korridor-Oberkante (z.y+tiefe ≈ cor.y+tiefe)
            elif abs((z.y + z.tiefe) - cy2) < TOL and z.tiefe >= MIN_ZONE_SIZE:
                z.tiefe = round(z.tiefe - cor.tiefe, 2)
                _update_delta(z)
                print(f"  [flur-trim] '{z.name}' von oben um {cor.tiefe:.1f}m gekürzt")
            # Fall 3: Zone startet an Korridor-Linkkante (z.x ≈ cor.x)
            elif abs(z.x - cx1) < TOL and z.breite >= MIN_ZONE_SIZE:
                z.x      = round(z.x     + cor.breite, 2)
                z.breite = round(z.breite - cor.breite, 2)
                _update_delta(z)
                print(f"  [flur-trim] '{z.name}' nach rechts verschoben um {cor.breite:.1f}m")
            # Fall 4: Zone endet an Korridor-Rechtkante (z.x+breite ≈ cor.x+breite)
            elif abs((z.x + z.breite) - cx2) < TOL and z.breite >= MIN_ZONE_SIZE:
                z.breite = round(z.breite - cor.breite, 2)
                _update_delta(z)
                print(f"  [flur-trim] '{z.name}' von rechts um {cor.breite:.1f}m gekürzt")

    zone_map = {z.name: z for z in zones}
    new_zones = list(zones)
    corridor_idx = 0

    for i in range(len(process_order) - 1):
        src_name = process_order[i]
        tgt_name = process_order[i + 1]
        if src_name not in zone_map or tgt_name not in zone_map:
            continue
        a = zone_map[src_name]
        b = zone_map[tgt_name]
        if _sw(a, b) >= MIN_WALL_TOL:
            continue   # bereits benachbart → kein Korridor nötig

        # Mittelpunkte und Hauptrichtung
        ax_mid = a.x + a.breite / 2
        ay_mid = a.y + a.tiefe / 2
        bx_mid = b.x + b.breite / 2
        by_mid = b.y + b.tiefe / 2
        dx = abs(bx_mid - ax_mid)
        dy = abs(by_mid - ay_mid)

        if dx >= dy:
            # ── Horizontale Lücke ─────────────────────────────────────────
            left_z  = a if a.x <= b.x else b
            right_z = b if a.x <= b.x else a

            # x-Überlappungsbereich (gemeinsame y-Fläche)
            ov_y1 = max(left_z.y, right_z.y)
            ov_y2 = min(left_z.y + left_z.tiefe, right_z.y + right_z.tiefe)
            if ov_y2 - ov_y1 < 1.0:
                continue  # keine y-Überlappung

            # Korridor an der Rechtkante der linken Zone platzieren
            cor_x = round(left_z.x + left_z.breite - CORRIDOR_W, 2)
            cor_y = round(ov_y1, 2)
            cor_w = CORRIDOR_W
            cor_h = round(ov_y2 - ov_y1, 2)
            if left_z.breite < MIN_ZONE_SIZE:
                continue  # zu schmal zum Trimmen
        else:
            # ── Vertikale Lücke ───────────────────────────────────────────
            bot_z = a if a.y <= b.y else b
            top_z = b if a.y <= b.y else a

            # x-Überlappungsbereich
            ov_x1 = max(bot_z.x, top_z.x)
            ov_x2 = min(bot_z.x + bot_z.breite, top_z.x + top_z.breite)
            if ov_x2 - ov_x1 < 1.0:
                continue  # keine x-Überlappung

            # Korridor an der Oberkante der unteren Zone platzieren
            cor_x = round(ov_x1, 2)
            cor_y = round(bot_z.y + bot_z.tiefe - CORRIDOR_W, 2)
            cor_w = round(ov_x2 - ov_x1, 2)
            cor_h = CORRIDOR_W
            if bot_z.tiefe < MIN_ZONE_SIZE:
                continue  # zu flach zum Trimmen

        corridor_idx += 1
        cor_name = f"Erschliessung {corridor_idx} ({src_name[:4]}-{tgt_name[:4]})"
        cor_area = round(cor_w * cor_h, 1)
        cor = Zone(
            name=cor_name,
            x=cor_x, y=cor_y,
            breite=round(cor_w, 2),
            tiefe=round(cor_h, 2),
            flaeche_m2=cor_area,
            din_kategorie="VF",
            farbe=CORRIDOR_COLOR,
            floors=1,
            planned_area_m2=cor_area,
        )
        cor.delta_m2  = 0.0
        cor.delta_pct = 0.0

        # Zonen, die mit dem Korridor überlappen, zurückschieben
        _trim_overlapping(new_zones, cor)

        new_zones.append(cor)
        zone_map[cor_name] = cor
        print(f"  [gap-corridor] {src_name} <-> {tgt_name}: "
              f"Korridor {cor_w:.1f}×{cor_h:.1f}m bei ({cor_x:.0f},{cor_y:.0f})")

    return new_zones




def _block_mit_reserve_layout(
    *,
    nodes: list[dict],
    topology: dict,
    zone_roles: dict[str, str],
    envelope: dict,
    settings: dict,
    raster_x: float,
    raster_y: float,
    freie_fassade_pct: float,
) -> list[Zone]:
    """Variante B: Kompakter Block links + schraffierte Erweiterungszone rechts.

    ┌────────────────┬────────────────────┐
    │  Kompakter     │   Erweiterungs-    │
    │  Block         │   reserve          │
    │  (alle Zonen)  │   (schraffiert)    │
    └────────────────┴────────────────────┘
    """
    grid = max(3.0, min(raster_x, raster_y) / 6)
    nodes = [_snap_node_dimensions(n, grid, grid) for n in nodes]
    node_map = {n["name"]: n for n in nodes}

    bx = envelope["x"]
    by = envelope["y"]
    bw = envelope["width_m"]
    bd = envelope["depth_m"]

    # Block-Zonen und Reserve-Zonen trennen
    # base_role normalisiert "reserve_1" / "block_2" → "reserve" / "block" (LLM-Index-Suffix)
    block_nodes: list[dict] = []
    for n in nodes:
        role = zone_roles.get(n["name"])
        base_role = role.split("_")[0] if role else None
        if base_role == "reserve":
            continue  # Reserve-Zone wird synthetisch erzeugt
        block_nodes.append(n)

    # Ziel-Grundfläche aus Briefing — Block darf nicht den ganzen Envelope füllen
    required_fp = sum(n["planned_area_m2"] / max(1, n.get("floors", 1)) for n in block_nodes)
    circulation_ratio = 0.09 + 0.05 * float(settings.get("process_pull", 1.0))
    target_fp = required_fp * (1.0 + circulation_ratio)
    target_fp = min(envelope.get("max_footprint_m2", bw * bd), target_fp)
    _, _, fit_bw, _ = _fit_rect_in_envelope(envelope, target_fp, grid, settings)

    total_footprint = sum(n["planned_area_m2"] / max(1, n.get("floors", 1)) for n in block_nodes)

    # Block-Breite: freie Fassade ist Preference; block darf nicht über die Grundstückstiefe hinaus wachsen.
    freie_fassade_pct = max(0.05, min(0.70, freie_fassade_pct))
    pref_block_w = _snap(min(fit_bw, bw * (1.0 - freie_fassade_pct)), grid)
    # Minimum block_w: alle Zonen müssen in die Grundstückstiefe (bd) passen
    min_block_w_fit = _snap(max(grid * 4, math.ceil(total_footprint / max(1.0, bd - grid))), grid)
    block_w = max(min_block_w_fit, pref_block_w)
    block_w = min(block_w, bw - grid * 2)
    block_w = max(grid * 4, block_w)
    reserve_w = max(grid * 2, bw - block_w)

    # Block-Höhe = volle Envelope-Tiefe (bd) → Block und Reserve-Zone deckungsgleich.
    # Ein schmaler Block (block_w) mit voller Höhe gibt bessere AR als ein quadratischer Block.
    # Geringfügig höhere Flächendeltas (~5%) sind akzeptabel; keine sichtbare Lücke an der Blockoberseite.
    block_h = bd

    zones: list[Zone] = []

    all_items = [(n, float(n["planned_area_m2"] / max(1, n.get("floors", 1)))) for n in block_nodes]
    all_placements = _sq_layout_zones(all_items, bx, by, block_w, block_h)
    zones = [
        _zone_from_node_with_rect(n, zx, zy, zw, zh, zw * zh * max(1, n.get("floors", 1)))
        for n, zx, zy, zw, zh in all_placements
    ]

    # Reserve-Zone: rechts, volle Envelope-Höhe (Erweiterungsreserve = gesamte Grundstückstiefe)
    reserve_x = bx + block_w
    reserve = Zone(
        name="Erweiterungsreserve",
        x=round(reserve_x, 2),
        y=round(by, 2),
        breite=round(reserve_w, 2),
        tiefe=round(bd, 2),
        flaeche_m2=round(reserve_w * bd, 2),
        din_kategorie="NUF 4",
        farbe="#AAAAAA",
        schraffur=True,
        planned_area_m2=round(reserve_w * bd, 2),
    )
    zones.append(reserve)

    # Überlappungscheck
    for i, a in enumerate(zones):
        for b in zones[i + 1:]:
            if _overlap(a, b) and a.name != b.name:
                print(f"[block_reserve_layout] Warnung: Überlappung zwischen '{a.name}' und '{b.name}'")

    return zones


def _sliced_building_layout(
    *,
    nodes: list[dict],
    topology: dict,
    layout_strategy: dict,
    layout_corrections: dict,
    envelope: dict,
    variante_key: str,
    settings: dict,
    raster_x: float,
    raster_y: float,
) -> list[Zone]:
    """Teilt ein zusammenhaengendes Gebaeuderechteck in Funktionsflaechen."""
    grid = _layout_grid(settings, layout_corrections, raster_x, raster_y)
    nodes = [_snap_node_dimensions(n, grid, grid) for n in nodes]
    node_map = {n["name"]: n for n in nodes}
    variant_strategy = (layout_strategy.get("variants") or {}).get(variante_key, {})
    strategy_sequence = variant_strategy.get("process_sequence") or topology.get("process_order", [])
    process = [node_map[n] for n in strategy_sequence if n in node_map]
    for n in topology.get("process_order", []):
        if n in node_map and n not in {p["name"] for p in process}:
            process.append(node_map[n])
    support = [n for n in nodes if n["name"] not in {p["name"] for p in process}]

    required_area = sum(n["planned_area_m2"] / max(1, n["floors"]) for n in nodes)
    circulation_ratio = 0.09 + 0.05 * float(settings.get("process_pull", 1.0))
    compactness = float(settings.get("compactness", 1.0))
    target_area = required_area * (1.0 + circulation_ratio)
    target_area *= 1.0 + max(0.0, 1.1 - compactness) * 0.08
    if settings.get("use_full_building_parcel"):
        bx = float(envelope["x"])
        by = float(envelope["y"])
        bw = float(envelope["width_m"])
        bd = float(envelope["depth_m"])
    else:
        target_area = min(envelope.get("max_footprint_m2", envelope["area_m2"]), target_area)
        bx, by, bw, bd = _fit_rect_in_envelope(envelope, target_area, grid, settings)

    circulation_h = max(6.0, _snap(raster_y / 2, grid))
    global_strategy = dict(layout_strategy.get("global") or {})
    if layout_corrections.get("tech_to_outer_edge"):
        global_strategy["tech_position"] = "outer_edge"
    if layout_corrections.get("office_away_from_logistics"):
        global_strategy["office_position"] = "north_west"
    bands = _bands_for_variant(process, support, variante_key, variant_strategy, global_strategy, settings)
    band_area_sum = sum(sum(n["planned_area_m2"] / max(1, n["floors"]) for n in band) for band in bands)
    available_h = max(circulation_h, bd - circulation_h)

    zones: list[Zone] = []
    y = by
    lower_bands, upper_bands = _split_bands_around_corridor(bands, variante_key, variant_strategy)
    for band in lower_bands:
        h = _band_height(band, band_area_sum, available_h, grid)
        zones += _split_band_to_zones(band, bx, y, bw, h)
        y += h

    # Korridor-Geometrie: y-Cursor vorwärts (keine Zone mehr)
    y += circulation_h

    for idx, band in enumerate(upper_bands):
        remaining_h = by + bd - y
        h = remaining_h if idx == len(upper_bands) - 1 else _band_height(band, band_area_sum, available_h, grid)
        zones += _split_band_to_zones(band, bx, y, bw, max(grid * 2, h))
        y += h

    return zones


def _layout_grid(settings: dict, layout_corrections: dict, raster_x: float, raster_y: float) -> float:
    if layout_corrections.get("snap_to_grid") or layout_corrections.get("increase_grid_alignment"):
        return max(3.0, min(raster_x, raster_y) / 2)
    if settings.get("grid_priority") == "high":
        return max(3.0, min(raster_x, raster_y) / 3)
    return 3.0


def _fit_rect_in_envelope(envelope: dict, target_area: float, grid: float, settings: dict) -> tuple[float, float, float, float]:
    max_w = envelope["width_m"]
    max_d = envelope["depth_m"]
    aspect = (max_w / max(1.0, max_d)) * float(settings.get("aspect_bias", 1.0))
    width = min(max_w, math.sqrt(target_area * aspect))
    depth = min(max_d, target_area / max(1.0, width))
    if depth > max_d:
        depth = max_d
        width = min(max_w, target_area / depth)
    width = max(grid * 4, math.floor(width / grid) * grid)
    depth = max(grid * 4, math.floor(depth / grid) * grid)
    x = envelope["x"] + (max_w - width) / 2
    y = envelope["y"] + (max_d - depth) / 2
    return round(x, 2), round(y, 2), round(width, 2), round(depth, 2)


def _bands_for_variant(
    process: list[dict],
    support: list[dict],
    variante_key: str,
    variant_strategy: dict,
    global_strategy: dict,
    settings: dict,
) -> list[list[dict]]:
    office_position = global_strategy.get("office_position", "south_west")
    tech_position = global_strategy.get("tech_position", "outer_edge")
    support_sorted = _sort_support_nodes(support, office_position, tech_position)
    typology = variant_strategy.get("typology")
    process_pull = float(settings.get("process_pull", 1.0))
    compactness = float(settings.get("compactness", 1.0))
    if process_pull >= 1.2 or variante_key == "A_Materialfluss" or typology == "linear_process":
        return [support_sorted, process]
    if compactness >= 1.1 or variante_key == "B_Erweiterbarkeit" or typology in {"compact_with_reserve", "split_process"}:
        split = max(1, math.ceil(len(process) / 2))
        return [support_sorted, process[:split], process[split:]]
    return [process[1::2] + support_sorted[:1], support_sorted[1:], process[::2]]


def _sort_support_nodes(support: list[dict], office_position: str, tech_position: str) -> list[dict]:
    def priority(node: dict) -> tuple[int, str]:
        name = node["name"]
        if "Büro" in name or "Buero" in name or name == "NOC":
            return (0 if "west" in office_position else 3, name)
        if name == "Sozial":
            return (1, name)
        if name == "Technik":
            return (4 if tech_position in {"east_edge", "outer_edge"} else -1, name)
        return (2, name)
    return sorted(support, key=priority)


def _split_bands_around_corridor(
    bands: list[list[dict]],
    variante_key: str,
    variant_strategy: dict,
) -> tuple[list[list[dict]], list[list[dict]]]:
    if len(bands) <= 1:
        return [], bands
    support_band = variant_strategy.get("support_band", "south")
    if support_band == "north":
        if variante_key == "C_Ausgewogen":
            return bands[:1], bands[1:]
        return bands[1:], bands[:1]
    if variante_key == "A_Materialfluss":
        return bands[:1], bands[1:]
    if variante_key == "B_Erweiterbarkeit":
        return bands[:1], bands[1:]
    return bands[:2], bands[2:]


def _band_height(band: list[dict], total_area: float, available_h: float, grid: float) -> float:
    if not band or total_area <= 0:
        return grid * 2
    area = sum(n["planned_area_m2"] / max(1, n["floors"]) for n in band)
    raw = available_h * area / total_area
    min_height = grid * 2
    if len(band) >= 3:
        min_height = max(min_height, grid * 4)
    if any((n["planned_area_m2"] / max(1, n["floors"])) <= 250 for n in band):
        min_height = max(min_height, grid * 3)
    return max(min_height, round(raw / grid) * grid)


def _split_band_to_zones(band: list[dict], x: float, y: float, width: float, height: float) -> list[Zone]:
    if not band:
        return []
    # Use briefing footprint_m2 so stacked zones (floors=2) don't inflate proportions.
    def _fp(n: dict) -> float:
        return float(n.get("footprint_m2") or n["planned_area_m2"] / max(1, n["floors"]))
    total_area = sum(_fp(n) for n in band) or float(len(band))
    ar_min = height / MAX_ASPECT_RATIO

    # Pass 1: proportional widths and per-zone minimums.
    # ar_min is enforced strictly for all zones (no cap at proportional share).
    # Pass 2 handles overflow by scaling non-bumped zones down.
    props = [width * _fp(n) / total_area for n in band]
    mins = [max(3.0, ar_min) for _ in props]
    widths = [max(p, m) for p, m in zip(props, mins)]

    # Pass 2: if bumped minimums cause the total to exceed `width`, scale free zones down.
    total_w = sum(widths)
    if total_w > width + 0.01:
        bumped = [widths[i] > props[i] + 0.001 for i in range(len(band))]
        fixed = sum(w for w, b in zip(widths, bumped) if b)
        available = width - fixed
        free_total = sum(w for w, b in zip(widths, bumped) if not b)
        if available > 0 and free_total > 0:
            scale = available / free_total
            widths = [max(3.0, w * scale) if not b else w for w, b in zip(widths, bumped)]
    elif total_w < width - 0.01:
        scale = width / total_w
        widths = [w * scale for w in widths]

    # Build zones; last zone takes exact remainder to avoid floating-point drift.
    zones = []
    cursor = x
    for idx, (node, w) in enumerate(zip(band, widths)):
        if idx == len(band) - 1:
            w = x + width - cursor
        planned = w * height * max(1, node["floors"])
        zones.append(_zone_from_node_with_rect(node, cursor, y, w, height, planned))
        cursor += w
    return zones


def _zone_from_node_with_rect(node: dict, x: float, y: float, width: float, height: float, planned_area: float) -> Zone:
    delta = planned_area - node["area_m2"]
    delta_pct = (delta / node["area_m2"]) * 100 if node["area_m2"] else 0
    return Zone(
        name=node["name"],
        x=round(x, 2),
        y=round(y, 2),
        breite=round(width, 2),
        tiefe=round(height, 2),
        flaeche_m2=node["area_m2"],
        din_kategorie=node["din_kategorie"],
        farbe=node["farbe"],
        floors=node["floors"],
        planned_area_m2=round(planned_area, 2),
        delta_m2=round(delta, 2),
        delta_pct=round(delta_pct, 1),
    )


def _snap_node_dimensions(node: dict, grid_x: float, grid_y: float) -> dict:
    n = dict(node)
    width = max(grid_x * 2, round(n["breite"] / grid_x) * grid_x)
    depth = max(grid_y * 2, round(n["tiefe"] / grid_y) * grid_y)
    n["breite"] = width
    n["tiefe"] = depth
    n["planned_area_m2"] = round(width * depth * max(1, n.get("floors", 1)), 2)
    n["delta_m2"] = round(n["planned_area_m2"] - n["area_m2"], 2)
    n["delta_pct"] = round((n["delta_m2"] / n["area_m2"]) * 100, 1) if n["area_m2"] else 0.0
    return n


def _corridor_y(variante_key: str, usable_d: float, circulation_w: float, margin: float) -> float:
    if variante_key == "A_Materialfluss":
        raw = usable_d * 0.38
    elif variante_key == "B_Erweiterbarkeit":
        raw = usable_d * 0.46
    else:
        raw = usable_d * 0.43
    return max(margin, min(usable_d - margin - circulation_w, raw))


def _split_process_nodes(process_nodes: list[dict], variante_key: str) -> tuple[list[dict], list[dict]]:
    if variante_key == "A_Materialfluss":
        return process_nodes, []
    if variante_key == "B_Erweiterbarkeit":
        split = max(1, math.ceil(len(process_nodes) / 2))
        return process_nodes[:split], list(reversed(process_nodes[split:]))
    above = process_nodes[::2]
    below = process_nodes[1::2]
    return above, below


def _place_row(
    *,
    row: list[dict],
    y: float,
    side: str,
    usable_w: float,
    margin: float,
    grid_x: float,
    grid_y: float,
) -> list[Zone]:
    if not row:
        return []
    gap = grid_x
    total_w = sum(n["breite"] for n in row) + gap * (len(row) - 1)
    x = max(margin, (usable_w - total_w) / 2)
    zones = []
    for n in row:
        zone_y = y if side == "above" else y - n["tiefe"]
        zones.append(_zone_from_node(n, x, max(0.0, zone_y)))
        x += n["breite"] + gap
    return zones


def _place_service_nodes(
    *,
    nodes: list[dict],
    existing: list[Zone],
    corridor_y: float,
    circulation_w: float,
    usable_w: float,
    usable_d: float,
    margin: float,
    grid_x: float,
    grid_y: float,
) -> list[Zone]:
    placed = []
    ordered = sorted(nodes, key=lambda n: (n.get("height_class") != "low", n["area_m2"]))
    candidate_slots = []
    x = margin
    while x < usable_w - margin:
        candidate_slots.append((x, max(0.0, corridor_y - grid_y)))
        candidate_slots.append((x, min(usable_d, corridor_y + circulation_w)))
        x += grid_x * 2
    candidate_slots += [
        (margin, margin),
        (usable_w - margin, margin),
        (margin, usable_d - margin),
        (usable_w - margin, usable_d - margin),
    ]

    for n in ordered:
        best = None
        if n.get("external_edge"):
            edge_x = 0 if n.get("name") == "Technik" else usable_w - n["breite"]
            best = _try_service_position(n, edge_x, corridor_y + circulation_w, existing + placed, usable_w, usable_d)
            if not best:
                best = _try_service_position(n, edge_x, corridor_y - n["tiefe"], existing + placed, usable_w, usable_d)
        if not best:
            for cx, cy in candidate_slots:
                y = cy if cy >= corridor_y else cy - n["tiefe"]
                candidate = _try_service_position(n, cx, y, existing + placed, usable_w, usable_d)
                if candidate:
                    best = candidate
                    break
        if not best:
            best = _zone_from_node(n, margin, max(0.0, corridor_y - n["tiefe"]))
        placed.append(best)
    return placed


def _try_service_position(n: dict, x: float, y: float, occupied: list[Zone], usable_w: float, usable_d: float) -> Zone | None:
    x = max(0.0, min(usable_w - n["breite"], x))
    y = max(0.0, min(usable_d - n["tiefe"], y))
    candidate = _zone_from_node(n, x, y)
    if any(_overlap(candidate, other) for other in occupied):
        return None
    return candidate


def _layout_span(zones: list[Zone], margin: float, usable_w: float) -> tuple[float, float]:
    if not zones:
        return margin, usable_w - margin
    x0 = max(0.0, min(z.x for z in zones) - margin / 2)
    x1 = min(usable_w, max(z.x + z.breite for z in zones) + margin / 2)
    return x0, x1


def _zone_from_node(node: dict, x: float, y: float) -> Zone:
    return Zone(
        name=node["name"],
        x=round(x, 2),
        y=round(y, 2),
        breite=round(node["breite"], 2),
        tiefe=round(node["tiefe"], 2),
        flaeche_m2=node["area_m2"],
        din_kategorie=node["din_kategorie"],
        farbe=node["farbe"],
        floors=node["floors"],
        planned_area_m2=node.get("planned_area_m2"),
        delta_m2=node.get("delta_m2", 0.0),
        delta_pct=node.get("delta_pct", 0.0),
    )


def _initial_positions(
    nodes: list[dict],
    topology: dict,
    site_geometry: dict | None,
    usable_w: float,
    usable_d: float,
    variante_key: str,
    rng: random.Random,
) -> dict[str, tuple[float, float]]:
    process_order = topology.get("process_order", [])
    node_map = {n["name"]: n for n in nodes}
    positions = {}
    access_targets = _access_targets(site_geometry, usable_w, usable_d)

    for i, name in enumerate(process_order):
        if name not in node_map:
            continue
        n = node_map[name]
        t = i / max(1, len(process_order) - 1)
        if variante_key == "A_Materialfluss":
            cx = usable_w * (0.12 + 0.76 * t)
            cy = usable_d * (0.62 + 0.08 * math.sin(t * math.pi))
        elif variante_key == "B_Erweiterbarkeit":
            cx = usable_w * (0.24 + 0.44 * (i % 3) / 2)
            cy = usable_d * (0.66 - 0.26 * (i // 3))
        else:
            cx = usable_w * (0.20 + 0.58 * t)
            cy = usable_d * (0.70 - 0.28 * t)
        positions[name] = (cx - n["breite"] / 2, cy - n["tiefe"] / 2)

    for n in nodes:
        if n["name"] in positions:
            continue
        target = _role_target(n, access_targets, usable_w, usable_d)
        if target:
            cx, cy = target
        elif n.get("height_class") == "low":
            cx = usable_w * rng.uniform(0.12, 0.42)
            cy = usable_d * rng.uniform(0.10, 0.32)
        elif n.get("external_edge"):
            cx = usable_w * rng.choice([0.12, 0.82])
            cy = usable_d * rng.uniform(0.18, 0.82)
        else:
            cx = usable_w * rng.uniform(0.20, 0.75)
            cy = usable_d * rng.uniform(0.25, 0.80)
        positions[n["name"]] = (cx - n["breite"] / 2, cy - n["tiefe"] / 2)
    return positions


def _relax_positions(
    nodes: list[dict],
    edges: list[dict],
    positions: dict[str, tuple[float, float]],
    usable_w: float,
    usable_d: float,
    settings: dict,
) -> dict[str, tuple[float, float]]:
    node_map = {n["name"]: n for n in nodes}
    center = (usable_w * 0.43, usable_d * 0.52)

    for _ in range(90):
        deltas = {n["name"]: [0.0, 0.0] for n in nodes}
        for edge in edges:
            a = node_map.get(edge["source"])
            b = node_map.get(edge["target"])
            if not a or not b:
                continue
            ax, ay = _center(a, positions[a["name"]])
            bx, by = _center(b, positions[b["name"]])
            dx, dy = bx - ax, by - ay
            dist = max(1.0, math.hypot(dx, dy))
            weight = float(edge["weight"])
            target = (a["breite"] + b["breite"] + a["tiefe"] + b["tiefe"]) * (0.18 if weight > 0 else 0.9)
            force = (dist - target) / dist * 0.025 * abs(weight)
            if weight < 0:
                force *= -1.2
            if edge.get("kind") == "process":
                force *= settings["process_pull"]
            deltas[a["name"]][0] += dx * force
            deltas[a["name"]][1] += dy * force
            deltas[b["name"]][0] -= dx * force
            deltas[b["name"]][1] -= dy * force

        for n in nodes:
            x, y = positions[n["name"]]
            cx, cy = _center(n, (x, y))
            compact = settings["compactness"] * 0.008
            deltas[n["name"]][0] += (center[0] - cx) * compact
            deltas[n["name"]][1] += (center[1] - cy) * compact
            if n.get("external_edge"):
                nearest_x = 0 if cx < usable_w / 2 else usable_w
                deltas[n["name"]][0] += (nearest_x - cx) * settings["edge_pull"] * 0.012

        for n in nodes:
            x, y = positions[n["name"]]
            x += deltas[n["name"]][0]
            y += deltas[n["name"]][1]
            positions[n["name"]] = _clamp_rect(x, y, n, usable_w, usable_d)

    return positions


def _resolve_overlaps(nodes: list[dict], positions: dict[str, tuple[float, float]], usable_w: float, usable_d: float):
    for _ in range(120):
        moved = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                ax, ay = positions[a["name"]]
                bx, by = positions[b["name"]]
                ox = min(ax + a["breite"], bx + b["breite"]) - max(ax, bx)
                oy = min(ay + a["tiefe"], by + b["tiefe"]) - max(ay, by)
                if ox <= 0 or oy <= 0:
                    continue
                moved = True
                ac = _center(a, (ax, ay))
                bc = _center(b, (bx, by))
                sx = 1 if ac[0] <= bc[0] else -1
                sy = 1 if ac[1] <= bc[1] else -1
                if ox < oy:
                    shift = (ox / 2) + 0.8
                    ax -= sx * shift
                    bx += sx * shift
                else:
                    shift = (oy / 2) + 0.8
                    ay -= sy * shift
                    by += sy * shift
                positions[a["name"]] = _clamp_rect(ax, ay, a, usable_w, usable_d)
                positions[b["name"]] = _clamp_rect(bx, by, b, usable_w, usable_d)
        if not moved:
            break
    return positions


def _repair_remaining_overlaps(zones: list[Zone], usable_w: float, usable_d: float, raster_x: float, raster_y: float) -> list[Zone]:
    fixed: list[Zone] = []
    for zone in sorted(zones, key=lambda z: z.flaeche_m2, reverse=True):
        if not any(_overlap(zone, other) for other in fixed):
            fixed.append(zone)
            continue
        placed = False
        step_x = max(6.0, raster_x / 2)
        step_y = max(6.0, raster_y / 2)
        y = 0.0
        while y <= max(0.0, usable_d - zone.tiefe) and not placed:
            x = 0.0
            while x <= max(0.0, usable_w - zone.breite):
                candidate = Zone(zone.name, x, y, zone.breite, zone.tiefe, zone.flaeche_m2, zone.din_kategorie, zone.farbe, zone.schraffur, zone.floors)
                if not any(_overlap(candidate, other) for other in fixed):
                    fixed.append(candidate)
                    placed = True
                    break
                x += step_x
            y += step_y
        if not placed:
            fixed.append(zone)
    return fixed


def _access_targets(site_geometry: dict | None, usable_w: float, usable_d: float) -> dict[str, tuple[float, float]]:
    targets = {}
    if not site_geometry:
        return targets
    access_points = site_geometry.get("access_points") or []
    for idx, access in enumerate(access_points):
        point = access["point"]
        x = min(float(point[0]), usable_w)
        y = min(float(point[1]), usable_d)
        role = "inbound" if idx == 0 else "outbound"
        targets[role] = (x, y)
    if access_points:
        x, y = access_points[0]["point"]
        targets["visitor"] = (min(float(x), usable_w), min(float(y), usable_d))
        targets["utility"] = (min(float(x), usable_w), min(float(y), usable_d))
    return targets


def _role_target(node: dict, access_targets: dict, usable_w: float, usable_d: float) -> tuple[float, float] | None:
    role = node.get("access_role")
    if role and role in access_targets:
        x, y = access_targets[role]
        inset = 10.0
        return (
            max(inset, min(usable_w - inset, x)),
            max(inset, min(usable_d - inset, y)),
        )
    return None


def _center(node: dict, pos: tuple[float, float]) -> tuple[float, float]:
    return pos[0] + node["breite"] / 2, pos[1] + node["tiefe"] / 2


def _clamp_rect(x: float, y: float, node: dict, usable_w: float, usable_d: float) -> tuple[float, float]:
    return (
        max(0.0, min(usable_w - node["breite"], x)),
        max(0.0, min(usable_d - node["tiefe"], y)),
    )


def _overlap(a: Zone, b: Zone) -> bool:
    eps = 0.05  # 5 cm tolerance for floating-point boundary touches
    return not (
        a.x + a.breite <= b.x + eps or
        b.x + b.breite <= a.x + eps or
        a.y + a.tiefe <= b.y + eps or
        b.y + b.tiefe <= a.y + eps
    )


def _snap(value: float, grid: float) -> float:
    if grid <= 0:
        return value
    return round(value / grid) * grid


def _append_freif_zones(
    zones: list[Zone], scaled_env: dict, raw_env: dict
) -> list[Zone]:
    """Füllt den Leerraum zwischen skaliertem Gebäude-Envelope und rohem Baufeld
    mit schraffierten 'Freifläche'-Zonen. Verhindert die sichtbare Fuge im Grundriss.

    Erzeugt maximal zwei Streifen (rechts + oben), die sich nicht überlappen:
    - Rechter Streifen: volle Höhe des Baufelds
    - Oberer Streifen: Breite des skalierten Envelopes (kein Overlap mit rechtem Streifen)
    """
    if not raw_env:
        return zones
    scaled_right = scaled_env["x"] + scaled_env["width_m"]
    raw_right     = raw_env["x"]   + raw_env["width_m"]
    scaled_top    = scaled_env["y"] + scaled_env["depth_m"]
    raw_top       = raw_env["y"]   + raw_env["depth_m"]
    gap_w = round(raw_right - scaled_right, 2)
    gap_h = round(raw_top   - scaled_top,   2)
    if gap_w < 0.5 and gap_h < 0.5:
        return zones  # kein Leerraum — keine Zonen nötig

    extra: list[Zone] = []
    if gap_w >= 0.5:
        # Rechter Streifen (volle Höhe des Baufelds)
        extra.append(Zone(
            name="Freifläche",
            x=scaled_right,
            y=raw_env["y"],
            breite=gap_w,
            tiefe=raw_env["depth_m"],
            flaeche_m2=round(gap_w * raw_env["depth_m"], 1),
            din_kategorie="AF",
            farbe="#D8E4C8",
            schraffur=True,
        ))
    if gap_h >= 0.5:
        # Oberer Streifen (Breite des skalierten Envelopes, kein Overlap mit rechtem Streifen)
        extra.append(Zone(
            name="Freifläche",
            x=scaled_env["x"],
            y=scaled_top,
            breite=scaled_env["width_m"],
            tiefe=gap_h,
            flaeche_m2=round(scaled_env["width_m"] * gap_h, 1),
            din_kategorie="AF",
            farbe="#D8E4C8",
            schraffur=True,
        ))
    return zones + extra


def _skaliere_envelope_auf_briefing(
    envelope: dict, nodes: list[dict], raster_x: float, raster_y: float
) -> dict:
    """Verkleinert den Envelope so dass Flächendeltas unter ~15% bleiben.

    Verhindert d+28%-Situationen wenn das Grundstück-Envelope deutlich größer
    ist als das Raumprogramm (häufig bei unregelmaessigen Polygonen).
    Trigger: envelope > total_fp * 1.10 * 1.05  (5% Toleranz über 10% Puffer)
    """
    total_fp = sum(float(n.get("footprint_m2") or n.get("area_m2") or 0) for n in nodes)
    if total_fp <= 0:
        return envelope

    # 10 % Puffer für Erschließung, Wände, Korridor (VF ist eigene Zone, braucht keinen grossen Puffer)
    total_fp_mit_puffer = total_fp * 1.10
    env_area = float(envelope.get("area_m2") or
                     envelope["width_m"] * envelope["depth_m"])

    if env_area <= total_fp_mit_puffer * 1.05:
        return envelope  # Envelope passt — kein Eingriff (≤15.5% Überschuss OK)

    # Ziel: envelope auf total_fp * 1.10 skalieren (10% Puffer)
    scale = math.sqrt(total_fp_mit_puffer / env_area)
    grid = min(raster_x, raster_y) / 3
    new_w = max(grid * 6, math.ceil(envelope["width_m"] * scale / grid) * grid)
    new_d = max(grid * 6, math.ceil(envelope["depth_m"] * scale / grid) * grid)

    # Kein Offset — Gebäude beginnt an der Südwest-Ecke des Baufeldes (keine Lücke).
    return {
        **envelope,
        "x":               envelope["x"],
        "y":               envelope["y"],
        "width_m":         round(new_w, 2),
        "depth_m":         round(new_d, 2),
        "area_m2":         round(new_w * new_d, 2),
        "max_footprint_m2": round(min(float(envelope.get("max_footprint_m2") or new_w * new_d), new_w * new_d), 2),
    }


def _zone_zu_dict(z: Zone) -> dict:
    return {
        "name": z.name,
        "x": z.x,
        "y": z.y,
        "breite": z.breite,
        "tiefe": z.tiefe,
        "flaeche_m2": z.flaeche_m2,
        "din_kategorie": z.din_kategorie,
        "farbe": z.farbe,
        "schraffur": z.schraffur,
        "floors": z.floors,
        "planned_area_m2": z.planned_area_m2,
        "delta_m2": z.delta_m2,
        "delta_pct": z.delta_pct,
    }

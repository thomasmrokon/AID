"""
AID Demo - Evaluation-Agent.

Bewertet Varianten deterministisch und nutzt optional ein LLM als
Compliance-Waechter gegen das YAML-Regelset.
"""

from __future__ import annotations

import json
import math
import re
import yaml
from pathlib import Path

from app.llm import invoke_messages, is_llm_configured
from app.state import PlanningState
from app.tools.geometry import Zone
from app.tools.scoring import bewerte_variante


def evaluation_agent(state: PlanningState) -> dict:
    """LangGraph-Node: Varianten bewerten und beste Variante bestimmen."""
    variants = state["variants"]
    rules = state["rules"]
    briefing = state["structured_briefing"]
    nutzungstyp = briefing["nutzungstyp"]

    reasoning_log = list(state.get("reasoning_log") or [])
    planning_decisions = list(state.get("planning_decisions") or [])
    evaluations = []
    all_compliance_issues: list[dict] = []

    site_geometry = state.get("site_geometry") or {}
    site_area_m2 = float(site_geometry.get("area_m2") or 0) or None
    tragwerk_config = state.get("tragwerk_config") or {}
    topology_diagram = state.get("topology_diagram")

    for v in variants:
        zonen = [Zone(**z) for z in v["zonen"]]
        g = v["gewichtung"]
        optimization_result = _optimization_result_for_variant(v)

        score = bewerte_variante(
            variante_name=v["name"],
            zonen=zonen,
            nutzungstyp=nutzungstyp,
            gewichtung=g,
            rules=rules,
            site_breite=v["site_breite"],
            site_tiefe=v["site_tiefe"],
            site_area_m2=site_area_m2,
            optimization_result=optimization_result,
            topology_diagram=topology_diagram,
        )

        score_dict = score.als_dict()
        score_dict["flaechendeltas"] = _flaechendeltas(zonen)
        score_dict["flaechendelta_sum_abs_m2"] = round(
            sum(abs(d["delta_m2"]) for d in score_dict["flaechendeltas"]), 2
        )
        score_dict.update(_optimizer_metrics(optimization_result))

        # Neuer Tragwerks-Score (0.0 - 1.0)
        kompatibel = 0
        valid_zonen = [z for z in zonen if not z.schraffur and z.din_kategorie != 'VF']
        if not valid_zonen:
            valid_zonen = zonen
        raster_x = float(v.get("raster_x", 1.0))
        for z in valid_zonen:
            if (z.breite % raster_x) < (raster_x * 0.25):
                kompatibel += 1
        raster_score = kompatibel / max(1, len(valid_zonen))

        lk = tragwerk_config.get("lastklasse", "")
        kran_req = briefing.get("kranbahn_erforderlich", False)
        hochregal = briefing.get("hochregallager", False)
        lk_score = 1.0
        if kran_req and lk != "kran":        lk_score -= 0.5
        if lk == "kran" and not kran_req:    lk_score -= 0.5
        if hochregal and lk != "schwer":     lk_score -= 0.5
        if nutzungstyp == "Data Center" and lk != "schwer": lk_score -= 0.5
        lk_score = max(0.0, lk_score)

        th_score = 1.0
        try:
            _tw_path = Path(__file__).parent.parent / "data" / "rules_tragwerk.yaml"
            with open(_tw_path, encoding="utf-8") as f:
                tw_rules = yaml.safe_load(f)
            th = float(tw_rules.get("typologien", {}).get(
                tragwerk_config.get("typologie", ""), {}).get("traufhoehe_standard_m", 0))
            if nutzungstyp == "Data Center" and th < 7.0:  th_score -= 0.5
            if hochregal and th < 18.0:                    th_score -= 0.5
        except Exception:
            pass
        th_score = max(0.0, th_score)

        score_dict["tragwerk_score"] = round((raster_score + lk_score + th_score) / 3.0, 2)

        # Gesamtscore neu berechnen — tragwerk_score wurde oben überschrieben,
        # der Wert aus bewerte_variante() ist veraltet.
        _tw = score_dict["tragwerk_score"]
        _mf = score_dict.get("materialfluss_score", 0.0)
        _eb = score_dict.get("erweiterbarkeit_score", 0.0)
        score_dict["gesamtscore"] = round(
            g.get("materialfluss", 0.0) * _mf
            + g.get("erweiterbarkeit", 0.0) * _eb
            + g.get("tragwerk", 0.0) * _tw,
            2,
        )

        metadata = _layout_metadata(v, zonen)
        compliance_issues = compliance_check(
            variante=v["name"],
            metadata=metadata,
            rules=rules,
            briefing=briefing,
        )
        if compliance_issues:
            score_dict["regelverletzungen"] = list(score_dict.get("regelverletzungen") or [])
            for issue in compliance_issues:
                score_dict["regelverletzungen"].append(
                    f"{issue.get('severity', 'info').upper()}: "
                    f"{issue.get('message')} ({issue.get('rule_ref')})"
                )
        score_dict["compliance_issues"] = compliance_issues
        all_compliance_issues.extend(compliance_issues)

        # ── Entscheidungsprotokoll: Bewertung ─────────────────────────────────
        for kriterium, score_key, gew_key in [
            ("Materialfluss",   "materialfluss_score",   "materialfluss"),
            ("Erweiterbarkeit", "erweiterbarkeit_score", "erweiterbarkeit"),
            ("Tragwerk",        "tragwerk_score",        "tragwerk"),
        ]:
            kr_score = score_dict.get(score_key, 0.0)
            kr_gew   = g.get(gew_key, 0.0)
            planning_decisions.append({
                "agent":      "evaluation",
                "variante":   v["name"],
                "kategorie":  "Bewertung",
                "zone":       None,
                "aktion":     f"{kriterium}: {kr_score:.1f}/10 (Gewichtung {kr_gew:.0%})",
                "begruendung": (
                    f"Beitrag zum Gesamtscore: {kr_score * kr_gew:.2f} Punkte. "
                    + (f"{len(compliance_issues)} Compliance-Hinweis(e)."
                       if kriterium == "Tragwerk" and compliance_issues else "")
                ),
                "wert":       {"score": kr_score, "gewichtung": kr_gew, "beitrag": round(kr_score * kr_gew, 3)},
                "regel_ref":  f"scoring.{gew_key}",
            })

        evaluations.append(score_dict)
        reasoning_log.append({
            "agent":       "evaluation_agent",
            "disziplin":   "Bewertung",
            "variante":    v["name"],
            "entscheidung": (
                f"MF={score.materialfluss_score:.1f} "
                f"EB={score.erweiterbarkeit_score:.1f} "
                f"TW={score.tragwerk_score:.1f} "
                f"-> Gesamt={score.gesamtscore:.1f}"
            ),
            "begruendung": f"{len(compliance_issues)} Compliance-Hinweise",
            "regelref":    "scoring.bewerte_variante",
        })
        print(
            f"[evaluation] {v['name']:20s}  "
            f"MF={score.materialfluss_score:.1f}  "
            f"EB={score.erweiterbarkeit_score:.1f}  "
            f"TW={score.tragwerk_score:.1f}  "
            f"-> Gesamt={score.gesamtscore:.1f}"
        )

    best = max(evaluations, key=lambda e: e["gesamtscore"])
    best["empfohlen"] = True
    reasoning_log.append({
        "agent":       "evaluation_agent",
        "disziplin":   "Empfehlung",
        "variante":    best["variante"],
        "entscheidung": f"Variante {best['variante']} empfohlen (Gesamt={best['gesamtscore']:.1f})",
        "begruendung": "Hoechster gewichteter Gesamtscore",
        "regelref":    "scoring.max_gesamtscore",
    })

    print(f"[evaluation] Empfehlung: {best['variante']}")

    current_iteration = int(state.get("layout_iteration") or 0)
    layout_corrections = _corrections_from_issues(all_compliance_issues)
    needs_refinement = bool(all_compliance_issues) and bool(layout_corrections) and current_iteration < 1

    return {
        "evaluations":          evaluations,
        "selected_variant":     best["variante"],
        "compliance_issues":    all_compliance_issues,
        "layout_corrections":   layout_corrections if needs_refinement else {},
        "layout_iteration":     current_iteration + 1 if needs_refinement else current_iteration,
        "needs_layout_refinement": needs_refinement,
        "reasoning_log":        reasoning_log,
        "planning_decisions":   planning_decisions,
    }


def compliance_check(variante: str, metadata: dict, rules: dict, briefing: dict) -> list[dict]:
    """Prueft Layout-Metadaten regelbasiert und optional mit LLM."""
    deterministic = _deterministic_compliance_check(variante, metadata, rules)
    if not is_llm_configured():
        return deterministic

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = invoke_messages([
            SystemMessage(content=(
                "Du bist Compliance-Waechter fuer Industriebau-Layouts. "
                "Pruefe ausschliesslich die gelieferten Layout-Metadaten gegen das YAML-Regelset. "
                "Nutze das LLM nicht zum Zeichnen. Jede Beanstandung muss einen konkreten rule_ref "
                "aus dem Regelset oder briefing.sonderbedingungen enthalten. "
                "Antworte ausschliesslich als JSON mit issues-Liste."
            )),
            HumanMessage(content=json.dumps({
                "variant": variante,
                "briefing": briefing,
                "rules": rules,
                "layout_metadata": metadata,
                "deterministic_findings": deterministic,
                "output_schema": {
                    "issues": [
                        {
                            "severity": "low | medium | high",
                            "rule_ref": "z.B. brandschutz.brandabschnitt_max_m2",
                            "zone": "betroffene Zone oder null",
                            "message": "konkrete Verletzung",
                            "action": (
                                "move_tech_outer_edge | split_brand_section | increase_spacing | "
                                "snap_to_grid | office_away_from_logistics"
                            ),
                            "rationale": "kurze Whitebox-Begruendung",
                        }
                    ]
                },
            }, ensure_ascii=False, indent=2, default=str)),
        ], temperature=0.0)

        parsed = _parse_json(response)
        llm_issues = [
            _sanitize_issue(variante, issue)
            for issue in parsed.get("issues", [])
            if isinstance(issue, dict)
        ]
        llm_issues = [
            issue for issue in llm_issues
            if _issue_supported_by_metadata(issue, metadata, rules)
        ]
        combined = _dedupe_issues(deterministic + llm_issues)
        if combined:
            print(f"[evaluation] Compliance {variante}: {len(combined)} Hinweise")
        return combined
    except Exception as exc:
        print(f"[evaluation] LLM-Compliance fehlgeschlagen: {exc} - deterministische Pruefung")
        return deterministic


def _layout_metadata(variant: dict, zonen: list[Zone]) -> dict:
    centers = {z.name: (z.x + z.breite / 2, z.y + z.tiefe / 2) for z in zonen}
    body_bounds = _building_body_bounds(zonen)
    zones = []
    for z in zonen:
        if z.schraffur:
            continue
        planned = z.planned_area_m2 if z.planned_area_m2 is not None else z.gezeichnete_flaeche * z.floors
        zones.append({
            "name": z.name,
            "din_kategorie": z.din_kategorie,
            "x": z.x,
            "y": z.y,
            "width_m": z.breite,
            "depth_m": z.tiefe,
            "floors": z.floors,
            "target_area_m2": z.flaeche_m2,
            "planned_area_m2": round(planned, 2),
            "aspect_ratio": round(max(z.breite, z.tiefe) / max(1.0, min(z.breite, z.tiefe)), 2),
            "touches_outer_edge": _touches_building_edge(z, body_bounds),
        })

    distances = []
    names = list(centers)
    for idx, source in enumerate(names):
        for target in names[idx + 1:]:
            sx, sy = centers[source]
            tx, ty = centers[target]
            distances.append({
                "source": source,
                "target": target,
                "distance_m": round(math.hypot(sx - tx, sy - ty), 2),
            })

    hall_area = sum(z["planned_area_m2"] for z in zones if z["din_kategorie"] in {"NUF 3", "NUF 4"})
    body_x2 = body_bounds.get("x", 0.0) + body_bounds.get("width_m", 0.0)
    east_free_fraction = max(0.0, (float(variant["site_breite"]) - body_x2) / max(1.0, float(variant["site_breite"])))
    return {
        "variant": variant["name"],
        "site": {
            "width_m": variant["site_breite"],
            "depth_m": variant["site_tiefe"],
            "building_envelope": variant.get("building_envelope"),
            "building_body_bounds": body_bounds,
            "east_free_fraction": round(east_free_fraction, 3),
        },
        "grid": {"x_m": variant.get("raster_x"), "y_m": variant.get("raster_y")},
        "layout_settings": variant.get("layout_settings"),
        "zones": zones,
        "distances": distances,
        "brand_sections": [
            {
                "name": "Hallenbereich_gesamt",
                "area_m2": round(hall_area, 2),
                "included_din": ["NUF 3", "NUF 4"],
            }
        ],
    }


def _deterministic_compliance_check(variante: str, metadata: dict, rules: dict) -> list[dict]:
    issues: list[dict] = []
    max_brand = rules.get("brandschutz", {}).get("brandabschnitt_max_m2")
    if max_brand:
        for section in metadata.get("brand_sections") or []:
            if section["area_m2"] > float(max_brand):
                issues.append(_sanitize_issue(variante, {
                    "severity": "high",
                    "rule_ref": "brandschutz.brandabschnitt_max_m2",
                    "zone": section["name"],
                    "message": (
                        f"Brandabschnitt {section['area_m2']} m2 ueberschreitet "
                        f"Grenzwert {max_brand} m2."
                    ),
                    "action": "split_brand_section",
                    "rationale": "Gesamter Hallenbereich wird als ein Brandabschnitt bewertet.",
                }))

    for zone in metadata.get("zones") or []:
        name = zone["name"]
        if name == "Technik" and not zone["touches_outer_edge"]:
            issues.append(_sanitize_issue(variante, {
                "severity": "medium",
                "rule_ref": "betrieb.technik_aussenwand_zugang",
                "zone": name,
                "message": "Technik liegt nicht an der Aussenwand; Wartungszugang fehlt.",
                "action": "move_tech_outer_edge",
                "rationale": "Technikflaechen sollen extern wartbar bleiben.",
            }))
        if zone["din_kategorie"] != "VF" and zone["aspect_ratio"] > 4.0:
            issues.append(_sanitize_issue(variante, {
                "severity": "medium",
                "rule_ref": "tragwerk.raster_standard_x_m",
                "zone": name,
                "message": f"Zone {name} hat ein extremes Seitenverhaeltnis {zone['aspect_ratio']}:1.",
                "action": "snap_to_grid",
                "rationale": "Sehr schlanke Zuschnitte sind fuer Raster und Nutzung unplausibel.",
            }))
    min_east = rules.get("erweiterbarkeit", {}).get("freie_ostfassade_min_pct")
    if min_east and metadata.get("site", {}).get("east_free_fraction", 1.0) < float(min_east):
        issues.append(_sanitize_issue(variante, {
            "severity": "medium",
            "rule_ref": "erweiterbarkeit.freie_ostfassade_min_pct",
            "zone": None,
            "message": (
                f"Freie Ostfassade {metadata['site']['east_free_fraction']:.0%} "
                f"liegt unter Zielwert {float(min_east):.0%}."
            ),
            "action": "increase_spacing",
            "rationale": "Ostseite soll fuer spaetere Erweiterung frei bleiben.",
        }))
    return issues


def _flaechendeltas(zonen: list[Zone]) -> list[dict]:
    deltas = []
    for z in zonen:
        if z.schraffur or z.din_kategorie == "VF" or z.flaeche_m2 <= 0:
            continue
        planned = z.planned_area_m2 if z.planned_area_m2 is not None else z.gezeichnete_flaeche * z.floors
        delta_m2 = planned - z.flaeche_m2
        delta_pct = (delta_m2 / z.flaeche_m2) * 100 if z.flaeche_m2 else 0.0
        deltas.append({
            "name": z.name,
            "soll_m2": round(z.flaeche_m2, 2),
            "ist_m2": round(planned, 2),
            "delta_m2": round(delta_m2, 2),
            "delta_pct": round(delta_pct, 1),
            "floors": z.floors,
        })
    return deltas


def _optimization_result_for_variant(variant: dict):
    result = (
        variant.get("optimization_result")
        or variant.get("optimizer_result")
        or variant.get("layout_optimizer_result")
    )
    if result is not None:
        return result

    try:
        from app.agents.layout import _last_optimization_result
        return _last_optimization_result.get(variant.get("name"))
    except Exception:
        return None


def _result_value(result, key: str, default=None):
    if result is None:
        return default
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _optimizer_metrics(optimization_result) -> dict:
    if optimization_result is None:
        return {
            "optimizer_quality_score": None,
            "adjacency_fulfillment_pct": None,
            "convergence_warning": None,
        }

    objective_value = float(_result_value(optimization_result, "objective_value", 0.0) or 0.0)
    quality = 10.0 * (1.0 - min(1.0, objective_value / 3.0))

    decisions = _result_value(optimization_result, "zone_decisions", []) or []
    adjacency_scores = []
    for decision in decisions:
        value = decision.get("adjacency_score") if isinstance(decision, dict) else getattr(decision, "adjacency_score", None)
        if value is None:
            continue
        adjacency_scores.append(float(value))

    if adjacency_scores:
        adjacency_pct = sum(adjacency_scores) / len(adjacency_scores) * 100.0
    else:
        adjacency_pct = None

    iterations = int(_result_value(optimization_result, "iterations", 0) or 0)
    max_iter = int(_result_value(optimization_result, "max_iter", 0) or _result_value(optimization_result, "max_iterations", 0) or 400)
    converged = bool(_result_value(optimization_result, "converged", False))

    return {
        "optimizer_quality_score": round(max(0.0, min(10.0, quality)), 2),
        "adjacency_fulfillment_pct": round(adjacency_pct, 1) if adjacency_pct is not None else None,
        "convergence_warning": (not converged) or (bool(max_iter) and iterations == max_iter),
    }


def _building_body_bounds(zonen: list[Zone]) -> dict:
    visible = [z for z in zonen if not z.schraffur]
    if not visible:
        return {}
    min_x = min(z.x for z in visible)
    min_y = min(z.y for z in visible)
    max_x = max(z.x + z.breite for z in visible)
    max_y = max(z.y + z.tiefe for z in visible)
    return {
        "x": round(min_x, 2),
        "y": round(min_y, 2),
        "width_m": round(max_x - min_x, 2),
        "depth_m": round(max_y - min_y, 2),
    }


def _touches_building_edge(zone: Zone, bounds: dict) -> bool:
    if not bounds:
        return False
    bx = float(bounds.get("x", 0.0))
    by = float(bounds.get("y", 0.0))
    bw = float(bounds.get("width_m", 0.0))
    bd = float(bounds.get("depth_m", 0.0))
    eps = 0.5
    return (
        abs(zone.x - bx) <= eps or
        abs(zone.y - by) <= eps or
        abs(zone.x + zone.breite - (bx + bw)) <= eps or
        abs(zone.y + zone.tiefe - (by + bd)) <= eps
    )


def _sanitize_issue(variante: str, issue: dict) -> dict:
    return {
        "variant": issue.get("variant") or variante,
        "severity": issue.get("severity") if issue.get("severity") in {"low", "medium", "high"} else "medium",
        "rule_ref": issue.get("rule_ref") or "rules.unspecified",
        "zone": issue.get("zone"),
        "message": issue.get("message") or "Regelhinweis ohne Detailtext.",
        "action": issue.get("action") or "review",
        "rationale": issue.get("rationale") or issue.get("reason") or "",
    }


def _issue_supported_by_metadata(issue: dict, metadata: dict, rules: dict) -> bool:
    rule_ref = str(issue.get("rule_ref") or "")
    action = str(issue.get("action") or "")
    zone_name = issue.get("zone")

    if "brandabschnitt_max_m2" in rule_ref or action == "split_brand_section":
        max_brand = rules.get("brandschutz", {}).get("brandabschnitt_max_m2")
        if not max_brand:
            return False
        return any(
            section.get("area_m2", 0) > float(max_brand)
            for section in metadata.get("brand_sections") or []
        )

    if action == "move_tech_outer_edge" or "technik_aussenwand" in rule_ref:
        return any(
            z.get("name") == "Technik" and not z.get("touches_outer_edge")
            for z in metadata.get("zones") or []
        )

    if action == "snap_to_grid" or "raster" in rule_ref:
        if zone_name:
            return any(
                z.get("name") == zone_name and z.get("aspect_ratio", 0) > 4.0
                for z in metadata.get("zones") or []
            )
        return any(z.get("aspect_ratio", 0) > 4.0 for z in metadata.get("zones") or [])

    if "freie_ostfassade" in rule_ref or action == "increase_spacing":
        min_east = rules.get("erweiterbarkeit", {}).get("freie_ostfassade_min_pct")
        if not min_east:
            return False
        return metadata.get("site", {}).get("east_free_fraction", 1.0) < float(min_east)

    return True


def _dedupe_issues(issues: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for issue in issues:
        key = (issue.get("variant"), issue.get("rule_ref"), issue.get("zone"), issue.get("action"))
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _corrections_from_issues(issues: list[dict]) -> dict:
    corrections: dict[str, bool] = {}
    for issue in issues:
        action = issue.get("action")
        if action == "move_tech_outer_edge":
            corrections["tech_to_outer_edge"] = True
        elif action == "office_away_from_logistics":
            corrections["office_away_from_logistics"] = True
        elif action in {"snap_to_grid", "split_brand_section"}:
            corrections["snap_to_grid"] = True
            corrections["increase_grid_alignment"] = True
        elif action == "increase_spacing":
            corrections["increase_spacing"] = True
    return corrections


def _parse_json(text: str | None) -> dict:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    parsed = json.loads(match.group())
    return parsed if isinstance(parsed, dict) else {}

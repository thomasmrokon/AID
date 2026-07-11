"""
AID Demo - Topology-Agent.

Erzeugt ein abstraktes Nutzungsdiagramm aus Funktionsflaechen (Knoten) und
gewichteten Beziehungen (Kanten). Der Layout-Agent nutzt dieses Diagramm als
Basis fuer flexiblere Varianten.
"""

from __future__ import annotations

import json
import re

from app.llm import invoke_messages, is_llm_configured
from app.state import PlanningState, Nutzungstyp

# CONTRACT-VORSCHLAG FÜR CLAUDE (state.py):
# process_steps: list[dict] | None
#   Owner: streamlit / briefing_agent
#   Readers: topology_agent, layout_agent
#   Format: [{name, din_kategorie, flaeche_m2, min_breite_m, adj_next}, ...]
#   None = monolithische Produktionsfläche (bisheriges Verhalten)


def _expand_production_steps(
    briefing: dict,
    process_steps: list[dict] | None,
    diagram: dict,
) -> list[dict]:
    """
    Wenn process_steps gesetzt:
      - Ersetze den NUF-3-Knoten (bzw. Haupt-Knoten) durch n Schritt-Knoten
      - Fläche je Knoten = NUF3_gesamt × flaeche_pct (oder flaeche_m2)
      - Kanten zwischen aufeinanderfolgenden Schritten mit adj_next
      - process_order = [Schritt1, Schritt2, ...]
    Wenn process_steps None: unverändert (bestehende Logik).
    Gibt erweiterte nodes-Liste zurück.
    """
    if not process_steps:
        return diagram.get("nodes", [])

    nodes = diagram.get("nodes", [])
    edges = diagram.get("edges", [])
    nutzungstyp = diagram.get("nutzungstyp")
    
    target_name = "Produktion"
    if nutzungstyp == "Logistik":
        target_name = "Lager"
    elif nutzungstyp == "Data Center":
        target_name = "Whitespace IT"

    target_node = next((n for n in nodes if n["name"] == target_name), None)
    if not target_node:
        return nodes

    total_area = target_node["area_m2"]
    new_nodes = []
    step_names = []

    for step in process_steps:
        name = step.get("name", "Unbekannt")
        step_names.append(name)
        
        area = step.get("flaeche_m2")
        if area is None:
            area = total_area * step.get("flaeche_pct", 0)

        new_nodes.append(_node(
            name=name,
            area=area,
            din=step.get("din_kategorie", target_node["din_kategorie"]),
            farbe=target_node["farbe"],
            target_aspect=target_node.get("target_aspect", 1.5),
            height_class=target_node.get("height_class", "hall"),
            floors=target_node.get("floors", 1)
        ))

    first_step = step_names[0]
    last_step = step_names[-1]

    new_edges = []
    for edge in edges:
        if edge["source"] == target_name:
            edge["source"] = last_step
            new_edges.append(edge)
        elif edge["target"] == target_name:
            edge["target"] = first_step
            new_edges.append(edge)
        else:
            new_edges.append(edge)

    for i in range(len(process_steps) - 1):
        adj = process_steps[i].get("adj_next")
        if adj is not None:
            new_edges.append(_edge(step_names[i], step_names[i+1], adj, "process"))

    process_order = diagram.get("process_order", [])
    new_process_order = []
    for po in process_order:
        if po == target_name:
            new_process_order.extend(step_names)
        else:
            new_process_order.append(po)

    nodes.remove(target_node)
    nodes.extend(new_nodes)
    diagram["nodes"] = nodes
    diagram["edges"] = new_edges
    diagram["process_order"] = new_process_order

    return nodes


def topology_agent(state: PlanningState) -> dict:
    """LangGraph-Node: Nutzungsdiagramm erzeugen."""
    briefing = state["structured_briefing"]
    nutzungstyp = briefing["nutzungstyp"]

    if nutzungstyp == Nutzungstyp.PRODUKTION:
        diagram = _produktion_topology(briefing)
    elif nutzungstyp == Nutzungstyp.LOGISTIK:
        diagram = _logistik_topology(briefing)
    elif nutzungstyp == Nutzungstyp.DATA_CENTER:
        diagram = _datacenter_topology(briefing)
    else:
        raise ValueError(f"Unbekannter Nutzungstyp: {nutzungstyp}")
        
    diagram["nodes"] = _expand_production_steps(briefing, state.get("process_steps"), diagram)

    decisions: list[dict] = []
    llm_used_agents: list[str] = list(state.get("llm_used_agents") or [])

    # Sprint P — Determinismus: LLM-Topologieanpassung nur bei Sonderbedingungen.
    # _llm_adjust_topology passt Kantengewichte aus Freitextanforderungen an — das ist
    # legitime NLP-Nutzung. Ohne sonderbedingungen wäre es ein Leerlauf-LLM-Aufruf.
    sonderbedingungen = ((state.get("structured_briefing") or {}).get("sonderbedingungen") or "").strip()
    if is_llm_configured() and sonderbedingungen:
        diagram, decisions = _llm_adjust_topology(diagram, state)
        if decisions and "topology" not in llm_used_agents:
            llm_used_agents.append("topology")

    valid_node_names = {node["name"] for node in diagram.get("nodes", [])}
    original_process_order = diagram.get("process_order", [])
    valid_process_order = []
    for name in original_process_order:
        if name in valid_node_names:
            valid_process_order.append(name)
        else:
            print(f"[topology] Warnung: Entferne unbekannten Knoten '{name}' aus process_order")
            
    if len(valid_process_order) < 2:
        fallback_nodes = [node["name"] for node in diagram.get("nodes", []) if node["name"] not in valid_process_order]
        while len(valid_process_order) < 2 and fallback_nodes:
            added = fallback_nodes.pop(0)
            valid_process_order.append(added)
            print(f"[topology] Warnung: process_order zu kurz. Fuege '{added}' als Fallback hinzu")
            
    diagram["process_order"] = valid_process_order

    print(
        f"[topology] Nutzungsdiagramm erzeugt - "
        f"{len(diagram['nodes'])} Funktionen, {len(diagram['edges'])} Beziehungen"
    )

    reasoning_log = list(state.get("reasoning_log") or [])
    process_chain = diagram.get("process_order", [])
    preview = " → ".join(process_chain[:4]) + (" ..." if len(process_chain) > 4 else "")
    reasoning_log.append({
        "agent":       "topology_agent",
        "disziplin":   "Topologie",
        "variante":    "alle",
        "entscheidung": f"{len(diagram['nodes'])} Knoten, {len(diagram['edges'])} Kanten",
        "begruendung": f"Prozesskette: {preview}",
        "regelref":    f"topology.{str(nutzungstyp).lower().replace(' ', '_')}_standard",
    })
    for d in decisions:
        reasoning_log.append({
            "agent":       "topology_agent",
            "disziplin":   "Topologie (LLM)",
            "variante":    "alle",
            "entscheidung": d.get("reason", ""),
            "begruendung": d.get("effect", ""),
            "regelref":    d.get("rule_ref", "topology"),
        })

    return {
        "topology_diagram":  diagram,
        "topology_decisions": decisions,
        "reasoning_log":     reasoning_log,
        "llm_used_agents":   llm_used_agents,
    }


def _node(
    name: str,
    area: float,
    din: str,
    farbe: str,
    *,
    floors: int = 1,
    target_aspect: float = 1.5,
    height_class: str = "hall",
    external_edge: bool = False,
    access_role: str | None = None,
) -> dict:
    floors = max(1, int(floors))
    return {
        "name": name,
        "area_m2": float(area),
        "footprint_m2": round(float(area) / floors, 2),
        "din_kategorie": din,
        "farbe": farbe,
        "floors": floors,
        "target_aspect": target_aspect,
        "height_class": height_class,
        "external_edge": external_edge,
        "access_role": access_role,
    }


def _edge(source: str, target: str, weight: float, kind: str = "adjacency") -> dict:
    return {"source": source, "target": target, "weight": weight, "kind": kind}


def _llm_adjust_topology(diagram: dict, state: PlanningState) -> tuple[dict, list[dict]]:
    """Passt Kantengewichte auf Basis freier Anforderungen an."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = invoke_messages([
            SystemMessage(content=(
                "Du bist ein regelbasierter Topologie-Agent fuer Industriebau. "
                "Du darfst keine Geometrie zeichnen. Passe nur Kanten im Nutzungsgraphen an: "
                "positive weights ziehen Funktionen zusammen, negative weights trennen sie. "
                "Nutze Knoten exakt so, wie sie im JSON vorkommen. "
                "Begruende jede Aenderung mit einem Regelbezug oder einer Freitextanforderung. "
                "Antworte ausschliesslich als JSON."
            )),
            HumanMessage(content=json.dumps({
                "briefing": state.get("structured_briefing"),
                "freitext": (state.get("structured_briefing") or {}).get("sonderbedingungen"),
                "sonderbedingungen_parsed": state.get("sonderbedingungen_parsed"),
                "rules": state.get("rules"),
                "base_graph": diagram,
                "output_schema": {
                    "edge_updates": [
                        {
                            "source": "bestehender Knotenname",
                            "target": "bestehender Knotenname",
                            "weight": "-1.0..1.0",
                            "kind": "adjacency | process | separation | compliance",
                            "rule_ref": "Regelpfad oder briefing.sonderbedingungen",
                            "reason": "kurze Begruendung",
                        }
                    ],
                    "new_edges": [
                        {
                            "source": "bestehender Knotenname",
                            "target": "bestehender Knotenname",
                            "weight": "-1.0..1.0",
                            "kind": "adjacency | separation | compliance",
                            "rule_ref": "Regelpfad oder briefing.sonderbedingungen",
                            "reason": "kurze Begruendung",
                        }
                    ],
                    "decisions": [
                        {
                            "rule_ref": "Regelpfad oder briefing.sonderbedingungen",
                            "reason": "kurze Begruendung",
                            "effect": "Kantenwirkung",
                        }
                    ],
                },
            }, ensure_ascii=False, indent=2, default=str)),
        ], temperature=0.1)

        parsed = _parse_json(response)
        adjusted = json.loads(json.dumps(diagram))
        decisions: list[dict] = []
        valid_nodes = {n["name"] for n in adjusted.get("nodes", [])}

        for update in parsed.get("edge_updates") or []:
            _apply_edge_update(adjusted, update, valid_nodes, decisions)
        for update in parsed.get("new_edges") or []:
            _apply_edge_update(adjusted, update, valid_nodes, decisions, create=True)
        for decision in parsed.get("decisions") or []:
            if isinstance(decision, dict):
                decisions.append(decision)

        if decisions:
            print(f"[topology] LLM-Topologie angepasst - {len(decisions)} Entscheidungen")
        return adjusted, decisions
    except Exception as exc:
        print(f"[topology] LLM-Topologieanpassung fehlgeschlagen: {exc} - Basisgraph")
        return diagram, []


def _apply_edge_update(
    diagram: dict,
    update: dict,
    valid_nodes: set[str],
    decisions: list[dict],
    *,
    create: bool = False,
) -> None:
    source = update.get("source")
    target = update.get("target")
    if source not in valid_nodes or target not in valid_nodes or source == target:
        return
    weight = _clamp_weight(update.get("weight"))
    kind = update.get("kind") if update.get("kind") in {"adjacency", "process", "separation", "compliance"} else "adjacency"
    edge = _find_edge(diagram.get("edges", []), source, target)
    if edge:
        edge["weight"] = weight
        edge["kind"] = kind
    elif create:
        diagram.setdefault("edges", []).append(_edge(source, target, weight, kind))
    else:
        return
    decisions.append({
        "rule_ref": update.get("rule_ref") or "briefing.sonderbedingungen",
        "reason": update.get("reason") or "Topologiegewicht aus Freitextanforderung angepasst.",
        "effect": f"{source} -> {target}: weight {weight}, kind {kind}",
    })


def _find_edge(edges: list[dict], source: str, target: str) -> dict | None:
    pair = {source, target}
    for edge in edges:
        if {edge.get("source"), edge.get("target")} == pair:
            return edge
    return None


def _clamp_weight(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(-1.0, min(1.0, number)), 3)


def _parse_json(text: str | None) -> dict:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    parsed = json.loads(match.group())
    return parsed if isinstance(parsed, dict) else {}


def _produktion_topology(b: dict) -> dict:
    prod = b["produktionsflaeche"]
    qs = b.get("qualitaetssicherung") or round(prod * 0.10)
    buero_floors = int(b.get("buero_geschosse") or 2)
    nodes = [
        _node("Wareneingang", b["wareneingang"], "NUF 4", "#5B8DB8", target_aspect=1.2, access_role="inbound"),
        _node("Lager Rohstoffe", b["lager_rohstoffe"], "NUF 4", "#F4A261", target_aspect=1.4),
        _node("Produktion", prod, "NUF 3", "#2A9D8F", target_aspect=1.7),
        _node("Qualitätssicherung", qs, "NUF 3", "#E76F51", target_aspect=1.3),
        _node("Lager Fertigwaren", b["lager_fertigwaren"], "NUF 4", "#E9C46A", target_aspect=1.4),
        _node("Versand", b["versand"], "NUF 4", "#264653", target_aspect=1.2, access_role="outbound"),
        _node("Büro / Verwaltung", b["buero_nuf2"], "NUF 2", "#A8DADC", floors=buero_floors, target_aspect=1.6, height_class="low", access_role="visitor"),
        _node("Technik", b["technikflaeche_tf"], "TF", "#8D99AE", target_aspect=1.2, height_class="service", external_edge=True),
        _node("Sozial", b["sozialraeume_nuf7"], "NUF 7", "#B7E4C7", floors=2, target_aspect=1.3, height_class="low"),
    ]
    edges = [
        _edge("Wareneingang", "Lager Rohstoffe", 0.95, "process"),
        _edge("Lager Rohstoffe", "Produktion", 0.95, "process"),
        _edge("Produktion", "Qualitätssicherung", 0.85, "process"),
        _edge("Qualitätssicherung", "Lager Fertigwaren", 0.85, "process"),
        _edge("Lager Fertigwaren", "Versand", 0.95, "process"),
        _edge("Büro / Verwaltung", "Produktion", 0.25),
        _edge("Büro / Verwaltung", "Wareneingang", -0.35, "separation"),
        _edge("Büro / Verwaltung", "Versand", -0.35, "separation"),
        _edge("Sozial", "Büro / Verwaltung", 0.55),
        _edge("Technik", "Produktion", 0.30),
    ]
    return {"nutzungstyp": "Produktion", "process_order": [e["source"] for e in edges[:5]] + ["Versand"], "nodes": nodes, "edges": edges}


def _logistik_topology(b: dict) -> dict:
    buero_floors = int(b.get("buero_geschosse") or 2)
    nodes = [
        _node("Wareneingang", b["wareneingang_rampen"], "NUF 4", "#5B8DB8", target_aspect=1.4, access_role="inbound"),
        _node("Lager", b["lagerflaeche"], "NUF 4", "#F4A261", target_aspect=2.0),
        _node("Kommissionierung", b["kommissionierung"], "NUF 4", "#E9C46A", target_aspect=1.6),
        _node("Versand", b["warenausgang_rampen"], "NUF 4", "#264653", target_aspect=1.4, access_role="outbound"),
        _node("Büro / Verwaltung", b["buero_nuf2"], "NUF 2", "#A8DADC", floors=buero_floors, target_aspect=1.5, height_class="low", access_role="visitor"),
        _node("Technik", b["technikflaeche_tf"], "TF", "#8D99AE", target_aspect=1.2, height_class="service", external_edge=True),
        _node("Sozial", b["sozialraeume_nuf7"], "NUF 7", "#B7E4C7", floors=2, target_aspect=1.3, height_class="low"),
    ]
    if b.get("retouren"):
        nodes.append(_node("Retouren", b["retouren"], "NUF 4", "#E76F51", target_aspect=1.3, access_role="inbound"))
    edges = [
        _edge("Wareneingang", "Lager", 0.9, "process"),
        _edge("Lager", "Kommissionierung", 0.9, "process"),
        _edge("Kommissionierung", "Versand", 0.9, "process"),
        _edge("Büro / Verwaltung", "Lager", -0.45, "separation"),
        _edge("Büro / Verwaltung", "Sozial", 0.65),
        _edge("Technik", "Lager", 0.25),
    ]
    if b.get("retouren"):
        edges += [_edge("Retouren", "Wareneingang", 0.75), _edge("Retouren", "Versand", -0.35, "separation")]
    return {"nutzungstyp": "Logistik", "process_order": ["Wareneingang", "Lager", "Kommissionierung", "Versand"], "nodes": nodes, "edges": edges}


def _datacenter_topology(b: dict) -> dict:
    buero_floors = int(b.get("buero_geschosse") or 2)
    ws = b["whitespace_it"]
    usv = round(ws * b["usv_trafo_pct"])
    kue = round(ws * b["kuehlung_chiller_pct"])
    nst = round(ws * b["notstrom_generatoren_pct"])
    nodes = [
        _node("Einspeisung", usv, "TF", "#264653", target_aspect=1.1, external_edge=True, access_role="utility"),
        _node("USV / Trafo", usv, "TF", "#8D99AE", target_aspect=1.2, external_edge=True),
        _node("Kühlung", kue, "TF", "#5B8DB8", target_aspect=1.5, external_edge=True),
        _node("Whitespace IT", ws, "NUF 3", "#2A9D8F", target_aspect=1.8),
        _node("Notstrom", nst, "TF", "#E76F51", target_aspect=1.5, external_edge=True),
        _node("NOC", b["noc_buero"], "NUF 2", "#A8DADC", floors=buero_floors, target_aspect=1.5, height_class="low", access_role="visitor"),
        _node("Technik", b["technikflaeche_tf"], "TF", "#8D99AE", target_aspect=1.2, external_edge=True),
        _node("Sozial", b["sozialraeume_nuf7"], "NUF 7", "#B7E4C7", floors=2, target_aspect=1.3, height_class="low"),
    ]
    if b.get("staging_lager"):
        nodes.append(_node("Staging", b["staging_lager"], "NUF 4", "#F4A261", target_aspect=1.3, access_role="inbound"))
    edges = [
        _edge("Einspeisung", "USV / Trafo", 0.9, "process"),
        _edge("USV / Trafo", "Kühlung", 0.55),
        _edge("Kühlung", "Whitespace IT", 0.85),
        _edge("Whitespace IT", "NOC", 0.45),
        _edge("Notstrom", "Whitespace IT", -0.3, "separation"),
        _edge("NOC", "Sozial", 0.55),
    ]
    if b.get("staging_lager"):
        edges.append(_edge("Staging", "Whitespace IT", 0.65))
    return {"nutzungstyp": "Data Center", "process_order": ["Einspeisung", "USV / Trafo", "Kühlung", "Whitespace IT", "NOC"], "nodes": nodes, "edges": edges}

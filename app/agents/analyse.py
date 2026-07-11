"""
AID Demo – Analyse-Agent
Qualitative LLM-Analyse der Variantenbewertung.
Erklärt warum eine Variante empfohlen wird und benennt Zielkonflikte.
Wird übersprungen wenn kein API-Key gesetzt ist.
"""

from __future__ import annotations
import json
from app.state import PlanningState
from app.llm import invoke_messages, is_llm_configured


def analyse_agent(state: PlanningState) -> dict:
    """LangGraph-Node: Qualitative LLM-Analyse der Scores."""

    if not is_llm_configured():
        return {"llm_analyse": None}

    briefing             = state["structured_briefing"]
    evaluations          = state["evaluations"]
    selected             = state["selected_variant"]
    variants             = state["variants"]
    nutzungstyp          = briefing["nutzungstyp"]
    typology_assignments = state.get("typology_assignments") or {}
    reasoning_log        = state.get("reasoning_log") or []

    # Nur inhaltliche Entscheidungen (kein Fallback/System), max. 10 Highlights
    log_highlights = [
        {
            "disziplin":    e.get("disziplin"),
            "variante":     e.get("variante"),
            "entscheidung": e.get("entscheidung"),
            "begruendung":  e.get("begruendung"),
        }
        for e in reasoning_log
        if e.get("disziplin") not in ("System",) and e.get("variante") not in ("alle", "", None)
    ][:10]

    eval_map = {e["variante"]: e for e in evaluations}

    # Kontext für das LLM aufbauen
    kontext = {
        "nutzungstyp":  nutzungstyp,
        "bgf_m2":       briefing["bgf_gesamt"],
        "nuf_m2":       briefing["nuf_gesamt"],
        "sonderbedingungen": briefing.get("sonderbedingungen"),
        "empfehlung":   selected,
        "typologien":   typology_assignments,
        "planungsrat_highlights": log_highlights,
        "varianten": [
            {
                "name":        e["variante"],
                "typologie":   typology_assignments.get(e["variante"], ""),
                "gewichtung": next(
                    v["gewichtung"] for v in variants if v["name"] == e["variante"]
                ),
                "scores": {
                    "materialfluss":   e["materialfluss_score"],
                    "erweiterbarkeit": e["erweiterbarkeit_score"],
                    "tragwerk":        e["tragwerk_score"],
                    "gesamt":          e["gesamtscore"],
                },
                "regelverletzungen": e["regelverletzungen"],
            }
            for e in evaluations
        ],
    }

    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        analyse_text = invoke_messages([
            SystemMessage(content="""Du bist ein erfahrener Industriebau-Planer bei Drees & Sommer.
Analysiere die drei Layoutvarianten und liefere eine kompakte qualitative Einschätzung.
Die Daten enthalten die Typologie jeder Variante (kamm/block_reserve/kreuzgang) und \
Schlüsselentscheidungen des Planungsrats.

Deine Analyse enthält:
1. **Empfehlung** (2-3 Sätze): Warum ist die empfohlene Variante die beste Wahl? Benenne die Typologie.
2. **Zielkonflikte** (1-2 Sätze): Welche Spannungen bestehen zwischen den Anforderungen?
3. **Risiken** (1-2 Sätze): Was sind die kritischen Punkte der empfohlenen Variante?
4. **Nächster Schritt** (1 Satz): Was sollte als nächstes konkret geprüft werden?

Schreibe präzise, professionell und direkt – keine Einleitungssätze.
Antworte auf Deutsch. Nutze Markdown-Formatierung."""),
            HumanMessage(content=json.dumps(kontext, ensure_ascii=False, indent=2, default=str)),
        ], temperature=0.4)
        print(f"[analyse] LLM-Analyse erfolgreich ({len(analyse_text)} Zeichen)")

    except Exception as e:
        print(f"[analyse] LLM-Analyse fehlgeschlagen: {e}")
        analyse_text = None

    return {"llm_analyse": analyse_text}

def generate_zone_decisions(result: "OptimizationResult", state: PlanningState) -> list["ZoneDecision"]:
    """Generiert für jede Zone einen deutschen Begründungssatz per LLM."""
    from langchain_core.messages import SystemMessage, HumanMessage
    
    decisions = result.zone_decisions
    topology = result.tree_topology
    
    process_context = state.get("structured_briefing", {}).get("nutzungstyp", "Industriebau")

    for decision in decisions:
        x, y = decision.position
        position_str = f"({x:.0f}m/{y:.0f}m)"
        
        system_prompt = f"""Du bist ein Industriebau-Planungsexperte. Erkläre in einem präzisen deutschen
Satz (max. 25 Wörter) warum Zone "{decision.zone_name}" an Position {position_str} platziert wurde.

Kontext:
- Flächenabweichung: {decision.area_delta_pct:+.1f}%
- Nachbarerfüllung: {decision.adjacency_score:.0%} der gewichteten Verbindungen sind direkt angrenzend
- Seitenverhältnis: {decision.aspect_ratio:.1f}:1
- Rasterabweichung: {decision.grid_deviation_m:.1f} m vom Tragwerksraster
- Baumstruktur: Zone liegt im Teilraum "{topology}"
- Prozessfluss: {process_context}

Antworte nur mit dem Begründungssatz, keine Einleitung."""

        try:
            response = invoke_messages([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Generiere die Begründung für {decision.zone_name}.")
            ], temperature=0.3)
            
            if response:
                decision.human_reason = response.strip()
            else:
                decision.human_reason = f"{decision.zone_name} wurde durch die Optimierung an Position {position_str} platziert."
        except Exception:
            decision.human_reason = f"{decision.zone_name} wurde durch die Optimierung an Position {position_str} platziert."

    return decisions

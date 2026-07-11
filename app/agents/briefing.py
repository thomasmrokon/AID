"""
AID Demo – Briefing-Agent
Validiert den strukturierten Input, befüllt Defaults und parst
den optionalen Freitext (sonderbedingungen) per LLM.
"""

from __future__ import annotations
import json
import re

from app.state import (
    PlanningState,
    ProduktionInput,
    LogistikInput,
    DataCenterInput,
    Nutzungstyp,
)
from app.llm import invoke_messages, is_llm_configured


def briefing_agent(state: PlanningState) -> dict:
    """LangGraph-Node: Briefing-Verarbeitung."""

    raw = state["user_input"]
    typ = raw.get("nutzungstyp")

    # --- Pydantic-Validierung je Typ ---
    if typ == Nutzungstyp.PRODUKTION:
        briefing = ProduktionInput(**raw)
        nuf = (
            briefing.produktionsflaeche
            + briefing.lager_rohstoffe
            + briefing.lager_fertigwaren
            + briefing.wareneingang
            + briefing.versand
            + briefing.buero_nuf2
            + (briefing.qualitaetssicherung or 0)
        )
    elif typ == Nutzungstyp.LOGISTIK:
        briefing = LogistikInput(**raw)
        nuf = (
            briefing.lagerflaeche
            + briefing.kommissionierung
            + briefing.wareneingang_rampen
            + briefing.warenausgang_rampen
            + briefing.buero_nuf2
            + (briefing.retouren or 0)
        )
    elif typ == Nutzungstyp.DATA_CENTER:
        briefing = DataCenterInput(**raw)
        tf_ws = briefing.whitespace_it * (
            briefing.usv_trafo_pct
            + briefing.kuehlung_chiller_pct
            + briefing.notstrom_generatoren_pct
        )
        nuf = briefing.whitespace_it + briefing.noc_buero + (briefing.staging_lager or 0) + tf_ws
    else:
        raise ValueError(f"Unbekannter Nutzungstyp: {typ}")

    b = briefing.model_dump()

    # --- Defaults befüllen ---
    if not b.get("technikflaeche_tf"):
        b["technikflaeche_tf"] = round(nuf * 0.06)

    if not b.get("sozialraeume_nuf7"):
        b["sozialraeume_nuf7"] = round(nuf * 0.03)

    b["nuf_gesamt"] = round(nuf)
    b["bgf_gesamt"] = round(nuf * 1.25)
    b["tragwerk_raster_m"] = raw.get("tragwerk_raster_m")

    # --- Freitext per LLM parsen (nur wenn vorhanden und API-Key gesetzt) ---
    parsed_conditions = None
    process_steps = None
    if briefing.sonderbedingungen and is_llm_configured():
        parsed_conditions = _parse_sonderbedingungen(briefing.sonderbedingungen)
        
        total_nuf3_m2 = 0
        if typ == Nutzungstyp.PRODUKTION:
            total_nuf3_m2 = briefing.produktionsflaeche
        elif typ == Nutzungstyp.LOGISTIK:
            total_nuf3_m2 = briefing.lagerflaeche
        elif typ == Nutzungstyp.DATA_CENTER:
            total_nuf3_m2 = briefing.whitespace_it
            
        process_steps = _extract_process_steps(briefing.sonderbedingungen, typ, total_nuf3_m2, None)

    # --- MEP-Anforderungen aus UI-Eingaben extrahieren ---
    mep_anforderungen = {
        "lueftung":     raw.get("mep_lueftung", "mechanisch"),
        "sprinkler":    bool(raw.get("mep_sprinkler", False)),
        "druckluft":    bool(raw.get("mep_druckluft", False)),
        "kaelte":       bool(raw.get("mep_kaelte", False)),
        "usv_notstrom": bool(raw.get("mep_usv_notstrom", False)),
        "it_kategorie": raw.get("mep_it_kategorie", "basis"),
    }

    # --- Tragwerk-Konfiguration aus UI-Eingaben extrahieren ---
    tragwerk_config = {
        "typologie":  raw.get("tragwerk_typologie", "stahl"),
        "lastklasse": raw.get("tragwerk_lastklasse", "mittel"),
    }

    return {
        "structured_briefing":    b,
        "sonderbedingungen_parsed": parsed_conditions,
        "process_steps":          process_steps,
        "mep_anforderungen":      mep_anforderungen,
        "tragwerk_config":        tragwerk_config,
    }


def _extract_process_steps(
    sonderbedingungen: str,
    nutzungstyp: str,
    total_nuf3_m2: float,
    llm=None,
) -> list[dict] | None:
    """
    Prompt: Extrahiere Produktionsschritte aus dem Text.
    Output-Schema: [{name, flaeche_m2, min_breite_m, adj_next}, ...]
    Gibt None zurück wenn kein klarer Prozess erkennbar.
    Validiert: Summe der Einzelflächen ≤ total_nuf3_m2 * 1.05
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.llm import invoke_messages
    
    try:
        response = invoke_messages([
            SystemMessage(content=(
                "Du bist Experte für Industriebau-Planung. "
                f"Extrahiere aus dem Text Produktionsschritte für den Nutzungstyp '{nutzungstyp}'. "
                "Antworte NUR mit einem JSON-Array von Objekten. Jedes Objekt muss folgende Felder haben: "
                "name (str), flaeche_m2 (float), min_breite_m (float), adj_next (float oder null, Gewichtung zum nächsten Schritt, z.B. 0.9). "
                "Wenn kein klarer Prozess erkennbar ist, antworte mit einem leeren Array []."
            )),
            HumanMessage(content=sonderbedingungen),
        ], temperature=0)
        
        match = re.search(r"\[.*\]", response or "", re.DOTALL)
        if match:
            steps = json.loads(match.group())
            if not steps:
                return None
            
            total_extracted = sum(step.get("flaeche_m2", 0) for step in steps)
            if total_extracted > total_nuf3_m2 * 1.05:
                print(f"[briefing] Warnung: Extrahierte Flächen ({total_extracted}) überschreiten Limit ({total_nuf3_m2 * 1.05})")
                return None
            return steps
    except Exception as e:
        print(f"[briefing] _extract_process_steps fehlgeschlagen: {e}")
        
    return None


def _parse_sonderbedingungen(text: str) -> dict:
    """Extrahiert strukturierte Anforderungen aus dem Freitext via LLM."""
    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        response = invoke_messages([
            SystemMessage(content=(
                "Du bist Experte für Industriebau-Planung. "
                "Extrahiere aus dem Text strukturierte Planungsanforderungen als JSON. "
                "Antworte NUR mit einem JSON-Objekt mit den Feldern: "
                "constraints (list[str], harte Anforderungen), "
                "preferences (list[str], weiche Präferenzen), "
                "keywords (list[str])."
            )),
            HumanMessage(content=text),
        ], temperature=0)

        match = re.search(r"\{.*\}", response or "", re.DOTALL)
        if match:
            return json.loads(match.group())

    except Exception as e:
        print(f"[briefing] LLM-Parsing fehlgeschlagen: {e}")

    # Fallback: Freitext als Präferenz übernehmen
    return {"constraints": [], "preferences": [text], "keywords": []}

"""
AID Demo – Rule-Agent mit LLM-Planungsrat

Laedt die Wissensbasis (rules_hard + rules_conventions) und laesst den
LLM-Planungsrat fuer jede Variante eine interpretierte Regelkonfiguration
erzeugen. Fuenf Fachdisziplinen analysieren unabhaengig, dann synthetisiert
der Rat varianten-spezifische Planungsanweisungen.

Fallback: deterministische Default-Werte aus rules_conventions wenn kein LLM.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import yaml

from app.llm import invoke_messages, is_llm_configured
from app.state import PlanningState, VARIANTEN_GEWICHTUNGEN, Nutzungstyp

DATA = Path(__file__).parent.parent / "data"
RULES_HARD_PATH       = DATA / "rules_hard.yaml"
RULES_CONVENTIONS_PATH = DATA / "rules_conventions.yaml"
RULES_LEGACY_PATH     = DATA / "demo_rules.yaml"
RULES_PATH            = RULES_LEGACY_PATH  # Alias für Streamlit-UI

TYPE_KEY_MAP = {
    Nutzungstyp.PRODUKTION:  "produktion",
    Nutzungstyp.LOGISTIK:    "logistik",
    Nutzungstyp.DATA_CENTER: "data_center",
}


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def rule_agent(state: PlanningState) -> dict:
    """LangGraph-Node: Wissensbasis laden und Planungsrat ausfuehren."""
    briefing     = state["structured_briefing"]
    nutzungstyp  = briefing["nutzungstyp"]
    gewichtungen = state.get("custom_gewichtungen") or {
        k: g.model_dump() for k, g in VARIANTEN_GEWICHTUNGEN.items()
    }

    rules_hard        = _load_yaml(RULES_HARD_PATH)
    rules_conventions = _load_yaml(RULES_CONVENTIONS_PATH)
    rules_legacy      = _load_legacy(nutzungstyp)

    reasoning_log: list[dict] = list(state.get("reasoning_log") or [])
    llm_used_agents: list[str] = list(state.get("llm_used_agents") or [])

    # Sprint P — Determinismus: LLM-Planungsrat nur bei expliziten Sonderbedingungen.
    # Begründung: _fallback_interpreted() deckt Standardfälle vollständig ab (Raster,
    # Traufhöhe, Brandabschnitte). Der LLM-Aufruf war bisher immer aktiv, solange ein
    # API-Key gesetzt war → nicht-deterministisch. Mit dieser Änderung wird der LLM
    # nur aufgerufen, wenn sonderbedingungen Freitext enthält (NLP-Parsing-Aufgabe).
    has_sonderbedingungen = bool((briefing.get("sonderbedingungen") or "").strip())

    if is_llm_configured() and has_sonderbedingungen:
        interpreted, log_entries = _planungsrat(
            briefing=briefing,
            rules_hard=rules_hard,
            rules_conventions=rules_conventions,
            gewichtungen=gewichtungen,
            nutzungstyp=nutzungstyp,
        )
        reasoning_log.extend(log_entries)
        quelle = "llm"
        if "rules" not in llm_used_agents:
            llm_used_agents.append("rules")
    else:
        interpreted = _fallback_interpreted(rules_conventions, nutzungstyp, briefing)
        reasoning_log.append(_log_entry(
            agent="rule_agent", disziplin="System", variante="alle",
            entscheidung="Deterministisch (kein LLM-Planungsrat)",
            begruendung=(
                "Sonderbedingungen leer — Default-Werte aus rules_conventions verwendet."
                if not has_sonderbedingungen
                else "Kein API-Key — deterministische Default-Werte verwendet."
            ),
            regelref="rules_conventions.*.default",
        ))
        quelle = "fallback"

    for v_name, v_rules in interpreted.items():
        if "tragwerk" in v_rules:
            max_aspect_ratio = rules_conventions.get("tragwerk", {}).get("max_aspect_ratio", {}).get("default", 4.0)
            v_rules["tragwerk"]["max_aspect_ratio"] = float(max_aspect_ratio)

    print(
        f"[rules] Planungsrat abgeschlossen ({quelle}) — "
        f"{len(interpreted)} Varianten interpretiert"
    )

    # ── Entscheidungsprotokoll: Regelanwendung ────────────────────────────────
    planning_decisions = list(state.get("planning_decisions") or [])

    _log_rule_kvs = [
        ("Brandabschnitt max",        rules_legacy.get("brandschutz", {}).get("brandabschnitt_max_m2"), "m²",  "rules.brandschutz.brandabschnitt_max_m2"),
        ("Fluchtweg max",             rules_legacy.get("brandschutz", {}).get("fluchtweg_max_m"),        "m",   "rules.brandschutz.fluchtweg_max_m"),
        ("Freie Ostfassade min",      rules_legacy.get("erweiterbarkeit", {}).get("freie_ostfassade_min_pct"), "%", "rules.erweiterbarkeit.freie_ostfassade_min_pct"),
        ("LKW-Rangierbreite",         rules_legacy.get("erschliessung", {}).get("rangierbreite_lkw_m"),  "m",   "rules.erschliessung.rangierbreite_lkw_m"),
        ("Stellplätze je 100 m²",     rules_legacy.get("erschliessung", {}).get("stellplaetze_je_100m2_buero"), "SP", "rules.erschliessung.stellplaetze"),
        ("Technische Zonenfläche %",  rules_legacy.get("betrieb", {}).get("technikflaeche_pct_nuf"),     "%",   "rules.betrieb.technikflaeche_pct_nuf"),
    ]

    _nutzungstyp_str = str(nutzungstyp)
    for label, wert, einheit, regelref in _log_rule_kvs:
        if wert is None:
            continue
        planning_decisions.append({
            "agent":      "rules",
            "variante":   "alle",
            "kategorie":  "Regelanwendung",
            "zone":       None,
            "aktion":     f"{label}: {wert} {einheit}",
            "begruendung": f"Aus aktivem Regelset ({_nutzungstyp_str}) übernommen.",
            "wert":       {"wert": wert, "einheit": einheit},
            "regel_ref":  regelref,
        })

    return {
        "rules":            rules_legacy,
        "rules_hard":       rules_hard,
        "rules_conventions": rules_conventions,
        "interpreted_rules": interpreted,
        "reasoning_log":    reasoning_log,
        "planning_decisions": planning_decisions,
        "llm_used_agents":  llm_used_agents,
    }


# ---------------------------------------------------------------------------
# LLM-Planungsrat
# ---------------------------------------------------------------------------

def _planungsrat(
    *,
    briefing: dict,
    rules_hard: dict,
    rules_conventions: dict,
    gewichtungen: dict,
    nutzungstyp: str,
) -> tuple[dict, list[dict]]:
    """Single-Call mit erzwungener Rollentrennung (Hybrid-Ansatz)."""
    from langchain_core.messages import SystemMessage, HumanMessage

    aktive_disziplinen = _aktive_disziplinen(nutzungstyp, briefing)

    system = (
        "Du bist ein Planungsrat fuer Industriebauten. "
        "Du analysierst ein Projektsteckbrief und leitest daraus "
        "varianten-spezifische Planungskonfigurationen ab.\n\n"
        "WICHTIG: Antworte ausschliesslich mit einem JSON-Objekt.\n\n"
        "Vorgehen:\n"
        "1. Analysiere das Briefing aus Sicht jeder Fachdisziplin UNABHAENGIG.\n"
        "   Jede Disziplin schreibt ihre Anforderungen ohne Kompromiss.\n"
        "2. Synthetisiere anschliessend fuer jede Variante basierend auf "
        "   deren Gewichtung (materialfluss/erweiterbarkeit/tragwerk).\n"
        "3. Harte Regeln (rules_hard) sind unveraenderlich — pruefe nur ob "
        "   Kompensationsmassnahmen sinnvoll sind.\n"
        "4. Weiche Regeln (rules_conventions) waehle aus dem 'range'-Wertebereich.\n\n"
        f"Aktive Disziplinen: {', '.join(aktive_disziplinen)}"
    )

    output_schema = {
        "disziplin_analysen": {
            "<Disziplin>": {
                "kernforderungen": ["..."],
                "konflikte_mit": {"<andere Disziplin>": "Konfliktbeschreibung"},
                "kompensationen": ["Sprinkleranlage empfohlen wenn..."],
            }
        },
        "interpreted_rules": {
            "<VariantenName>": {
                "tragwerk": {
                    "raster_x_m": 18,
                    "raster_y_m": 12,
                    "traufhoehe_m": 8.0,
                },
                "brandschutz": {
                    "brandabschnitt_max_m2": 5000,
                    "sprinkler_erforderlich": False,
                },
                "logistik": {
                    "materialfluss_max_laenge_m": 150,
                    "andockstellen_we_min": 2,
                    "andockstellen_versand_min": 2,
                    "rangierflaeche_tiefe_m": 35,
                },
                "erschliessung": {
                    "erschliessungsbreite_m": 6.0,
                },
                "erweiterbarkeit": {
                    "freie_fassade_min_pct": 0.30,
                    "erweiterungsrichtung": "Ost",
                },
            }
        },
        "reasoning": [
            {
                "disziplin": "<Disziplin>",
                "variante": "<VariantenName>",
                "entscheidung": "Raster 24m gewaehlt",
                "begruendung": "Kranbahn erfordert mindestens 24m",
                "regelref": "rules_conventions.tragwerk.raster_x_m",
                "wert_vorher": 18,
                "wert_nachher": 24,
            }
        ],
    }

    try:
        response = invoke_messages(
            [
                SystemMessage(content=system),
                HumanMessage(content=json.dumps({
                    "briefing": briefing,
                    "varianten_gewichtungen": gewichtungen,
                    "rules_hard": rules_hard,
                    "rules_conventions": rules_conventions,
                    "output_schema": output_schema,
                }, ensure_ascii=False, indent=2, default=str)),
            ],
            temperature=0.15,
        )

        parsed = _parse_json(response)
        interpreted = parsed.get("interpreted_rules") or {}
        raw_reasoning = parsed.get("reasoning") or []

        log_entries = [
            _log_entry(
                agent="rule_agent",
                disziplin=r.get("disziplin", ""),
                variante=r.get("variante", ""),
                entscheidung=r.get("entscheidung", ""),
                begruendung=r.get("begruendung", ""),
                regelref=r.get("regelref", ""),
                wert_vorher=r.get("wert_vorher"),
                wert_nachher=r.get("wert_nachher"),
            )
            for r in raw_reasoning
            if isinstance(r, dict)
        ]

        if not interpreted:
            raise ValueError("LLM hat kein interpreted_rules zurueckgegeben")

        _validate_interpreted(interpreted)
        return interpreted, log_entries

    except Exception as exc:
        print(f"[rules] LLM-Planungsrat fehlgeschlagen: {exc} — Fallback")
        from app.state import VARIANTEN_GEWICHTUNGEN
        nutztyp = str(nutzungstyp)
        fb = _fallback_interpreted(rules_conventions, nutztyp, briefing)
        log = [_log_entry(
            agent="rule_agent", disziplin="System", variante="alle",
            entscheidung="Fallback nach LLM-Fehler",
            begruendung=str(exc),
            regelref="rules_conventions.*.default",
        )]
        return fb, log


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback_interpreted(
    rules_conventions: dict,
    nutzungstyp: str,
    briefing: dict,
) -> dict:
    """Deterministischer Fallback: Default-Werte aus rules_conventions."""
    trag = rules_conventions.get("tragwerk", {})
    log  = rules_conventions.get("logistik", {})
    erw  = rules_conventions.get("erweiterbarkeit", {})
    ers  = rules_conventions.get("erschliessung", {})

    kranbahn  = briefing.get("kranbahn_erforderlich", False)
    hochregal = briefing.get("hochregallager", False)

    raster_x = 24 if (kranbahn or hochregal) else _default(trag, "raster_x_m", 18)
    traufh   = 10.0 if kranbahn else (18.0 if hochregal else _default(trag, "traufhoehe_m", 8.0))

    basis = {
        "tragwerk": {
            "raster_x_m":    raster_x,
            "raster_y_m":    _default(trag, "raster_y_m", 12),
            "traufhoehe_m":  traufh,
        },
        "brandschutz": {
            "brandabschnitt_max_m2": 10000 if nutzungstyp == "Logistik" else 5000,
            "sprinkler_erforderlich": nutzungstyp == "Logistik",
        },
        "logistik": {
            "materialfluss_max_laenge_m": _default(log, "materialfluss_max_laenge_m", 150),
            "andockstellen_we_min":       _default(log, "andockstellen_we_min", 2),
            "andockstellen_versand_min":  _default(log, "andockstellen_versand_min", 2),
            "rangierflaeche_tiefe_m":     _default(log, "rangierflaeche_tiefe_m", 35),
        },
        "erschliessung": {
            "erschliessungsbreite_m": _default(ers, "erschliessungsbreite_haupt_m", 6.0),
        },
        "erweiterbarkeit": {
            "freie_fassade_min_pct":  _default(erw, "freie_fassade_min_pct", 0.30),
            "erweiterungsrichtung":   "Ost",
        },
    }

    return {
        "A_Materialfluss":   copy.deepcopy(basis),
        "B_Erweiterbarkeit": _variant_b(basis, erw),
        "C_Ausgewogen":      copy.deepcopy(basis),
    }


def _variant_b(basis: dict, erw: dict) -> dict:
    b = copy.deepcopy(basis)
    b["erweiterbarkeit"]["freie_fassade_min_pct"] = _default(erw, "freie_fassade_min_pct", 0.40)
    return b


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _aktive_disziplinen(nutzungstyp: str, briefing: dict) -> list[str]:
    disziplinen = ["Tragwerk", "Brandschutz", "Materialfluss", "Erschliessung", "Erweiterbarkeit"]
    buero_nuf2 = float(briefing.get("buero_nuf2") or 0)
    bgf = float(briefing.get("bgf_gesamt") or 1)
    if buero_nuf2 / bgf > 0.15:
        disziplinen.append("Arbeitsstaettenrecht")
    if nutzungstyp in ("Data Center", "Nutzungstyp.DATA_CENTER"):
        disziplinen.append("TGA_Haustechnik")
    return disziplinen


def _validate_interpreted(interpreted: dict) -> None:
    """Prueft Mindeststruktur — wirft ValueError bei fehlendem Inhalt."""
    required_variants = {"A_Materialfluss", "B_Erweiterbarkeit", "C_Ausgewogen"}
    missing = required_variants - set(interpreted.keys())
    if missing:
        raise ValueError(f"interpreted_rules fehlt Varianten: {missing}")
    for v, cfg in interpreted.items():
        if not isinstance(cfg, dict) or "tragwerk" not in cfg:
            raise ValueError(f"Variante {v}: kein 'tragwerk'-Schluessel")


def _default(section: dict, key: str, fallback):
    entry = section.get(key, {})
    if isinstance(entry, dict):
        return entry.get("default", fallback)
    return fallback


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_legacy(nutzungstyp) -> dict:
    """Laedt altes demo_rules.yaml fuer Rueckwaertskompatibilitaet."""
    if not RULES_LEGACY_PATH.exists():
        return {}
    key_map = {
        Nutzungstyp.PRODUKTION:  "produktion",
        Nutzungstyp.LOGISTIK:    "logistik",
        Nutzungstyp.DATA_CENTER: "data_center",
    }
    key = key_map.get(nutzungstyp, "")
    with open(RULES_LEGACY_PATH, encoding="utf-8") as f:
        all_rules = yaml.safe_load(f) or {}
    return copy.deepcopy(all_rules.get(key, {}))


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


def _log_entry(
    *,
    agent: str,
    disziplin: str,
    variante: str,
    entscheidung: str,
    begruendung: str,
    regelref: str,
    wert_vorher=None,
    wert_nachher=None,
) -> dict:
    entry: dict = {
        "agent":       agent,
        "disziplin":   disziplin,
        "variante":    variante,
        "entscheidung": entscheidung,
        "begruendung": begruendung,
        "regelref":    regelref,
    }
    if wert_vorher is not None:
        entry["wert_vorher"] = wert_vorher
    if wert_nachher is not None:
        entry["wert_nachher"] = wert_nachher
    return entry

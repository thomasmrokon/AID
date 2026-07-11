"""
AID Demo – State-Definitionen
Pydantic-Modelle für alle drei Nutzungstypen sowie der LangGraph-PlanningState.
"""

from __future__ import annotations
from typing import TypedDict, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Nutzungstyp(str, Enum):
    PRODUKTION   = "Produktion"
    LOGISTIK     = "Logistik"
    DATA_CENTER  = "Data Center"


class TierLevel(str, Enum):
    I   = "I"
    II  = "II"
    III = "III"
    IV  = "IV"


# ---------------------------------------------------------------------------
# Gemeinsame Felder (alle Typen)
# ---------------------------------------------------------------------------

class GemeinsameFelder(BaseModel):
    nutzungstyp:      Nutzungstyp
    buero_nuf2:       float = Field(..., gt=0,
                                   description="Büro- und Verwaltungsfläche (NUF 2) in m²")
    buero_geschosse:  int = Field(2, ge=1, le=6,
                                   description="Geschossigkeit Büro / Verwaltung")
    technikflaeche_tf:  Optional[float] = Field(None,
                                   description="Technikfläche (TF) in m² – Default: 6 % der NUF")
    sozialraeume_nuf7:  Optional[float] = Field(None,
                                   description="Sozialräume / Sanitär (NUF 7) in m²")
    sonderbedingungen:  Optional[str]   = Field(None,
                                   description="Freies Feld für besondere Anforderungen")


# ---------------------------------------------------------------------------
# Typ 1: Produktion
# ---------------------------------------------------------------------------

class ProduktionInput(GemeinsameFelder):
    nutzungstyp:          Nutzungstyp   = Nutzungstyp.PRODUKTION
    produktionsflaeche:   float         = Field(..., ge=500,  le=20_000,
                                               description="Produktionsfläche (NUF 3) in m²")
    lager_rohstoffe:      float         = Field(..., ge=200,  le=5_000,
                                               description="Lager Rohstoffe/Halbzeuge (NUF 4) in m²")
    lager_fertigwaren:    float         = Field(..., ge=200,  le=5_000,
                                               description="Lager Fertigwaren (NUF 4) in m²")
    wareneingang:         float         = Field(..., ge=100,  le=2_000,
                                               description="Wareneingang (NUF 4) in m²")
    versand:              float         = Field(..., ge=100,  le=2_000,
                                               description="Versand / Warenausgang (NUF 4) in m²")
    qualitaetssicherung:  Optional[float] = Field(None, ge=50, le=1_000,
                                               description="Qualitätssicherung (NUF 3) in m²")
    kranbahn_erforderlich: bool         = Field(False,
                                               description="Kranbahn erforderlich → beeinflusst Stützenraster")


# ---------------------------------------------------------------------------
# Typ 2: Logistik
# ---------------------------------------------------------------------------

class LogistikInput(GemeinsameFelder):
    nutzungstyp:           Nutzungstyp   = Nutzungstyp.LOGISTIK
    lagerflaeche:          float         = Field(..., ge=2_000, le=50_000,
                                                description="Lagerfläche inkl. Puffer (NUF 4) in m²")
    kommissionierung:      float         = Field(..., ge=500,   le=10_000,
                                                description="Kommissionierung / Picking (NUF 4) in m²")
    wareneingang_rampen:   float         = Field(..., ge=300,   le=3_000,
                                                description="Wareneingang mit Rampen (NUF 4) in m²")
    warenausgang_rampen:   float         = Field(..., ge=300,   le=3_000,
                                                description="Warenausgang / Versand mit Rampen (NUF 4) in m²")
    retouren:              Optional[float] = Field(None, ge=100, le=2_000,
                                                description="Retourenfläche (NUF 4) in m²")
    hochregallager:        bool           = Field(False,
                                                description="Hochregallager → Stützenraster 24×12 m, h ≥ 18 m")


# ---------------------------------------------------------------------------
# Typ 3: Data Center
# ---------------------------------------------------------------------------

class DataCenterInput(GemeinsameFelder):
    nutzungstyp:               Nutzungstyp   = Nutzungstyp.DATA_CENTER
    whitespace_it:             float         = Field(..., ge=500,  le=10_000,
                                                    description="IT-Fläche / Whitespace (NUF 3) in m²")
    usv_trafo_pct:             float         = Field(0.20, ge=0.15, le=0.25,
                                                    description="USV / Trafo als Anteil am Whitespace")
    kuehlung_chiller_pct:      float         = Field(0.25, ge=0.20, le=0.30,
                                                    description="Kühlung / Chiller als Anteil am Whitespace")
    notstrom_generatoren_pct:  float         = Field(0.12, ge=0.10, le=0.15,
                                                    description="Notstrom / Generatoren als Anteil am Whitespace")
    noc_buero:                 float         = Field(..., ge=100,  le=1_000,
                                                    description="NOC / Büro (NUF 2) in m²")
    staging_lager:             Optional[float] = Field(None, ge=100, le=500,
                                                    description="Staging-Lager für Hardware (NUF 4) in m²")
    tier_level:                TierLevel     = Field(TierLevel.III,
                                                    description="Tier-Level nach Uptime Institute (I–IV)")
    it_last_kw:                Optional[float] = Field(None,
                                                    description="IT-Last in kW – beeinflusst Kühlflächenbedarf")


# ---------------------------------------------------------------------------
# Varianten-Gewichtungen
# ---------------------------------------------------------------------------

class ParameterGewichtung(BaseModel):
    materialfluss:   float = Field(..., ge=0.0, le=1.0)
    erweiterbarkeit: float = Field(..., ge=0.0, le=1.0)
    tragwerk:        float = Field(..., ge=0.0, le=1.0)
    beschreibung:    str   = ""


VARIANTEN_GEWICHTUNGEN: dict[str, ParameterGewichtung] = {
    "A_Materialfluss": ParameterGewichtung(
        materialfluss=0.7, erweiterbarkeit=0.2, tragwerk=0.1,
        beschreibung="Optimiert auf kurze Transportwege entlang der Prozesskette"
    ),
    "B_Erweiterbarkeit": ParameterGewichtung(
        materialfluss=0.2, erweiterbarkeit=0.7, tragwerk=0.1,
        beschreibung="Maximale Erweiterungsreserve an der freisten Fassade (standortabhängig)"
    ),
    "C_Ausgewogen": ParameterGewichtung(
        materialfluss=0.4, erweiterbarkeit=0.4, tragwerk=0.2,
        beschreibung="Ausgewogenes Verhältnis aller drei Parameter"
    ),
}


# ---------------------------------------------------------------------------
# LangGraph PlanningState
# ---------------------------------------------------------------------------

class PlanningState(TypedDict, total=False):
    # CONTRACT: Owner = Claude Code. Neue Keys nur via Claude hinzufügen.
    # Readers sind in den Kommentaren vermerkt. Bestehende Keys nicht umbenennen.
    # Siehe AGENTS.md → Contract A für die vollständigen Regeln.

    # --- Input (Owner: streamlit_app / demo.py) ---
    user_input:             dict[str, Any]   # validiertes Pydantic-Dict | Readers: briefing, alle
    site_geometry:          dict[str, Any]   # Gebäudeparzelle aus Masterplanung; Legacy: Grundstück | Readers: layout, report, tools
    masterplan:             dict[str, Any]   # Gesamtgrundstück, Erschließung, Nebenbauten, Freiflächen | Readers: streamlit, report
    building_parcels:       list[dict[str, Any]]  # alle von der Masterplanung erzeugten Gebäudeparzellen | Readers: streamlit
    selected_building_parcel_id: str                # gewählte Parzelle für Layoutplanung | Readers: streamlit, report
    building_parcel:        dict[str, Any]          # ausgewählte Schnittstelle Masterplanung -> Layoutplanung | Readers: layout, streamlit

    # --- Briefing-Agent (Owner: briefing.py) ---
    structured_briefing:    dict[str, Any]   # angereichertes Briefing mit Defaults | Readers: rules, topology, layout, evaluation
    sonderbedingungen_parsed: Optional[dict[str, Any]]  # LLM-Extraktion aus Freitext
    process_steps:          Optional[list[dict[str, Any]]]  # Produktionsschritte aus Sonderbedingungen | Owner: briefing_agent | Readers: topology_agent, layout_agent
    mep_anforderungen:      dict[str, Any]   # MEP-Gewerke + Lastkategorie aus Schritt 2 | Owner: briefing_agent | Readers: mep_agent, report_agent
    tragwerk_config:        dict[str, Any]   # Tragwerktypologie + Raster aus Schritt 2 | Owner: briefing_agent | Readers: layout_agent, evaluation_agent, report_agent

    # --- Rule-Agent (Owner: gemini / rules.py) ---
    rules:                  dict[str, Any]   # typspezifisches Regelset (Basiswerte, Fallback) | Readers: layout, evaluation
    rules_hard:             dict[str, Any]   # gesetzlich bindende Anforderungen (unveraenderlich)
    rules_conventions:      dict[str, Any]   # Planungskonventionen mit Wertebereichen
    interpreted_rules:      dict[str, dict[str, Any]]  # LLM-interpretierte Regeln pro Variante | Readers: strategy, layout
    rule_overrides:         dict[str, Any]   # manuelle YAML/JSON-Anpassungen fuer das aktive Regelset
    rule_change_request:    Optional[str]    # Freitext-Wunsch fuer LLM-basierte Regelanpassung
    rule_change_summary:    Optional[str]    # Kurzprotokoll der angewendeten Regelanpassung

    # --- Topology-Agent (Owner: gemini / topology.py) ---
    topology_diagram:       dict[str, Any]   # Funktionsknoten und gewichtete Beziehungen | Readers: strategy, evaluation, analyse

    # --- Strategy-Agent (Owner: claude / strategy.py) ---
    layout_strategy:        dict[str, Any]   # LLM/Fallback-Strategie fuer Layouttypologie
    zone_roles:             dict[str, dict[str, str]]  # Zonenzuweisung pro Variante (spine/tooth/quadrant/...)
    typology_assignments:   dict[str, str]             # Topologiefunktion pro Variante ("recursive")
    topology_decisions:     list[dict[str, Any]]
    strategy_decisions:     list[dict[str, Any]]
    compliance_issues:      list[dict[str, Any]]
    layout_corrections:     dict[str, Any]
    layout_iteration:       int
    needs_layout_refinement: bool

    # --- Layout-Agent (Owner: claude / layout.py + layout_recursive.py) ---
    variants:               list[dict[str, Any]]  # 3 Layoutvarianten | Readers: erschliessung, mep, evaluation, report, streamlit

    # --- Erschließungs-Agent (Owner: claude / erschliessung.py) ---
    erschliessungsgraphen:  dict[str, dict]  # Verbindungsgraph je Variante | Readers: mep, drawing, report
    # Kanten-Felder: typ, shared_wall_m, korridor_breite_m, pfad_punkte, pfad_laenge_m

    # --- MEP-Agent (Owner: mep.py) ---
    mep_trassennetz:        dict[str, Any]   # MEP-Anforderungen + Trassen-Skeleton je Variante | Owner: mep_agent | Readers: drawing, report

    # --- Evaluation-Agent (Owner: copilot / evaluation.py) ---
    evaluations:            list[dict[str, Any]]  # Scores je Variante | Readers: analyse, report, streamlit
    selected_variant:       str                   # empfohlene Variante

    # --- Analyse-Agent (Owner: gemini / analyse.py, optional) ---
    llm_analyse:            Optional[str]    # Qualitative Analyse, None wenn kein API-Key

    # --- Report-Agent (Owner: gemini / report.py) ---
    report_markdown:        str
    artifacts:              dict[str, str]   # Dateinamen der generierten PNGs/JSONs

    # --- Reasoning Log (alle Agenten schreiben, niemand liest außer Analyse/Report) ---
    reasoning_log:          list[dict[str, Any]]  # Entscheidungsketten fuer Report + Debugging

    # --- Projektziele & Layout-Konfiguration (Owner: claude / streamlit_app.py → layout.py) ---
    custom_gewichtungen:    dict[str, dict[str, float]]  # z.B. {"A_Materialfluss": {"materialfluss": 0.8, ...}}
    projektziele:           list[str]                    # gewählte Projektziele, z.B. ["materialfluss", "erweiterbarkeit"]
    split_priority_map:     dict[str, str]               # {variante_key: split_priority} für rekursives Layout
    adjacency_weights:      dict[str, float]             # Kantengewichte aus Funktionsgraph {src__tgt: weight} | Owner: streamlit | Readers: layout
    zone_splits:            dict[str, int]               # Zone-Name → Anzahl Teilbereiche (1 = keine Aufteilung) | Owner: streamlit | Readers: layout
    gap_strategy:           str                          # Lückenbehandlung: "none" | "sort" | "corridor" | "all" | Owner: streamlit | Readers: layout

    # --- Entscheidungsprotokoll (alle Agenten schreiben, Report liest) ---
    planning_decisions:  list[dict[str, Any]]  # strukturiertes Entscheidungsprotokoll

    # --- Determinismus-Tracking (alle Agenten schreiben, Streamlit liest) ---
    # Owner: rules/topology (schreiben), streamlit (liest für Badge)
    # Enthält Namen der Agenten, die LLM für PLANUNGSENTSCHEIDUNGEN verwendet haben.
    # Reine Textagenten (analyse, report) werden hier NICHT erfasst.
    llm_used_agents:     list[str]  # z.B. ["rules", "topology"]

    # --- Prozessplanung (Owner: process.py / Streamlit Schritt 7) ---
    process_input:       Optional[dict[str, Any]]   # {mode, zone_name, maschinenpark, reference_layout} | Owner: streamlit | Readers: process_agent
    process_layout:      Optional[dict[str, Any]]   # {mode, maschinen, strips, kpis, transfer?}  | Owner: process_agent | Readers: process_viz, streamlit
    process_selected_variant: Optional[str]         # welche Layoutvariante als Basis | Owner: streamlit


# ---------------------------------------------------------------------------
# Prozessplanung: Datenmodelle
# ---------------------------------------------------------------------------

class Maschine(TypedDict, total=False):
    """Eine Maschine / Arbeitsstation im Produktionsprozess."""
    id:           str          # eindeutige ID, z.B. "M01"
    name:         str          # Anzeigename, z.B. "CNC-Fräse"
    schritt:      int          # Reihenfolge im Prozessablauf (1-basiert)
    breite_m:     float        # Maschinenbreite inkl. Bedienerbereich [m]
    tiefe_m:      float        # Maschinentiefe inkl. Bedienerbereich [m]
    anzahl:       int          # Anzahl gleichartiger Maschinen
    taktzeit_s:   float        # Zykluszeit pro Teil [s]
    farbe:        str          # Hex-Farbe für Visualisierung
    kategorie:    str          # "Bearbeitung" | "Montage" | "Prüfung" | "Lager" | "Transport"


DEMO_MASCHINENPARK: list[dict] = [
    # Schritt 1 – Zuschnitt / Vorbereitung
    {"id": "M01", "name": "Tafelschere",        "schritt": 1, "breite_m": 4.0, "tiefe_m": 2.5, "anzahl": 1, "taktzeit_s": 45,  "farbe": "#2E86AB", "kategorie": "Bearbeitung"},
    {"id": "M02", "name": "Ablängsäge",         "schritt": 1, "breite_m": 3.5, "tiefe_m": 2.0, "anzahl": 1, "taktzeit_s": 30,  "farbe": "#2E86AB", "kategorie": "Bearbeitung"},
    # Schritt 2 – Bearbeitung
    {"id": "M03", "name": "CNC-Fräse",          "schritt": 2, "breite_m": 4.5, "tiefe_m": 4.0, "anzahl": 2, "taktzeit_s": 120, "farbe": "#A23B72", "kategorie": "Bearbeitung"},
    {"id": "M04", "name": "Drehmaschine",       "schritt": 2, "breite_m": 3.0, "tiefe_m": 2.0, "anzahl": 2, "taktzeit_s": 90,  "farbe": "#A23B72", "kategorie": "Bearbeitung"},
    # Schritt 3 – Oberflächenbehandlung
    {"id": "M05", "name": "Strahlkabine",       "schritt": 3, "breite_m": 5.0, "tiefe_m": 4.0, "anzahl": 1, "taktzeit_s": 180, "farbe": "#F18F01", "kategorie": "Bearbeitung"},
    {"id": "M06", "name": "Lackieranlage",      "schritt": 3, "breite_m": 8.0, "tiefe_m": 5.0, "anzahl": 1, "taktzeit_s": 240, "farbe": "#F18F01", "kategorie": "Bearbeitung"},
    # Schritt 4 – Montage
    {"id": "M07", "name": "Montagetisch 1",     "schritt": 4, "breite_m": 3.0, "tiefe_m": 1.5, "anzahl": 4, "taktzeit_s": 300, "farbe": "#C73E1D", "kategorie": "Montage"},
    {"id": "M08", "name": "Schweißplatz",       "schritt": 4, "breite_m": 3.5, "tiefe_m": 3.0, "anzahl": 2, "taktzeit_s": 200, "farbe": "#C73E1D", "kategorie": "Montage"},
    # Schritt 5 – Prüfung / QS
    {"id": "M09", "name": "Messmaschine (KMG)", "schritt": 5, "breite_m": 4.0, "tiefe_m": 3.5, "anzahl": 1, "taktzeit_s": 150, "farbe": "#3B1F2B", "kategorie": "Prüfung"},
    {"id": "M10", "name": "Prüfstand",          "schritt": 5, "breite_m": 5.0, "tiefe_m": 4.0, "anzahl": 1, "taktzeit_s": 180, "farbe": "#3B1F2B", "kategorie": "Prüfung"},
]

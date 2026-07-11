"""
AID Demo – Hauptskript
Führt die LangGraph-Pipeline mit einem Beispiel-Briefing aus.

Verwendung:
    python demo.py                    # Produktion (Default)
    python demo.py --typ logistik
    python demo.py --typ datacenter
"""

import argparse
import json
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env wird nicht benötigt wenn kein OpenAI-Key gesetzt ist
from app.graph import graph
from app.state import Nutzungstyp
from app.tools.site import get_demo_site, get_demo_sites


# ---------------------------------------------------------------------------
# Beispiel-Inputs je Nutzungstyp
# ---------------------------------------------------------------------------

BEISPIEL_INPUTS = {

    "produktion": {
        "nutzungstyp":          Nutzungstyp.PRODUKTION,
        "produktionsflaeche":   1200,
        "lager_rohstoffe":      400,
        "lager_fertigwaren":    400,
        "wareneingang":         200,
        "versand":              200,
        "qualitaetssicherung":  150,
        "buero_nuf2":           250,
        "buero_geschosse":      2,
        "technikflaeche_tf":    None,   # → wird automatisch berechnet
        "sozialraeume_nuf7":    None,   # → wird automatisch berechnet
        "kranbahn_erforderlich": False,
        "sonderbedingungen":    "Erweiterung nach Osten muss möglich bleiben. "
                                "Büro und Produktion sollen akustisch getrennt sein.",
    },

    "logistik": {
        "nutzungstyp":          Nutzungstyp.LOGISTIK,
        "lagerflaeche":         5000,
        "kommissionierung":     1200,
        "wareneingang_rampen":  600,
        "warenausgang_rampen":  600,
        "retouren":             300,
        "buero_nuf2":           350,
        "buero_geschosse":      2,
        "technikflaeche_tf":    None,
        "sozialraeume_nuf7":    None,
        "hochregallager":       False,
        "sonderbedingungen":    "LKW-Zufahrt von Norden. Retourenfläche separat erschlossen.",
    },

    "datacenter": {
        "nutzungstyp":              Nutzungstyp.DATA_CENTER,
        "whitespace_it":            1500,
        "usv_trafo_pct":            0.20,
        "kuehlung_chiller_pct":     0.25,
        "notstrom_generatoren_pct": 0.12,
        "noc_buero":                250,
        "staging_lager":            150,
        "buero_nuf2":               200,
        "buero_geschosse":          2,
        "technikflaeche_tf":        None,
        "sozialraeume_nuf7":        None,
        "tier_level":               "III",
        "it_last_kw":               3000,
        "sonderbedingungen":        "Zwei unabhängige Mittelspannungseinspeisung erforderlich. "
                                    "Erweiterung auf Tier IV muss architektonisch vorbereitet werden.",
    },
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AID Demo – Layoutgenerator")
    parser.add_argument(
        "--typ", choices=["produktion", "logistik", "datacenter"],
        default="produktion",
        help="Nutzungstyp für den Demo-Lauf (default: produktion)"
    )
    parser.add_argument(
        "--grundstueck",
        choices=[site["id"] for site in get_demo_sites()],
        default="A_kompakt",
        help="Reproduzierbares Demo-Grundstueck"
    )
    parser.add_argument(
        "--regelwerk-json",
        help="Pfad zu einer JSON-Datei mit Overrides für das aktive Regelset"
    )
    parser.add_argument(
        "--regelwerk-text",
        help="Freitext-Wunsch für eine LLM-basierte Regelwerkanpassung"
    )
    args = parser.parse_args()

    user_input = BEISPIEL_INPUTS[args.typ]
    site_geometry = get_demo_site(args.grundstueck)
    print(f"\n{'='*60}")
    print(f"  AID Demo · Nutzungstyp: {user_input['nutzungstyp']}")
    print(f"  Grundstueck: {site_geometry['name']} ({site_geometry['area_m2']} m2)")
    print(f"{'='*60}\n")

    initial_state = {
        "user_input": user_input,
        "site_geometry": site_geometry,
    }
    if args.regelwerk_json:
        with open(Path(args.regelwerk_json), "r", encoding="utf-8") as f:
            initial_state["rule_overrides"] = json.load(f)
    if args.regelwerk_text:
        initial_state["rule_change_request"] = args.regelwerk_text

    result = graph.invoke(initial_state)

    print(f"\n{'='*60}")
    print("  REPORT")
    print(f"{'='*60}")
    print(result["report_markdown"])

    print(f"\n{'='*60}")
    print("  ARTEFAKTE")
    print(f"{'='*60}")
    for name, path in result["artifacts"].items():
        print(f"  {name:30s}  ->  {path}")

    print(f"\n  Empfehlung: {result['selected_variant']}\n")
    if result.get("rule_change_summary"):
        print(f"  Regelwerk: {result['rule_change_summary']}\n")


if __name__ == "__main__":
    main()

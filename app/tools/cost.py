"""
AID Demo – Kostenschätzung
Berechnet eine grobe Kostenindikation (3 Szenarien) aus Zonen-Footprints.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml


_COSTS_PATH = Path(__file__).parent.parent / "data" / "costs.yaml"
_costs_cache: dict | None = None


def _load_costs() -> dict:
    global _costs_cache
    if _costs_cache is None:
        with open(_COSTS_PATH, encoding="utf-8") as f:
            _costs_cache = yaml.safe_load(f)
    return _costs_cache


def estimate_costs(variant: dict[str, Any], briefing: dict[str, Any]) -> dict[str, Any]:
    """Schätzt Baukosten für eine Layoutvariante (3 Szenarien: min / mid / max).

    Args:
        variant:  Varianten-Dict aus PlanningState["variants"][i]
        briefing: structured_briefing aus PlanningState

    Returns:
        {
            "baukosten_min":      float,   # € Untergrenze
            "baukosten_mid":      float,   # € Mittelwert
            "baukosten_max":      float,   # € Obergrenze
            "nebenkosten_mid":    float,   # € Nebenkosten (auf Mittelwert)
            "gesamtkosten_mid":   float,   # € Gesamt Mittelwert
            "kosten_je_m2_bgf":   float,   # €/m² Brutto-Grundfläche
            "zonen_aufschluesselung": [
                {
                    "zone": str,
                    "din_kategorie": str,
                    "flaeche_m2": float,
                    "kosten_min": float,
                    "kosten_mid": float,
                    "kosten_max": float,
                }
            ],
        }
    """
    costs = _load_costs()
    din_costs = costs.get("din_kategorien", {})
    zuschlaege = costs.get("zuschlaege", {})
    nebenkosten_cfg = costs.get("nebenkosten", {})

    kranbahn = bool(briefing.get("kranbahn_erforderlich", False))
    hochregal = bool(briefing.get("hochregallager", False))

    zonen = variant.get("zonen", [])
    aufschluesselung = []
    total_min = total_mid = total_max = 0.0
    total_bgf = 0.0

    for z in zonen:
        if z.get("schraffur"):          # Erweiterungsreserve überspringen
            continue
        din = z.get("din_kategorie", "NUF 3")
        floors = max(1, int(z.get("floors", 1)))
        footprint = float(z.get("breite", 0)) * float(z.get("tiefe", 0))
        flaeche = footprint * floors      # BGF dieser Zone (mehrgeschossig)

        base = din_costs.get(din, din_costs.get("NUF 3", {}))
        rate_min = float(base.get("min_eur_m2", 800))
        rate_mid = float(base.get("mid_eur_m2", 1100))
        rate_max = float(base.get("max_eur_m2", 1500))

        # Zuschläge
        if din == "NUF 3" and kranbahn:
            zuschl = float(zuschlaege.get("kranbahn_nuf3", 0))
            rate_min += zuschl
            rate_mid += zuschl
            rate_max += zuschl
        if din == "NUF 4" and hochregal:
            zuschl = float(zuschlaege.get("hochregal_nuf4", 0))
            rate_min += zuschl
            rate_mid += zuschl
            rate_max += zuschl
        if floors >= 2:
            og_zuschl = float(zuschlaege.get("mehrgeschossig", 0)) * (floors - 1)
            rate_min += og_zuschl
            rate_mid += og_zuschl
            rate_max += og_zuschl

        k_min = round(flaeche * rate_min, 0)
        k_mid = round(flaeche * rate_mid, 0)
        k_max = round(flaeche * rate_max, 0)

        aufschluesselung.append({
            "zone":          z.get("name", din),
            "din_kategorie": din,
            "flaeche_m2":    round(flaeche, 1),
            "kosten_min":    k_min,
            "kosten_mid":    k_mid,
            "kosten_max":    k_max,
        })
        total_min += k_min
        total_mid += k_mid
        total_max += k_max
        total_bgf += flaeche

    # Nebenkosten auf Mittelwert
    nk_pct = sum([
        float(nebenkosten_cfg.get("planung_honorar_pct", 0.13)),
        float(nebenkosten_cfg.get("bauleitung_pct", 0.04)),
        float(nebenkosten_cfg.get("unvorhergesehenes_pct", 0.10)),
        float(nebenkosten_cfg.get("aussenanlagen_pct", 0.06)),
        float(nebenkosten_cfg.get("baunebenkosten_pct", 0.05)),
    ])
    nebenkosten_mid = round(total_mid * nk_pct, 0)
    gesamtkosten_mid = round(total_mid + nebenkosten_mid, 0)
    kosten_je_m2 = round(gesamtkosten_mid / max(1.0, total_bgf), 0)

    return {
        "baukosten_min":          round(total_min, 0),
        "baukosten_mid":          round(total_mid, 0),
        "baukosten_max":          round(total_max, 0),
        "nebenkosten_mid":        nebenkosten_mid,
        "gesamtkosten_mid":       gesamtkosten_mid,
        "kosten_je_m2_bgf":       kosten_je_m2,
        "nebenkosten_pct":        round(nk_pct, 3),
        "zonen_aufschluesselung": aufschluesselung,
    }

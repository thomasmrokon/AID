"""
AID Demo – Scoring-Logik
Transparente, deterministische Bewertung der drei Layoutvarianten.
Alle Scores liegen im Bereich 0.0–10.0.
"""

from __future__ import annotations
from dataclasses import dataclass
from app.tools.geometry import (
    Zone,
    berechne_pfadlaenge,
    berechne_beste_freie_fassade,
    berechne_raster_score,
    shared_wall,
)


# ---------------------------------------------------------------------------
# Prozesspfade je Nutzungstyp
# ---------------------------------------------------------------------------

PROZESSPFADE = {
    "Produktion": [
        "Wareneingang", "Lager Rohstoffe", "Produktion",
        "Qualitätssicherung", "Lager Fertigwaren", "Versand"
    ],
    "Logistik": [
        "Wareneingang", "Lager", "Kommissionierung", "Versand"
    ],
    "Data Center": [
        "Einspeisung", "USV / Trafo", "Kühlung", "Whitespace IT", "NOC"
    ],
}

# Referenzlänge für die Normierung (Worst-Case-Pfad = Site-Diagonale × 2)
REFERENZ_PFAD_FAKTOR = 2.0


# ---------------------------------------------------------------------------
# Score-Ergebnis
# ---------------------------------------------------------------------------

@dataclass
class VariantenScore:
    variante:              str
    materialfluss_score:   float   # 0–10
    erweiterbarkeit_score: float   # 0–10
    tragwerk_score:        float   # 0–10
    regelverletzungen:     list[str]
    gesamtscore:           float   # gewichteter Gesamtscore
    aspect_ratio_score:    float | None = None
    grid_conformity_score: float | None = None
    empfohlen:             bool = False

    def als_dict(self) -> dict:
        return {
            "variante":              self.variante,
            "materialfluss_score":   self.materialfluss_score,
            "erweiterbarkeit_score": self.erweiterbarkeit_score,
            "tragwerk_score":        self.tragwerk_score,
            "regelverletzungen":     self.regelverletzungen,
            "gesamtscore":           self.gesamtscore,
            "aspect_ratio_score":    self.aspect_ratio_score,
            "grid_conformity_score": self.grid_conformity_score,
            "empfohlen":             self.empfohlen,
        }


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Adjacency-Gap-Analyse
# ---------------------------------------------------------------------------

def berechne_adjacency_gaps(
    zonen: list[Zone],
    topology_diagram: dict | None,
    min_weight: float = 0.5,
) -> list[tuple[str, str, float]]:
    """Liefert alle Topology-Kanten (src, tgt, weight) ohne gemeinsame Wand.

    Nur positive Kanten mit Gewicht ≥ min_weight werden geprüft
    (Separation-Kanten mit negativem Gewicht werden ignoriert).
    """
    if not topology_diagram:
        return []
    zone_map = {z.name: z for z in zonen if not z.schraffur}
    gaps: list[tuple[str, str, float]] = []
    for e in topology_diagram.get("edges", []):
        src = e.get("source", "")
        tgt = e.get("target", "")
        w   = float(e.get("weight", 0))
        if w < min_weight:          # Separation (negativ) und schwache Kanten
            continue
        if src not in zone_map or tgt not in zone_map:
            continue
        if shared_wall(zone_map[src], zone_map[tgt]) < 0.5:
            gaps.append((src, tgt, w))
    return gaps


def bewerte_variante(
    variante_name:  str,
    zonen:          list[Zone],
    nutzungstyp:    str,
    gewichtung:     dict,            # {"materialfluss": float, "erweiterbarkeit": float, "tragwerk": float}
    rules:          dict,
    site_breite:    float,
    site_tiefe:     float,
    site_area_m2:   float | None = None,
    optimization_result=None,
    topology_diagram: dict | None = None,
) -> VariantenScore:
    """Berechnet alle drei Teilscores und den gewichteten Gesamtscore."""

    zonen_dict = {z.name: z for z in zonen}

    # --- 1. Materialfluss-Score ---
    pfad = PROZESSPFADE.get(nutzungstyp, [])
    pfadlaenge = berechne_pfadlaenge(zonen_dict, pfad)

    import math
    site_diag  = math.dist((0, 0), (site_breite, site_tiefe))
    max_pfad   = site_diag * REFERENZ_PFAD_FAKTOR
    min_pfad   = site_breite * 0.5   # optimaler linearer Pfad

    mf_score = 10.0 * (1.0 - max(0.0, pfadlaenge - min_pfad) / max(1.0, max_pfad - min_pfad))
    mf_score = round(max(0.0, min(10.0, mf_score)), 2)

    # --- 1b. Adjacency-Gap-Penalty (fehlende Wandkontakte bei Prozess-Kanten) ---
    adjacency_gaps: list[tuple[str, str, float]] = []
    if topology_diagram:
        adjacency_gaps = berechne_adjacency_gaps(zonen, topology_diagram, min_weight=0.5)
        for src, tgt, w in adjacency_gaps:
            # Abzug 0.4 pro Gap, skaliert mit Kantengewicht
            penalty = round(0.4 * w, 2)
            mf_score = max(0.0, mf_score - penalty)

    # --- 2. Erweiterbarkeit-Score ---
    freie_fassade, _best_dir = berechne_beste_freie_fassade(zonen, site_breite, site_tiefe)
    min_pct   = rules.get("erweiterbarkeit", {}).get("freie_ostfassade_min_pct", 0.30)
    eb_score  = round(min(10.0, (freie_fassade / max(0.01, min_pct)) * 6.0 + freie_fassade * 4.0), 2)
    # Grundstücksreserve: Erweiterbarkeit macht nur Sinn wenn genug Platz vorhanden ist.
    # Multiplier 0→0 bei <5% Reserve, linear auf 1→1.0 bei ≥40% Reserve.
    if site_area_m2 and site_area_m2 > 0:
        building_fp = sum(z.breite * z.tiefe for z in zonen if not z.schraffur)
        reserve_ratio = max(0.0, (site_area_m2 - building_fp) / site_area_m2)
        reserve_mult = min(1.0, reserve_ratio / 0.40)
        eb_score = eb_score * reserve_mult
    eb_score  = round(max(0.0, min(10.0, eb_score)), 2)

    # --- 3. Tragwerk-Score ---
    raster_key_x = (
        "raster_kran_x_m" if nutzungstyp == "Produktion"
        and any(z.name == "Kranbahn" for z in zonen)
        else "raster_standard_x_m"
    )
    raster_x = rules.get("tragwerk", {}).get(raster_key_x, 18)
    raster_y = rules.get("tragwerk", {}).get("raster_standard_y_m", 12)
    tw_raw   = berechne_raster_score(zonen, raster_x, raster_y)
    tw_score = round(tw_raw * 10.0, 2)
    aspect_ratio_score = _aspect_ratio_score(zonen, rules, optimization_result)
    grid_conformity_score = _grid_conformity_score(
        zonen,
        raster_x_m=float(raster_x or 1.0),
        raster_y_m=float(raster_y or raster_x or 1.0),
        optimization_result=optimization_result,
    )

    # --- 4. Regelverletzungen ---
    verstösse = _pruefe_regeln(zonen_dict, nutzungstyp, rules, site_breite, site_tiefe)
    for src, tgt, w in adjacency_gaps:
        verstösse.append(f"Kein Wandkontakt: {src} <-> {tgt} (w={w:.2f}) - Flur erforderlich")

    # Abzug pro Regelverletzung
    abzug = len(verstösse) * 0.5
    mf_score = max(0.0, mf_score - abzug)
    eb_score = max(0.0, eb_score - abzug)
    tw_score = max(0.0, tw_score - abzug)

    # --- 5. Gewichteter Gesamtscore ---
    g = gewichtung
    gesamt = round(
        g["materialfluss"]   * mf_score +
        g["erweiterbarkeit"] * eb_score +
        g["tragwerk"]        * tw_score,
        2
    )

    return VariantenScore(
        variante=variante_name,
        materialfluss_score=mf_score,
        erweiterbarkeit_score=eb_score,
        tragwerk_score=tw_score,
        regelverletzungen=verstösse,
        gesamtscore=gesamt,
        aspect_ratio_score=aspect_ratio_score,
        grid_conformity_score=grid_conformity_score,
    )


def _decision_map(optimization_result) -> dict:
    if not optimization_result:
        return {}
    decisions = getattr(optimization_result, "zone_decisions", None)
    if decisions is None and isinstance(optimization_result, dict):
        decisions = optimization_result.get("zone_decisions")

    result = {}
    for decision in decisions or []:
        name = getattr(decision, "zone_name", None)
        if name is None and isinstance(decision, dict):
            name = decision.get("zone_name")
        if name:
            result[str(name)] = decision
    return result


def _decision_value(decision, key: str, default: float = 0.0) -> float:
    if decision is None:
        return default
    value = decision.get(key, default) if isinstance(decision, dict) else getattr(decision, key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _aspect_ratio_score(
    zonen: list[Zone],
    rules: dict,
    optimization_result=None,
) -> float:
    valid = [z for z in zonen if not z.schraffur and z.din_kategorie != "VF"]
    if not valid:
        return 10.0

    max_aspect = float(rules.get("tragwerk", {}).get("max_aspect_ratio", 4.0) or 4.0)
    decisions = _decision_map(optimization_result)
    zone_scores = []
    for z in valid:
        decision = decisions.get(z.name)
        if decision is not None:
            aspect = _decision_value(decision, "aspect_ratio", 1.0)
        else:
            aspect = max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe))
        penalty = min(1.0, max(0.0, aspect - max_aspect) / max(0.1, max_aspect))
        zone_scores.append(1.0 - penalty)
    return round(sum(zone_scores) / len(zone_scores) * 10.0, 2)


def _grid_conformity_score(
    zonen: list[Zone],
    raster_x_m: float,
    raster_y_m: float | None = None,
    optimization_result=None,
) -> float:
    valid = [z for z in zonen if not z.schraffur]
    if not valid:
        return 10.0

    raster_x_m = max(0.01, float(raster_x_m or 1.0))
    raster_y_m = max(0.01, float(raster_y_m or raster_x_m))
    decisions = _decision_map(optimization_result)
    zone_scores = []
    for z in valid:
        decision = decisions.get(z.name)
        if decision is not None:
            grid_deviation = _decision_value(decision, "grid_deviation_m", 0.0)
        else:
            dev_w = (z.breite % raster_x_m) / raster_x_m
            dev_h = (z.tiefe % raster_y_m) / raster_y_m
            grid_deviation = (
                min(dev_w, 1 - dev_w) * raster_x_m
                + min(dev_h, 1 - dev_h) * raster_y_m
            ) / 2
        zone_scores.append(1.0 - min(1.0, grid_deviation / raster_x_m))
    return round(sum(zone_scores) / len(zone_scores) * 10.0, 2)


# ---------------------------------------------------------------------------
# Regelprüfungen
# ---------------------------------------------------------------------------

def _pruefe_regeln(
    zonen_dict: dict[str, Zone],
    nutzungstyp: str,
    rules: dict,
    site_breite: float,
    site_tiefe: float,
) -> list[str]:
    verstösse = []

    if nutzungstyp == "Produktion":
        # Büro nicht im Logistikfluss
        buero = zonen_dict.get("Büro / Verwaltung")
        we    = zonen_dict.get("Wareneingang")
        vs    = zonen_dict.get("Versand")
        if buero and we and vs:
            buero_x = buero.centroid[0]
            we_x    = we.centroid[0]
            vs_x    = vs.centroid[0]
            x_min, x_max = min(we_x, vs_x), max(we_x, vs_x)
            if x_min < buero_x < x_max:
                verstösse.append("Büro liegt im Hauptlogistikfluss (WE–Versand)")

        # Technik an Außenwand prüfen
        technik = zonen_dict.get("Technik")
        if technik:
            an_aussenwand = (
                technik.x <= 1.0 or
                technik.x + technik.breite >= site_breite - 1.0 or
                technik.y <= 1.0 or
                technik.y + technik.tiefe >= site_tiefe - 1.0
            )
            if not an_aussenwand:
                verstösse.append("Technik nicht an Außenwand (Wartungszugang fehlt)")

    elif nutzungstyp == "Logistik":
        # Büro getrennt von Logistikzone
        buero  = zonen_dict.get("Büro / Verwaltung")
        lager  = zonen_dict.get("Lager")
        if buero and lager:
            import math
            dist = math.dist(buero.centroid, lager.centroid)
            if dist < 15.0:
                verstösse.append("Büro zu nah an Lagerfläche (< 15 m Abstand)")

    elif nutzungstyp == "Data Center":
        # Kühlung an Außenwand
        kuehlung = zonen_dict.get("Kühlung")
        if kuehlung:
            an_aussenwand = (
                kuehlung.x <= 1.0 or
                kuehlung.x + kuehlung.breite >= site_breite - 1.0
            )
            if not an_aussenwand:
                verstösse.append("Kühlaggregate nicht an Außenwand (PUE-Zielwert gefährdet)")

    return verstösse

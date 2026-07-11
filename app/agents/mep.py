"""
AID Demo – MEP-Agent (Sprint 4A: Anforderungsermittlung + Trassen-Skeleton)

Liest `mep_anforderungen` aus dem Briefing, ordnet jeder Zone die benötigten
Gewerke zu und bereitet das Trassen-Netz vor.

Sprint 4C: vollständiges Routing (Backbone, Abzweige, Dimensionierung).

READS:  state["mep_anforderungen"], state["variants"], state["structured_briefing"],
        state["erschliessungsgraphen"]
WRITES: {"mep_trassennetz": dict}
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

from app.state import PlanningState

MEP_RULES_PATH = Path(__file__).parent.parent / "data" / "rules_mep.yaml"

# DIN-277-Kategorie → YAML-Schlüssel in rules_mep.yaml
_DIN_TO_KEY: dict[str, str] = {
    "NUF 2": "NUF_2",
    "NUF 3": "NUF_3",
    "NUF 4": "NUF_4",
    "NUF 7": "NUF_7",
    "TF":    "TF",
    "VF":    "VF",
}

# Farben je Gewerk für spätere Visualisierung (Sprint 4C)
GEWERK_FARBEN: dict[str, str] = {
    "elektro_stark":     "#FFD700",   # Gelb
    "daten_it":          "#00BFFF",   # Hellblau
    "lueftung_rlt":      "#90EE90",   # Hellgrün
    "druckluft":         "#FFA07A",   # Lachs
    "wasser_trinkwasser": "#4169E1",  # Blau
    "abwasser":          "#8B4513",   # Braun
    "sprinkler":         "#FF6347",   # Tomatenrot
    "kaelte":            "#87CEEB",   # Himmelblau
}


def mep_agent(state: PlanningState) -> dict:
    """LangGraph-Node: MEP-Anforderungen je Zone ermitteln und Trassen-Netz vorbereiten."""
    mep_anf  = state.get("mep_anforderungen") or {}
    variants = state.get("variants") or []

    rules_mep        = _load_mep_rules()
    gewerke_regeln   = rules_mep.get("gewerke", {})
    trassen_defaults = rules_mep.get("trassen_defaults", {})

    aktive_gewerke = _aktive_gewerke_liste(mep_anf)
    mep_trassennetz: dict[str, dict] = {}

    for v in variants:
        variante_name = v.get("name", "")
        zonen_raw     = v.get("zonen", [])

        zonen_mep: list[dict] = []
        for z in zonen_raw:
            if z.get("schraffur"):
                continue
            din_raw = z.get("din_kategorie", "")
            din_key = _DIN_TO_KEY.get(din_raw)
            if not din_key:
                continue

            flaeche_m2 = float(z.get("breite", 0)) * float(z.get("tiefe", 0))
            erforderliche: dict[str, dict] = {}

            for gewerk_id, g_def in gewerke_regeln.items():
                anf   = g_def.get("anforderungen", {}).get(din_key, {})
                stufe = anf.get("stufe", "none")
                stufe = _user_override(gewerk_id, stufe, mep_anf)
                if stufe == "none":
                    continue

                auslegung_key = next(
                    (k for k in anf if k not in ("stufe", "norm")), None
                )
                auslegung_wert = anf.get(auslegung_key) if auslegung_key else None

                erforderliche[gewerk_id] = {
                    "label":               g_def.get("label", gewerk_id),
                    "stufe":               stufe,
                    "einheit":             g_def.get("einheit", ""),
                    "auslegung_wert":      auslegung_wert,
                    "auslegung_ergebnis":  _dimensioniere(gewerk_id, auslegung_wert, flaeche_m2, mep_anf),
                    "norm":                anf.get("norm", ""),
                    "farbe":               GEWERK_FARBEN.get(gewerk_id, "#AAAAAA"),
                }

            zonen_mep.append({
                "zone_name":     z.get("name", ""),
                "din_kategorie": din_raw,
                "flaeche_m2":    round(flaeche_m2, 1),
                "x":             z.get("x", 0),
                "y":             z.get("y", 0),
                "breite":        z.get("breite", 0),
                "tiefe":         z.get("tiefe", 0),
                "gewerke":       erforderliche,
            })

        # TF als Trassen-Anker identifizieren
        tf_zone = next((z for z in zonen_mep if z["din_kategorie"] == "TF"), None)

        # Backbone aus Erschließungsgraph ableiten
        erschl_graph = (state.get("erschliessungsgraphen") or {}).get(variante_name, {})
        backbone_kanten = [
            k for k in erschl_graph.get("kanten", [])
            if k["typ"] == "direkt"
        ]
        # Für Trassen-Routing: TF-Zone als Ursprung, direkte Kanten als Backbone-Segmente
        # korridor-Kanten werden in Sprint C mit Pfad-Geometrie ergänzt

        korridor_kanten = [k for k in erschl_graph.get("kanten", []) if k["typ"] == "korridor"]
        korridor_kanten_mit_pfad = [k for k in korridor_kanten if k.get("pfad_punkte")]
        backbone_geometrie = _baue_backbone_geometrie(korridor_kanten_mit_pfad)
        trassen_laenge = round(_berechne_trassen_laenge(backbone_kanten, korridor_kanten, zonen_mep), 1)

        mep_trassennetz[variante_name] = {
            "zonen":              zonen_mep,
            "tf_ursprung":        tf_zone,
            "backbone_kanten":    backbone_kanten,
            "korridor_kanten":    korridor_kanten,
            "korridor_kanten_mit_pfad": korridor_kanten_mit_pfad,
            "backbone_geometrie": backbone_geometrie,
            "aktive_gewerke":     aktive_gewerke,
            "trassen_defaults":   trassen_defaults,
            "trassen_laenge_gesamt_m": trassen_laenge,
        }

    gesamt_gewerke = sum(
        len(z["gewerke"])
        for vd in mep_trassennetz.values()
        for z in vd["zonen"]
    )
    gesamt_trassen_laenge = sum(v.get("trassen_laenge_gesamt_m", 0) for v in mep_trassennetz.values())
    gesamt_backbone_laenge = sum(
        sum(s.get("laenge_m", 0) for s in v.get("backbone_geometrie", []))
        for v in mep_trassennetz.values()
    )
    print(f"[mep] {len(variants)} Varianten · {gesamt_gewerke} Gewerk-Zuweisungen · "
          f"aktive Gewerke: {aktive_gewerke} · "
          f"Backbone: {gesamt_backbone_laenge:.0f} m · "
          f"Trassenlänge: {gesamt_trassen_laenge:.0f} m")
    return {"mep_trassennetz": mep_trassennetz}


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _baue_backbone_geometrie(korridor_kanten_mit_pfad: list[dict]) -> list[dict]:
    """
    Leitet aus korridor_kanten_mit_pfad eine flache Segment-Liste ab:
    [{"x0": float, "y0": float, "x1": float, "y1": float,
      "von": str, "nach": str, "laenge_m": float}, ...]
    """
    import math as _m
    segmente = []
    for kante in korridor_kanten_mit_pfad:
        pts = kante.get("pfad_punkte") or []
        for i in range(len(pts) - 1):
            x0, y0 = float(pts[i][0]),   float(pts[i][1])
            x1, y1 = float(pts[i+1][0]), float(pts[i+1][1])
            segmente.append({
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "von":   kante.get("von",  ""),
                "nach":  kante.get("nach", ""),
                "laenge_m": round(_m.hypot(x1-x0, y1-y0), 2),
            })
    return segmente

def _berechne_trassen_laenge(backbone_kanten, korridor_kanten, zonen_mep):
    """
    Schätzt Gesamt-Trassenlänge in Metern.
    backbone:  shared_wall_m / 2 je direkte Kante (Backbone läuft entlang Wand)
    korridor:  pfad_laenge_m je Korridor-Kante
    intern:    sum(zone["breite"] + zone["tiefe"]) * 0.5 je Produktions-/Lager-Zone
    """
    laenge = 0.0
    for k in backbone_kanten:
        laenge += float(k.get("shared_wall_m", 0)) / 2.0
    for k in korridor_kanten:
        laenge += float(k.get("pfad_laenge_m", 0))
    for z in zonen_mep:
        if z.get("din_kategorie") in ("NUF 2", "NUF 7"):
            laenge += (float(z.get("breite", 0)) + float(z.get("tiefe", 0))) * 0.5
    return laenge

def _load_mep_rules() -> dict:
    try:
        with open(MEP_RULES_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data or {}
    except FileNotFoundError:
        print(f"[mep] Warnung: {MEP_RULES_PATH} nicht gefunden — leere Regeln.")
        return {}
    except Exception as e:
        print(f"[mep] Fehler beim Laden der MEP-Regeln: {e}")
        return {}


def _user_override(gewerk_id: str, stufe: str, mep_anf: dict) -> str:
    """Wertet User-Schalter aus mep_anforderungen aus.

    optional  + Schalter OFF → none
    optional  + Schalter ON  → required
    standard  + Schalter OFF → none (für opt-out-Gewerke wie Sprinkler)
    required               → unverändert (Pflicht aus Norm)
    """
    if stufe == "required":
        return stufe

    schalter: dict[str, str] = {
        "sprinkler":         "sprinkler",
        "druckluft":         "druckluft",
        "kaelte":            "kaelte",
        "wasser_trinkwasser": None,   # kein Toggle, immer nach Zone
        "abwasser":           None,
    }

    # Lüftung: stufe abhängig von Lüftungskonzept-Auswahl
    if gewerk_id == "lueftung_rlt":
        lue = mep_anf.get("lueftung", "mechanisch")
        if lue == "fenster":
            return "none" if stufe in ("optional", "standard") else stufe
        if lue == "klima":
            return "required"
        return stufe  # "mechanisch" → Stufe aus YAML behalten

    toggle_key = schalter.get(gewerk_id, "KEIN_TOGGLE")
    if toggle_key is None:
        return stufe  # Zone-Logik, kein User-Toggle

    if toggle_key == "KEIN_TOGGLE":
        return stufe  # kein bekannter Toggle → unverändert

    user_an = bool(mep_anf.get(toggle_key, False))
    if not user_an:
        return "none"   # Nutzer hat Gewerk deaktiviert
    return "required"   # Nutzer hat Gewerk aktiviert


def _dimensioniere(gewerk_id: str, auslegung_wert, flaeche_m2: float, mep_anf: dict):
    """Grobe Auslegungsberechnung je Gewerk (Faustregeln für Sprint 4A)."""
    if auslegung_wert is None or flaeche_m2 <= 0:
        return None
    try:
        val = float(auslegung_wert)
        if gewerk_id == "elektro_stark":
            return round(val * flaeche_m2 / 1000, 1)     # → kW
        if gewerk_id == "lueftung_rlt":
            raumhoehe = 5.0                               # Annahme Industriehalle
            return round(val * flaeche_m2 * raumhoehe / 3600, 2)  # → m³/s
        if gewerk_id == "daten_it":
            return max(1, math.ceil(val * flaeche_m2 / 100))       # → Ports
        if gewerk_id == "sprinkler":
            return max(1, math.ceil(flaeche_m2 / max(1.0, val)))   # → Sprinklerköpfe
        return round(val * flaeche_m2, 1)
    except (TypeError, ValueError):
        return None


def _aktive_gewerke_liste(mep_anf: dict) -> list[str]:
    """Gibt geordnete Liste aller aktiven Gewerke zurück."""
    aktiv = ["elektro_stark", "daten_it"]          # immer aktiv
    if mep_anf.get("lueftung", "mechanisch") != "fenster":
        aktiv.append("lueftung_rlt")
    if mep_anf.get("sprinkler"):
        aktiv.append("sprinkler")
    if mep_anf.get("druckluft"):
        aktiv.append("druckluft")
    if mep_anf.get("kaelte"):
        aktiv.append("kaelte")
    if mep_anf.get("usv_notstrom"):
        aktiv.append("usv_notstrom")
    aktiv.extend(["wasser_trinkwasser", "abwasser"])  # immer vorhanden
    return aktiv

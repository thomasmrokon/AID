"""
AID Demo – Sprint Q: Prozessplanung-Agent
=========================================
Dritte Planungsmaßstabsebene: Maschinenlayout innerhalb einer Produktionszone.

Modi:
- ai_suggestion: KI-/regelgestützter Vorschlag aus Prozessschritten und Anforderungen.
  Aktuell deterministisch über Strip-Packing, später LLM-Planungslogik möglich.
- adaptive_transfer: Überträgt ein vorhandenes Vorgabelayout proportional auf eine
  neue Funktionsfläche und prüft die geometrische Abweichung.

Algorithmus Vorschlagsmodus: Deterministisches Strip-Packing
- Maschinen werden nach Prozessschritt sortiert (→ U-förmiger Materialfluss)
- Strips: horizontale Reihen entlang der Zonenbreite
- Jeder Strip wird von links nach rechts mit Maschinen gleichen Schritts gefüllt
- Überlaufende Maschinen wandern in den nächsten Strip
- Gänge: 3m zwischen Strips (Flurförderzeug-Breite), 1.5m an Außenwänden

KPIs:
- Engpass:   Schritt mit längster Durchlaufzeit (Takt × Anzahl aller Aufträge)
- Durchsatz: min(Kapazität aller Schritte) → Teile/Schicht
- Auslastung: je Maschine = Taktzeit / Zykluszeit-Kapazität
- Materialflussweg: Summe aller Distanzen zwischen aufeinanderfolgenden Schritten [m]
"""
from __future__ import annotations

import math
from typing import Any

from app.state import PlanningState, DEMO_MASCHINENPARK


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

GANG_AUSSEN_M  = 1.5   # Mindestabstand zur Zonenwand [m]
GANG_ZWISCHEN_M = 3.0  # Gangbreite zwischen Maschinenstrips [m]
MASCHINEN_ABSTAND_M = 1.0  # Abstand zwischen Maschinen in einem Strip [m]
SCHICHT_STUNDEN = 8.0  # Schichtlänge [h]
TEILE_PRO_AUFTRAG = 100  # Referenz-Losgröße für KPI-Berechnung


# ---------------------------------------------------------------------------
# Haupt-Agentenfunktion
# ---------------------------------------------------------------------------

def process_layout_agent(state: PlanningState) -> dict[str, Any]:
    """LangGraph-Node: Maschinenlayout für eine Produktionszone.

    READS:  state["process_input"]  → {mode, zone_name, zone_breite_m, zone_tiefe_m,
                                        maschinenpark, reference_layout}
    WRITES: state["process_layout"] → {maschinen, strips, kpis, zone_breite_m, zone_tiefe_m}
    """
    process_input: dict = state.get("process_input") or {}

    zone_breite = float(process_input.get("zone_breite_m") or 40.0)
    zone_tiefe  = float(process_input.get("zone_tiefe_m")  or 75.0)
    zone_name   = process_input.get("zone_name", "Produktion")
    mode        = process_input.get("mode") or "ai_suggestion"
    park: list[dict] = process_input.get("maschinenpark") or DEMO_MASCHINENPARK

    if mode == "adaptive_transfer":
        reference_layout = process_input.get("reference_layout") or {}
        placed, strips, transfer_meta = _adaptive_transfer(reference_layout, park, zone_breite, zone_tiefe)
    else:
        placed, strips = _strip_pack(park, zone_breite, zone_tiefe)
        transfer_meta = None

    kpis = _compute_kpis(placed, park)

    process_layout = {
        "mode":         mode,
        "mode_label":   _mode_label(mode),
        "zone_name":    zone_name,
        "zone_breite_m": zone_breite,
        "zone_tiefe_m": zone_tiefe,
        "maschinen":    placed,   # list[PlacedMachine dict]
        "strips":       strips,   # list[Strip dict] für Visualisierung
        "kpis":         kpis,
        "maschinenpark": park,    # original park für Sankey
    }
    if transfer_meta:
        process_layout["transfer"] = transfer_meta

    return {"process_layout": process_layout}


def _mode_label(mode: str) -> str:
    if mode == "adaptive_transfer":
        return "Adaptiver Transfer eines Vorgabelayouts"
    return "KI-gestützter Layoutvorschlag"


# ---------------------------------------------------------------------------
# Strip-Packing-Algorithmus
# ---------------------------------------------------------------------------

def _strip_pack(
    park: list[dict],
    zone_breite: float,
    zone_tiefe: float,
) -> tuple[list[dict], list[dict]]:
    """Deterministisches Strip-Packing.

    Gibt (placed_machines, strips) zurück.
    placed_machines: [{"id", "name", "schritt", "x", "y", "breite_m", "tiefe_m",
                        "anzahl", "farbe", "kategorie", "instance_idx"}, ...]
    strips:          [{"strip_idx", "schritt", "y_start", "y_end", "hoehe_m"}, ...]
    """
    # 1. Alle Maschineninstanzen aufklappen (anzahl > 1 → mehrere Platzierungen)
    instances: list[dict] = []
    for m in sorted(park, key=lambda x: (x["schritt"], x["id"])):
        for i in range(int(m.get("anzahl", 1))):
            instances.append({
                **m,
                "instance_idx": i,
                "uid": f"{m['id']}_{i}",
            })

    # 2. Schritte ermitteln (sortiert)
    schritte = sorted({m["schritt"] for m in instances})

    # 3. Nutzbare Zonenbreite (ohne Außengänge)
    nutzbreite = zone_breite - 2 * GANG_AUSSEN_M

    # 4. Strip-Generierung: Ein Strip pro Schritt (Überlauf → neuer Strip)
    strips: list[dict] = []
    placed: list[dict] = []
    y_cursor = GANG_AUSSEN_M  # Aktueller Y-Offset von der Zonenunterkante

    for schritt in schritte:
        schritt_maschinen = [m for m in instances if m["schritt"] == schritt]

        # Sub-Strips: Wenn Schritt zu breit für eine Reihe → mehrere Strips
        current_strip_maschinen: list[dict] = []
        current_strip_breite = 0.0
        strip_hoehe = 0.0  # maximale Tiefe in aktuellem Strip

        def _finalize_strip(mlist: list[dict], strip_h: float) -> None:
            nonlocal y_cursor
            if not mlist:
                return
            strip_idx = len(strips)
            strip_y_start = y_cursor
            strip_y_end   = y_cursor + strip_h

            strips.append({
                "strip_idx": strip_idx,
                "schritt":   schritt,
                "y_start":   round(strip_y_start, 3),
                "y_end":     round(strip_y_end, 3),
                "hoehe_m":   round(strip_h, 3),
            })

            # Maschinen innerhalb des Strips von links nach rechts platzieren
            x_cursor = GANG_AUSSEN_M
            for m in mlist:
                placed.append({
                    "id":           m["id"],
                    "uid":          m["uid"],
                    "name":         m["name"],
                    "schritt":      m["schritt"],
                    "instance_idx": m["instance_idx"],
                    "x":            round(x_cursor, 3),
                    "y":            round(strip_y_start, 3),
                    "breite_m":     m["breite_m"],
                    "tiefe_m":      m["tiefe_m"],
                    "taktzeit_s":   m.get("taktzeit_s", 60),
                    "anzahl":       m.get("anzahl", 1),
                    "farbe":        m.get("farbe", "#888888"),
                    "kategorie":    m.get("kategorie", "Bearbeitung"),
                })
                x_cursor += m["breite_m"] + MASCHINEN_ABSTAND_M

            y_cursor = strip_y_end + GANG_ZWISCHEN_M

        for m in schritt_maschinen:
            needed = m["breite_m"] + (MASCHINEN_ABSTAND_M if current_strip_maschinen else 0)
            if current_strip_breite + needed > nutzbreite and current_strip_maschinen:
                # Diesen Strip finalisieren, neuen beginnen
                _finalize_strip(current_strip_maschinen, strip_hoehe)
                current_strip_maschinen = []
                current_strip_breite = 0.0
                strip_hoehe = 0.0

            current_strip_maschinen.append(m)
            current_strip_breite += m["breite_m"] + (MASCHINEN_ABSTAND_M if len(current_strip_maschinen) > 1 else 0)
            strip_hoehe = max(strip_hoehe, m["tiefe_m"])

        if current_strip_maschinen:
            _finalize_strip(current_strip_maschinen, strip_hoehe)

    # 5. Prüfe ob Layout in Zonengrenze passt; wenn nicht → skaliere Tiefe
    gesamt_tiefe = y_cursor - GANG_ZWISCHEN_M + GANG_AUSSEN_M
    if gesamt_tiefe > zone_tiefe:
        # Skalierungsfaktor anwenden (alle Y-Koordinaten und Höhen skalieren)
        scale = zone_tiefe / gesamt_tiefe
        for m in placed:
            m["y"]       = round(m["y"] * scale, 3)
            m["tiefe_m"] = round(m["tiefe_m"] * scale, 3)
        for s in strips:
            s["y_start"] = round(s["y_start"] * scale, 3)
            s["y_end"]   = round(s["y_end"] * scale, 3)
            s["hoehe_m"] = round(s["hoehe_m"] * scale, 3)

    return placed, strips


def _adaptive_transfer(
    reference_layout: dict[str, Any],
    park: list[dict],
    zone_breite: float,
    zone_tiefe: float,
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Skaliert und überträgt ein bestehendes Maschinenlayout auf eine neue Fläche.

    reference_layout erwartet:
      {"zone_breite_m", "zone_tiefe_m", "maschinen": [{"id", "x", "y", ...}]}
    Fehlende Maschinen werden über Strip-Packing ergänzt.
    """
    ref_breite = float(reference_layout.get("zone_breite_m") or zone_breite)
    ref_tiefe = float(reference_layout.get("zone_tiefe_m") or zone_tiefe)
    ref_machines = reference_layout.get("maschinen") or []

    if not ref_machines:
        placed, strips = _strip_pack(park, zone_breite, zone_tiefe)
        return placed, strips, {
            "status": "fallback_suggestion",
            "hinweis": "Kein Vorgabelayout vorhanden; Vorschlagsmodus verwendet.",
        }

    scale_x = zone_breite / max(ref_breite, 0.001)
    scale_y = zone_tiefe / max(ref_tiefe, 0.001)
    machine_defaults = {m["id"]: m for m in park if "id" in m}
    placed: list[dict] = []
    violations: list[dict[str, Any]] = []

    for idx, ref in enumerate(ref_machines):
        machine_id = str(ref.get("id") or ref.get("uid") or f"REF{idx + 1:02d}")
        defaults = machine_defaults.get(machine_id, {})
        breite = float(ref.get("breite_m") or defaults.get("breite_m") or 3.0) * scale_x
        tiefe = float(ref.get("tiefe_m") or defaults.get("tiefe_m") or 2.0) * scale_y
        x = float(ref.get("x") or 0.0) * scale_x
        y = float(ref.get("y") or 0.0) * scale_y

        clipped_x = min(max(x, GANG_AUSSEN_M), max(GANG_AUSSEN_M, zone_breite - breite - GANG_AUSSEN_M))
        clipped_y = min(max(y, GANG_AUSSEN_M), max(GANG_AUSSEN_M, zone_tiefe - tiefe - GANG_AUSSEN_M))
        if abs(clipped_x - x) > 0.001 or abs(clipped_y - y) > 0.001:
            violations.append({
                "id": machine_id,
                "typ": "boundary_clip",
                "dx_m": round(clipped_x - x, 3),
                "dy_m": round(clipped_y - y, 3),
            })

        placed.append({
            "id": machine_id,
            "uid": str(ref.get("uid") or f"{machine_id}_0"),
            "name": str(ref.get("name") or defaults.get("name") or machine_id),
            "schritt": int(ref.get("schritt") or defaults.get("schritt") or idx + 1),
            "instance_idx": int(ref.get("instance_idx") or 0),
            "x": round(clipped_x, 3),
            "y": round(clipped_y, 3),
            "breite_m": round(breite, 3),
            "tiefe_m": round(tiefe, 3),
            "taktzeit_s": float(ref.get("taktzeit_s") or defaults.get("taktzeit_s") or 60),
            "anzahl": int(ref.get("anzahl") or defaults.get("anzahl") or 1),
            "farbe": ref.get("farbe") or defaults.get("farbe") or "#888888",
            "kategorie": ref.get("kategorie") or defaults.get("kategorie") or "Bearbeitung",
        })

    strips = _strips_from_placed(placed)
    meta = {
        "status": "transferred",
        "source_zone_breite_m": ref_breite,
        "source_zone_tiefe_m": ref_tiefe,
        "scale_x": round(scale_x, 3),
        "scale_y": round(scale_y, 3),
        "aspect_ratio_change_pct": round(abs(scale_x - scale_y) / max(scale_x, scale_y, 0.001) * 100, 1),
        "violations": violations,
    }
    return placed, strips, meta


def _strips_from_placed(placed: list[dict]) -> list[dict]:
    """Leitet Visualisierungs-Strips aus platzierten Maschinen ab."""
    strips: list[dict] = []
    for idx, schritt in enumerate(sorted({m["schritt"] for m in placed})):
        ms = [m for m in placed if m["schritt"] == schritt]
        y_start = min(m["y"] for m in ms)
        y_end = max(m["y"] + m["tiefe_m"] for m in ms)
        strips.append({
            "strip_idx": idx,
            "schritt": schritt,
            "y_start": round(y_start, 3),
            "y_end": round(y_end, 3),
            "hoehe_m": round(y_end - y_start, 3),
        })
    return strips


# ---------------------------------------------------------------------------
# KPI-Berechnung
# ---------------------------------------------------------------------------

def _compute_kpis(placed: list[dict], park: list[dict]) -> dict[str, Any]:
    """Berechnet Engpass, Durchsatz, Auslastung und Materialflussweg.

    Alle Werte deterministisch (keine Zufallskomponente).
    """
    if not placed or not park:
        return {}

    # --- Kapazität je Schritt (Teile/Schicht) ---
    # Kapazität = Σ(Schicht_Sekunden / Taktzeit) für alle Instanzen eines Schritts
    schicht_s = SCHICHT_STUNDEN * 3600
    kapazitaet_je_schritt: dict[int, float] = {}
    for m in park:
        schritt = m["schritt"]
        takt    = float(m.get("taktzeit_s") or 60)
        anzahl  = int(m.get("anzahl") or 1)
        kap     = (schicht_s / takt) * anzahl
        kapazitaet_je_schritt[schritt] = kapazitaet_je_schritt.get(schritt, 0.0) + kap

    # --- Engpass: Schritt mit minimaler Kapazität ---
    engpass_schritt = min(kapazitaet_je_schritt, key=lambda s: kapazitaet_je_schritt[s])
    engpass_kap     = kapazitaet_je_schritt[engpass_schritt]

    # --- Gesamtdurchsatz = Engpass-Kapazität ---
    durchsatz_teile_pro_schicht = math.floor(engpass_kap)

    # --- Auslastung je Schritt (%) ---
    auslastung_je_schritt: dict[int, float] = {
        s: min(100.0, round(engpass_kap / kap * 100, 1))
        for s, kap in kapazitaet_je_schritt.items()
    }

    # --- Materialflussweg (Schwerpunkt-Distanz Schritt i → i+1) ---
    schritte_sorted = sorted(kapazitaet_je_schritt.keys())
    schwerpunkte: dict[int, tuple[float, float]] = {}
    for schritt in schritte_sorted:
        ms = [m for m in placed if m["schritt"] == schritt]
        if ms:
            cx = sum(m["x"] + m["breite_m"] / 2 for m in ms) / len(ms)
            cy = sum(m["y"] + m["tiefe_m"] / 2 for m in ms) / len(ms)
            schwerpunkte[schritt] = (cx, cy)

    materialflussweg_m = 0.0
    for i in range(len(schritte_sorted) - 1):
        s1, s2 = schritte_sorted[i], schritte_sorted[i + 1]
        if s1 in schwerpunkte and s2 in schwerpunkte:
            dx = schwerpunkte[s2][0] - schwerpunkte[s1][0]
            dy = schwerpunkte[s2][1] - schwerpunkte[s1][1]
            materialflussweg_m += math.sqrt(dx ** 2 + dy ** 2)

    # --- Sankey-Daten vorbereiten ---
    sankey_nodes = []
    sankey_links = []
    schritt_namen: dict[int, str] = {}
    for m in park:
        s = m["schritt"]
        if s not in schritt_namen:
            schritt_namen[s] = f"Schritt {s}"

    # Materialmenge als Dummy-Wert: normiert auf Engpass-Durchsatz
    node_idx: dict[int, int] = {}
    for i, s in enumerate(schritte_sorted):
        sankey_nodes.append({"label": schritt_namen[s], "schritt": s})
        node_idx[s] = i

    for i in range(len(schritte_sorted) - 1):
        s1, s2 = schritte_sorted[i], schritte_sorted[i + 1]
        wert = round(min(kapazitaet_je_schritt[s1], kapazitaet_je_schritt[s2]))
        sankey_links.append({"source": node_idx[s1], "target": node_idx[s2], "value": wert})

    return {
        "engpass_schritt":              engpass_schritt,
        "engpass_kapazitaet_t_schicht": round(engpass_kap, 1),
        "durchsatz_teile_pro_schicht":  durchsatz_teile_pro_schicht,
        "kapazitaet_je_schritt":        {str(k): round(v, 1) for k, v in kapazitaet_je_schritt.items()},
        "auslastung_je_schritt":        {str(k): v for k, v in auslastung_je_schritt.items()},
        "materialflussweg_m":           round(materialflussweg_m, 1),
        "sankey_nodes":                 sankey_nodes,
        "sankey_links":                 sankey_links,
        "schwerpunkte":                 {str(k): list(v) for k, v in schwerpunkte.items()},
    }

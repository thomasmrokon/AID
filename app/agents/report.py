"""
AID Demo – Report-Agent
Erzeugt die Entscheidungsvorlage als Markdown und rendert die Layout-PNGs.
LLM wird nur für die Formulierung der Empfehlung verwendet.
"""

from __future__ import annotations
import json
from datetime import date
from pathlib import Path

from app.state import PlanningState
from app.llm import invoke_messages, is_llm_configured
from app.tools.geometry import Zone
from app.tools.drawing import zeichne_layout
from app.tools.rhino_geometry import exportiere_rhino_3dm, ist_verfuegbar as rhino3dm_verfuegbar
from app.tools.rhino_compute import (
    is_running as compute_is_running,
    start_server as compute_start_server,
    run_grasshopper_layout,
)
from app.tools.rhino_inside_runner import (
    ist_verfuegbar as rhinoinside_verfuegbar,
    export_3dm as rhinoinside_export_3dm,
    run_zone_geometry,
)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"


def report_agent(state: PlanningState) -> dict:
    """LangGraph-Node: PNGs rendern + Markdown-Report erzeugen."""

    variants    = state["variants"]
    evaluations = state["evaluations"]
    briefing    = state["structured_briefing"]
    selected    = state["selected_variant"]
    nutzungstyp = briefing["nutzungstyp"]
    site_geometry = state.get("site_geometry")

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Evaluations als Dict für schnellen Zugriff
    eval_map = {e["variante"]: e for e in evaluations}

    # --- Rhino-Backends prüfen ---
    rhinoinside_aktiv = rhinoinside_verfuegbar()
    if rhinoinside_aktiv:
        print("[report] rhinoinside (Rhino 8) bereit — nativer 3DM-Export aktiv")
    else:
        print("[report] rhinoinside nicht verfuegbar — Fallback auf rhino3dm")

    compute_aktiv = compute_is_running()
    if not compute_aktiv:
        compute_aktiv = compute_start_server(wait_seconds=6)
    if compute_aktiv:
        print("[report] Rhino.Compute bereit")

    # --- PNGs + 3DM + Zonen-JSON pro Variante ---
    artifacts = {}
    rhino_aktiv = rhino3dm_verfuegbar()

    tragwerk_config       = state.get("tragwerk_config") or {}
    mep_trassennetz       = state.get("mep_trassennetz") or {}
    typology_assignments  = state.get("typology_assignments") or {}

    for v in variants:
        ev   = eval_map[v["name"]]
        ev["empfohlen"] = (v["name"] == selected)
        zonen = [Zone(**z) for z in v["zonen"]]

        # --- 2D-Plan (matplotlib) ---
        png_name = f"variant_{v['name']}.png"
        png_path = OUTPUT_DIR / png_name

        zeichne_layout(
            variante_name    = v["name"],
            beschreibung     = v["beschreibung"],
            zonen            = zonen,
            site_breite      = v["site_breite"],
            site_tiefe       = v["site_tiefe"],
            raster_x         = v["raster_x"],
            raster_y         = v["raster_y"],
            scores           = ev,
            gewichtung       = v["gewichtung"],
            output_path      = png_path,
            nutzungstyp      = nutzungstyp,
            site_geometry    = v.get("site_geometry"),
            tragwerk_config  = tragwerk_config or None,
            mep_variant_data = mep_trassennetz.get(v["name"]),
            building_envelope = v.get("building_envelope"),
            show_legend      = False,   # Legende → Streamlit-Popover
            show_violations  = False,   # Warnungen → Streamlit-Popover
            typology_key     = typology_assignments.get(v["name"]),
        )
        artifacts[png_name] = str(png_path)
        print(f"[report] PNG gespeichert: {png_path}")

        # --- Zonen-JSON für Grasshopper ---
        json_name = f"zones_{v['name']}.json"
        json_path = OUTPUT_DIR / json_name
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(v["zonen"], f, ensure_ascii=False, indent=2)
        artifacts[json_name] = str(json_path)

        # --- Grasshopper via Rhino.Compute ---
        if compute_aktiv:
            gh_result = run_grasshopper_layout(v["zonen"])
            if gh_result and gh_result.get("values"):
                print(f"[report] GH-Geometrie: {len(gh_result['values'])} Output-Parameter ({v['name']})")
                gh_json_name = f"gh_result_{v['name']}.json"
                gh_json_path = OUTPUT_DIR / gh_json_name
                with open(gh_json_path, "w", encoding="utf-8") as f:
                    json.dump(gh_result, f, ensure_ascii=False, indent=2)
                artifacts[gh_json_name] = str(gh_json_path)
            elif gh_result is not None:
                errs = gh_result.get("errors") or []
                print(f"[report] GH-Auswertung fehlgeschlagen ({v['name']}): {errs[:1]}")

        # --- Rhino 3DM: rhinoinside (nativ, bevorzugt) oder rhino3dm ---
        dm_name = f"variant_{v['name']}.3dm"
        dm_path = OUTPUT_DIR / dm_name
        if rhinoinside_aktiv:
            try:
                ok = rhinoinside_export_3dm(
                    variante_name = v["name"],
                    zonen         = v["zonen"],
                    site_breite   = v["site_breite"],
                    site_tiefe    = v["site_tiefe"],
                    output_path   = dm_path,
                )
                if ok:
                    artifacts[dm_name] = str(dm_path)
                    print(f"[report] 3DM (rhinoinside) gespeichert: {dm_path}")
            except Exception as e:
                print(f"[report] rhinoinside 3DM-Fehler ({v['name']}): {e}")
        elif rhino_aktiv:
            try:
                ok = exportiere_rhino_3dm(
                    variante_name = v["name"],
                    zonen         = zonen,
                    site_breite   = v["site_breite"],
                    site_tiefe    = v["site_tiefe"],
                    raster_x      = v["raster_x"],
                    raster_y      = v["raster_y"],
                    output_path   = dm_path,
                )
                if ok:
                    artifacts[dm_name] = str(dm_path)
            except Exception as e:
                print(f"[report] 3DM-Export Fehler ({v['name']}): {e}")

    # --- Evaluation JSON speichern ---
    eval_path = OUTPUT_DIR / "evaluation.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(evaluations, f, ensure_ascii=False, indent=2)
    artifacts["evaluation.json"] = str(eval_path)

    # --- Markdown-Report formulieren ---
    llm_analyse = state.get("llm_analyse")
    report_md = _formuliere_report(briefing, variants, evaluations, selected, nutzungstyp,
                                   site_geometry, llm_analyse)
    report_md = _append_mep_section(report_md, mep_trassennetz)
    report_md = _append_layout_decisions_section(report_md, state)
    report_md = _append_whitebox_section(report_md, state)

    report_path = OUTPUT_DIR / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    artifacts["report.md"] = str(report_path)

    print(f"[report] Report gespeichert: {report_path}")

    return {
        "report_markdown": report_md,
        "artifacts":       artifacts,
        "site_geometry":   site_geometry,
        "layout_strategy": state.get("layout_strategy"),
    }


# ---------------------------------------------------------------------------
# Markdown-Formulierung (LLM oder deterministisch)
# ---------------------------------------------------------------------------

def _formuliere_report(
    briefing: dict,
    variants: list[dict],
    evaluations: list[dict],
    selected: str,
    nutzungstyp: str,
    site_geometry: dict | None = None,
    llm_analyse: str | None = None,
) -> str:
    """Erstellt den Markdown-Report. LLM wird genutzt wenn API-Key vorhanden."""

    eval_map = {e["variante"]: e for e in evaluations}
    sel_ev   = eval_map[selected]
    sel_var  = next(v for v in variants if v["name"] == selected)

    if is_llm_configured():
        md = _llm_report(briefing, variants, evaluations, selected, nutzungstyp,
                         sel_ev, sel_var, site_geometry)
    else:
        md = _deterministischer_report(briefing, variants, evaluations, selected,
                                       nutzungstyp, sel_ev, sel_var, site_geometry)

    if llm_analyse:
        md = md.rstrip() + "\n\n---\n\n## Qualitative Analyse\n\n" + llm_analyse + "\n"

    return md


def _deterministischer_report(
    briefing, variants, evaluations, selected, nutzungstyp, sel_ev, sel_var, site_geometry=None
) -> str:
    today = date.today().strftime("%d.%m.%Y")
    rows = "\n".join(
        f"| {e['variante']:20s} | {e['materialfluss_score']:4.1f} | "
        f"{e['erweiterbarkeit_score']:4.1f} | {e['tragwerk_score']:4.1f} | "
        f"**{e['gesamtscore']:.1f}** | "
        f"{'* Empfohlen' if e.get('empfohlen') else ''} |"
        for e in evaluations
    )
    vst = "\n".join(f"- {v}" for v in sel_ev["regelverletzungen"]) or "— keine —"

    return f"""# AID Demo – Planungsempfehlung
*Erstellt: {today} · Nutzungstyp: {nutzungstyp}*

---

## Eingabe-Zusammenfassung

| Parameter | Wert |
|---|---|
| Nutzungstyp | {briefing['nutzungstyp']} |
| NUF gesamt | {briefing['nuf_gesamt']} m² |
| BGF gesamt | {briefing['bgf_gesamt']} m² |
| Büro/Verwaltung | {briefing['buero_nuf2']} m² |

---

## Variantenvergleich

| Variante | Materialfluss | Erweiterbarkeit | Tragwerk | Gesamt | |
|---|---|---|---|---|---|
{rows}

---

## Empfehlung: Variante {selected}

**{sel_var['beschreibung']}**

Gesamtscore: **{sel_ev['gesamtscore']:.1f} / 10**

### Regelkonformität
{vst}

### Nächste Schritte
1. Detailabstimmung Stützenraster {sel_var['raster_x']} × {sel_var['raster_y']} m mit Tragwerksplanung
2. Überprüfung Außenanlagen und Andockstellen
3. Brandschutzkonzept auf Basis der Zoneneinteilung entwickeln

---
*Generiert durch AID Demo v0.1 · Hochschule Mainz / Drees & Sommer*
"""


def _llm_report(
    briefing, variants, evaluations, selected, nutzungstyp, sel_ev, sel_var, site_geometry=None
) -> str:
    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        kontext = json.dumps({
            "nutzungstyp":   nutzungstyp,
            "bgf_m2":        briefing["bgf_gesamt"],
            "grundstueck":   site_geometry,
            "varianten":     [
                {
                    "name":        e["variante"],
                    "scores":      {
                        "materialfluss":   e["materialfluss_score"],
                        "erweiterbarkeit": e["erweiterbarkeit_score"],
                        "tragwerk":        e["tragwerk_score"],
                        "gesamt":          e["gesamtscore"],
                    },
                    "regelverletzungen": e["regelverletzungen"],
                    "gewichtung": next(
                        v["gewichtung"] for v in variants if v["name"] == e["variante"]
                    ),
                }
                for e in evaluations
            ],
            "empfehlung": selected,
        }, ensure_ascii=False, indent=2, default=str)

        response = invoke_messages([
            SystemMessage(content=(
                "Du bist Experte für Industriebau-Planung und erstellst professionelle "
                "Entscheidungsvorlagen. Formuliere auf Basis der JSON-Daten einen "
                "strukturierten Markdown-Report (max. 500 Wörter) mit: "
                "Kurzfassung, Variantenvergleich-Tabelle, Begründung der Empfehlung, "
                "Hinweise zu Regelverletzungen, nächste Schritte. "
                "Sprache: Deutsch. Ton: professionell, sachlich."
            )),
            HumanMessage(content=kontext),
        ], temperature=0.3)
        return response

    except Exception as e:
        print(f"[report] LLM-Formulierung fehlgeschlagen: {e} – Fallback auf deterministischen Report")
        return _deterministischer_report(
            briefing, variants, evaluations, selected, nutzungstyp, sel_ev, sel_var, site_geometry
        )


def _append_mep_section(report_md: str, mep_trassennetz: dict) -> str:
    if not mep_trassennetz:
        return report_md

    lines = [
        "",
        "## MEP-Konzept",
        "",
        "| Variante | Aktive Gewerke | Starkstrom | Lüftung | Druckluft | Sprinkler |",
        "|----------|---------------|-----------|---------|-----------|-----------|"
    ]

    for var_name, mep_data in mep_trassennetz.items():
        aktive_count = len(mep_data.get("aktive_gewerke", []))
        zonen = mep_data.get("zonen", [])
        
        sum_elektro = 0.0
        sum_lueftung = 0.0
        sum_druckluft = 0.0
        sum_sprinkler = 0.0
        
        einheit_elektro = "kW"
        einheit_lueftung = "m³/s"
        einheit_druckluft = "bar·m³/h"
        einheit_sprinkler = "Köpfe"

        for z in zonen:
            gw = z.get("gewerke", {})
            if "elektro_stark" in gw:
                val = gw["elektro_stark"].get("auslegung_ergebnis", 0)
                if val: sum_elektro += float(val)
                einheit_elektro = gw["elektro_stark"].get("einheit", einheit_elektro)
            if "lueftung_rlt" in gw:
                val = gw["lueftung_rlt"].get("auslegung_ergebnis", 0)
                if val: sum_lueftung += float(val)
                einheit_lueftung = gw["lueftung_rlt"].get("einheit", einheit_lueftung)
            if "druckluft" in gw:
                val = gw["druckluft"].get("auslegung_ergebnis", 0)
                if val: sum_druckluft += float(val)
                einheit_druckluft = gw["druckluft"].get("einheit", einheit_druckluft)
            if "sprinkler" in gw:
                val = gw["sprinkler"].get("auslegung_ergebnis", 0)
                if val: sum_sprinkler += float(val)
                einheit_sprinkler = gw["sprinkler"].get("einheit", einheit_sprinkler)

        def _fmt(val, unit, is_int=False):
            if val <= 0: return "–"
            if is_int: return f"{int(val)} {unit}"
            s = str(round(val, 1)).replace(".", ",")
            if s.endswith(",0"): s = s[:-2]
            return f"{s} {unit}"

        str_elektro = _fmt(sum_elektro, einheit_elektro)
        str_lueftung = _fmt(sum_lueftung, einheit_lueftung)
        str_druckluft = _fmt(sum_druckluft, einheit_druckluft)
        str_sprinkler = _fmt(sum_sprinkler, einheit_sprinkler, is_int=True)

        lines.append(f"| {var_name} | {aktive_count} | {str_elektro} | {str_lueftung} | {str_druckluft} | {str_sprinkler} |")

    lines.append("")
    for var_name, mep_data in mep_trassennetz.items():
        trassen_laenge_gesamt_m = mep_data.get("trassen_laenge_gesamt_m", 0)
        backbone_geometrie = mep_data.get("backbone_geometrie", [])
        korridor_kanten_mit_pfad = mep_data.get("korridor_kanten_mit_pfad", [])
        aktive_gewerke = mep_data.get("aktive_gewerke", [])
        
        lines.append(f"## MEP- und Medienerschließung — {var_name}")
        lines.append("")
        lines.append("| Kennwert | Wert |")
        lines.append("|----------|------|")
        lines.append(f"| Gesamttrassenlänge | {trassen_laenge_gesamt_m:.0f} m |")
        lines.append(f"| Backbone-Segmente | {len(backbone_geometrie)} Stk. |")
        lines.append(f"| Korridor-Verbindungen mit Pfad | {len(korridor_kanten_mit_pfad)} |")
        lines.append(f"| Aktive Gewerke | {', '.join(aktive_gewerke)} |")
        lines.append("")

    section_str = "\n".join(lines) + "\n"
    if "## Empfehlung" in report_md:
        return report_md.replace("## Empfehlung", section_str + "\n## Empfehlung")
    return report_md.rstrip() + "\n" + section_str


def _append_whitebox_section(report_md: str, state: PlanningState) -> str:
    """Hängt das vollständige Entscheidungsprotokoll an den Report an."""

    planning_decisions: list[dict] = state.get("planning_decisions") or []
    compliance:         list[dict] = state.get("compliance_issues") or []
    reasoning_log = state.get("reasoning_log") or []

    if not planning_decisions and not compliance and not reasoning_log:
        return report_md

    lines = [
        "",
        "---",
        "",
        "## Entscheidungsprotokoll",
        "",
        "> Automatisch generiertes Protokoll aller deterministischen Planungsentscheidungen.",
        "",
    ]

    # ── 1. Regelanwendung (variante-übergreifend) ────────────────────────────
    regel_entries = [d for d in planning_decisions if d.get("kategorie") == "Regelanwendung"]
    if regel_entries:
        lines += [
            "### Angewendetes Regelset",
            "",
            "| Regel | Wert | Regelreferenz |",
            "|-------|------|---------------|",
        ]
        for d in regel_entries:
            lines.append(
                f"| {d['aktion'].split(':')[0]} "
                f"| **{d['aktion'].split(':', 1)[1].strip()}** "
                f"| `{d.get('regel_ref', '—')}` |"
            )
        lines.append("")

    # ── 2. Zonenplatzierung pro Variante ─────────────────────────────────────
    for variante_key in ["A_Materialfluss", "B_Erweiterbarkeit", "C_Ausgewogen"]:
        variante_label = variante_key.replace("_", " ")
        zone_entries = [
            d for d in planning_decisions
            if d.get("variante") == variante_key
            and d.get("kategorie") in ("Zonenplatzierung", "Erweiterungsreserve")
        ]
        if not zone_entries:
            continue

        lines += [
            f"### Variante {variante_label} — Zonenplatzierung",
            "",
            "| Zone | Kategorie | Position | Ist m² | Soll m² | Δ% | Angrenzend / Bemerkung |",
            "|------|-----------|----------|--------|---------|-----|------------------------|",
        ]
        for d in zone_entries:
            wert = d.get("wert") or {}
            if d.get("kategorie") == "Erweiterungsreserve":
                lines.append(
                    f"| *{d.get('zone', '—')}* | Reserve | {d.get('aktion', '—')} "
                    f"| {wert.get('area_m2', '—')} | — | — | Erweiterungsreserve |"
                )
            else:
                ist = wert.get('area_ist_m2', 0)
                soll = wert.get('area_soll_m2', 0)
                delta = wert.get('delta_pct', 0.0)
                begr = d.get('begruendung', '')
                adj = begr.split('Angrenzend:')[-1].strip() if 'Angrenzend:' in begr else '—'
                din = begr.split('.')[0] if begr else '—'
                lines.append(
                    f"| **{d.get('zone', '—')}** | {din} "
                    f"| {d.get('aktion', '—')} "
                    f"| {ist:,.0f} "
                    f"| {soll:,.0f} "
                    f"| {delta:+.0f}% "
                    f"| {adj} |"
                )
        lines.append("")

    # ── 3. Bewertungs-Begründungen ────────────────────────────────────────────
    bewertung_entries = [d for d in planning_decisions if d.get("kategorie") == "Bewertung"]
    if bewertung_entries:
        lines += [
            "### Bewertungsergebnis",
            "",
            "| Variante | Kriterium | Score | Gewichtung | Beitrag |",
            "|----------|-----------|-------|-----------|---------|",
        ]
        for d in bewertung_entries:
            wert = d.get("wert") or {}
            lines.append(
                f"| {d.get('variante', '—').replace('_', ' ')} "
                f"| {d.get('aktion', '—').split(':')[0]} "
                f"| {wert.get('score', 0):.1f}/10 "
                f"| {wert.get('gewichtung', 0):.0%} "
                f"| {wert.get('beitrag', 0):.2f} |"
            )
        lines.append("")

    # ── 4. Compliance-Hinweise ────────────────────────────────────────────────
    if compliance:
        lines += [
            "### Compliance-Hinweise",
            "",
            "| Schwere | Variante | Zone | Hinweis | Regelreferenz |",
            "|---------|----------|------|---------|---------------|",
        ]
        _severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        for issue in compliance:
            icon = _severity_icon.get(issue.get("severity", "low"), "⚪")
            lines.append(
                f"| {icon} {issue.get('severity', '—')} "
                f"| {issue.get('variant', '—').replace('_', ' ')} "
                f"| {issue.get('zone') or '—'} "
                f"| {issue.get('message', '—')} "
                f"| `{issue.get('rule_ref', '—')}` |"
            )
        lines.append("")

    # ── 5. Fallback: altes Reasoning-Log (Zusammenfassung) ───────────────────
    if reasoning_log and not planning_decisions:
        from collections import Counter
        lines += ["### Pipeline-Protokoll (Zusammenfassung)", ""]
        agent_counts = Counter(e.get("agent", "?") for e in reasoning_log)
        for agent in sorted(agent_counts):
            lines.append(f"- **{agent}**: {agent_counts[agent]} Einträge")
        lines.append("")

    return report_md + "\n".join(lines)


def _append_layout_decisions_section(report_md: str, state: PlanningState) -> str:
    lines = []
    try:
        from app.agents.layout import _last_optimization_result
    except ImportError:
        _last_optimization_result = {}

    for var in state.get("variants", []):
        var_name = var.get("name")
        opt_res = var.get("optimization_result")
        if not opt_res:
            opt_res = _last_optimization_result.get(var_name)
        
        if not opt_res:
            continue

        if hasattr(opt_res, "tree_topology"):
            topology = opt_res.tree_topology
            envelope = opt_res.envelope_used
            iterations = opt_res.iterations
            decisions = opt_res.zone_decisions
        elif isinstance(opt_res, dict):
            topology = opt_res.get("tree_topology", "")
            envelope = opt_res.get("envelope_used", {})
            iterations = opt_res.get("iterations", 0)
            decisions = opt_res.get("zone_decisions", [])
        else:
            continue
            
        width = envelope.get("width_m", 0)
        depth = envelope.get("depth_m", 0)
        rot = envelope.get("rotation_deg", 0)

        lines.append("")
        lines.append(f"## Layoutentscheidungen — Variante {var_name}")
        lines.append("")
        lines.append("**Algorithmus**: Slicing-Floorplan-Optimizer (scipy L-BFGS-B)  ")
        lines.append(f"**Baumstruktur**: `{topology}`  ")
        lines.append(f"**Envelope**: {width:.0f} m × {depth:.0f} m, Rotation {rot:.0f}°  ")
        lines.append(f"**Konvergenz**: {iterations} Iterationen ✓")
        lines.append("")
        lines.append("| Zone | Fläche Δ | Nachbarn | Begründung |")
        lines.append("|------|----------|----------|------------|")

        for d in decisions:
            if hasattr(d, "zone_name"):
                name = d.zone_name
                delta = d.area_delta_pct
                adj = d.adjacency_score
                reason = d.human_reason
            else:
                name = d.get("zone_name", "")
                delta = d.get("area_delta_pct", 0)
                adj = d.get("adjacency_score", 0)
                reason = d.get("human_reason", "")

            lines.append(f"| {name} | {delta:+.1f}% | {adj:.0%} | {reason} |")
    
    if lines:
        if "## Empfehlung" in report_md:
            return report_md.replace("## Empfehlung", "\n".join(lines) + "\n\n## Empfehlung")
        return report_md + "\n" + "\n".join(lines) + "\n"
    return report_md


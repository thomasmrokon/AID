# Sprint 8C – Claude Code: Transparentes Entscheidungsprotokoll

## Kontext

Du arbeitest an einem Python-Projekt (LangGraph + Streamlit) zur Industriebau-Planung.
Deine Aufgabe: deterministisches **Entscheidungsprotokoll** — jede Planungsentscheidung wird
strukturiert geloggt und im Report als lesbarer Abschnitt gerendert.

**Betroffene Dateien:**
1. `app/state.py` — neuen Key `planning_decisions` ergänzen
2. `app/agents/layout.py` — Zonenplatzierungs-Entscheidungen loggen
3. `app/agents/rules.py` — Regelanwendungs-Entscheidungen loggen
4. `app/agents/evaluation.py` — Bewertungs-Begründungen ergänzen
5. `app/agents/report.py` — `_append_whitebox_section` → vollständiges Entscheidungsprotokoll

---

## Datenstruktur: `planning_decisions`

Jeder Eintrag ist ein Dict mit folgenden Keys:

```python
{
    "agent":      str,        # "layout" | "rules" | "evaluation"
    "variante":   str,        # "A_Materialfluss" | "B_Erweiterbarkeit" | "C_Ausgewogen" | "alle"
    "kategorie":  str,        # "Zonenplatzierung" | "Erweiterungsreserve" | "Regelanwendung"
                              # | "Compliance" | "Bewertung" | "Empfehlung"
    "zone":       str | None, # Zonenname wenn zonenspezifisch, sonst None
    "aktion":     str,        # Kurze Aussage: was wurde entschieden
    "begruendung":str,        # Längere Erklärung: warum
    "wert":       dict | None,# Messgröße: {"area_m2": 2400, "delta_pct": 0.0, ...}
    "regel_ref":  str | None, # Regelreferenz: "topology.adjacency" | "rules.grz" | ...
}
```

---

## Aufgabe 1: `app/state.py`

Den Key `planning_decisions` am Ende der PlanningState TypedDict ergänzen
(nach `adjacency_weights`, als letzter Eintrag):

```python
    # --- Entscheidungsprotokoll (alle Agenten schreiben, Report liest) ---
    planning_decisions:  list[dict[str, Any]]  # strukturiertes Entscheidungsprotokoll
```

---

## Aufgabe 2: `app/agents/layout.py`

### Wo einfügen

In der Schleife `for variante_key, gewichtung in aktive_gewichtungen.items():`,
**nach** dem Aufruf `zonen, envelope = _layout_from_topology(...)` (ca. Zeile 201)
und **vor** dem `variants.append(...)` Block.

### Was hinzufügen

```python
        # ── Entscheidungsprotokoll: Zonenplatzierung ──────────────────────────
        planning_decisions = list(state.get("planning_decisions") or [])

        def _are_adjacent(a: Zone, b: Zone, eps: float = 0.5) -> bool:
            # Prüft ob zwei Zonen eine gemeinsame Kante haben
            x_overlap = a.x < b.x + b.breite + eps and b.x < a.x + a.breite + eps
            y_touch   = (abs(a.y - (b.y + b.tiefe)) < eps or
                         abs(b.y - (a.y + a.tiefe)) < eps)
            y_overlap = a.y < b.y + b.tiefe + eps and b.y < a.y + a.tiefe + eps
            x_touch   = (abs(a.x - (b.x + b.breite)) < eps or
                         abs(b.x - (a.x + a.breite)) < eps)
            return (x_overlap and y_touch) or (y_overlap and x_touch)

        for zone in zonen:
            adj_names = [
                z2.name for z2 in zonen
                if z2.name != zone.name and _are_adjacent(zone, z2)
            ]
            ist_area = round(zone.breite * zone.tiefe * zone.floors, 1)
            soll_area = zone.flaeche_m2
            delta_pct = round((ist_area - soll_area) / max(1, soll_area) * 100, 1)

            if zone.schraffur:
                planning_decisions.append({
                    "agent":      "layout",
                    "variante":   variante_key,
                    "kategorie":  "Erweiterungsreserve",
                    "zone":       zone.name,
                    "aktion":     f"Reserve {zone.breite:.0f}×{zone.tiefe:.0f} m bei x={zone.x:.0f}/y={zone.y:.0f}",
                    "begruendung": (
                        f"Split-Strategie '{split_priority_map.get(variante_key, '?')}': "
                        f"{round(zone.breite * zone.tiefe):,} m² Erweiterungsreserve freigehalten."
                    ),
                    "wert":       {"area_m2": round(zone.breite * zone.tiefe), "x": zone.x, "y": zone.y},
                    "regel_ref":  "layout.reserve_fraction",
                })
            else:
                adj_str = ", ".join(adj_names) if adj_names else "—"
                planning_decisions.append({
                    "agent":      "layout",
                    "variante":   variante_key,
                    "kategorie":  "Zonenplatzierung",
                    "zone":       zone.name,
                    "aktion":     f"x={zone.x:.0f} m, y={zone.y:.0f} m, {zone.breite:.0f}×{zone.tiefe:.0f} m",
                    "begruendung": (
                        f"DIN {zone.din_kategorie}. "
                        f"Ist: {ist_area:,.0f} m² (Soll: {soll_area:,.0f} m², Δ {delta_pct:+.0f}%). "
                        f"Angrenzend: {adj_str}."
                    ),
                    "wert":       {
                        "area_soll_m2": soll_area,
                        "area_ist_m2":  ist_area,
                        "delta_pct":    delta_pct,
                        "floors":       zone.floors,
                    },
                    "regel_ref":  f"topology.{zone.din_kategorie.lower().replace(' ', '_')}",
                })
```

### Return-Wert erweitern

Im `return`-Statement am Ende von `layout_agent()` (wo `variants` und `reasoning_log` zurückgegeben werden):

```python
        "planning_decisions": planning_decisions,
```

hinzufügen.

---

## Aufgabe 3: `app/agents/rules.py`

### Wo einfügen

Am Ende von `rules_agent()`, kurz vor dem `return`-Statement.

Lese den aktuellen Stand der Funktion. Das Muster: nach dem Zusammenbauen von `rules`,
`rules_hard`, `rules_conventions` — bevor `return` aufgerufen wird.

```python
    # ── Entscheidungsprotokoll: Regelanwendung ────────────────────────────────
    planning_decisions = list(state.get("planning_decisions") or [])

    # Zentrale Kennwerte aus dem aktiven Regelset loggen
    _log_rule_kvs = [
        ("Brandabschnitt max",        rules.get("brandschutz", {}).get("brandabschnitt_max_m2"), "m²",  "rules.brandschutz.brandabschnitt_max_m2"),
        ("Fluchtweg max",             rules.get("brandschutz", {}).get("fluchtweg_max_m"),        "m",   "rules.brandschutz.fluchtweg_max_m"),
        ("Freie Ostfassade min",      rules.get("erweiterbarkeit", {}).get("freie_ostfassade_min_pct"), "%", "rules.erweiterbarkeit.freie_ostfassade_min_pct"),
        ("LKW-Rangierbreite",         rules.get("erschliessung", {}).get("rangierbreite_lkw_m"),  "m",   "rules.erschliessung.rangierbreite_lkw_m"),
        ("Stellplätze je 100 m²",     rules.get("erschliessung", {}).get("stellplaetze_je_100m2_buero"), "SP", "rules.erschliessung.stellplaetze"),
        ("Technische Zonenfläche %",  rules.get("betrieb", {}).get("technikflaeche_pct_nuf"),     "%",   "rules.betrieb.technikflaeche_pct_nuf"),
    ]

    for label, wert, einheit, regelref in _log_rule_kvs:
        if wert is None:
            continue
        planning_decisions.append({
            "agent":      "rules",
            "variante":   "alle",
            "kategorie":  "Regelanwendung",
            "zone":       None,
            "aktion":     f"{label}: {wert} {einheit}",
            "begruendung": f"Aus aktivem Regelset ({nutzungstyp}) übernommen.",
            "wert":       {"wert": wert, "einheit": einheit},
            "regel_ref":  regelref,
        })
```

Im `return`-Statement ergänzen:
```python
        "planning_decisions": planning_decisions,
```

**Hinweis:** `nutzungstyp` ist in `rules_agent()` bereits verfügbar (aus `state["user_input"]` oder `structured_briefing`). Falls nicht, lies ihn aus `(state.get("structured_briefing") or state.get("user_input") or {}).get("nutzungstyp", "")`.

---

## Aufgabe 4: `app/agents/evaluation.py`

### Wo einfügen

In der Schleife `for v in variants:`, **nach** dem Block der `score_dict["tragwerk_score"]`-Berechnung
und **vor** dem `evaluations.append(score_dict)`.

```python
        # ── Entscheidungsprotokoll: Bewertung ─────────────────────────────────
        planning_decisions = list(state.get("planning_decisions") or [])

        _g = g  # Gewichtungsdict des aktuellen Variante
        for kriterium, score_key, gew_key in [
            ("Materialfluss",   "materialfluss_score",   "materialfluss"),
            ("Erweiterbarkeit", "erweiterbarkeit_score", "erweiterbarkeit"),
            ("Tragwerk",        "tragwerk_score",        "tragwerk"),
        ]:
            kr_score = score_dict.get(score_key, 0.0)
            kr_gew   = _g.get(gew_key, 0.0)
            planning_decisions.append({
                "agent":      "evaluation",
                "variante":   v["name"],
                "kategorie":  "Bewertung",
                "zone":       None,
                "aktion":     f"{kriterium}: {kr_score:.1f}/10 (Gewichtung {kr_gew:.0%})",
                "begruendung": (
                    f"Beitrag zum Gesamtscore: {kr_score * kr_gew:.2f} Punkte. "
                    + (f"{len(compliance_issues)} Compliance-Hinweis(e)."
                       if kriterium == "Tragwerk" and compliance_issues else "")
                ),
                "wert":       {"score": kr_score, "gewichtung": kr_gew, "beitrag": round(kr_score * kr_gew, 3)},
                "regel_ref":  f"scoring.{gew_key}",
            })
```

Im `return`-Statement am Ende von `evaluation_agent()` ergänzen:
```python
        "planning_decisions": planning_decisions,
```

---

## Aufgabe 5: `app/agents/report.py` — Entscheidungsprotokoll rendern

### Bestehende Funktion `_append_whitebox_section` ersetzen

Die bestehende Funktion (ab `def _append_whitebox_section`) durch diese vollständige Version ersetzen:

```python
def _append_whitebox_section(report_md: str, state: PlanningState) -> str:
    """Hängt das vollständige Entscheidungsprotokoll an den Report an."""

    planning_decisions: list[dict] = state.get("planning_decisions") or []
    compliance:         list[dict] = state.get("compliance_issues") or []

    # Fallback auf altes reasoning_log wenn keine planning_decisions vorhanden
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
                lines.append(
                    f"| **{d.get('zone', '—')}** | {d.get('begruendung', '').split('.')[0]} "
                    f"| {d.get('aktion', '—')} "
                    f"| {wert.get('area_ist_m2', '—'):,.0f} "
                    f"| {wert.get('area_soll_m2', '—'):,.0f} "
                    f"| {wert.get('delta_pct', 0.0):+.0f}% "
                    f"| {d.get('begruendung', '').split('Angrenzend:')[-1].strip() if 'Angrenzend:' in d.get('begruendung', '') else '—'} |"
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
```

---

## Verifikation

Nach Implementierung einen vollständigen Pipeline-Lauf starten und prüfen:

1. `st.session_state.result.get("planning_decisions")` ist nicht leer (> 10 Einträge)
2. Im Markdown-Report erscheint der Abschnitt `## Entscheidungsprotokoll` mit:
   - Tabelle "Angewendetes Regelset"
   - Tabelle "Variante A – Zonenplatzierung" (alle Zonen mit Ist/Soll/Δ)
   - Tabelle "Bewertungsergebnis"
3. Kein bestehender Test/Lauf schlägt fehl (keine Breaking Changes an vorhandenen State-Keys)

---

## Wichtige Regeln

- `planning_decisions` aus State immer mit `list(state.get("planning_decisions") or [])` lesen
  (niemals direkter Zugriff — Key könnte fehlen wenn alter State geladen wird)
- Bestehende `reasoning_log`-Einträge NICHT entfernen — sie laufen parallel weiter
- Die `_are_adjacent`-Hilfsfunktion in `layout.py` als lokale Funktion direkt in der
  Schleife definieren (kein Modul-Level, kein Import)
- In `evaluation.py` die `compliance_issues`-Variable nutzen, die bereits in der Schleife
  berechnet wird (nicht nochmals berechnen)

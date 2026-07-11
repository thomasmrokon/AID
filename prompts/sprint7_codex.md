# Sprint 7B – Codex: PDF-Lageplan + Kostenschätzung-UI + DXF-Download

## Kontext

Du arbeitest an einem Python-Projekt (LangGraph + Streamlit) zur Industriebau-Planung.
Deine Aufgabe umfasst **zwei Dateien**:

1. `app/tools/drawing.py` — neue Funktion `zeichne_lageplan_pdf()` + Hilfsfunktion `_draw_plankopf()`
2. `streamlit_app.py` — Kostenschätzungs-Expander + PDF- und DXF-Download-Buttons in `schritt_ergebnisse()`

Keine anderen Dateien werden angefasst.

---

## Abhängigkeiten (durch Sprint 7A – Gemini bereits erstellt)

Sprint 7A hat folgende Dateien bereits angelegt — du benutzt sie nur, du veränderst sie nicht:

- `app/tools/cost.py` mit `estimate_costs(variant: dict, briefing: dict) -> dict`
- `app/tools/dxf_export.py` mit `export_layout_to_dxf(variant: dict, site_geometry: dict, briefing: dict) -> bytes`

Rückgabe von `estimate_costs(...)`:
```python
{
    "baukosten_min": 3_200_000.0,
    "baukosten_mid": 3_950_000.0,
    "baukosten_max": 4_700_000.0,
    "nebenkosten_mid": 711_000.0,         # 18 % der baukosten_mid
    "gesamtkosten_mid": 4_661_000.0,
    "kosten_je_m2_bgf": 1_165.0,
    "zonen_aufschluesselung": [
        {
            "zone": "Produktion",
            "din_kategorie": "NUF 3",
            "flaeche_m2": 2400.0,
            "kosten_min": 1_056_000.0,
            "kosten_mid": 1_200_000.0,
            "kosten_max": 1_344_000.0,
        },
        ...
    ],
}
```

---

## Aufgabe 1: `app/tools/drawing.py`

### 1a. Neue Hilfsfunktion `_draw_plankopf()`

Füge diese Funktion **am Ende der Datei** ein (nach `_draw_scalebar`):

```python
def _draw_plankopf(
    ax,
    projektname: str,
    variante_name: str,
    nutzungstyp: str,
    massstab: str,
    scores: dict,
    plannummer: str,
) -> None:
    """Zeichnet den DIN-Plankopf in den unteren Axes-Bereich."""
    import datetime
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    datum = datetime.date.today().strftime("%d.%m.%Y")
    gesamtscore = scores.get("gesamtscore", 0.0)

    felder = [
        ("PROJEKT",     projektname,                    0.00, 0.55),
        ("VARIANTE",    variante_name.replace("_", " "),0.00, 0.00),
        ("NUTZUNG",     nutzungstyp,                    0.22, 0.00),
        ("MASSSTAB",    massstab,                       0.44, 0.00),
        ("DATUM",       datum,                          0.58, 0.00),
        ("PLAN-NR.",    plannummer,                     0.72, 0.00),
        ("GESAMTSCORE", f"{gesamtscore:.1f} / 10",      0.86, 0.00),
    ]

    # Trennlinie oben
    ax.axhline(y=0.92, color="#444444", lw=1.0, xmin=0.0, xmax=1.0)

    for label, value, x, y_extra in felder:
        is_projekt = y_extra > 0.0
        box_x = x
        box_w = 0.22 if is_projekt else 0.14
        box_h = 0.88 if is_projekt else 0.88

        ax.add_patch(mpatches.FancyBboxPatch(
            (box_x + 0.002, 0.04), box_w - 0.004, box_h - 0.04,
            boxstyle="square,pad=0",
            linewidth=0.5, edgecolor="#888888", facecolor="#FFFFFF",
            transform=ax.transAxes,
        ))
        ax.text(
            box_x + 0.005, 0.90, label,
            transform=ax.transAxes,
            ha="left", va="top", fontsize=5.5, color="#888888",
        )
        ax.text(
            box_x + box_w / 2, 0.48, value,
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=8 if not is_projekt else 9,
            fontweight="bold", color="#111111",
            wrap=True,
        )
```

### 1b. Neue Hauptfunktion `zeichne_lageplan_pdf()`

Füge diese Funktion **direkt nach `zeichne_layout()`** ein (also nach Zeile 276, vor dem Kommentar
`# Hilfs-Zeichenfunktionen`):

```python
def zeichne_lageplan_pdf(
    variante_name:      str,
    beschreibung:       str,
    zonen:              list[Zone],
    site_breite:        float,
    site_tiefe:         float,
    raster_x:           float,
    raster_y:           float,
    scores:             dict,
    gewichtung:         dict,
    output_path:        Path,
    nutzungstyp:        str = "",
    site_geometry:      dict | None = None,
    tragwerk_config:    dict | None = None,
    mep_variant_data:   dict | None = None,
    projektname:        str = "AID Demo",
    plannummer:         str = "L-001",
) -> Path:
    """Rendert ein Layout als Vektor-PDF im Format A3 quer mit DIN-Plankopf.

    Gibt den Pfad zur erzeugten PDF-Datei zurück.
    """
    import matplotlib.gridspec as gridspec

    # A3 quer in Zoll (420 × 297 mm)
    fig = plt.figure(figsize=(16.54, 11.69))
    fig.patch.set_facecolor("#FAFAFA")

    gs = gridspec.GridSpec(
        2, 1,
        figure=fig,
        height_ratios=[82, 18],
        hspace=0.02,
    )
    ax_plan = fig.add_subplot(gs[0])
    ax_kopf = fig.add_subplot(gs[1])

    ax_plan.set_facecolor("#E8EDF0")

    # ── Planinhalt (identisch zu zeichne_layout) ────────────────────────────
    _draw_site(ax_plan, site_geometry, site_breite, site_tiefe)
    _draw_grid(ax_plan, zonen, raster_x, raster_y)

    for zone in zonen:
        _draw_zone(ax_plan, zone)

    trassen_laenge = _draw_techniktrassen(ax_plan, zonen, mep_variant_data)

    for zone in zonen:
        _draw_zone_label(ax_plan, zone)

    if site_geometry:
        _draw_access_points(ax_plan, site_geometry, site_breite, site_tiefe)

    building_fp = sum(
        z.breite * z.tiefe
        for z in zonen
        if not z.schraffur and z.din_kategorie != "VF"
    )
    site_area = float((site_geometry or {}).get("area_m2") or site_breite * site_tiefe)
    stellplaetze = berechne_stellplaetze(site_area, building_fp)
    gezeichnete_stellplaetze = _draw_parking_info(
        ax_plan, site_geometry, site_breite, site_tiefe, zonen, stellplaetze
    )

    _draw_legend(ax_plan, zonen)
    _draw_badges(ax_plan, zonen, site_breite, site_tiefe, gezeichnete_stellplaetze, trassen_laenge)
    _draw_north_arrow(ax_plan, site_breite, site_tiefe)
    _draw_scalebar(ax_plan, site_tiefe)

    verstoesse = scores.get("regelverletzungen", [])
    if verstoesse:
        vtext = "WARNUNG: " + "\nWARNUNG: ".join(verstoesse)
        ax_plan.text(0.02, 0.04, vtext,
                     transform=ax_plan.transAxes,
                     ha="left", va="bottom", fontsize=7, color="#C0392B",
                     bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF3F3",
                               edgecolor="#C0392B", alpha=0.9),
                     zorder=10)

    if tragwerk_config:
        _draw_tragwerk_badge(ax_plan, site_breite, site_tiefe, tragwerk_config)
    if mep_variant_data:
        _draw_mep_gewerk_legende(ax_plan, mep_variant_data)

    margin = max(8.0, min(site_breite, site_tiefe) * 0.10)
    ax_plan.set_xlim(-margin, site_breite + margin * 2)
    ax_plan.set_ylim(-margin * 1.2, site_tiefe + margin)
    ax_plan.set_aspect("equal")
    ax_plan.set_xlabel("Breite [m]", fontsize=8)
    ax_plan.set_ylabel("Tiefe [m]", fontsize=8)
    ax_plan.tick_params(labelsize=7)

    # ── Maßstab berechnen ───────────────────────────────────────────────────
    # Grundlage: Planbreite ≈ 14" (A3 minus Rand); site in Metern → mm-Faktor
    plan_width_mm = 340.0  # Nutzbreite des Planfelds auf A3 quer
    site_max_m = max(site_breite, site_tiefe)
    raw_scale = (site_max_m * 1000.0) / plan_width_mm
    # Runden auf nächsthöhere Standardmaßstabstufe
    for std in (100, 200, 250, 500, 750, 1000, 1250, 1500, 2000):
        if raw_scale <= std:
            massstab_zahl = std
            break
    else:
        massstab_zahl = int(round(raw_scale / 100) * 100)
    massstab_str = f"1 : {massstab_zahl}"

    # ── Plankopf ─────────────────────────────────────────────────────────────
    _draw_plankopf(
        ax_kopf,
        projektname=projektname,
        variante_name=variante_name,
        nutzungstyp=nutzungstyp,
        massstab=massstab_str,
        scores=scores,
        plannummer=plannummer,
    )

    # ── Speichern ────────────────────────────────────────────────────────────
    pdf_path = Path(str(output_path).replace(".png", ".pdf"))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(pdf_path, format="pdf", bbox_inches="tight", dpi=150)
    plt.close(fig)
    return pdf_path
```

### Bestehende Imports prüfen

`matplotlib.gridspec` ist in der Standardbibliothek von matplotlib. Es wird bereits `import matplotlib`
und `import matplotlib.pyplot as plt` importiert — kein neuer Top-Level-Import notwendig, da der
`import gridspec` lokal in der Funktion steht.

---

## Aufgabe 2: `streamlit_app.py`

### 2a. Kostenschätzungs-Expander

**Einfügeposition:** In `schritt_ergebnisse()`, innerhalb der `for tab, key in zip(tabs, variante_keys):`
Schleife, **nach dem MEP-Expander-Block** (der endet ca. bei `if rows: st.dataframe(...)`) und
**vor dem Block** `# --- Download-Links ---` (ca. Zeile 1371).

**Ersetze** den Kommentar `# --- Download-Links ---` durch diesen Block (füge ihn davor ein):

```python
            # --- Kostenschätzung ---
            try:
                from app.tools.cost import estimate_costs
                cost_data = estimate_costs(
                    vdata_z or {},
                    result.get("structured_briefing") or {},
                )
                with st.expander("Kostenschätzung (Indikation)", expanded=False):
                    kc1, kc2, kc3 = st.columns(3)
                    kc1.metric(
                        "Baukosten (Mitte)",
                        f"{cost_data['baukosten_mid'] / 1_000_000:.2f} Mio. €",
                        help=f"Spanne: {cost_data['baukosten_min']/1e6:.2f} – "
                             f"{cost_data['baukosten_max']/1e6:.2f} Mio. €",
                    )
                    kc2.metric(
                        "Gesamtkosten inkl. NK",
                        f"{cost_data['gesamtkosten_mid'] / 1_000_000:.2f} Mio. €",
                        help=f"Nebenkosten (18 %): {cost_data['nebenkosten_mid']/1e6:.2f} Mio. €",
                    )
                    kc3.metric(
                        "Kosten je m² BGF",
                        f"{cost_data['kosten_je_m2_bgf']:,.0f} €/m²",
                    )
                    import pandas as pd
                    aufschl = cost_data.get("zonen_aufschluesselung", [])
                    if aufschl:
                        df_cost = pd.DataFrame([
                            {
                                "Zone": r["zone"],
                                "DIN": r["din_kategorie"],
                                "Fläche m²": f"{r['flaeche_m2']:,.0f}",
                                "Kosten min €": f"{r['kosten_min']:,.0f}",
                                "Kosten mid €": f"{r['kosten_mid']:,.0f}",
                                "Kosten max €": f"{r['kosten_max']:,.0f}",
                            }
                            for r in aufschl
                        ])
                        st.dataframe(df_cost, hide_index=True, use_container_width=True)
                        st.caption(
                            "Richtwerte nach BKI / BMVBS-Kostenkennwerten (Preisstand 2024). "
                            "Keine Gewähr. Nur für Planungszwecke."
                        )
            except Exception as _cost_err:
                st.caption(f"Kostenschätzung nicht verfügbar: {_cost_err}")
```

### 2b. PDF- und DXF-Download-Buttons

**Einfügeposition:** **Nach** dem bestehenden `dl_cols`-Block (der endet nach dem `gh_path_art`-Zweig,
ca. Zeile 1399), **vor** `st.divider()` (Zeile 1400).

**Füge direkt nach dem letzten `if gh_path_art ...`-Block ein:**

```python
            # --- PDF + DXF Download ---
            vdata_dl = variants_data.get(key)
            if vdata_dl and vdata_dl.get("zonen"):
                pdf_dxf_cols = st.columns(2)

                # PDF-Lageplan
                with pdf_dxf_cols[0]:
                    if st.button(f"PDF generieren ({key})", key=f"btn_pdf_{key}"):
                        try:
                            import tempfile
                            from app.tools.geometry import Zone as ZonePDF
                            from app.tools.drawing import zeichne_lageplan_pdf
                            ev_pdf = next(
                                (e for e in result.get("evaluations", [])
                                 if e.get("variante") == key), {}
                            )
                            zonen_pdf = [
                                ZonePDF(
                                    name=z["name"], x=z["x"], y=z["y"],
                                    breite=z["breite"], tiefe=z["tiefe"],
                                    flaeche_m2=z["flaeche_m2"],
                                    din_kategorie=z["din_kategorie"],
                                    farbe=z["farbe"], schraffur=z.get("schraffur", False),
                                    floors=z.get("floors", 1),
                                    planned_area_m2=z.get("planned_area_m2"),
                                    delta_m2=z.get("delta_m2", 0.0),
                                    delta_pct=z.get("delta_pct", 0.0),
                                )
                                for z in vdata_dl["zonen"]
                            ]
                            with tempfile.NamedTemporaryFile(
                                suffix=".png", delete=False
                            ) as tmp:
                                tmp_path = Path(tmp.name)
                            pdf_path = zeichne_lageplan_pdf(
                                variante_name=key,
                                beschreibung=vdata_dl.get("beschreibung", ""),
                                zonen=zonen_pdf,
                                site_breite=vdata_dl.get("site_breite", 0),
                                site_tiefe=vdata_dl.get("site_tiefe", 0),
                                raster_x=vdata_dl.get("raster_x", 18.0),
                                raster_y=vdata_dl.get("raster_y", 9.0),
                                scores=ev_pdf,
                                gewichtung=vdata_dl.get("gewichtung", {}),
                                output_path=tmp_path,
                                nutzungstyp=st.session_state.user_input.get("nutzungstyp", ""),
                                site_geometry=vdata_dl.get("site_geometry"),
                                tragwerk_config=result.get("tragwerk_config"),
                                mep_variant_data=(
                                    result.get("mep_trassennetz") or {}
                                ).get(key),
                                projektname=st.session_state.user_input.get(
                                    "projektname", "AID Demo"
                                ),
                                plannummer=f"L-{key[:1]}-001",
                            )
                            with open(pdf_path, "rb") as fh:
                                st.download_button(
                                    "⬇ Lageplan PDF",
                                    data=fh.read(),
                                    file_name=f"lageplan_{key}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_pdf_{key}",
                                )
                            tmp_path.unlink(missing_ok=True)
                            pdf_path.unlink(missing_ok=True)
                        except Exception as e:
                            st.warning(f"PDF-Erzeugung fehlgeschlagen: {e}")

                # DXF-Export
                with pdf_dxf_cols[1]:
                    if st.button(f"DXF generieren ({key})", key=f"btn_dxf_{key}"):
                        try:
                            from app.tools.dxf_export import export_layout_to_dxf
                            dxf_bytes = export_layout_to_dxf(
                                variant=vdata_dl,
                                site_geometry=vdata_dl.get("site_geometry") or {},
                                briefing=result.get("structured_briefing") or {},
                            )
                            st.download_button(
                                "⬇ DXF (AutoCAD)",
                                data=dxf_bytes,
                                file_name=f"layout_{key}.dxf",
                                mime="application/dxf",
                                key=f"dl_dxf_{key}",
                            )
                        except Exception as e:
                            st.warning(f"DXF-Export fehlgeschlagen: {e}")
```

---

## Vollständige Einfügereihenfolge in `schritt_ergebnisse()` (Zusammenfassung)

Innerhalb der `for tab, key in zip(tabs, variante_keys):` Schleife, nach allen bestehenden Blöcken,
ist die Reihenfolge jetzt:

1. Score-Metriken (bereits vorhanden)
2. Zonen-Flächenvergleich-Expander (bereits vorhanden)
3. Grundriss-Tab / 3D-Tab / Overlay-Toggle (bereits vorhanden)
4. MEP-Anforderungen-Expander (bereits vorhanden)
5. **Kostenschätzung-Expander** ← NEU (Aufgabe 2a)
6. Download-Links: 3DM + JSON (bereits vorhanden, `dl_cols = st.columns(3)`)
7. **PDF + DXF Download-Buttons** ← NEU (Aufgabe 2b), nach dem `gh_path_art`-Block

---

## Wichtige Hinweise

### Zu `zeichne_lageplan_pdf()`
- Die Funktion ruft **dieselben privaten `_draw_*`-Hilfsfunktionen** auf wie `zeichne_layout()` — kein Code duplizieren, nur aufrufen.
- `_draw_graph_overlay()` wird **nicht** aufgerufen (kein interaktiver Overlay im PDF).
- `_draw_techniktrassen()` ist bereits in der Datei vorhanden — einfach aufrufen.
- `berechne_stellplaetze()` ist bereits in der Datei vorhanden.
- `_draw_badges()` ist bereits in der Datei vorhanden.

### Zu `_draw_plankopf()`
- Die Funktion verwendet `ax.transAxes` (relatives Koordinatensystem 0–1).
- `mpatches` ist bereits importiert (`import matplotlib.patches as mpatches`).
- `datetime` wird lokal importiert, kein neuer Top-Level-Import nötig.
- Das Feld PROJEKT erhält die volle linke Hälfte (x=0.00, breite≈0.44), die anderen Felder teilen die rechte Hälfte.

### Zu den Download-Buttons
- Buttons triggern die Generierung erst on-click (nicht beim Laden der Seite) — spart Rechenzeit.
- Falls `app.tools.cost` oder `app.tools.dxf_export` noch nicht existiert (Gemini-Sprint nicht ausgeführt), fängt `except` das ab und zeigt eine Warnung.
- `st.session_state.user_input.get("projektname", "AID Demo")` — das Feld `projektname` existiert aktuell nicht im UI; wenn es fehlt, wird der Default `"AID Demo"` verwendet. Kein Fehler.

---

## Verifikation

Nach Implementierung:

```python
# Minimaler Smoke-Test (nicht als Datei speichern):
from pathlib import Path
from app.tools.geometry import Zone
from app.tools.drawing import zeichne_lageplan_pdf

test_zone = Zone(
    name="Produktion", x=0, y=0, breite=60, tiefe=40,
    flaeche_m2=2400, din_kategorie="NUF 3",
    farbe="#E8A87C", schraffur=False,
)
pdf = zeichne_lageplan_pdf(
    variante_name="A_Materialfluss",
    beschreibung="Prozessfolge",
    zonen=[test_zone],
    site_breite=80, site_tiefe=60,
    raster_x=18.0, raster_y=9.0,
    scores={"gesamtscore": 7.4},
    gewichtung={},
    output_path=Path("outputs/test_lageplan.png"),
    projektname="Testprojekt",
    plannummer="L-A-001",
)
print(f"PDF erzeugt: {pdf} ({pdf.stat().st_size / 1024:.0f} KB)")
assert pdf.suffix == ".pdf"
assert pdf.stat().st_size > 10_000
```

Erwartung: `outputs/test_lageplan.pdf` mit >10 KB, öffenbar im PDF-Viewer mit sichtbarem Plankopf.

---

## Was du NICHT änderst

- `app/tools/cost.py` (von Gemini erstellt)
- `app/tools/dxf_export.py` (von Gemini erstellt)
- `app/data/costs.yaml` (von Gemini erstellt)
- `pyproject.toml` (bereits durch Gemini-Sprint aktualisiert)
- Alle anderen Dateien im Projekt

# Sprint 6B – Codex: Folium-Karte + Erschließungsschematik

## Kontext

Du arbeitest an einem Python-Projekt (LangGraph + Streamlit) zur KI-gestützten Industriebau-Planung.
Zwei Dateien werden geändert:
1. **`app/tools/graph_viz.py`** — Funktion `build_erschliessungsgraph_figure()` neu schreiben
2. **`streamlit_app.py`** — Tab "Adresssuche" in `schritt_grundstueck()` komplett ersetzen

---

## Aufgabe 1: `app/tools/graph_viz.py` — Erschließungs-Schematik

### Was aktuell drin steht (ersetzen)

Die bestehende `build_erschliessungsgraph_figure()` zeigt 6 hardcoded Knoten im Kreis — das ist nicht verständlich. Sie wird durch eine räumliche Lageplan-Ansicht ersetzt.

```python
# BESTEHEND — vollständig ersetzen:
def build_erschliessungsgraph_figure(
    user_input: dict,
    site_geometry: dict | None,
) -> "go.Figure":
    import plotly.graph_objects as go
    # ... [hardcoded Kreis-Graph mit 6 Knoten] ...
```

### Was du schreibst

Die neue Funktion zeichnet eine räumliche Draufsicht:
- Grundstück als Polygon-Outline
- Gebäude-Footprint als grauer Bereich (wenn `variants` übergeben)
- Zufahrten aus `site_geometry["access_points"]` als farbige Pfeile
- LKW-Routen (rot gestrichelt) + PKW-Routen (grün gepunktet)

**Signatur** (Signatur ändert sich — `variants` wird neu ergänzt):

```python
def build_erschliessungsgraph_figure(
    user_input: dict,
    site_geometry: dict | None,
    variants: list[dict] | None = None,
) -> "go.Figure":
```

**Implementierung:**

```python
def build_erschliessungsgraph_figure(
    user_input: dict,
    site_geometry: dict | None,
    variants: list[dict] | None = None,
) -> "go.Figure":
    """Räumliche Erschließungs-Schematik als Draufsicht (Lageplan).

    Zeichnet Grundstück-Polygon, Gebäude-Footprint und farbige Erschließungsrouten.
    Kein Knoten-Kanten-Graph. Nur go.Scatter + go.Scatter shapes.
    """
    import plotly.graph_objects as go
    import math

    traces: list = []
    annotations: list = []

    # ── 1. Grundstück ─────────────────────────────────────────────────────────
    polygon = (site_geometry or {}).get("polygon", [])
    site_w = (site_geometry or {}).get("width_m", 100.0)
    site_d = (site_geometry or {}).get("depth_m", 100.0)

    if polygon:
        xs = [p[0] for p in polygon] + [polygon[0][0]]
        ys = [p[1] for p in polygon] + [polygon[0][1]]
    else:
        xs = [0, site_w, site_w, 0, 0]
        ys = [0, 0, site_d, site_d, 0]

    traces.append(go.Scatter(
        x=xs, y=ys, mode="lines", fill="toself",
        fillcolor="rgba(216,228,200,0.5)",
        line=dict(color="#5A7A3A", width=2),
        name="Grundstück", showlegend=True,
        hoverinfo="skip",
    ))

    # ── 2. Gebäude-Footprint ──────────────────────────────────────────────────
    env = {}
    if variants:
        env = (variants[0] or {}).get("building_envelope") or {}
    if env.get("width_m"):
        bx, by = env.get("x", 0), env.get("y", 0)
        bw, bd = env["width_m"], env["depth_m"]
        traces.append(go.Scatter(
            x=[bx, bx+bw, bx+bw, bx, bx],
            y=[by, by,    by+bd, by+bd, by],
            mode="lines", fill="toself",
            fillcolor="rgba(180,180,180,0.35)",
            line=dict(color="#888888", width=1.5, dash="dot"),
            name="Gebäude (Footprint)", showlegend=True,
            hovertemplate="Gebäude-Footprint<br>"
                          f"{bw:.0f} × {bd:.0f} m<extra></extra>",
        ))

    # ── 3. Zufahrten + Routen ─────────────────────────────────────────────────
    access_points = (site_geometry or {}).get("access_points", [])
    nutzungstyp = str((user_input or {}).get("nutzungstyp", ""))

    # Zufahrtstyp ermitteln: erste = LKW (rot), zweite = PKW (grün)
    ap_colors   = ["#C0392B", "#27AE60", "#2980B9"]
    ap_labels   = ["LKW-Zufahrt", "PKW-Zufahrt", "Zufahrt"]
    route_dashes = ["dash", "dot", "dashdot"]

    for i, ap in enumerate(access_points[:3]):
        pt = ap.get("point", [site_w/2, 0])
        side = ap.get("side", "south")
        width_m = ap.get("width_m", 7.5)
        color = ap_colors[min(i, 2)]
        label = ap_labels[min(i, 2)]

        # Pfeil: von außen (8m entfernt) in Richtung Grundstücksmitte
        arrow_len = 12.0
        if side == "south":
            ax0, ay0 = pt[0], pt[1] - arrow_len
            ax1, ay1 = pt[0], pt[1]
        elif side == "north":
            ax0, ay0 = pt[0], pt[1] + arrow_len
            ax1, ay1 = pt[0], pt[1]
        elif side == "west":
            ax0, ay0 = pt[0] - arrow_len, pt[1]
            ax1, ay1 = pt[0], pt[1]
        else:  # east
            ax0, ay0 = pt[0] + arrow_len, pt[1]
            ax1, ay1 = pt[0], pt[1]

        # Zufahrtspfeil
        traces.append(go.Scatter(
            x=[ax0, ax1], y=[ay0, ay1], mode="lines",
            line=dict(color=color, width=3),
            showlegend=False, hoverinfo="skip",
        ))
        annotations.append(dict(
            x=ax1, y=ay1, ax=ax0, ay=ay0,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=1.5,
            arrowwidth=2.5, arrowcolor=color,
        ))
        # Label
        traces.append(go.Scatter(
            x=[(ax0+ax1)/2], y=[(ay0+ay1)/2],
            mode="text",
            text=[f"<b>{label}</b><br>{width_m:.0f} m"],
            textfont=dict(size=9, color=color),
            showlegend=False, hoverinfo="skip",
        ))

        # Route durch Grundstück (gestrichelt)
        mid_x, mid_y = site_w / 2, site_d / 2
        dash = route_dashes[min(i, 2)]
        if i == 0:  # LKW: Zufahrt → Gebäude-WE-Seite → Gebäude-Versand-Seite → Ausfahrt
            route_x = [pt[0], pt[0], mid_x, mid_x]
            route_y = [pt[1], by + bd * 0.2 if env.get("width_m") else site_d * 0.3,
                       by + bd * 0.8 if env.get("width_m") else site_d * 0.7, pt[1] + site_d * 0.6]
            traces.append(go.Scatter(
                x=route_x, y=route_y, mode="lines",
                line=dict(color=color, width=1.8, dash=dash),
                name="LKW-Route", showlegend=True,
                hovertemplate="LKW-Route (schematisch)<extra></extra>",
            ))
        elif i == 1:  # PKW: Zufahrt → Stellplatzfläche (vor Gebäude)
            park_x = bx + bw * 0.25 if env.get("width_m") else site_w * 0.25
            park_y = by - 8 if env.get("width_m") and by > 8 else by + bd + 8
            traces.append(go.Scatter(
                x=[pt[0], park_x], y=[pt[1], park_y], mode="lines",
                line=dict(color=color, width=1.8, dash=dash),
                name="PKW-Route", showlegend=True,
                hovertemplate="PKW-Route (schematisch)<extra></extra>",
            ))

    # ── 4. Nordpfeil ──────────────────────────────────────────────────────────
    nx, ny = site_w * 0.92, site_d * 0.85
    annotations.append(dict(
        x=nx, y=ny + site_d * 0.05, ax=nx, ay=ny,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
        arrowcolor="#333333",
    ))
    traces.append(go.Scatter(
        x=[nx], y=[ny + site_d * 0.07], mode="text",
        text=["N"], textfont=dict(size=11, color="#333333", family="Arial Black"),
        showlegend=False, hoverinfo="skip",
    ))

    # ── Figure zusammenbauen ──────────────────────────────────────────────────
    pad = max(site_w, site_d) * 0.12
    fig = go.Figure(data=traces)
    fig.update_layout(
        paper_bgcolor="#FAFAFA",
        plot_bgcolor="#E8EDF0",
        xaxis=dict(
            range=[-pad, site_w + pad],
            title="Breite [m]", showgrid=True, gridcolor="#DDDDDD",
            zeroline=False,
        ),
        yaxis=dict(
            range=[-pad, site_d + pad],
            title="Tiefe [m]", showgrid=True, gridcolor="#DDDDDD",
            zeroline=False, scaleanchor="x",
        ),
        margin=dict(l=50, r=120, t=40, b=50),
        height=480,
        legend=dict(
            x=1.01, y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#CCCCCC", borderwidth=1,
            font=dict(size=10),
        ),
        title=dict(
            text="Erschließungsschema (Draufsicht)",
            font=dict(size=12, color="#333"),
        ),
        annotations=annotations,
        hovermode="closest",
    )
    return fig
```

---

## Aufgabe 2: `streamlit_app.py` — Tab "Adresssuche"

### Was aktuell drin steht (ersetzen)

Im `with tab_adresse:` Block (ca. Zeile 182–243) steht der alte Code: einfaches Text-Input + Laden-Button + statische Vorschau. Diesen Block komplett ersetzen.

**Aktueller Block (zur Orientierung):**
```python
with tab_adresse:
    st.caption("Echtdaten über OpenStreetMap / Overpass API.")
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        address = st.text_input("Adresse / Standort", ...)
    with col_btn:
        st.write("")
        search = st.button("Laden", ...)
    if search and address:
        with st.spinner("Geocoding + OSM-Abfrage..."):
            try:
                from app.tools.gis import site_from_address
                site = site_from_address(address)
            except ImportError:
                ...
        if site:
            st.session_state.gis_site = site
            ...
    gis_site = st.session_state.get("gis_site")
    if gis_site:
        st.pyplot(_plot_site(gis_site), clear_figure=True)
        # ... baurechtliche Kennzahlen + "Verwenden"-Button ...
```

### Was du schreibst

Den gesamten `with tab_adresse:` Block durch folgenden Code ersetzen:

```python
with tab_adresse:
    st.caption("Klicke auf die Karte oder suche eine Adresse, um Grundstücke zu laden.")

    # ── Session-State initialisieren ──────────────────────────────────────────
    for _k, _v in [
        ("gis_center",     [51.0, 10.0]),
        ("gis_zoom",       6),
        ("gis_candidates", []),
        ("gis_selected",   0),
        ("gis_map_click",  None),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # ── Adress-Suche zum Zentrieren ───────────────────────────────────────────
    col_adr, col_btn = st.columns([4, 1])
    with col_adr:
        address = st.text_input(
            "Adresse / Standort",
            placeholder="z.B. Gewerbegebiet Ismaning oder Industriepark Mainz",
            key="gis_address_input",
            label_visibility="collapsed",
        )
    with col_btn:
        search_btn = st.button("Suchen", type="primary", key="gis_search_btn")

    if search_btn and address:
        with st.spinner("Geocoding…"):
            try:
                from app.tools.gis import geocode_address, fetch_all_parcels_osm
                coords = geocode_address(address)
            except ImportError:
                coords = None
                st.warning("GIS-Modul nicht verfügbar (pyproj / requests fehlen).")
        if coords:
            lat, lon = coords
            st.session_state.gis_center = [lat, lon]
            st.session_state.gis_zoom = 15
            with st.spinner("Grundstücke laden…"):
                parcels = fetch_all_parcels_osm(lat, lon, radius_m=400)
            st.session_state.gis_candidates = parcels
            st.session_state.gis_selected = 0
            st.rerun()
        else:
            st.error("Adresse konnte nicht gefunden werden.")

    # ── Folium-Karte ──────────────────────────────────────────────────────────
    try:
        import folium
        from streamlit_folium import st_folium

        m = folium.Map(
            location=st.session_state.gis_center,
            zoom_start=st.session_state.gis_zoom,
            tiles="CartoDB Positron",
        )

        # Gefundene Parzellen als farbige Polygone
        for idx, parcel in enumerate(st.session_state.gis_candidates):
            poly = parcel.get("polygon", [])
            if not poly:
                continue
            is_sel = (idx == st.session_state.gis_selected)
            # Koordinaten: polygon ist (x=lon_local, y=lat_local) nach Normalisierung.
            # Für Folium brauchen wir WGS84 (lat, lon). Da die lokalen Koordinaten
            # normalisiert sind, nutzen wir den Geocode-Punkt als Ursprung.
            center_lat = st.session_state.gis_center[0]
            center_lon = st.session_state.gis_center[1]
            # Näherungsweise Rückrechnung: 1 m ≈ 1/111320 ° lat, 1/111320*cos(lat) ° lon
            import math as _math
            lat_per_m = 1.0 / 111320.0
            lon_per_m = 1.0 / (111320.0 * _math.cos(_math.radians(center_lat)))
            folium_coords = [
                (center_lat + (pt[1] - poly[0][1]) * lat_per_m,
                 center_lon + (pt[0] - poly[0][0]) * lon_per_m)
                for pt in poly
            ]
            folium.Polygon(
                locations=folium_coords,
                color="#1A73E8" if is_sel else "#888888",
                fill=True,
                fill_opacity=0.30 if is_sel else 0.12,
                weight=3 if is_sel else 1.5,
                tooltip=folium.Tooltip(
                    f"<b>{parcel.get('name', 'Grundstück')}</b><br>"
                    f"{parcel.get('area_m2', 0):.0f} m²"
                ),
            ).add_to(m)

        map_result = st_folium(
            m, width="100%", height=400,
            returned_objects=["last_clicked"],
            key="gis_folium_map",
        )

        # Klick auf Karte → neue Overpass-Abfrage
        click = map_result.get("last_clicked") if map_result else None
        if click and click != st.session_state.gis_map_click:
            st.session_state.gis_map_click = click
            click_lat, click_lon = click["lat"], click["lng"]
            st.session_state.gis_center = [click_lat, click_lon]
            st.session_state.gis_zoom = 15
            with st.spinner("Grundstücke an Klick-Position laden…"):
                try:
                    from app.tools.gis import fetch_all_parcels_osm
                    parcels = fetch_all_parcels_osm(click_lat, click_lon, radius_m=300)
                except ImportError:
                    parcels = []
            if parcels:
                st.session_state.gis_candidates = parcels
                st.session_state.gis_selected = 0
            st.rerun()

    except ImportError:
        st.info("Folium nicht installiert. Bitte `pip install streamlit-folium` ausführen.")
        st.caption("Fallback: Adresssuche ohne interaktive Karte.")

    # ── Kandidaten-Auswahl ────────────────────────────────────────────────────
    candidates = st.session_state.gis_candidates
    if candidates:
        st.markdown("**Gefundene Grundstücke** (Klick auf Karte oder Adresssuche)")
        options = [
            f"{p.get('name', 'Grundstück')}  —  {p.get('area_m2', 0):.0f} m²"
            f"  ({p.get('width_m', 0):.0f} × {p.get('depth_m', 0):.0f} m)"
            for p in candidates
        ]
        sel_label = st.radio(
            "Parzelle auswählen:", options,
            index=min(st.session_state.gis_selected, len(options) - 1),
            key="gis_radio",
            label_visibility="collapsed",
        )
        new_sel = options.index(sel_label)
        if new_sel != st.session_state.gis_selected:
            st.session_state.gis_selected = new_sel
            st.rerun()

        selected_parcel = candidates[st.session_state.gis_selected]

        # Baurechtliche Kennzahlen (editierbar, identisch mit bisherigem Code)
        p = selected_parcel.get("planning", {})
        st.markdown("#### Baurechtliche Kennzahlen")
        gc1, gc2, gc3, gc4 = st.columns(4)
        with gc1:
            grz = st.number_input("GRZ", 0.1, 1.0, float(p.get("grz", 0.8)), 0.05, key="gis_grz")
        with gc2:
            gfz = st.number_input("GFZ", 0.1, 5.0, float(p.get("gfz", 2.4)), 0.1, key="gis_gfz")
        with gc3:
            abst = st.number_input("Abstandsfaktor", 0.0, 1.0,
                                   float(p.get("abstandsfaktor", 0.4)), 0.05, key="gis_abst")
        with gc4:
            hoehe = st.number_input("Max. Höhe m", 4.0, 30.0,
                                    float(p.get("max_gebaeudehoehe_m", 12.0)), 0.5, key="gis_hoehe")

        selected_parcel = {
            **selected_parcel,
            "planning": {
                **p,
                "grz": grz, "gfz": gfz,
                "abstandsfaktor": abst,
                "max_gebaeudehoehe_m": hoehe,
            },
        }

        st.markdown("---")
        if st.button("✓ Dieses Grundstück verwenden →", type="primary",
                     key="gis_use_btn", use_container_width=True):
            st.session_state.site_geometry = selected_parcel
            st.session_state.gis_site = selected_parcel
            st.session_state.schritt = 2
            st.rerun()
    else:
        if not st.session_state.get("gis_map_click") and not st.session_state.get("gis_candidates"):
            st.info("Klicke auf die Karte oder suche eine Adresse, um Grundstücke zu finden.")
```

### Außerdem: `build_erschliessungsgraph_figure` Aufruf anpassen

Im `with tab_eg:` Block (ca. Zeile 870–874) den Aufruf um `variants` ergänzen:

```python
with tab_eg:
    from app.tools.graph_viz import build_erschliessungsgraph_figure
    _variants = (st.session_state.get("result") or {}).get("variants")
    fig_eg = build_erschliessungsgraph_figure(
        user_input,
        st.session_state.site_geometry,
        variants=_variants,
    )
    st.plotly_chart(fig_eg, use_container_width=True)
    st.caption("Schematische Draufsicht der Erschließungsrouten (nicht editierbar).")
```

---

## Session-State-Übersicht (nur lesen/schreiben, nicht anlegen)

Bereits vorhandene Keys, die du verwenden kannst:
- `st.session_state.site_geometry` → wird von "Verwenden"-Button gesetzt
- `st.session_state.gis_site` → Zwischenspeicher GIS-Grundstück (bereits initialisiert)
- `st.session_state.schritt` → Steuerung der Navigation
- `st.session_state.result` → Pipeline-Ergebnis (enthält `variants`)

Neue Keys die du initialisierst (in `schritt_grundstueck` → `tab_adresse`):
- `gis_center`, `gis_zoom`, `gis_candidates`, `gis_selected`, `gis_map_click`

---

## Wichtig: Was du NICHT änderst

- `with tab_demo:` Block — bleibt unverändert
- `_plot_site()` Hilfsfunktion — bleibt unverändert
- `build_funktionsgraph_figure()` in `graph_viz.py` — bleibt unverändert
- `EDGE_COLORS`, `build_edge_editor_data()`, `parse_edge_editor_data()` — bleibt unverändert
- `app/tools/gis.py` — wird von Gemini bearbeitet, nicht anfassen

---

## Verifikation

1. `streamlit run streamlit_app.py`
2. Schritt 1 → Tab "Adresssuche (Beta)"
3. Folium-Karte erscheint (Deutschland-Übersicht, grauer Hintergrund)
4. Adresse eingeben → Suchen → Karte springt auf Location, blaue Polygon-Overlays
5. Klick auf Karte → neue Kandidaten laden, Radio-Liste aktualisiert sich
6. Baurechtliche Kennzahlen editierbar → "Verwenden" → weiter zu Schritt 2
7. Schritt 3 → Tab "Erschließungsgraph" → Grundriss-Schematik (nicht mehr Kreis-Graph)
8. Wenn Pipelineergebnis vorhanden: Gebäude-Footprint als gepunktetes Grau sichtbar

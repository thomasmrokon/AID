"""
AID Demo – Interaktiver Plotly-Funktionsgraph
Nodes: Größe proportional zur Zone-Fläche
Edges: Stärke proportional zum Gewicht, Farbe je Kategorie
Interaktion via st.plotly_chart(on_select="rerun")
"""
from __future__ import annotations
import math

# ---------------------------------------------------------------------------
# Kantenfarben je Kategorie
# ---------------------------------------------------------------------------

EDGE_COLORS: dict[str, str] = {
    # Legacy (von _get_graph_config)
    "Prozess":     "#005A8E",
    "Betrieb":     "#777777",
    "Supervision": "#333333",
    "Extern":      "#BBBBBB",
    "Personal":    "#F39C12",
    # Neu (von topology_diagram)
    "Adjacency":   "#E67E22",    # orange — Nähe-Anforderung
    "Separation":  "#E74C3C",    # rot   — Trennkante (negatives Gewicht)
    "Compliance":  "#8E44AD",    # violett
}

# Gestrichelte Darstellung für bestimmte Kantentypen
EDGE_DASH: dict[str, str] = {
    "Separation": "dash",
    "Extern":     "dot",
}

# Kanten die der Nutzer nicht editieren soll
EDGE_READONLY: set[str] = {"Separation"}


# ---------------------------------------------------------------------------
# Sidebar-Editing: Streamlit data_editor helpers
# ---------------------------------------------------------------------------

def build_edge_editor_data(
    edges: list[tuple],
    weights: dict[str, float],
) -> list[dict]:
    """
    Gibt eine Liste von Dicts zurück, die direkt in st.data_editor
    verwendet werden kann. Jede Zeile: Von, Nach, Typ, Gewicht (0.0-1.0).
    Schlüssel "key" = "src__tgt" für Rückabgleich.
    """
    rows: list[dict] = []
    for src, tgt, default_w, kategorie in edges:
        key = f"{src}__{tgt}"
        weight = weights.get(key, default_w)
        rows.append({
            "key": key,
            "Von": str(src).replace("_", " "),
            "Nach": str(tgt).replace("_", " "),
            "Typ": kategorie,
            "Gewicht": float(max(0.0, min(1.0, weight))),
        })
    return rows


def parse_edge_editor_data(rows: list[dict]) -> dict[str, float]:
    """Konvertiert die data_editor-Zeilen zurück in {src__tgt: weight}."""
    parsed: dict[str, float] = {}
    for row in rows:
        key = row.get("key")
        if not key:
            continue
        weight = float(row.get("Gewicht", 0.0) or 0.0)
        parsed[str(key)] = max(0.0, min(1.0, weight))
    return parsed

# ---------------------------------------------------------------------------
# Spring-Layout (ohne networkx-Abhängigkeit)
# ---------------------------------------------------------------------------

def _spring_layout(
    node_ids: list[str],
    edges: list[tuple[str, str, float]],
    seed: int = 42,
    iterations: int = 120,
    k: float = 2.0,
) -> dict[str, tuple[float, float]]:
    """Kräftebasiertes Layout. Gibt {id: (x, y)} zurück."""
    import random
    rng = random.Random(seed)
    pos: dict[str, list[float]] = {
        n: [rng.uniform(-1, 1), rng.uniform(-1, 1)]
        for n in node_ids
    }
    n = len(node_ids)
    if n < 2:
        return {nid: (pos[nid][0], pos[nid][1]) for nid in node_ids}

    # Optimal distance
    area = 4.0
    k_opt = k * math.sqrt(area / n)

    for _ in range(iterations):
        disp: dict[str, list[float]] = {nid: [0.0, 0.0] for nid in node_ids}

        # Repulsion
        for i, u in enumerate(node_ids):
            for v in node_ids[i + 1:]:
                dx = pos[u][0] - pos[v][0]
                dy = pos[u][1] - pos[v][1]
                d = max(0.01, math.sqrt(dx * dx + dy * dy))
                rep = k_opt * k_opt / d
                disp[u][0] += (dx / d) * rep
                disp[u][1] += (dy / d) * rep
                disp[v][0] -= (dx / d) * rep
                disp[v][1] -= (dy / d) * rep

        # Attraction along edges
        for src, tgt, w in edges:
            if src not in pos or tgt not in pos:
                continue
            dx = pos[src][0] - pos[tgt][0]
            dy = pos[src][1] - pos[tgt][1]
            d = max(0.01, math.sqrt(dx * dx + dy * dy))
            att = (d * d / k_opt) * w
            disp[src][0] -= (dx / d) * att
            disp[src][1] -= (dy / d) * att
            disp[tgt][0] += (dx / d) * att
            disp[tgt][1] += (dy / d) * att

        # Apply
        temp = 0.1
        for nid in node_ids:
            d = max(0.01, math.sqrt(disp[nid][0] ** 2 + disp[nid][1] ** 2))
            pos[nid][0] += (disp[nid][0] / d) * min(d, temp)
            pos[nid][1] += (disp[nid][1] / d) * min(d, temp)

    return {nid: (pos[nid][0], pos[nid][1]) for nid in node_ids}


# ---------------------------------------------------------------------------
# Layered-Layout: Prozessfluss von oben nach unten
# ---------------------------------------------------------------------------

def _layered_layout(
    node_ids: list[str],
    process_order: list[str],
    edges: list[tuple[str, str, float]],
) -> dict[str, tuple[float, float]]:
    """
    Knoten werden auf Ebenen verteilt:
      - Layer = Position in process_order (0 = oben, n = unten)
      - X-Position: Prozessknoten mittig, Support-Zonen auf Randebenen

    Gibt {node_id: (x, y)} zurück, normiert auf [-1, 1].
    """
    if not node_ids:
        return {}

    ordered_process = [nid for nid in process_order if nid in node_ids]
    layer_by_node = {nid: i for i, nid in enumerate(ordered_process)}
    support_nodes = [nid for nid in node_ids if nid not in layer_by_node]
    max_layer = max(len(ordered_process) - 1, 1)

    def y_for_layer(layer: float) -> float:
        if len(ordered_process) <= 1:
            return 0.0
        return 1.0 - 2.0 * (layer / max_layer)

    pos: dict[str, tuple[float, float]] = {}
    for nid in ordered_process:
        pos[nid] = (0.0, y_for_layer(layer_by_node[nid]))

    support_layer: dict[str, float] = {}
    for nid in support_nodes:
        connected_layers: list[int] = []
        for src, tgt, _ in edges:
            if src == nid and tgt in layer_by_node:
                connected_layers.append(layer_by_node[tgt])
            elif tgt == nid and src in layer_by_node:
                connected_layers.append(layer_by_node[src])
        support_layer[nid] = (
            sum(connected_layers) / len(connected_layers)
            if connected_layers
            else max_layer / 2
        )

    support_nodes.sort(key=lambda nid: (support_layer[nid], nid))
    side_counts = {-1: 0, 1: 0}
    for idx, nid in enumerate(support_nodes):
        side = 1 if idx % 2 == 0 else -1
        side_counts[side] += 1
        x = 0.72 * side
        if side_counts[side] > 1:
            x += 0.14 * side * ((side_counts[side] - 1) % 2)
        pos[nid] = (x, y_for_layer(support_layer[nid]))

    return pos


# ---------------------------------------------------------------------------
# Haupt-Funktion: Funktionsgraph-Figure
# ---------------------------------------------------------------------------

def build_funktionsgraph_figure(
    nodes: list[dict],        # [{id, farbe, din, area_m2 (optional)}]
    edges: list[tuple],       # [(src, tgt, weight, kategorie), ...]
    weights: dict[str, float],
    selected_edge: str | None = None,
    selected_node: str | None = None,
    area_lookup: dict[str, float] | None = None,
    layout_mode: str = "layered",
    process_order: list[str] | None = None,
) -> "go.Figure":
    import plotly.graph_objects as go

    node_ids = [n["id"] for n in nodes]
    node_color = {n["id"]: n["farbe"] for n in nodes}

    # Edge list with current weights
    edge_list = [(src, tgt, weights.get(f"{src}__{tgt}", w)) for src, tgt, w, _ in edges]

    if layout_mode == "spring":
        pos = _spring_layout(node_ids, edge_list, seed=42, iterations=150, k=1.2)

        # Normalize positions to [-1, 1] so layout fills the plot area
        all_x = [p[0] for p in pos.values()]
        all_y = [p[1] for p in pos.values()]
        cx = (max(all_x) + min(all_x)) / 2
        cy = (max(all_y) + min(all_y)) / 2
        scale = max(max(all_x) - min(all_x), max(all_y) - min(all_y), 0.001) / 1.6
        pos = {nid: ((p[0] - cx) / scale, (p[1] - cy) / scale) for nid, p in pos.items()}
    else:
        effective_order = list(process_order or [])
        if not effective_order:
            for src, tgt, _, cat in edges:
                if cat in ("Prozess", "Prozess", "process"):
                    effective_order.extend([src, tgt])
        effective_order = [nid for nid in dict.fromkeys(effective_order) if nid in node_ids]
        pos = _layered_layout(node_ids, effective_order, edge_list)

    # Node sizes proportional to briefing area
    base_size = 42
    if area_lookup:
        max_area = max(area_lookup.values()) if area_lookup else 1
        sizes = {
            nid: base_size + 28 * math.sqrt(area_lookup.get(nid, 100) / max(max_area, 1))
            for nid in node_ids
        }
    else:
        sizes = {nid: base_size for nid in node_ids}

    traces: list[go.BaseTraceType] = []

    # ── Kanten ────────────────────────────────────────────────────────────
    for src, tgt, default_w, cat in edges:
        key = f"{src}__{tgt}"
        w = weights.get(key, default_w)
        display_w = abs(w)          # Separation hat negatives Gewicht
        x0, y0 = pos.get(src, (0, 0))
        x1, y1 = pos.get(tgt, (0, 0))
        is_selected = key == selected_edge
        color = EDGE_COLORS.get(cat, "#888")
        dash  = EDGE_DASH.get(cat, "solid")
        lw = 1.0 + display_w * 5.5
        w_label = f"{w:.2f}" if w < 0 else f"{w:.1f}"

        # Edge line
        traces.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(
                color=color if not is_selected else "#FF4400",
                width=lw if not is_selected else lw + 2,
                dash=dash,
            ),
            opacity=0.25 + display_w * 0.65,
            hoverinfo="skip",
            showlegend=False,
        ))

        # Arrowhead (as a scatter marker at tgt)
        dx, dy = x1 - x0, y1 - y0
        d = max(0.001, math.sqrt(dx * dx + dy * dy))
        arrow_x = x1 - (dx / d) * 0.06
        arrow_y = y1 - (dy / d) * 0.06
        traces.append(go.Scatter(
            x=[arrow_x], y=[arrow_y],
            mode="markers",
            marker=dict(
                symbol="arrow",
                size=10 + display_w * 6,
                color=color if not is_selected else "#FF4400",
                angle=math.degrees(math.atan2(-dy, -dx)) + 90,
                line=dict(width=0),
            ),
            hoverinfo="skip",
            showlegend=False,
        ))

        # Weight label at edge midpoint
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        traces.append(go.Scatter(
            x=[mx], y=[my],
            mode="text",
            text=[w_label],
            textfont=dict(size=8, color=color),
            hoverinfo="skip",
            showlegend=False,
            customdata=[[key, cat, src, tgt]],
            name=f"edge_{key}",
        ))

        # Invisible wider hit area on the edge (for hover only)
        hover_src = src.replace("_", " ")
        hover_tgt = tgt.replace("_", " ")
        kind_hint = " (Trennung)" if cat == "Separation" else ""
        traces.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(color="rgba(0,0,0,0)", width=18),
            hovertemplate=(
                f"<b>{hover_src} → {hover_tgt}</b><br>"
                f"Kategorie: {cat}{kind_hint}<br>"
                f"Gewicht: {w_label}<br>"
                f"<i>Klick zum Bearbeiten</i><extra></extra>"
            ),
            showlegend=False,
            hoverinfo="skip" if cat == "Separation" else None,
            customdata=[[key, cat, src, tgt]] * 2 + [None],
            name=f"hit_{key}",
        ))

        # Invisible clickable marker at edge midpoint (für on_select)
        # Größe 26px — unsichtbar aber klickbar; customdata[1]="edge" für Event-Parsing
        traces.append(go.Scatter(
            x=[mx], y=[my],
            mode="markers",
            marker=dict(
                size=26,
                color="rgba(0,0,0,0)",
                line=dict(width=0),
            ),
            hovertemplate=(
                f"<b>{hover_src} → {hover_tgt}</b><br>"
                f"Gewicht: {w_label} · {cat}{kind_hint}<br>"
                f"<i>Klick zum Bearbeiten</i><extra></extra>"
            ),
            showlegend=False,
            customdata=[[key, "edge", src, tgt]],
            name=f"selmark_{key}",
        ))

    # ── Legende: Kantentypen ───────────────────────────────────────────────
    cats_seen = list(dict.fromkeys(cat for _, _, _, cat in edges))
    for cat in cats_seen:
        traces.append(go.Scatter(
            x=[None], y=[None],
            mode="lines",
            line=dict(color=EDGE_COLORS.get(cat, "#888"), width=3),
            name=cat,
            showlegend=True,
            legendgroup=f"cat_{cat}",
        ))

    # ── Knoten ────────────────────────────────────────────────────────────
    # selected_node kann ein einzelner ID-String sein oder "A+B" für zwei gewählte Knoten
    _sel_nodes: set[str] = set()
    if selected_node:
        _sel_nodes = set(selected_node.split("+"))

    annotations: list[dict] = []
    for node in nodes:
        nid = node["id"]
        x, y = pos[nid]
        sz = sizes[nid]
        is_sel = nid in _sel_nodes
        display_name = nid.replace("_", " ")
        is_short = len(display_name) <= 6
        circle_text = display_name if is_short else f"{display_name[:4]}."
        area_val = area_lookup.get(nid, 0) if area_lookup else 0
        hover = (
            f"<b>{display_name}</b><br>"
            f"DIN: {node.get('din', '')}<br>"
            + (f"Fläche: {area_val:.0f} m²<br>" if area_val else "")
            + "<i>Klick zum Verbinden</i>"
        )
        traces.append(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(
                size=sz,
                color=node_color.get(nid, "#CCC"),
                line=dict(
                    width=3 if is_sel else 1.5,
                    color="#FF4400" if is_sel else "white",
                ),
            ),
            text=[circle_text],
            textposition="middle center",
            textfont=dict(size=8, color="white", family="Arial Black"),
            hovertemplate=hover + "<extra></extra>",
            name=nid,
            showlegend=False,
            # customdata[1]="node" — Event-Parsing in streamlit_app.py
            customdata=[[nid, "node", "", ""]],
        ))
        if not is_short:
            annotations.append(dict(
                x=x,
                y=y,
                text=display_name,
                showarrow=False,
                xanchor="center",
                yanchor="top",
                yshift=-(sz / 2 + 8),
                font=dict(size=10, color="#222222"),
                bgcolor="white",
                bordercolor=node_color.get(nid, "#CCC"),
                borderwidth=1,
                borderpad=3,
            ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        paper_bgcolor="#FAFAFA",
        plot_bgcolor="#FAFAFA",
        xaxis=dict(visible=False, range=[-1.1, 1.1]),
        yaxis=dict(visible=False, range=[-1.1, 1.1], scaleanchor="x"),
        margin=dict(l=5, r=120, t=20, b=5),
        legend=dict(
            title="Verbindungstyp",
            x=1.01, y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#DDD",
            borderwidth=1,
            font=dict(size=10),
        ),
        autosize=True,
        height=600,
        hovermode="closest",
        dragmode="pan",
        annotations=annotations,
    )
    return fig


# ---------------------------------------------------------------------------
# Erschließungsgraph (statisch, nicht editierbar)
# ---------------------------------------------------------------------------

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
    bx, by, bw, bd = 0.0, 0.0, 0.0, 0.0
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
    ap_colors = ["#C0392B", "#27AE60", "#2980B9"]
    ap_labels = ["LKW-Zufahrt", "PKW-Zufahrt", "Zufahrt"]
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
            showlegend=False,
            hoverinfo="skip",
        ))

        # Route durch Grundstück (gestrichelt)
        mid_x, mid_y = site_w / 2, site_d / 2
        dash = route_dashes[min(i, 2)]
        if i == 0:  # LKW: Zufahrt → Gebäude-WE-Seite → Gebäude-Versand-Seite → Ausfahrt
            route_x = [pt[0], pt[0], mid_x, mid_x]
            route_y = [
                pt[1],
                by + bd * 0.2 if env.get("width_m") else site_d * 0.3,
                by + bd * 0.8 if env.get("width_m") else site_d * 0.7,
                pt[1] + site_d * 0.6,
            ]
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

"""
AID Demo – Sprint Q: Prozessplanung-Visualisierung
===================================================
Zwei Ausgaben:
  1. draw_machine_layout()   → Matplotlib-Figure (2D-Grundriss der Produktionszone)
  2. build_sankey_figure()   → Plotly-Figure (Materialfluss-Sankey)
"""
from __future__ import annotations

import math
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import plotly.graph_objects as go


# ---------------------------------------------------------------------------
# Farbpalette (DIN-konsistent mit drawing.py)
# ---------------------------------------------------------------------------

_KATEGORIE_FARBEN = {
    "Bearbeitung": "#2E86AB",
    "Montage":     "#C73E1D",
    "Prüfung":     "#3B1F2B",
    "Lager":       "#8B9E6F",
    "Transport":   "#F18F01",
}

_SCHRITT_FARBEN = [
    "#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#3B1F2B",
    "#6A994E", "#386FA4", "#8B5CF6", "#E63946", "#2A9D8F",
]


# ---------------------------------------------------------------------------
# 1. Maschinenlayout (Matplotlib)
# ---------------------------------------------------------------------------

def draw_machine_layout(
    process_layout: dict[str, Any],
    figsize: tuple[float, float] = (14, 10),
) -> plt.Figure:
    """Zeichnet das 2D-Maschinenlayout in eine Matplotlib-Figure.

    process_layout: dict aus process_layout_agent():
      {"zone_name", "zone_breite_m", "zone_tiefe_m", "maschinen", "strips", "kpis", "maschinenpark"}
    """
    zone_b = float(process_layout.get("zone_breite_m") or 40.0)
    zone_t = float(process_layout.get("zone_tiefe_m")  or 75.0)
    zone_name = process_layout.get("zone_name", "Produktion")
    maschinen = process_layout.get("maschinen") or []
    strips    = process_layout.get("strips")    or []
    kpis      = process_layout.get("kpis")      or {}

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_aspect("equal")

    # --- Zonenhintergrund ---
    ax.add_patch(mpatches.Rectangle(
        (0, 0), zone_b, zone_t,
        linewidth=2, edgecolor="#1A1A2E", facecolor="#F7F7F7", zorder=0
    ))

    # --- Strip-Hintergrundstreifen (alternierende Grautöne) ---
    for i, strip in enumerate(strips):
        bg = "#EDEDF0" if i % 2 == 0 else "#E2E2E8"
        ax.add_patch(mpatches.Rectangle(
            (0, strip["y_start"]), zone_b, strip["hoehe_m"],
            linewidth=0, facecolor=bg, zorder=1, alpha=0.6
        ))
        # Schritt-Label am linken Rand
        ax.text(
            0.3, (strip["y_start"] + strip["y_end"]) / 2,
            f"Schritt {strip['schritt']}",
            fontsize=7, color="#666666", va="center", ha="left",
            rotation=90, zorder=6,
        )

    # --- Maschinenboxen ---
    schritte_alle = sorted({m["schritt"] for m in maschinen})
    schritt_farbe = {s: _SCHRITT_FARBEN[i % len(_SCHRITT_FARBEN)] for i, s in enumerate(schritte_alle)}

    engpass_schritt = kpis.get("engpass_schritt")

    for m in maschinen:
        farbe = m.get("farbe") or schritt_farbe.get(m["schritt"], "#888888")
        is_engpass = (m["schritt"] == engpass_schritt)

        # Maschinenrechteck
        rect = mpatches.Rectangle(
            (m["x"], m["y"]), m["breite_m"], m["tiefe_m"],
            linewidth=2.5 if is_engpass else 1.5,
            edgecolor="#CC0000" if is_engpass else "#1A1A2E",
            facecolor=farbe,
            alpha=0.82, zorder=3,
        )
        ax.add_patch(rect)

        # Engpass-Markierung (rotes Dreieck)
        if is_engpass:
            ax.text(
                m["x"] + m["breite_m"] - 0.3,
                m["y"] + m["tiefe_m"] - 0.3,
                "⚠",
                fontsize=9, color="#CC0000",
                ha="right", va="top", zorder=7,
            )

        # Maschinen-Label (Name + Takt)
        cx = m["x"] + m["breite_m"] / 2
        cy = m["y"] + m["tiefe_m"] / 2
        label = m["name"]
        if m.get("instance_idx", 0) > 0:
            label += f" #{m['instance_idx'] + 1}"
        ax.text(cx, cy + 0.2, label, fontsize=6.5, color="white",
                ha="center", va="center", fontweight="bold", zorder=5,
                bbox={"boxstyle": "round,pad=0.1", "fc": "none", "ec": "none"})
        takt = m.get("taktzeit_s", 0)
        ax.text(cx, cy - 0.45, f"{takt}s/Teil",
                fontsize=5.5, color="#EEEEEE", ha="center", va="center", zorder=5)

    # --- Materialfluss-Pfeile (Schwerpunkt → Schwerpunkt) ---
    schwerpunkte = kpis.get("schwerpunkte") or {}
    for i in range(len(schritte_alle) - 1):
        s1, s2 = str(schritte_alle[i]), str(schritte_alle[i + 1])
        if s1 in schwerpunkte and s2 in schwerpunkte:
            x1, y1 = schwerpunkte[s1]
            x2, y2 = schwerpunkte[s2]
            ax.annotate(
                "", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(
                    arrowstyle="->, head_width=0.4, head_length=0.3",
                    color="#005A8E", lw=2.0, connectionstyle="arc3,rad=0.08",
                ),
                zorder=8,
            )

    # --- Gang-Linien (horizontale gestrichelte Trennlinien) ---
    for strip in strips:
        ax.axhline(strip["y_start"], color="#AAAAAA", linewidth=0.5, linestyle="--", zorder=2, alpha=0.7)
        ax.axhline(strip["y_end"],   color="#AAAAAA", linewidth=0.5, linestyle="--", zorder=2, alpha=0.7)

    # --- KPI-Box oben rechts ---
    kpi_lines = [
        f"Durchsatz: {kpis.get('durchsatz_teile_pro_schicht', '—')} T/Schicht",
        f"Engpass: Schritt {kpis.get('engpass_schritt', '—')}",
        f"Materialflussweg: {kpis.get('materialflussweg_m', 0):.1f} m",
    ]
    kpi_text = "\n".join(kpi_lines)
    ax.text(
        zone_b - 0.5, zone_t - 0.5, kpi_text,
        fontsize=7.5, color="#1A1A2E", ha="right", va="top", zorder=10,
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#CCCCCC", alpha=0.9),
    )

    # --- Legende: Auslastung je Schritt ---
    auslastung = kpis.get("auslastung_je_schritt") or {}
    legend_handles = []
    for s in schritte_alle:
        farbe = schritt_farbe[s]
        last  = auslastung.get(str(s), 0)
        label = f"Schritt {s} — {last:.0f}% Auslastung"
        legend_handles.append(mpatches.Patch(color=farbe, label=label))
    if legend_handles:
        ax.legend(
            handles=legend_handles, loc="lower right",
            fontsize=6.5, framealpha=0.9,
            ncol=2 if len(legend_handles) > 4 else 1,
        )

    # --- Achsen & Titel ---
    ax.set_xlim(-0.5, zone_b + 0.5)
    ax.set_ylim(-0.5, zone_t + 1.0)
    ax.set_xlabel("Breite [m]", fontsize=8)
    ax.set_ylabel("Tiefe [m] (Materialflussrichtung ↑)", fontsize=8)
    ax.set_title(
        f"Maschinenlayout — {zone_name}\n"
        f"Strip-Packing | {len(maschinen)} Instanzen | ⚠ = Engpass",
        fontsize=10, fontweight="bold",
    )
    ax.tick_params(labelsize=7)
    ax.grid(visible=True, alpha=0.3, linewidth=0.5)

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 2. Materialfluss-Sankey (Plotly)
# ---------------------------------------------------------------------------

def build_sankey_figure(process_layout: dict[str, Any]) -> go.Figure:
    """Erstellt ein Plotly-Sankey-Diagramm des Materialflusses.

    Nodes = Prozessschritte, Links = Materialfluss (Einheit: Teile/Schicht).
    """
    kpis = process_layout.get("kpis") or {}
    nodes_raw = kpis.get("sankey_nodes") or []
    links_raw = kpis.get("sankey_links") or []
    park      = process_layout.get("maschinenpark") or []

    if not nodes_raw or not links_raw:
        fig = go.Figure()
        fig.add_annotation(text="Keine Sankey-Daten", x=0.5, y=0.5, showarrow=False)
        return fig

    # Schritt-Farben aus Maschinenpark
    schritte_sorted = sorted({m["schritt"] for m in park})
    schritt_farben = {s: _SCHRITT_FARBEN[i % len(_SCHRITT_FARBEN)] for i, s in enumerate(schritte_sorted)}

    node_colors = []
    node_labels = []
    for n in nodes_raw:
        s = n.get("schritt", 0)
        node_colors.append(schritt_farben.get(s, "#888888"))
        node_labels.append(n.get("label", f"Schritt {s}"))

    link_colors = []
    link_sources = []
    link_targets = []
    link_values  = []
    link_labels  = []

    auslastung = kpis.get("auslastung_je_schritt") or {}
    for lk in links_raw:
        src = lk["source"]
        tgt = lk["target"]
        val = lk["value"]
        link_sources.append(src)
        link_targets.append(tgt)
        link_values.append(val)

        src_schritt = nodes_raw[src].get("schritt", 0) if src < len(nodes_raw) else 0
        base_color = schritt_farben.get(src_schritt, "#888888")
        r = int(base_color[1:3], 16)
        g = int(base_color[3:5], 16)
        b = int(base_color[5:7], 16)
        link_colors.append(f"rgba({r},{g},{b},0.40)")
        link_labels.append(f"{val} T/Schicht")

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20, thickness=18,
            line=dict(color="#1A1A2E", width=0.5),
            label=node_labels,
            color=node_colors,
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Eingang: %{value} T/Schicht<extra></extra>"
            ),
        ),
        link=dict(
            source=link_sources,
            target=link_targets,
            value=link_values,
            color=link_colors,
            label=link_labels,
            hovertemplate=(
                "%{label}<br>"
                "%{source.label} → %{target.label}<extra></extra>"
            ),
        ),
    ))

    engpass = kpis.get("engpass_schritt", "—")
    durchsatz = kpis.get("durchsatz_teile_pro_schicht", "—")

    fig.update_layout(
        title=dict(
            text=f"Materialfluss-Sankey  |  Durchsatz: {durchsatz} T/Schicht  |  Engpass: Schritt {engpass}",
            font=dict(size=13),
        ),
        font=dict(size=11, family="Inter, Arial, sans-serif"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=380,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    return fig


# ---------------------------------------------------------------------------
# 3. Auslastungs-Balkendiagramm (Matplotlib, kompakt)
# ---------------------------------------------------------------------------

def draw_auslastung_chart(
    process_layout: dict[str, Any],
    figsize: tuple[float, float] = (8, 3),
) -> plt.Figure:
    """Horizontaler Balken: Auslastung je Prozessschritt."""
    kpis = process_layout.get("kpis") or {}
    auslastung = kpis.get("auslastung_je_schritt") or {}
    park       = process_layout.get("maschinenpark") or []

    if not auslastung:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "Keine KPIs", ha="center", va="center")
        return fig

    schritte = sorted(int(k) for k in auslastung.keys())
    schritt_namen = {}
    for m in park:
        s = m["schritt"]
        if s not in schritt_namen:
            schritt_namen[s] = f"Schritt {s}"

    labels = [schritt_namen.get(s, f"S{s}") for s in schritte]
    values = [auslastung[str(s)] for s in schritte]
    farben = [_SCHRITT_FARBEN[i % len(_SCHRITT_FARBEN)] for i in range(len(schritte))]
    engpass = kpis.get("engpass_schritt")

    fig, ax = plt.subplots(figsize=figsize)
    bars = ax.barh(labels, values, color=farben, edgecolor="#1A1A2E", linewidth=0.8, height=0.6)

    # Engpass-Markierung
    for i, s in enumerate(schritte):
        if s == engpass:
            bars[i].set_edgecolor("#CC0000")
            bars[i].set_linewidth(2.5)
            ax.text(values[i] + 0.5, i, " ⚠ Engpass", va="center", fontsize=7.5, color="#CC0000")
        else:
            ax.text(values[i] + 0.5, i, f"{values[i]:.0f}%", va="center", fontsize=7.5, color="#444444")

    ax.set_xlim(0, 120)
    ax.axvline(100, color="#CC0000", linewidth=1.2, linestyle="--", alpha=0.6, label="100% Kapazität")
    ax.set_xlabel("Auslastung [%]", fontsize=8)
    ax.set_title("Auslastung je Prozessschritt", fontsize=9, fontweight="bold")
    ax.tick_params(labelsize=7.5)
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    return fig

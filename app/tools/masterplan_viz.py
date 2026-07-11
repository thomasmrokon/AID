"""
AID Demo – Sprint R: Masterplan-Visualisierung
===============================================
draw_masterplan()  → Matplotlib-Figure (Lageplan, Maßstab 1:500)
"""
from __future__ import annotations

import math
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.collections import PatchCollection
from matplotlib.lines import Line2D


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _rect(ax, x, y, w, h, color, alpha=0.85, edgecolor="#1A1A2E", lw=1.0, zorder=3, **kw):
    ax.add_patch(mpatches.Rectangle(
        (x, y), w, h,
        linewidth=lw, edgecolor=edgecolor, facecolor=color,
        alpha=alpha, zorder=zorder, **kw
    ))


def _label(ax, x, y, w, h, text, fontsize=7.5, color="white", zorder=6, **kw):
    cx = x + w / 2
    cy = y + h / 2
    # Zeilenumbruch bei langen Labels
    if len(text) > 18 and " " in text:
        words = text.split()
        mid   = len(words) // 2
        text  = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
    ax.text(cx, cy, text, fontsize=fontsize, color=color, ha="center", va="center",
            zorder=zorder, fontweight="bold", **kw)


def _hatch_rect(ax, x, y, w, h, color, hatch="///", alpha=0.4, zorder=2, lw=0.8):
    ax.add_patch(mpatches.Rectangle(
        (x, y), w, h,
        linewidth=lw, edgecolor=color, facecolor=color,
        alpha=alpha, zorder=zorder, hatch=hatch,
    ))


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def draw_masterplan(
    masterplan: dict[str, Any],
    figsize: tuple[float, float] = (14, 10),
    show_dimensions: bool = True,
) -> plt.Figure:
    """Zeichnet den Masterplan (Lageplan 1:500) als Matplotlib-Figure."""
    site        = masterplan.get("site") or {}
    hg          = masterplan.get("hauptgebaeude") or {}
    gebaeude    = masterplan.get("gebaeude") or ([hg] if hg else [])
    nebenbauten = masterplan.get("nebenbauten") or []
    erschl      = masterplan.get("erschliessung") or {}
    freizonen   = masterplan.get("freizonen") or []
    bilanz      = masterplan.get("flaechenbilanz") or {}
    config      = masterplan.get("config") or {}
    infrastruktur = masterplan.get("infrastruktur") or {}

    site_w = float(site.get("width_m") or 100)
    site_d = float(site.get("depth_m") or 100)
    polygon = site.get("polygon") or [[0, 0], [site_w, 0], [site_w, site_d], [0, site_d]]

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_aspect("equal")

    # ── Hintergrund: Grundstück ─────────────────────────────────────────────
    poly_pts = [(float(p[0]), float(p[1])) for p in polygon]
    site_patch = MplPolygon(poly_pts, closed=True,
                            facecolor="#E8E8E0", edgecolor="#333333",
                            linewidth=2.5, zorder=0)
    ax.add_patch(site_patch)

    # ── Rangierzone / LKW-Erschließung ─────────────────────────────────────
    rz = erschl.get("rangierzone") or {}
    if rz:
        _hatch_rect(ax,
                    rz["x"], rz["y"], rz["breite_m"], rz["tiefe_m"],
                    color="#D4A96A", hatch="...", alpha=0.45, zorder=1)
        _label(ax, rz["x"], rz["y"], rz["breite_m"], rz["tiefe_m"],
               "Rangierzone\n(LKW)", fontsize=7, color="#7A4F1E", zorder=4)

    # LKW-Schleifenlinie
    schleife_pts = erschl.get("lkw_schleife_punkte") or []
    if len(schleife_pts) >= 3:
        xs = [p[0] for p in schleife_pts]
        ys = [p[1] for p in schleife_pts]
        ax.plot(xs, ys, color="#CC7722", linewidth=2.5,
                linestyle="-", zorder=5, alpha=0.85, label="LKW-Schleife")

    # ── Freizonen: Grünfläche + Stellplätze ─────────────────────────────────
    for fz in freizonen:
        if fz["typ"] == "gruen":
            _rect(ax, fz["x"], fz["y"], fz["breite_m"], fz["tiefe_m"],
                  color="#A8D5A2", alpha=0.70, edgecolor="#5A9E54", lw=0.8, zorder=1)
            if fz["breite_m"] > 8 and fz["tiefe_m"] > 6:
                _label(ax, fz["x"], fz["y"], fz["breite_m"], fz["tiefe_m"],
                       fz["name"], fontsize=6.5, color="#2D6A27", zorder=4)
        elif fz["typ"] == "stellplatz":
            _rect(ax, fz["x"], fz["y"], fz["breite_m"], fz["tiefe_m"],
                  color="#F5F0DC", alpha=0.85, edgecolor="#CCBB80", lw=0.8, zorder=1)
            _draw_stellplatz_raster(ax, fz["x"], fz["y"], fz["breite_m"], fz["tiefe_m"])
            if fz["breite_m"] > 10:
                _label(ax, fz["x"], fz["y"], fz["breite_m"], fz["tiefe_m"],
                       fz["name"], fontsize=6.5, color="#666633", zorder=4)


    # ── Infrastrukturtrassen ────────────────────────────────────────────────
    for idx, trasse in enumerate(infrastruktur.get("trassen") or []):
        pts = trasse.get("punkte") or []
        if len(pts) < 2:
            continue
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        ax.plot(xs, ys, color="#7B61FF", linewidth=1.6, linestyle="--",
                alpha=0.72, zorder=2.5)
        if idx < 3:
            ax.text(xs[-1], ys[-1], str(trasse.get("medium", "Trasse")),
                    fontsize=6.2, color="#4B3DB8", ha="left", va="bottom", zorder=7)

    # ── Gebäude ─────────────────────────────────────────────────────────────
    for idx, geb in enumerate(gebaeude):
        color = geb.get("farbe") or ("#1A3A5C" if idx == 0 else "#335C67")
        _rect(ax, geb["x"], geb["y"], geb["breite_m"], geb["tiefe_m"],
              color=color, alpha=0.90, edgecolor="#0A1A2C", lw=2.5, zorder=3)
        label = str(geb.get("name") or "Gebäude").replace("Hauptgebäude", "Produktion")
        _label(ax, geb["x"], geb["y"], geb["breite_m"], geb["tiefe_m"],
               f"{label}\n{geb['flaeche_m2']:.0f} m²",
               fontsize=8.2 if idx else 9, color="white", zorder=6)

    if hg and show_dimensions:
        # Bemaßung am Hauptgebäude
        bx, by = hg["x"], hg["y"]
        bw, bd = hg["breite_m"], hg["tiefe_m"]
        y_dim = by - 3.5
        ax.annotate("", xy=(bx + bw, y_dim), xytext=(bx, y_dim),
                    arrowprops=dict(arrowstyle="<->", color="#444", lw=1.2))
        ax.text(bx + bw / 2, y_dim - 1.5, f"{bw:.0f} m",
                ha="center", va="top", fontsize=7.5, color="#444")
        x_dim = bx + bw + 3.0
        ax.annotate("", xy=(x_dim, by + bd), xytext=(x_dim, by),
                    arrowprops=dict(arrowstyle="<->", color="#444", lw=1.2))
        ax.text(x_dim + 1.5, by + bd / 2, f"{bd:.0f} m",
                ha="left", va="center", fontsize=7.5, color="#444", rotation=90)

    # ── Nebenbauten ─────────────────────────────────────────────────────────
    for nb in nebenbauten:
        _rect(ax, nb["x"], nb["y"], nb["breite_m"], nb["tiefe_m"],
              color=nb["farbe"], alpha=0.85, edgecolor="#1A1A2E", lw=1.5, zorder=4)
        _label(ax, nb["x"], nb["y"], nb["breite_m"], nb["tiefe_m"],
               nb["name"], fontsize=6, color="white", zorder=6)

    # ── Zufahrtspfeile ───────────────────────────────────────────────────────
    access_pts = site.get("access_points") or []
    for ap in access_pts:
        side = ap.get("side", "south")
        px, py = float(ap["point"][0]), float(ap["point"][1])
        aw = float(ap.get("width_m", 6.0))
        arrow_len = 6.0
        if side == "south":
            ax.annotate("", xy=(px, py + arrow_len), xytext=(px, py - 0.5),
                        arrowprops=dict(arrowstyle="->, head_width=1.2, head_length=1.0",
                                        color="#CC0000", lw=2.0), zorder=8)
        elif side == "north":
            ax.annotate("", xy=(px, py - arrow_len), xytext=(px, py + 0.5),
                        arrowprops=dict(arrowstyle="->, head_width=1.2, head_length=1.0",
                                        color="#CC0000", lw=2.0), zorder=8)
        elif side == "west":
            ax.annotate("", xy=(px + arrow_len, py), xytext=(px - 0.5, py),
                        arrowprops=dict(arrowstyle="->, head_width=1.2, head_length=1.0",
                                        color="#CC0000", lw=2.0), zorder=8)
        elif side == "east":
            ax.annotate("", xy=(px - arrow_len, py), xytext=(px + 0.5, py),
                        arrowprops=dict(arrowstyle="->, head_width=1.2, head_length=1.0",
                                        color="#CC0000", lw=2.0), zorder=8)
        ax.text(px, py, f" Z{ap.get('id','')}\n{aw:.0f}m",
                fontsize=6.5, color="#CC0000", va="center", zorder=9, fontweight="bold")

    # ── Nordpfeil ────────────────────────────────────────────────────────────
    _draw_north_arrow(ax, x=site_w + 3, y=site_d - 10, size=5)
    _draw_scale_bar(ax, x=site_w - 25, y=-9, laenge_m=20.0)

    # ── Legende ─────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(color="#1A3A5C", alpha=0.90, label="Produktion"),
        mpatches.Patch(color="#335C67", alpha=0.90, label="Weitere Gebäude"),
        mpatches.Patch(color="#4A90D9", alpha=0.85, label="Pforte / Nebenbauten"),
        mpatches.Patch(color="#E67E22", alpha=0.85, label="Trafostation"),
        mpatches.Patch(color="#D4A96A", alpha=0.65, label="Rangierzone LKW"),
        mpatches.Patch(color="#F5F0DC", alpha=0.85, label="Stellplätze PKW"),
        mpatches.Patch(color="#A8D5A2", alpha=0.70, label="Grünfläche"),
        Line2D([0], [0], color="#CC7722", linewidth=2.5, label="LKW-Schleife"),
        Line2D([0], [0], color="#7B61FF", linewidth=1.6, linestyle="--", label="Infrastrukturtrassen"),
        Line2D([0], [0], color="#CC0000", linewidth=2.0,
               marker=">", markersize=7, label="Zufahrt"),
    ]
    ax.legend(handles=legend_items, loc="lower left",
              fontsize=7, framealpha=0.92, ncol=2)

    # ── Flächenbilanz-Box ────────────────────────────────────────────────────
    grz  = bilanz.get("grz", 0)
    gfz  = bilanz.get("gfz", 0)
    vs   = bilanz.get("versiegelungsgrad", 0)
    sp   = bilanz.get("stellplaetze_anzahl", 0)
    grz_lim = bilanz.get("grz_grenzwert", 0.60)
    grz_ok = "✓" if grz <= grz_lim else "⚠"

    bilanz_text = (
        f"Flächenbilanz\n"
        f"GRZ {grz:.2f} / {grz_lim:.2f} {grz_ok}\n"
        f"GFZ {gfz:.2f}\n"
        f"Versieg. {vs:.0%}\n"
        f"Stellplätze {sp} SP"
    )
    ax.text(site_w + 2, 2, bilanz_text,
            fontsize=8.5, color="#1A1A2E", va="bottom", ha="left", zorder=10,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#CCCCCC", alpha=0.95))

    # ── Achsen ──────────────────────────────────────────────────────────────
    pad = 12
    ax.set_xlim(-pad, site_w + 20)
    ax.set_ylim(-pad, site_d + pad)
    ax.set_xlabel("Breite [m]", fontsize=8)
    ax.set_ylabel("Tiefe [m]", fontsize=8)
    variant_label = masterplan.get("label") or masterplan.get("selected_masterplan_variant_id") or ""
    title_prefix = f"Masterplan {variant_label}" if variant_label else "Masterplan"
    ax.set_title(
        f"{title_prefix} — {site.get('name', site.get('id', 'Grundstück'))} "
        f"| {site.get('area_m2', 0):.0f} m² Grundstücksfläche "
        f"| GRZ {grz:.2f}",
        fontsize=11, fontweight="bold",
    )
    ax.tick_params(labelsize=7.5)
    ax.grid(visible=True, alpha=0.25, linewidth=0.5)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Stellplatz-Raster zeichnen
# ---------------------------------------------------------------------------

def _draw_stellplatz_raster(ax, x: float, y: float, w: float, h: float) -> None:
    """Zeichnet ein gestricheltes Stellplatz-Raster (2.5m × 5m) in das Rechteck."""
    SP_B = 2.5
    SP_T = 5.0
    GAP  = 0.5  # Fahrgang-Lücke
    cx = x
    while cx + SP_B <= x + w:
        ax.plot([cx, cx], [y, y + min(SP_T, h)],
                color="#BBAA66", linewidth=0.5, linestyle="--", zorder=2, alpha=0.6)
        cx += SP_B
    # Horizontale Abtrennung Fahrgang/Parkreihe
    row_h = SP_T + GAP
    cy = y
    while cy + row_h <= y + h:
        ax.axhline(cy + SP_T, xmin=(x / ax.get_xlim()[1]),
                   color="#BBAA66", linewidth=0.5, linestyle="--", zorder=2, alpha=0.5)
        cy += row_h


# ---------------------------------------------------------------------------
# Nordpfeil
# ---------------------------------------------------------------------------

def _draw_north_arrow(ax, x: float, y: float, size: float = 6) -> None:
    """Zeichnet einen einfachen Nordpfeil."""
    ax.annotate("", xy=(x, y + size), xytext=(x, y),
                arrowprops=dict(arrowstyle="->, head_width=1.0, head_length=0.8",
                                color="#1A1A2E", lw=1.5), zorder=10)
    ax.text(x, y + size + 0.8, "N", ha="center", va="bottom",
            fontsize=9, fontweight="bold", color="#1A1A2E", zorder=10)


def _draw_scale_bar(ax, x: float, y: float, laenge_m: float = 20.0) -> None:
    """Zeichnet eine Massstabsleiste bei (x, y) mit der angegebenen Laenge."""
    height = 1.0
    row_h = height / 2
    segment = laenge_m / 2
    colors = ("#111111", "#FFFFFF")

    for idx in range(2):
        sx = x + idx * segment
        top_color = colors[idx % 2]
        bottom_color = colors[(idx + 1) % 2]
        ax.add_patch(mpatches.Rectangle(
            (sx, y + row_h), segment, row_h,
            facecolor=top_color, edgecolor="#111111", linewidth=0.8,
            zorder=11,
        ))
        ax.add_patch(mpatches.Rectangle(
            (sx, y), segment, row_h,
            facecolor=bottom_color, edgecolor="#111111", linewidth=0.8,
            zorder=11,
        ))

    ax.plot([x, x + laenge_m], [y, y], color="#111111", linewidth=3.0, zorder=12)
    for tick_x in (x, x + segment, x + laenge_m):
        ax.plot([tick_x, tick_x], [y, y + height], color="#111111", linewidth=1.0, zorder=12)

    label_y = y - 0.8
    ax.text(x, label_y, "0 m", ha="center", va="top", fontsize=7, color="#111111", zorder=12)
    ax.text(x + segment, label_y, "10 m", ha="center", va="top", fontsize=7, color="#111111", zorder=12)
    ax.text(x + laenge_m, label_y, "20 m", ha="center", va="top", fontsize=7, color="#111111", zorder=12)

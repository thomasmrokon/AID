"""
AID Demo – Plotly 3D-Viewer
Erzeugt eine interaktive 3D-Darstellung aus Zone-Objekten.
Layer via Plotly-Legende ein-/ausblendbar.
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import TYPE_CHECKING

from app.tools.geometry import zone_height

if TYPE_CHECKING:
    from app.tools.geometry import Zone

# ---------------------------------------------------------------------------
# Höhen je DIN-Kategorie
# ---------------------------------------------------------------------------

_DIN_LABEL: dict[str, str] = {
    "NUF 3": "Produktion",
    "NUF 4": "Lager / Logistik",
    "NUF 2": "Büro / Verwaltung",
    "NUF 7": "Sozial",
    "TF":    "Technik",
    "VF":    "Erschließung",
}

TRAGWERK_RULES_PATH = Path(__file__).parent.parent / "data" / "rules_tragwerk.yaml"


def _zone_height(
    zone: "Zone",
    tragwerk_config: dict | None = None,
    nutzungstyp: str = "Produktion",
) -> float:
    return zone_height(zone, tragwerk_config, nutzungstyp)


def _hex_to_rgba(hex_color: str, alpha: float = 0.75) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _box_mesh(
    x0: float, y0: float, z0: float,
    x1: float, y1: float, z1: float,
) -> tuple[list, list, list, list, list, list]:
    """8-vertex box as 12 triangles. Returns (xs, ys, zs, i, j, k)."""
    xs = [x0, x1, x1, x0, x0, x1, x1, x0]
    ys = [y0, y0, y1, y1, y0, y0, y1, y1]
    zs = [z0, z0, z0, z0, z1, z1, z1, z1]
    # 12 triangles (2 per face)
    i = [0, 0,  4, 4,  0, 0,  3, 3,  0, 0,  1, 1]
    j = [1, 2,  5, 6,  1, 5,  2, 6,  4, 7,  2, 6]
    k = [2, 3,  6, 7,  5, 4,  6, 7,  7, 3,  6, 5]
    return xs, ys, zs, i, j, k


def _path_to_xyz(pfad_punkte, z: float = 0.05) -> tuple[list, list, list]:
    """Convert 2D path waypoints to Plotly line coordinates."""
    if not pfad_punkte:
        return [], [], []

    xs = [float(p[0]) for p in pfad_punkte]
    ys = [float(p[1]) for p in pfad_punkte]
    zs = [z] * len(pfad_punkte)
    return xs + [None], ys + [None], zs + [None]


def _load_traufhoehe(tragwerk_config: dict | None) -> float:
    if not tragwerk_config:
        return 8.0

    typologie = str(tragwerk_config.get("typologie") or "stahl")
    try:
        import yaml

        with open(TRAGWERK_RULES_PATH, encoding="utf-8") as f:
            rules = yaml.safe_load(f) or {}
        return float(
            rules.get("typologien", {})
            .get(typologie, {})
            .get("traufhoehe_standard_m", 8.0)
        )
    except Exception:
        return 8.0


def _building_envelope_bounds(
    site_geometry: dict | None,
    building_zones: list["Zone"],
) -> tuple[float, float, float, float] | None:
    envelope = None
    if site_geometry:
        if {"x", "y", "width_m", "depth_m"}.issubset(site_geometry):
            envelope = site_geometry
        elif isinstance(site_geometry.get("building_envelope"), dict):
            envelope = site_geometry["building_envelope"]

    if envelope:
        bx0 = float(envelope.get("x", 0.0))
        by0 = float(envelope.get("y", 0.0))
        return (
            bx0,
            by0,
            bx0 + float(envelope.get("width_m", 0.0)),
            by0 + float(envelope.get("depth_m", 0.0)),
        )

    if not building_zones:
        return None

    return (
        min(z.x for z in building_zones),
        min(z.y for z in building_zones),
        max(z.x + z.breite for z in building_zones),
        max(z.y + z.tiefe for z in building_zones),
    )


# ---------------------------------------------------------------------------
# Haupt-Funktion
# ---------------------------------------------------------------------------

def build_3d_figure(
    zonen: list["Zone"],
    site_geometry: dict | None,
    raster_x: float,
    raster_y: float,
    tragwerk_config: dict | None = None,
    variante_name: str = "",
    mep_variant_data: dict | None = None,
    erschliessungsgraph: dict | None = None,
) -> "go.Figure":
    import plotly.graph_objects as go

    traces: list[go.BaseTraceType] = []
    non_hatch = [z for z in zonen if not z.schraffur]

    # ── Layer 1: Grundstück (Polygon am Boden) ────────────────────────────
    if site_geometry and "polygon" in site_geometry:
        poly = site_geometry["polygon"]
        xs = [p[0] for p in poly] + [poly[0][0]]
        ys = [p[1] for p in poly] + [poly[0][1]]
        zs = [0.0] * len(xs)
        traces.append(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="lines",
            line=dict(color="#204B64", width=3),
            name="Grundstück",
            legendgroup="Grundstück",
            showlegend=True,
            hoverinfo="name",
        ))
    else:
        # Fallback: Bounding-Box des Gebäudes als Grundstück
        if non_hatch:
            sx0 = min(z.x for z in non_hatch)
            sy0 = min(z.y for z in non_hatch)
            sx1 = max(z.x + z.breite for z in non_hatch)
            sy1 = max(z.y + z.tiefe for z in non_hatch)
            traces.append(go.Scatter3d(
                x=[sx0, sx1, sx1, sx0, sx0],
                y=[sy0, sy0, sy1, sy1, sy0],
                z=[0, 0, 0, 0, 0],
                mode="lines",
                line=dict(color="#204B64", width=3),
                name="Grundstück",
                legendgroup="Grundstück",
                showlegend=True,
                hoverinfo="name",
            ))

    # ── Layer 2: Zonen als farbige 3D-Boxen ──────────────────────────────
    legend_added: set[str] = set()
    # VF-Zonen separat als transparente Bodenplatten (Korridor-Darstellung)
    vf_zones_all = [z for z in non_hatch if z.din_kategorie == "VF"]
    struct_zones  = [z for z in non_hatch if z.din_kategorie != "VF"]

    for zone in struct_zones:
        h = _zone_height(zone, tragwerk_config, variante_name)
        if h < 0.1:
            h = 0.5  # Minimum-Sichtbarkeit für flache Zonen
        xs, ys, zs, ii, jj, kk = _box_mesh(
            zone.x, zone.y, 0.0,
            zone.x + zone.breite, zone.y + zone.tiefe, h,
        )
        group_label = _DIN_LABEL.get(zone.din_kategorie, zone.din_kategorie)
        show_in_legend = group_label not in legend_added
        if show_in_legend:
            legend_added.add(group_label)

        planned = zone.planned_area_m2 or zone.gezeichnete_flaeche
        hover = (
            f"<b>{zone.name}</b><br>"
            f"Fläche: {planned:.0f} m²<br>"
            f"DIN: {zone.din_kategorie}<br>"
            f"Geschosse: {zone.floors}<br>"
            f"Höhe: {h:.1f} m"
        )
        traces.append(go.Mesh3d(
            x=xs, y=ys, z=zs,
            i=ii, j=jj, k=kk,
            color=zone.farbe,
            opacity=0.80,
            flatshading=True,
            name=group_label,
            legendgroup=group_label,
            showlegend=show_in_legend,
            hovertemplate=hover + "<extra></extra>",
            lighting=dict(ambient=0.7, diffuse=0.5, roughness=0.5),
        ))

    # VF-Zonen: transparente Korridor-Bodenplatten (kein Box-Volumen)
    _vf_legend_shown = False
    for vf in vf_zones_all:
        xs, ys, zs, ii, jj, kk = _box_mesh(
            vf.x, vf.y, 0.0,
            vf.x + vf.breite, vf.y + vf.tiefe, 0.08,
        )
        planned = vf.planned_area_m2 or vf.gezeichnete_flaeche
        traces.append(go.Mesh3d(
            x=xs, y=ys, z=zs,
            i=ii, j=jj, k=kk,
            color=vf.farbe if vf.farbe and vf.farbe != "#FFFFFF" else "#D4C89A",
            opacity=0.25,
            flatshading=True,
            name="Erschließung",
            legendgroup="Erschließung",
            showlegend=not _vf_legend_shown,
            hovertemplate=(
                f"<b>{vf.name}</b><br>"
                f"Erschließungszone · {planned:.0f} m²<extra></extra>"
            ),
        ))
        _vf_legend_shown = True

    # ── Layer 3: Tragwerk-Skelett (Stützen + Ringbalken) ─────────────────
    building_zones = [z for z in non_hatch if z.din_kategorie != "VF"]
    bounds = _building_envelope_bounds(site_geometry, building_zones)
    if building_zones and bounds and raster_x > 0 and raster_y > 0:
        bx0, by0, bx1, by1 = bounds
        traufhoehe = _load_traufhoehe(tragwerk_config)

        # Erstelle Zone-Lookup für Höhenabfrage am Rasterpunkt
        def _height_at(px: float, py: float) -> float:
            if tragwerk_config:
                return traufhoehe
            for z in building_zones:
                if z.x <= px <= z.x + z.breite and z.y <= py <= z.y + z.tiefe:
                    return _zone_height(z, tragwerk_config, variante_name)
            return 6.0

        col_xs: list = []
        col_ys: list = []
        col_zs: list = []

        col_x = bx0
        while col_x <= bx1 + 1e-9:
            col_y = by0
            while col_y <= by1 + 1e-9:
                h_col = _height_at(col_x, col_y)
                col_xs += [col_x, col_x, None]
                col_ys += [col_y, col_y, None]
                col_zs += [0.0, h_col, None]
                col_y += raster_y
            col_x += raster_x

        if col_xs:
            traces.append(go.Scatter3d(
                x=col_xs, y=col_ys, z=col_zs,
                mode="lines",
                line=dict(color="#888888", width=2) if tragwerk_config else dict(color="rgba(100,100,100,0.5)", width=1),
                name="Tragwerk" if tragwerk_config else "Tragwerk (Skelett)",
                legendgroup="Tragwerk",
                showlegend=True,
                hoverinfo="skip",
            ))

        # Primärträger: verbindet Stützenpaare in Raster-Querrichtung (y-Richtung)
        beam_xs: list = []
        beam_ys: list = []
        beam_zs: list = []
        col_x = bx0
        while col_x <= bx1 + 1e-9:
            col_y = by0
            while col_y < by1 - 1e-9:
                h_here = _height_at(col_x, col_y)
                h_next = _height_at(col_x, col_y + raster_y)
                h_beam = min(h_here, h_next)
                beam_xs += [col_x, col_x, None]
                beam_ys += [col_y, col_y + raster_y, None]
                beam_zs += [h_beam, h_beam, None]
                col_y += raster_y
            col_x += raster_x

        # Sekundärträger: verbindet in Längsrichtung (x-Richtung)
        sec_xs: list = []
        sec_ys: list = []
        sec_zs: list = []
        col_y = by0
        while col_y <= by1 + 1e-9:
            col_x = bx0
            while col_x < bx1 - 1e-9:
                h_beam = _height_at(col_x, col_y)
                sec_xs += [col_x, col_x + raster_x, None]
                sec_ys += [col_y, col_y, None]
                sec_zs += [h_beam, h_beam, None]
                col_x += raster_x
            col_y += raster_y

        if beam_xs:
            traces.append(go.Scatter3d(
                x=beam_xs, y=beam_ys, z=beam_zs,
                mode="lines",
                line=dict(color="#888888", width=3),
                name="Primärträger",
                legendgroup="Tragwerk",
                showlegend=False,
                hoverinfo="skip",
            ))
        if sec_xs:
            traces.append(go.Scatter3d(
                x=sec_xs, y=sec_ys, z=sec_zs,
                mode="lines",
                line=dict(color="#AAAAAA", width=2),
                name="Sekundärträger",
                legendgroup="Tragwerk",
                showlegend=False,
                hoverinfo="skip",
            ))

        # Ringbalken: horizontale Linien entlang Zonenoberkanten (X-Richtung)
        ring_xs: list = []
        ring_ys: list = []
        ring_zs: list = []
        seen_heights: set = set()
        for zone in building_zones:
            h_z = _zone_height(zone, tragwerk_config, variante_name)
            if h_z in seen_heights:
                continue
            seen_heights.add(h_z)
            y_pos = zone.y
            while y_pos <= zone.y + zone.tiefe + 0.5:
                ring_xs += [zone.x, zone.x + zone.breite, None]
                ring_ys += [y_pos, y_pos, None]
                ring_zs += [h_z, h_z, None]
                y_pos += raster_y
        if ring_xs:
            traces.append(go.Scatter3d(
                x=ring_xs, y=ring_ys, z=ring_zs,
                mode="lines",
                line=dict(color="rgba(80,80,80,0.3)", width=1),
                name="Tragwerk (Ringbalken)",
                legendgroup="Tragwerk",
                showlegend=False,
                hoverinfo="skip",
            ))

    # ── Layer 4: Techniktrassen (3D-Linien bei z=3m) ─────────────────────
    # Immer sichtbar: entweder aus mep_variant_data (reale Backbone-Geometrie)
    # oder Fallback aus VF-Zonengeometrie (wenn MEP-Agent nicht gelaufen ist)
    _vf_zones_mep = [z for z in zonen if z.din_kategorie == "VF"]
    mep_install_h = 3.0
    if _vf_zones_mep:
        # Trassenhöhe: leicht unter Erschließungszone-Höhe (mind. 3 m)
        _vf_h = max(
            (_zone_height(z, tragwerk_config, variante_name) for z in _vf_zones_mep),
            default=4.0,
        )
        mep_install_h = max(3.0, _vf_h - 0.5)

    mep_xs: list = []
    mep_ys: list = []
    mep_zs: list = []

    if mep_variant_data and mep_variant_data.get("backbone_geometrie"):
        # ── Modus A: Reale Backbone-Geometrie aus MEP-Agent ─────────────
        for seg in mep_variant_data["backbone_geometrie"]:
            p1 = seg.get("von") or []
            p2 = seg.get("nach") or []
            if len(p1) >= 2 and len(p2) >= 2:
                mep_xs += [float(p1[0]), float(p2[0]), None]
                mep_ys += [float(p1[1]), float(p2[1]), None]
                mep_zs += [mep_install_h, mep_install_h, None]
    else:
        # ── Modus B: Fallback aus VF-Zonengeometrie ──────────────────────
        for vf in _vf_zones_mep:
            if vf.breite >= vf.tiefe:
                # Horizontaler Korridor → Backbone entlang Mittellinie (Y)
                mid_y = vf.y + vf.tiefe / 2
                mep_xs += [vf.x, vf.x + vf.breite, None]
                mep_ys += [mid_y, mid_y, None]
            else:
                # Vertikaler Korridor → Backbone entlang Mittellinie (X)
                mid_x = vf.x + vf.breite / 2
                mep_xs += [mid_x, mid_x, None]
                mep_ys += [vf.y, vf.y + vf.tiefe, None]
            mep_zs += [mep_install_h, mep_install_h, None]

    # TF-Verbindung: TF-Zentroid → nächster Backbone-Punkt (Stammtrasse)
    tf_zones = [z for z in zonen if z.din_kategorie == "TF" and not z.schraffur]
    tf_xs: list = []
    tf_ys: list = []
    tf_zs: list = []
    if tf_zones and mep_xs:
        # Nächsten Nicht-None-Punkt im Backbone finden
        bb_pts = [(mep_xs[i], mep_ys[i]) for i in range(len(mep_xs)) if mep_xs[i] is not None]
        for tf in tf_zones:
            tcx, tcy = tf.centroid
            if bb_pts:
                nearest = min(bb_pts, key=lambda p: math.dist((tcx, tcy), p))
                tf_xs += [tcx, nearest[0], None]
                tf_ys += [tcy, nearest[1], None]
                tf_zs += [mep_install_h, mep_install_h, None]

    # Abzweige: Backbone → Zentroid produktiver Zonen (vertikal hinab)
    ab_xs: list = []
    ab_ys: list = []
    ab_zs: list = []
    for z in zonen:
        if z.din_kategorie in ("NUF 3", "NUF 4") and not z.schraffur:
            cx, cy = z.centroid
            ab_xs += [cx, cx, None]
            ab_ys += [cy, cy, None]
            ab_zs += [mep_install_h, 0.5, None]

    if mep_xs:
        traces.append(go.Scatter3d(
            x=mep_xs, y=mep_ys, z=mep_zs,
            mode="lines",
            line=dict(color="#E07B00", width=5),
            name="Techniktrassen (Backbone)",
            legendgroup="Techniktrassen",
            legendgrouptitle_text="Techniktrassen",
            showlegend=True,
            hoverinfo="name",
        ))
    if tf_xs:
        traces.append(go.Scatter3d(
            x=tf_xs, y=tf_ys, z=tf_zs,
            mode="lines",
            line=dict(color="#B85C00", width=3),
            name="Stammtrasse (TF)",
            legendgroup="Techniktrassen",
            showlegend=True,
            hoverinfo="name",
        ))
    if ab_xs:
        traces.append(go.Scatter3d(
            x=ab_xs, y=ab_ys, z=ab_zs,
            mode="lines",
            line=dict(color="#E07B00", width=2, dash="dot"),
            name="Abzweige",
            legendgroup="Techniktrassen",
            showlegend=True,
            hoverinfo="name",
        ))

    # ── Layer 5: Erschließungsgraph (direkt + korridor) ──────────────────
    if erschliessungsgraph:
        zone_map = {z.name: z for z in non_hatch}
        _FLOOR_Z = 0.05   # knapp über Bodenniveau

        direkt_xs: list = []
        direkt_ys: list = []
        direkt_zs: list = []
        korr_xs:   list = []
        korr_ys:   list = []
        korr_zs:   list = []
        _TOL = 0.5

        def _wall_mid(a, b):
            ax0, ax1 = a.x, a.x + a.breite
            ay0, ay1 = a.y, a.y + a.tiefe
            bx0, bx1 = b.x, b.x + b.breite
            by0, by1 = b.y, b.y + b.tiefe
            if abs(ax1 - bx0) < _TOL or abs(bx1 - ax0) < _TOL:
                xw = ax1 if abs(ax1 - bx0) < _TOL else bx1
                yw = (max(ay0, by0) + min(ay1, by1)) / 2
                return xw, yw
            if abs(ay1 - by0) < _TOL or abs(by1 - ay0) < _TOL:
                yw = ay1 if abs(ay1 - by0) < _TOL else by1
                xw = (max(ax0, bx0) + min(ax1, bx1)) / 2
                return xw, yw
            return None

        for kante in erschliessungsgraph.get("kanten", []):
            za = zone_map.get(kante["von"])
            zb = zone_map.get(kante["nach"])
            if za is None or zb is None:
                continue
            if kante["typ"] == "direkt":
                mid = _wall_mid(za, zb)
                if mid:
                    ca = za.centroid
                    cb = zb.centroid
                    direkt_xs += [ca[0], mid[0], cb[0], None]
                    direkt_ys += [ca[1], mid[1], cb[1], None]
                    direkt_zs += [_FLOOR_Z, _FLOOR_Z, _FLOOR_Z, None]
            elif kante["typ"] == "korridor":
                pfad_punkte = kante.get("pfad_punkte") or []
                if len(pfad_punkte) >= 2:
                    xs, ys, zs = _path_to_xyz(pfad_punkte, _FLOOR_Z)
                    korr_xs += xs
                    korr_ys += ys
                    korr_zs += zs
                else:
                    ca = za.centroid
                    cb = zb.centroid
                    korr_xs += [ca[0], cb[0], None]
                    korr_ys += [ca[1], cb[1], None]
                    korr_zs += [_FLOOR_Z, _FLOOR_Z, None]

        _direkt_added = False
        _korr_added   = False
        if direkt_xs:
            traces.append(go.Scatter3d(
                x=direkt_xs, y=direkt_ys, z=direkt_zs,
                mode="lines",
                line=dict(color="#5B8FA8", width=3, dash="dash"),
                name="Direkte Verbindung",
                legendgroup="Erschliessung",
                legendgrouptitle_text="Erschließung",
                showlegend=True,
                hoverinfo="name",
            ))
            _direkt_added = True
        if korr_xs:
            traces.append(go.Scatter3d(
                x=korr_xs, y=korr_ys, z=korr_zs,
                mode="lines",
                line=dict(color="#E07B00", width=2, dash="dot"),
                name="Korridor (geplant)",
                legendgroup="Erschliessung",
                legendgrouptitle_text="Erschließung" if not _direkt_added else None,
                showlegend=True,
                hoverinfo="name",
            ))

    # ── Schraffur-Zonen: Freifläche (flach + grün) vs. Reserve (Box grau) ──
    _freif_added = False
    _reserv_added = False
    for zone in [z for z in zonen if z.schraffur]:
        is_freif = zone.din_kategorie == "AF"
        if is_freif:
            # Freifläche: flache Bodenplatte (0.08m) in Zonenfarbe
            h_res = 0.08
            color = zone.farbe if zone.farbe and zone.farbe != "none" else "#C8DDB4"
            opacity = 0.55
            group = "Freifläche"
            show = not _freif_added
            _freif_added = True
        else:
            # Erweiterungsreserve / Pufferfläche
            h_res = 0.5
            color = "#AAAAAA"
            opacity = 0.15
            group = "Erweiterungsreserve"
            show = not _reserv_added
            _reserv_added = True

        xs, ys, zs_v, ii, jj, kk = _box_mesh(
            zone.x, zone.y, 0.0,
            zone.x + zone.breite, zone.y + zone.tiefe, h_res,
        )
        traces.append(go.Mesh3d(
            x=xs, y=ys, z=zs_v,
            i=ii, j=jj, k=kk,
            color=color,
            opacity=opacity,
            flatshading=True,
            name=group,
            legendgroup=group,
            showlegend=show,
            hovertemplate=(
                f"<b>{zone.name}</b><br>"
                f"{zone.breite:.0f} × {zone.tiefe:.0f} m = "
                f"{zone.gezeichnete_flaeche:.0f} m²<extra></extra>"
            ),
        ))

    # ── Layout & Kamera ───────────────────────────────────────────────────
    title = f"3D-Ansicht – Variante {variante_name}" if variante_name else "3D-Ansicht"

    # Kamera: isometrische Ansicht von Südwest, leicht von oben
    # Skaliert auf Gebäude-Ausdehnung für bessere initiale Darstellung
    _bb = _building_envelope_bounds(site_geometry, struct_zones or non_hatch)
    _cam_z = 1.2
    _cam_x, _cam_y = -1.4, -1.6
    if _bb:
        bw = max(1.0, _bb[2] - _bb[0])
        bd = max(1.0, _bb[3] - _bb[1])
        _ratio = bd / bw
        if _ratio > 1.5:     # sehr tiefes Grundstück → etwas flacher
            _cam_z = 1.0
        elif _ratio < 0.7:   # sehr breites Grundstück → etwas steiler
            _cam_z = 1.4

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#222")),
        paper_bgcolor="#FAFAFA",
        scene=dict(
            xaxis=dict(title="Breite [m]", backgroundcolor="#F0F2F4",
                       gridcolor="#DDD", showbackground=True, showspikes=False),
            yaxis=dict(title="Tiefe [m]", backgroundcolor="#F0F2F4",
                       gridcolor="#DDD", showbackground=True, showspikes=False),
            zaxis=dict(title="Höhe [m]", backgroundcolor="#E4EBF0",
                       gridcolor="#CCC", showbackground=True, showspikes=False,
                       range=[0, None]),
            camera=dict(
                eye=dict(x=_cam_x, y=_cam_y, z=_cam_z),
                up=dict(x=0, y=0, z=1),
                projection=dict(type="perspective"),
            ),
            aspectmode="data",
        ),
        legend=dict(
            title=dict(text="Layer", font=dict(size=12)),
            x=0.01, y=0.99,
            xanchor="left", yanchor="top",
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#CCC",
            borderwidth=1,
            font=dict(size=11),
            tracegroupgap=4,
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        height=580,
    )
    return fig

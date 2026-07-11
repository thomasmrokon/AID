"""SVG rendering for masterplan Lageplan views."""
from __future__ import annotations

from html import escape
from typing import Any


_COLORS = {
    "site": "#E8E8E0",
    "site_edge": "#333333",
    "rangier": "#D4A96A",
    "lkw": "#CC7722",
    "green": "#A8D5A2",
    "parking": "#F5F0DC",
    "parking_edge": "#CCBB80",
    "infra": "#7B61FF",
    "building": "#1A3A5C",
    "building_2": "#335C67",
    "access": "#CC0000",
    "text": "#1A1A2E",
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _site_bounds(site: dict[str, Any], polygon: list[list[float]]) -> tuple[float, float, float, float]:
    if polygon:
        xs = [_num(p[0]) for p in polygon]
        ys = [_num(p[1]) for p in polygon]
        return min(xs), min(ys), max(xs), max(ys)
    return 0.0, 0.0, _num(site.get("width_m"), 100.0), _num(site.get("depth_m"), 100.0)


def masterplan_to_svg(masterplan: dict[str, Any], *, title: str | None = None) -> str:
    """Return a scalable SVG Lageplan from a masterplan result.

    The SVG keeps meter coordinates in the viewBox so downstream export to PDF can
    preserve scale information. Text remains SVG text, not rasterized labels.
    """
    site = masterplan.get("site") or {}
    hg = masterplan.get("hauptgebaeude") or {}
    buildings = masterplan.get("gebaeude") or ([hg] if hg else [])
    nebenbauten = masterplan.get("nebenbauten") or []
    erschl = masterplan.get("erschliessung") or {}
    freizonen = masterplan.get("freizonen") or []
    bilanz = masterplan.get("flaechenbilanz") or {}
    infra = masterplan.get("infrastruktur") or {}
    zonierung = masterplan.get("zonierung") or []
    phasenlayer = masterplan.get("phasenlayer") or {}

    site_w = _num(site.get("width_m"), 100.0)
    site_d = _num(site.get("depth_m"), 100.0)
    polygon = site.get("polygon") or [[0, 0], [site_w, 0], [site_w, site_d], [0, site_d]]
    min_x, min_y, max_x, max_y = _site_bounds(site, polygon)
    pad = 18.0
    view_x = min_x - pad
    view_y = min_y - pad
    width = max(40.0, (max_x - min_x) + pad * 2 + 34.0)
    height = max(40.0, (max_y - min_y) + pad * 2)

    def sx(x: Any) -> float:
        return _num(x)

    def sy(y: Any) -> float:
        return _num(y)

    def rect(x: Any, y: Any, w: Any, h: Any, fill: str, stroke: str, *, opacity: float = 1.0, cls: str = "") -> str:
        return (
            f'<rect class="{cls}" x="{sx(x):.3f}" y="{sy(y):.3f}" '
            f'width="{_num(w):.3f}" height="{_num(h):.3f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="0.8" opacity="{opacity:.2f}" />'
        )

    def text_el(x: Any, y: Any, value: str, *, size: float = 3.4, fill: str = _COLORS["text"], weight: str = "600", anchor: str = "middle") -> str:
        return (
            f'<text x="{sx(x):.3f}" y="{sy(y):.3f}" font-size="{size:.2f}" '
            f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" '
            f'dominant-baseline="middle">{escape(value)}</text>'
        )

    def polygon_el(item: dict[str, Any], fill: str, stroke: str, *, opacity: float = 1.0) -> str:
        pts_raw = item.get("polygon") or []
        if not pts_raw:
            return rect(item.get("x"), item.get("y"), item.get("breite_m"), item.get("tiefe_m"), fill, stroke, opacity=opacity, cls="aid-site")
        pts = " ".join(f"{_num(p[0]):.3f},{_num(p[1]):.3f}" for p in pts_raw)
        return f'<polygon class="aid-site" points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="0.8" opacity="{opacity:.2f}" />'

    def label_rect(item: dict[str, Any], label: str, *, fill: str = "#FFFFFF", size: float = 3.4) -> str:
        x, y = _num(item.get("x")), _num(item.get("y"))
        w, h = _num(item.get("breite_m")), _num(item.get("tiefe_m"))
        lines = [line.strip() for line in str(label).split("\n") if line.strip()]
        if not lines:
            return ""
        cy = y + h / 2 - (len(lines) - 1) * size * 0.55
        out = []
        for idx, line in enumerate(lines):
            out.append(text_el(x + w / 2, cy + idx * size * 1.15, line, size=size, fill=fill))
        return "\n".join(out)

    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_x:.3f} {view_y:.3f} {width:.3f} {height:.3f}" role="img" aria-label="{escape(title or "Masterplan Lageplan")}">')
    parts.append("""
<style>
.aid-site { vector-effect: non-scaling-stroke; }
.aid-road, .aid-infra, .aid-access, .aid-dim { vector-effect: non-scaling-stroke; }
.aid-label { paint-order: stroke; stroke: rgba(255,255,255,.78); stroke-width: .7px; stroke-linejoin: round; }
</style>
<defs>
  <pattern id="aid-hatch" width="4" height="4" patternUnits="userSpaceOnUse">
    <path d="M0,4 L4,0" stroke="#B07D38" stroke-width="0.35" />
  </pattern>
  <marker id="aid-arrow-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#CC0000" />
  </marker>
  <marker id="aid-arrow-dim" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="3" markerHeight="3" orient="auto-start-reverse">
    <path d="M 0 5 L 10 0 L 7 5 L 10 10 z" fill="#444" />
  </marker>
</defs>
""")
    poly_points = " ".join(f"{_num(p[0]):.3f},{_num(p[1]):.3f}" for p in polygon)
    parts.append(f'<polygon class="aid-site" points="{poly_points}" fill="{_COLORS["site"]}" stroke="{_COLORS["site_edge"]}" stroke-width="1.6" />')

    legal = phasenlayer.get("1.2") or {}
    baugrenze = legal.get("baugrenze") or {}
    if baugrenze:
        parts.append(polygon_el(baugrenze, "#DDE7EF", "#5E7894", opacity=0.28))
    for hz in legal.get("height_zones") or []:
        if hz.get("polygon"):
            parts.append(polygon_el(hz, "#DDE7EF", "#8AA1B8", opacity=0.16))

    for zone in zonierung:
        ztyp = zone.get("typ")
        if ztyp == "building_parcel_candidate":
            parts.append(polygon_el(zone, "#FFFFFF", "#1C3557", opacity=0.18))
            parts.append(label_rect(zone, str(zone.get("name", "Parzelle")), fill="#1C3557", size=2.6))
        elif ztyp == "zielzone_andienung":
            parts.append(polygon_el(zone, "#E8D3AE", "#A96E22", opacity=0.45))
            parts.append(label_rect(zone, str(zone.get("name", "Andienhof")), fill="#7A4F1E", size=2.6))
        elif ztyp == "zielzone_pkw":
            parts.append(polygon_el(zone, "#F5F0DC", "#CCBB80", opacity=0.52))
            parts.extend(_parking_grid(zone))
            parts.append(label_rect(zone, str(zone.get("name", "PKW")), fill="#666633", size=2.5))
        elif ztyp == "zielzone_sicherheit":
            parts.append(polygon_el(zone, "#BFD7EA", "#4A90D9", opacity=0.75))
            parts.append(label_rect(zone, str(zone.get("name", "Pforte")), fill="#1C4E80", size=2.4))

    rz = erschl.get("rangierzone") or {}
    if rz:
        parts.append(polygon_el(rz, "url(#aid-hatch)", "#B07D38", opacity=0.7))
        parts.append(label_rect(rz, "Rangierzone\nLKW", fill="#7A4F1E", size=3.0))

    for fz in freizonen:
        typ = fz.get("typ")
        if typ == "gruen":
            parts.append(polygon_el(fz, _COLORS["green"], "#5A9E54", opacity=0.72))
            if _num(fz.get("breite_m")) > 8 and _num(fz.get("tiefe_m")) > 6:
                parts.append(label_rect(fz, str(fz.get("name", "Gruen")), fill="#2D6A27", size=2.8))
        elif typ == "stellplatz":
            parts.append(polygon_el(fz, _COLORS["parking"], _COLORS["parking_edge"], opacity=0.9))
            parts.extend(_parking_grid(fz))
            if _num(fz.get("breite_m")) > 10:
                parts.append(label_rect(fz, str(fz.get("name", "Stellplaetze")), fill="#666633", size=2.7))
        elif typ == "aussenlager":
            parts.append(polygon_el(fz, "#C9CDD2", "#8D99AE", opacity=0.82))
            parts.append(label_rect(fz, str(fz.get("name", "Aussenlager")), fill="#45515C", size=2.8))

    road_axes = erschl.get("strassenachsen") or []
    if not road_axes and erschl.get("lkw_schleife_punkte"):
        road_axes = [erschl.get("lkw_schleife_punkte") or []]
    for loop in road_axes:
        if len(loop) >= 2:
            pts = " ".join(f"{_num(p[0]):.3f},{_num(p[1]):.3f}" for p in loop)
            parts.append(f'<polyline class="aid-road" points="{pts}" fill="none" stroke="{_COLORS["lkw"]}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" opacity="0.95" />')

    for node in infra.get("knoten") or []:
        pt = node.get("point") or []
        if len(pt) >= 2:
            parts.append(f'<circle class="aid-infra" cx="{_num(pt[0]):.3f}" cy="{_num(pt[1]):.3f}" r="1.8" fill="#7B61FF" stroke="#FFFFFF" stroke-width="0.5" />')
            parts.append(text_el(_num(pt[0]) + 2.0, _num(pt[1]) - 2.0, str(node.get("id", "K")), size=2.5, fill="#4B3DB8", anchor="start"))

    for trasse in infra.get("trassen") or []:
        pts_raw = trasse.get("punkte") or []
        if len(pts_raw) < 2:
            continue
        pts = " ".join(f"{_num(p[0]):.3f},{_num(p[1]):.3f}" for p in pts_raw)
        parts.append(f'<polyline class="aid-infra" points="{pts}" fill="none" stroke="{_COLORS["infra"]}" stroke-width="0.75" stroke-dasharray="2 1.4" opacity="0.78" />')
        end = pts_raw[-1]
        parts.append(text_el(_num(end[0]) + 1.2, _num(end[1]) + 1.2, str(trasse.get("medium", "Trasse")), size=2.6, fill="#4B3DB8", anchor="start"))

    for idx, geb in enumerate(buildings):
        fill = geb.get("farbe") or (_COLORS["building"] if idx == 0 else _COLORS["building_2"])
        parts.append(rect(geb.get("x"), geb.get("y"), geb.get("breite_m"), geb.get("tiefe_m"), fill, "#0A1A2C", opacity=0.93, cls="aid-site"))
        label = str(geb.get("name") or "Gebaeude").replace("Hauptgebäude", "Produktion")
        area = _num(geb.get("flaeche_m2"))
        parts.append(label_rect(geb, f"{label}\n{area:.0f} m2", fill="#FFFFFF", size=3.4 if idx else 3.8))

    for nb in nebenbauten:
        parts.append(rect(nb.get("x"), nb.get("y"), nb.get("breite_m"), nb.get("tiefe_m"), nb.get("farbe", "#4A90D9"), "#1A1A2E", opacity=0.88, cls="aid-site"))
        parts.append(label_rect(nb, str(nb.get("name", "Nebenbau")), fill="#FFFFFF", size=2.6))

    if hg:
        bx, by = _num(hg.get("x")), _num(hg.get("y"))
        bw, bd = _num(hg.get("breite_m")), _num(hg.get("tiefe_m"))
        y_dim = by - 3.5
        x_dim = bx + bw + 3.0
        parts.append(f'<line class="aid-dim" x1="{bx:.3f}" y1="{y_dim:.3f}" x2="{bx + bw:.3f}" y2="{y_dim:.3f}" stroke="#444" stroke-width="0.55" marker-start="url(#aid-arrow-dim)" marker-end="url(#aid-arrow-dim)" />')
        parts.append(text_el(bx + bw / 2, y_dim - 2.0, f"{bw:.0f} m", size=2.7, fill="#444"))
        parts.append(f'<line class="aid-dim" x1="{x_dim:.3f}" y1="{by:.3f}" x2="{x_dim:.3f}" y2="{by + bd:.3f}" stroke="#444" stroke-width="0.55" marker-start="url(#aid-arrow-dim)" marker-end="url(#aid-arrow-dim)" />')
        parts.append(text_el(x_dim + 3.0, by + bd / 2, f"{bd:.0f} m", size=2.7, fill="#444", anchor="start"))

    for ap in site.get("access_points") or []:
        px, py = _num((ap.get("point") or [0, 0])[0]), _num((ap.get("point") or [0, 0])[1])
        side = ap.get("side", "south")
        dx, dy = {"south": (0, 6), "north": (0, -6), "west": (6, 0), "east": (-6, 0)}.get(side, (0, 6))
        parts.append(f'<line class="aid-access" x1="{px:.3f}" y1="{py:.3f}" x2="{px + dx:.3f}" y2="{py + dy:.3f}" stroke="{_COLORS["access"]}" stroke-width="1.2" marker-end="url(#aid-arrow-red)" />')
        parts.append(text_el(px + 1.0, py + 1.0, f"Z{ap.get('id', '')}", size=2.6, fill=_COLORS["access"], anchor="start"))

    # North arrow, scale bar and balance box.
    nx, ny = max_x + 8, max_y - 10
    parts.append(f'<line class="aid-access" x1="{nx:.3f}" y1="{ny + 6:.3f}" x2="{nx:.3f}" y2="{ny:.3f}" stroke="#1A1A2E" stroke-width="0.9" marker-end="url(#aid-arrow-red)" />')
    parts.append(text_el(nx, ny + 8.5, "N", size=3.2, fill="#1A1A2E"))
    sx0, sy0 = max_x - 25, min_y - 8
    parts.append(f'<line class="aid-dim" x1="{sx0:.3f}" y1="{sy0:.3f}" x2="{sx0 + 20:.3f}" y2="{sy0:.3f}" stroke="#1A1A2E" stroke-width="0.8" />')
    parts.append(text_el(sx0 + 10, sy0 + 2.5, "20 m", size=2.7, fill="#1A1A2E"))

    box_x, box_y = max_x + 3, min_y + 4
    parts.append(f'<rect x="{box_x:.3f}" y="{box_y:.3f}" width="28" height="24" rx="1.5" fill="#FFFFFF" stroke="#CCCCCC" opacity="0.94" />')
    grz = _num(bilanz.get("grz"))
    gfz = _num(bilanz.get("gfz"))
    vs = _num(bilanz.get("versiegelungsgrad"))
    sp = int(_num(bilanz.get("stellplaetze_anzahl")))
    grz_lim = _num(bilanz.get("grz_grenzwert"), 0.6)
    for idx, line in enumerate(["Flaechenbilanz", f"GRZ {grz:.2f} / {grz_lim:.2f}", f"GFZ {gfz:.2f}", f"Versieg. {vs:.0%}", f"Stellplaetze {sp} SP"]):
        parts.append(text_el(box_x + 2, box_y + 4 + idx * 4, line, size=2.6, fill="#1A1A2E", anchor="start", weight="700" if idx == 0 else "500"))

    variant_label = masterplan.get("label") or masterplan.get("selected_masterplan_variant_id") or ""
    plan_title = title or f"Masterplan {variant_label}".strip()
    parts.append(text_el(min_x, max_y + 8, f"{plan_title} · {site.get('name', site.get('id', 'Grundstueck'))} · {site.get('area_m2', 0):.0f} m2", size=4.0, fill="#1A1A2E", anchor="start", weight="700"))
    parts.append("</svg>")
    return "\n".join(parts)


def _parking_grid(fz: dict[str, Any]) -> list[str]:
    x, y = _num(fz.get("x")), _num(fz.get("y"))
    w, h = _num(fz.get("breite_m")), _num(fz.get("tiefe_m"))
    out: list[str] = []
    col = 0
    px = x + 0.7
    while px + 2.5 <= x + w - 0.5 and col < 60:
        out.append(f'<line class="aid-dim" x1="{px:.3f}" y1="{y:.3f}" x2="{px:.3f}" y2="{y + h:.3f}" stroke="#D8CA95" stroke-width="0.22" />')
        px += 2.5
        col += 1
    return out


def site_to_svg(site: dict[str, Any], *, title: str | None = None) -> str:
    site_w = _num(site.get("width_m"), 100.0)
    site_d = _num(site.get("depth_m"), 100.0)
    polygon = site.get("polygon") or [[0, 0], [site_w, 0], [site_w, site_d], [0, site_d]]
    min_x, min_y, max_x, max_y = _site_bounds(site, polygon)
    pad = max(site_w, site_d) * 0.08
    view = f"{min_x - pad:.3f} {min_y - pad:.3f} {(max_x - min_x) + pad * 2:.3f} {(max_y - min_y) + pad * 2:.3f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" aria-label="{escape(title or site.get("name", "Grundstueck"))}">']
    out.append('<style>.aid-site{vector-effect:non-scaling-stroke}.aid-label{paint-order:stroke;stroke:rgba(255,255,255,.8);stroke-width:.65px}</style>')
    pts = " ".join(f"{_num(p[0]):.3f},{_num(p[1]):.3f}" for p in polygon)
    out.append(f'<polygon class="aid-site" points="{pts}" fill="#DDE7EF" stroke="#204B64" stroke-width="1.5" />')
    for access in site.get("access_points") or []:
        point = access.get("point") or [0, 0]
        x, y = _num(point[0]), _num(point[1])
        out.append(f'<rect x="{x - 1.4:.3f}" y="{y - 1.4:.3f}" width="2.8" height="2.8" fill="#C05746" stroke="#7A2F25" stroke-width="0.35" />')
        out.append(f'<text class="aid-label" x="{x + 2.0:.3f}" y="{y:.3f}" font-size="3.2" fill="#7A2F25" dominant-baseline="middle">{escape(str(access.get("id", "")))}</text>')
    out.append(f'<text x="{min_x:.3f}" y="{max_y + pad * 0.45:.3f}" font-size="4" fill="#1A1A2E" font-weight="700">{escape(str(title or site.get("name", "Grundstueck")))} · {_num(site.get("area_m2")):.0f} m2</text>')
    out.append("</svg>")
    return "\n".join(out)

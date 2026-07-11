"""SVG renderers for process planning diagrams."""
from __future__ import annotations

from html import escape
from typing import Any

_STEP_COLORS = [
    "#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#3B1F2B",
    "#6A994E", "#386FA4", "#8B5CF6", "#E63946", "#2A9D8F",
]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _text(x: float, y: float, value: str, *, size: float = 3.2, fill: str = "#1A1A2E", anchor: str = "middle", weight: str = "600") -> str:
    return (
        f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size:.2f}" fill="{fill}" '
        f'font-weight="{weight}" text-anchor="{anchor}" dominant-baseline="middle">{escape(value)}</text>'
    )


def process_layout_to_svg(process_layout: dict[str, Any]) -> str:
    zone_b = _num(process_layout.get("zone_breite_m"), 40.0)
    zone_t = _num(process_layout.get("zone_tiefe_m"), 75.0)
    zone_name = str(process_layout.get("zone_name") or "Produktion")
    maschinen = process_layout.get("maschinen") or []
    strips = process_layout.get("strips") or []
    kpis = process_layout.get("kpis") or {}
    steps = sorted({int(m.get("schritt", 0)) for m in maschinen})
    step_color = {s: _STEP_COLORS[i % len(_STEP_COLORS)] for i, s in enumerate(steps)}
    engpass = kpis.get("engpass_schritt")
    pad = 9.0
    view = f"{-pad:.3f} {-pad:.3f} {zone_b + pad * 2 + 28:.3f} {zone_t + pad * 2:.3f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" aria-label="Prozesslayout {escape(zone_name)}">']
    out.append('''
<style>
.aid-line, .aid-zone, .aid-flow { vector-effect: non-scaling-stroke; }
.aid-label { paint-order: stroke; stroke: rgba(255,255,255,.82); stroke-width: .65px; stroke-linejoin: round; }
</style>
<defs>
  <marker id="aid-flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#005A8E" />
  </marker>
</defs>
''')
    out.append(f'<rect class="aid-zone" x="0" y="0" width="{zone_b:.3f}" height="{zone_t:.3f}" fill="#F7F7F7" stroke="#1A1A2E" stroke-width="1.1" />')
    for i, strip in enumerate(strips):
        y = _num(strip.get("y_start"))
        h = _num(strip.get("hoehe_m"))
        fill = "#EDEDF0" if i % 2 == 0 else "#E2E2E8"
        out.append(f'<rect x="0" y="{y:.3f}" width="{zone_b:.3f}" height="{h:.3f}" fill="{fill}" opacity="0.72" />')
        out.append(_text(1.5, y + h / 2, f"S{strip.get('schritt')}", size=2.8, fill="#666", anchor="start"))
        out.append(f'<line class="aid-line" x1="0" y1="{y:.3f}" x2="{zone_b:.3f}" y2="{y:.3f}" stroke="#AAAAAA" stroke-width="0.28" stroke-dasharray="1.5 1" />')
    for m in maschinen:
        x, y = _num(m.get("x")), _num(m.get("y"))
        w, h = _num(m.get("breite_m")), _num(m.get("tiefe_m"))
        step = int(m.get("schritt", 0))
        color = m.get("farbe") or step_color.get(step, "#888888")
        is_engpass = step == engpass
        out.append(f'<rect class="aid-zone" x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{color}" stroke="{"#CC0000" if is_engpass else "#1A1A2E"}" stroke-width="{"1.35" if is_engpass else "0.75"}" opacity="0.86" rx="0.25" />')
        label = str(m.get("name") or m.get("id") or "Maschine")
        if int(m.get("instance_idx", 0)) > 0:
            label += f" #{int(m.get('instance_idx')) + 1}"
        out.append(_text(x + w / 2, y + h / 2 - 0.6, label[:24], size=2.5, fill="#FFFFFF"))
        out.append(_text(x + w / 2, y + h / 2 + 2.1, f"{_num(m.get('taktzeit_s')):.0f}s/Teil", size=2.15, fill="#EEEEEE", weight="500"))
    centers = kpis.get("schwerpunkte") or {}
    for idx in range(len(steps) - 1):
        a, b = str(steps[idx]), str(steps[idx + 1])
        if a in centers and b in centers:
            x1, y1 = _num(centers[a][0]), _num(centers[a][1])
            x2, y2 = _num(centers[b][0]), _num(centers[b][1])
            out.append(f'<line class="aid-flow" x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="#005A8E" stroke-width="1.0" marker-end="url(#aid-flow-arrow)" opacity="0.88" />')
    bx, by = zone_b + 3.0, 3.0
    out.append(f'<rect x="{bx:.3f}" y="{by:.3f}" width="24" height="18" rx="1.2" fill="#FFFFFF" stroke="#CCCCCC" opacity="0.94" />')
    lines = [
        "Kennwerte",
        f"Durchsatz: {kpis.get('durchsatz_teile_pro_schicht', '-')} T/S",
        f"Engpass: S{kpis.get('engpass_schritt', '-')}",
        f"Flussweg: {_num(kpis.get('materialflussweg_m')):.0f} m",
    ]
    for i, line in enumerate(lines):
        out.append(_text(bx + 1.5, by + 3.0 + i * 4.0, line, size=2.45, anchor="start", weight="700" if i == 0 else "500"))
    out.append(_text(0, zone_t + 5.0, f"Prozesslayout · {zone_name} · {len(maschinen)} Maschinen", size=3.8, anchor="start", weight="700"))
    out.append("</svg>")
    return "\n".join(out)


def utilization_to_svg(process_layout: dict[str, Any]) -> str:
    kpis = process_layout.get("kpis") or {}
    values = kpis.get("auslastung_je_schritt") or {}
    if not values:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40"><text x="60" y="20" text-anchor="middle">Keine KPIs</text></svg>'
    steps = sorted(int(k) for k in values)
    row_h = 11.0
    width = 150.0
    height = 18.0 + row_h * len(steps)
    engpass = kpis.get("engpass_schritt")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" role="img" aria-label="Auslastung Prozessschritte">']
    out.append('<style>.aid-line{vector-effect:non-scaling-stroke}</style>')
    out.append(_text(4, 7, "Auslastung je Prozessschritt", size=4.0, anchor="start", weight="700"))
    x0, bar_w = 42.0, 92.0
    out.append(f'<line class="aid-line" x1="{x0 + bar_w:.3f}" y1="12" x2="{x0 + bar_w:.3f}" y2="{height - 2:.3f}" stroke="#CC0000" stroke-width="0.45" stroke-dasharray="2 1" />')
    for i, step in enumerate(steps):
        y = 15.0 + i * row_h
        val = _num(values.get(str(step)))
        fill = _STEP_COLORS[i % len(_STEP_COLORS)]
        out.append(_text(4, y + 3, f"Schritt {step}", size=3.0, anchor="start", weight="500"))
        out.append(f'<rect x="{x0:.3f}" y="{y:.3f}" width="{bar_w:.3f}" height="6" fill="#EEF2F6" rx="1" />')
        out.append(f'<rect x="{x0:.3f}" y="{y:.3f}" width="{min(val, 120) / 120 * bar_w:.3f}" height="6" fill="{fill}" stroke="{"#CC0000" if step == engpass else "#1A1A2E"}" stroke-width="0.35" rx="1" />')
        out.append(_text(x0 + min(118, val) / 120 * bar_w + 2, y + 3.2, f"{val:.0f}%" + (" Engpass" if step == engpass else ""), size=2.8, anchor="start", fill="#CC0000" if step == engpass else "#444"))
    out.append("</svg>")
    return "\n".join(out)

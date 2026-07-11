"""Prüft Zone-Koordinaten vs. Baufeld-Envelope für alle Sites."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.tools.site import get_demo_site, compute_building_envelope
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.state import PlanningState

BASE = {
    "nutzungstyp": "Produktion", "produktionsflaeche": 3000,
    "lager_rohstoffe": 600, "lager_fertigwaren": 600,
    "wareneingang": 250, "versand": 250, "qualitaetssicherung": 150,
    "buero_nuf2": 300, "kranbahn_erforderlich": False,
}

for site_id in ["A_kompakt", "B_langgezogen", "C_unregelmaessig"]:
    print(f"\n{'='*55}")
    print(f"Site: {site_id}")
    print("="*55)

    site = get_demo_site(site_id)
    raw_env = compute_building_envelope(site)
    raw_x1 = raw_env["x"] + raw_env["width_m"]
    raw_y1 = raw_env["y"] + raw_env["depth_m"]
    print(f"Raw envelope: x=[{raw_env['x']:.1f}, {raw_x1:.1f}] y=[{raw_env['y']:.1f}, {raw_y1:.1f}]  angle={raw_env.get('site_angle_deg',0):.1f}°")

    state: PlanningState = {"user_input": BASE, "briefing": BASE, "site_id": site_id, "site_geometry": site}
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    typologies = state.get("typology_assignments", {})

    for v in state.get("variants", []):
        name = v["name"]
        typ = typologies.get(name, "?")
        zonen = v["zonen"]
        env_v = v.get("building_envelope") or {}
        env_x1 = env_v.get("x", 0) + env_v.get("width_m", 0)
        env_y1 = env_v.get("y", 0) + env_v.get("depth_m", 0)

        violations = []
        close = []
        for z in zonen:
            x0, y0 = z["x"], z["y"]
            x1 = x0 + z["breite"]
            y1 = y0 + z["tiefe"]
            if x1 > raw_x1 + 0.5 or y1 > raw_y1 + 0.5 or x0 < raw_env["x"] - 0.5 or y0 < raw_env["y"] - 0.5:
                violations.append(f"  ❌ {z['name']:22s} x=[{x0:.1f},{x1:.1f}] y=[{y0:.1f},{y1:.1f}]  (limit x1={raw_x1:.1f} y1={raw_y1:.1f})")
            elif x1 > raw_x1 - 0.1 or y1 > raw_y1 - 0.1:
                close.append(f"  ~  {z['name']:22s} x1={x1:.1f} (limit {raw_x1:.1f})  y1={y1:.1f} (limit {raw_y1:.1f})")

        status = "❌" if violations else "✅"
        print(f"\n{status} {name} ({typ})  env=[{env_v.get('x',0):.0f},{env_x1:.0f}]x[{env_v.get('y',0):.0f},{env_y1:.0f}]  zones={len(zonen)}")
        for msg in violations:
            print(msg)
        for msg in close:
            print(msg)

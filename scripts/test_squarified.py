"""Detailed squarified layout verification."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone
from app.state import PlanningState

state = PlanningState(user_input={
    'nutzungstyp': 'Produktion',
    'produktionsflaeche': 3000,
    'lager_rohstoffe': 600,
    'lager_fertigwaren': 600,
    'wareneingang': 250,
    'versand': 250,
    'qualitaetssicherung': 150,
    'buero_nuf2': 300,
    'kranbahn_erforderlich': False,
    'grundstueck_id': 'B',
})

state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

variants = state["variants"]
print("=== SQUARIFIED LAYOUT VERIFICATION ===")
total_ar_viol = 0
total_area_err = 0

for v in variants:
    zonen = [Zone(**z) for z in v["zonen"]]
    env = v["building_envelope"]
    print()
    print(f"Variante: {v['name']}  [{env['width_m']:.0f}x{env['depth_m']:.0f} m]")
    max_ar = 0
    for z in sorted(zonen, key=lambda z: z.flaeche_m2, reverse=True):
        if z.schraffur:
            continue
        soll = z.flaeche_m2
        ist = z.planned_area_m2 or (z.breite * z.tiefe * z.floors)
        pct = (ist - soll) / max(1, soll) * 100
        ar = max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe))
        max_ar = max(max_ar, ar)
        ar_flag = " <<AR!" if ar > 4.0 else ""
        area_flag = " <<AREA!" if abs(pct) > 10 else ""
        if ar > 4.0:
            total_ar_viol += 1
        if abs(pct) > 10:
            total_area_err += 1
        print(f"  {z.name:<25} soll={soll:.0f} ist={ist:.0f} d={pct:+.1f}%  AR={ar:.2f} ({z.breite:.1f}x{z.tiefe:.1f}m){ar_flag}{area_flag}")
    print(f"  Max AR: {max_ar:.2f}  (limit: 4.0)")

print()
print(f"TOTAL: AR violations={total_ar_viol}  Area errors (>10%)={total_area_err}")

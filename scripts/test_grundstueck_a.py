"""Verifikation der Squarified-Layouts fuer Grundstueck A (kompakt)."""
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
    'grundstueck_id': 'A',   # <-- Grundstueck A (kompakt, ~90x81m)
})

state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

variants = state["variants"]
print("=== SQUARIFIED LAYOUT - GRUNDSTUECK A ===")

for v in variants:
    zonen = [Zone(**z) for z in v["zonen"]]
    env = v["building_envelope"]
    print()
    print(f"Variante: {v['name']}  [{env['width_m']:.0f}x{env['depth_m']:.0f} m]")
    for z in sorted(zonen, key=lambda z: z.flaeche_m2, reverse=True):
        if z.schraffur:
            continue
        soll = z.flaeche_m2
        ist = z.breite * z.tiefe * z.floors
        ar = max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe))
        ar_flag = " <<AR!" if ar > 4.0 else ""
        print(f"  {z.name:<25} x={z.x:5.1f} y={z.y:5.1f}  {z.breite:.1f}x{z.tiefe:.1f}m  AR={ar:.2f}{ar_flag}")

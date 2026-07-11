"""Pipeline end-to-end test: Briefing -> Layout -> Print results."""
import sys
sys.path.insert(0, ".")

from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone
from app.state import PlanningState

state = PlanningState(
    user_input={
        "nutzungstyp": "Produktion",
        "produktionsflaeche": 3000,
        "lager_rohstoffe": 600,
        "lager_fertigwaren": 600,
        "wareneingang": 250,
        "versand": 250,
        "qualitaetssicherung": 150,
        "buero_nuf2": 300,
        "kranbahn_erforderlich": False,
        "grundstueck_id": "B",
    },
)

print("[1] Briefing...")
state.update(briefing_agent(state))
print("[2] Rules...")
state.update(rule_agent(state))
print("[3] Topology...")
state.update(topology_agent(state))
print("[4] Strategy...")
state.update(layout_strategy_agent(state))
print("[5] Layout...")
state.update(layout_agent(state))

variants = state["variants"]
ta = state.get("typology_assignments", {})
print()
print("=== ERGEBNIS ===")
for v in variants:
    zonen = [Zone(**z) for z in v["zonen"]]
    env = v["building_envelope"]
    print()
    typ = ta.get(v["name"], "?")
    print("Variante: %s  [%.0fx%.0f m]  Typ=%s" % (
        v["name"], env["width_m"], env["depth_m"], typ))
    max_ar = 0
    for z in zonen:
        if z.schraffur:
            continue
        soll = z.flaeche_m2
        ist = z.planned_area_m2 or (z.breite * z.tiefe * z.floors)
        pct = (ist - soll) / max(1, soll) * 100
        ar = max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe))
        max_ar = max(max_ar, ar)
        flag = " <<AR!" if ar > 4.0 else ""
        print("  %-22s  d=%+5.1f%%  AR=%.1f  (%.0fx%.0f)%s" % (
            z.name, pct, ar, z.breite, z.tiefe, flag))
    print("  Max AR: %.1f  Zonen: %d" % (
        max_ar, len([z for z in zonen if not z.schraffur])))

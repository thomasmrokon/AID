"""Test aller drei Grundstuecke mit echter Site-Geometry (wie Streamlit-App)."""
import sys; sys.path.insert(0, '.')
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.geometry import Zone
from app.tools.site import get_demo_site, compute_building_envelope
from app.state import PlanningState

BASE_INPUT = {
    'nutzungstyp': 'Produktion',
    'produktionsflaeche': 3000,
    'lager_rohstoffe': 600,
    'lager_fertigwaren': 600,
    'wareneingang': 250,
    'versand': 250,
    'qualitaetssicherung': 150,
    'buero_nuf2': 300,
    'kranbahn_erforderlich': False,
}

print("=== Baufeld-Envelopes je Grundstueck ===")
for gid in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site = get_demo_site(gid)
    env = compute_building_envelope(site)
    if env:
        w, d = env['width_m'], env['depth_m']
        print(f"  {gid:<22} Polygon-Envelope: {w:.0f}x{d:.0f}m  AR={w/d:.2f}")
print()

for gid in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    site = get_demo_site(gid)

    print(f"\n{'='*60}")
    print(f"Grundstueck: {gid}")

    state = PlanningState(user_input={**BASE_INPUT, 'grundstueck_id': gid})
    # Echte site_geometry setzen — genau wie die Streamlit-App es tut
    state['site_geometry'] = site

    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))

    total_ar_viol = 0
    variants = state["variants"]
    for v in variants:
        zonen = [Zone(**z) for z in v["zonen"]]
        env = v["building_envelope"]
        bw, bd = env['width_m'], env['depth_m']
        max_ar = 0
        viol = 0
        worst_zone = ""
        for z in zonen:
            if z.schraffur: continue
            ar = max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe))
            if ar > max_ar:
                max_ar = ar
                worst_zone = z.name
            if ar > 4.0: viol += 1
        total_ar_viol += viol
        flag = f" <<! ({worst_zone})" if viol > 0 else " OK"
        print(f"  {v['name']:<22} [{bw:.0f}x{bd:.0f}m AR={bw/bd:.2f}]  "
              f"MaxAR={max_ar:.2f}  Viol={viol}{flag}")

    print(f"  TOTAL AR-Violations: {total_ar_viol}")

"""Zeigt Überlappungen zwischen Flur-Korridoren und bestehenden Zonen."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from app.agents.briefing   import briefing_agent
from app.agents.rules      import rule_agent
from app.agents.topology   import topology_agent
from app.agents.strategy   import layout_strategy_agent
from app.agents.layout     import layout_agent
from app.tools.site        import get_demo_site
from app.state             import PlanningState

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

site = get_demo_site('A_kompakt')
state = PlanningState(user_input={**BASE, 'grundstueck_id': 'A_kompakt'})
state['site_geometry'] = site
state['gap_strategy'] = 'corridor'
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

v = state['variants'][0]  # A_Materialfluss
print(f"Variante: {v['name']}")
print()

all_zonen = v['zonen']
flure = [z for z in all_zonen if z.get('din_kategorie') == 'VF' and not z.get('schraffur')]
funczonen = [z for z in all_zonen if not z.get('schraffur') and z.get('din_kategorie') != 'VF']

for f in flure:
    fx1, fy1 = f['x'], f['y']
    fx2, fy2 = fx1 + f['breite'], fy1 + f['tiefe']
    print(f"Flur '{f['name']}': ({fx1:.1f},{fy1:.1f}) → ({fx2:.1f},{fy2:.1f})  {f['breite']:.1f}×{f['tiefe']:.1f}m")

    for z in funczonen:
        zx1, zy1 = z['x'], z['y']
        zx2, zy2 = zx1 + z['breite'], zy1 + z['tiefe']
        # Überlappung prüfen
        ox1 = max(fx1, zx1);  ox2 = min(fx2, zx2)
        oy1 = max(fy1, zy1);  oy2 = min(fy2, zy2)
        if ox2 > ox1 + 0.1 and oy2 > oy1 + 0.1:
            ov_area = (ox2-ox1) * (oy2-oy1)
            print(f"  ⚠️  Überlapp mit '{z['name']}': "
                  f"({ox1:.1f},{oy1:.1f})→({ox2:.1f},{oy2:.1f})  {ov_area:.0f} m²")
    print()

print("Alle Funktionszonen (Position):")
for z in sorted(funczonen, key=lambda z: (round(z['y']), round(z['x']))):
    print(f"  {z['name']:28} x={z['x']:.1f}→{z['x']+z['breite']:.1f}  "
          f"y={z['y']:.1f}→{z['y']+z['tiefe']:.1f}  "
          f"({z['breite']:.1f}×{z['tiefe']:.1f})")

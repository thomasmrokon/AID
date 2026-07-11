import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.site import get_demo_site
from app.state import PlanningState

BASE = {'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False}
state = PlanningState(user_input={**BASE, 'grundstueck_id': 'A_kompakt'})
state['site_geometry'] = get_demo_site('A_kompakt')
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))

v = state['variants'][0]
print(f"Variante: {v['name']}")
print()
tf_zones = []
vf_zones = []
for z in sorted(v['zonen'], key=lambda z: z['name']):
    if not z.get('schraffur'):
        cat = z.get('din_kategorie', '?')
        print(f"  din={cat:4}  {z['name']:28}  x={z['x']:.1f} y={z['y']:.1f} ({z['breite']:.1f}x{z['tiefe']:.1f})")
        if cat == 'TF':
            tf_zones.append(z)
        if cat == 'VF':
            vf_zones.append(z)
print()
print(f"TF-Zonen: {len(tf_zones)}")
for z in tf_zones:
    cx = z['x'] + z['breite']/2
    cy = z['y'] + z['tiefe']/2
    print(f"  {z['name']} Zentroid=({cx:.1f},{cy:.1f})")
print(f"VF-Zonen: {len(vf_zones)}")
for z in vf_zones:
    cx = z['x'] + z['breite']/2
    cy = z['y'] + z['tiefe']/2
    print(f"  {z['name']} Zentroid=({cx:.1f},{cy:.1f})")

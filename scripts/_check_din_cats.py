"""Quick script: inspect DIN categories in all layout variants."""
import contextlib, io, sys

sys.stdout = io.StringIO()
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.tools.site import get_demo_site

state = {
    'user_input': {
        'nutzungstyp': 'Produktion',
        'produktionsflaeche': 1800,
        'lagerflaeche': 600,
        'bueroflaeche': 300,
        'sozialflaeche': 150,
    },
    'site_geometry': get_demo_site('A_kompakt'),
}
for fn in [briefing_agent, rule_agent, topology_agent, layout_strategy_agent, layout_agent]:
    state.update(fn(state))

sys.stdout = sys.__stdout__

for v in state['variants']:
    cats = sorted({z.get('din_kategorie', '?') for z in v['zonen'] if not z.get('schraffur')})
    names = sorted({z.get('name', '?') for z in v['zonen'] if not z.get('schraffur')})
    print(f"\n{v['name']}:")
    print(f"  DIN-Kategorien: {cats}")
    print(f"  Zonen:          {names}")

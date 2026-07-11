"""Check P0-1: alle Topology-Nodes in jeder Variante vorhanden?"""
import sys, io
sys.path.insert(0, '.')

import contextlib
from app.tools.site import get_demo_site
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent

BASE = {
    'nutzungstyp': 'Produktion',
    'produktionsflaeche': 1800, 'lager_rohstoffe': 450, 'lager_fertigwaren': 450,
    'wareneingang': 200, 'versand': 200, 'qualitaetssicherung': 100,
    'buero_nuf2': 250, 'buero_geschosse': 2,
    'technikflaeche_tf': None, 'sozialraeume_nuf7': None, 'sonderbedingungen': None,
    'kranbahn_erforderlich': False, 'mep_lueftung': 'mechanisch',
    'mep_sprinkler': False, 'mep_druckluft': True, 'mep_kaelte': False,
    'mep_usv_notstrom': False, 'mep_it_kategorie': 'basis',
    'tragwerk_typologie': 'stahl', 'tragwerk_lastklasse': 'mittel',
}

ok = True
for site_id in ['A_kompakt', 'B_langgezogen', 'C_unregelmaessig']:
    state = {'user_input': BASE, 'site_geometry': get_demo_site(site_id)}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for fn in [briefing_agent, rule_agent, topology_agent, layout_strategy_agent, layout_agent]:
            state.update(fn(state))

    expected = {n['name'] for n in state['topology_diagram']['nodes']}
    print(f'\n=== {site_id} — expected {len(expected)} Zonen: {sorted(expected)}')

    for v in state['variants']:
        actual = {z['name'] for z in v['zonen'] if not z.get('schraffur')}
        missing = expected - actual
        extra   = actual - expected
        status  = 'OK' if not missing else 'FEHLT'
        print(f'  {status} {v["name"]:25s}: {len(actual)} Zonen  |  missing={missing}  extra={extra}')
        if missing:
            ok = False

print('\n' + ('OK: Alle Zonen vollstaendig' if ok else 'FEHLER: Fehlende Zonen gefunden!'))

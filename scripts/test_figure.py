"""Test: PNG-Ausgabe ohne Legende und Violations."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.tools.rhino_inside_runner as _rir; _rir._available = False

from pathlib import Path
from app.agents.briefing   import briefing_agent
from app.agents.rules      import rule_agent
from app.agents.topology   import topology_agent
from app.agents.strategy   import layout_strategy_agent
from app.agents.layout     import layout_agent
from app.agents.evaluation import evaluation_agent
from app.agents.report     import report_agent
from app.tools.site        import get_demo_site
from app.state             import PlanningState
from app.tools.geometry    import Zone
from app.tools.drawing     import zeichne_layout

BASE = {
    'nutzungstyp': 'Produktion', 'produktionsflaeche': 3000,
    'lager_rohstoffe': 600, 'lager_fertigwaren': 600,
    'wareneingang': 250, 'versand': 250, 'qualitaetssicherung': 150,
    'buero_nuf2': 300, 'kranbahn_erforderlich': False,
}

site = get_demo_site('A_kompakt')
state = PlanningState(user_input={**BASE, 'grundstueck_id': 'A_kompakt'})
state['site_geometry'] = site
state.update(briefing_agent(state))
state.update(rule_agent(state))
state.update(topology_agent(state))
state.update(layout_strategy_agent(state))
state.update(layout_agent(state))
state.update(evaluation_agent(state))

variants  = state['variants']
evals     = state['evaluations']
eval_map  = {e['variante']: e for e in evals}

out_dir = Path('outputs')
out_dir.mkdir(exist_ok=True)

for v in variants:
    vname  = v['name']
    ev     = eval_map.get(vname, {})
    zonen  = [Zone(**z) for z in v['zonen']]
    out_sl = out_dir / f"test_no_legend_{vname}.png"

    # NEU: show_legend=False, show_violations=False
    zeichne_layout(
        variante_name   = vname,
        beschreibung    = v.get('beschreibung', ''),
        zonen           = zonen,
        site_breite     = v['site_breite'],
        site_tiefe      = v['site_tiefe'],
        raster_x        = v.get('raster_x', 18.0),
        raster_y        = v.get('raster_y', 12.0),
        scores          = ev,
        gewichtung      = v.get('gewichtung', {}),
        output_path     = out_sl,
        nutzungstyp     = 'Produktion',
        site_geometry   = v.get('site_geometry'),
        building_envelope = v.get('building_envelope'),
        show_legend     = False,
        show_violations = False,
    )
    print(f"[OK] {out_sl}")

print("\nAlle PNGs erzeugt. Kein Legende-Bereich rechts, kein roter WARNUNG-Block.")

"""Test: Flur-Generator erzeugt VF-Korridore und PNG sieht korrekt aus."""
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

out_dir = Path('outputs')
out_dir.mkdir(exist_ok=True)

for site_id in ['A_kompakt', 'C_unregelmaessig']:
    print(f"\n{'='*55}")
    print(f"Site: {site_id}")
    site = get_demo_site(site_id)
    state = PlanningState(user_input={**BASE, 'grundstueck_id': site_id})
    state['site_geometry'] = site
    state['gap_strategy']  = 'corridor'   # Flur-Generator aktivieren
    state.update(briefing_agent(state))
    state.update(rule_agent(state))
    state.update(topology_agent(state))
    state.update(layout_strategy_agent(state))
    state.update(layout_agent(state))
    state.update(evaluation_agent(state))

    for v in state['variants']:
        vname = v['name']
        alle  = v['zonen']
        vf    = [z for z in alle if z.get('din_kategorie') == 'VF' and not z.get('schraffur')]
        norm  = [z for z in alle if not z.get('schraffur') and z.get('din_kategorie') != 'VF']
        ev    = next((e for e in state['evaluations'] if e['variante'] == vname), {})

        print(f"  {vname}: {len(norm)} Zonen + {len(vf)} VF-Flure")
        for f in vf:
            print(f"    Flur '{f['name']}': "
                  f"x={f['x']:.1f} y={f['y']:.1f} "
                  f"b={f['breite']:.1f}m × t={f['tiefe']:.1f}m")

        # PNG mit Fluren erzeugen (nur Variante A und C — squarified)
        if 'squarified' in vname.lower() or 'Materialfluss' in vname or 'Ausgewogen' in vname:
            zonen_obj = [Zone(**z) for z in alle]
            out_path  = out_dir / f"test_flur_{site_id}_{vname}.png"
            zeichne_layout(
                variante_name   = f"{vname} (Flur)",
                beschreibung    = v.get('beschreibung', ''),
                zonen           = zonen_obj,
                site_breite     = v['site_breite'],
                site_tiefe      = v['site_tiefe'],
                raster_x        = v.get('raster_x', 18.0),
                raster_y        = v.get('raster_y', 12.0),
                scores          = ev,
                gewichtung      = v.get('gewichtung', {}),
                output_path     = out_path,
                nutzungstyp     = 'Produktion',
                site_geometry   = v.get('site_geometry'),
                building_envelope = v.get('building_envelope'),
                show_legend     = False,
                show_violations = False,
            )
            print(f"    PNG: {out_path}")

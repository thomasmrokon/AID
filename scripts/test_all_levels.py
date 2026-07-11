"""
Test: Alle drei Planungsmassstabsebenen - Masterplanung, Layout, Prozessplanung.
Laeuft ca. 30-60s, gibt strukturierten Report auf stdout aus.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import contextlib
import traceback
from typing import Any, Callable

sys.path.insert(0, ".")

try:
    import app.tools.rhino_inside_runner as _rhino_inside_runner
    _rhino_inside_runner._available = False
except Exception:
    pass

from app.tools.site import get_demo_site
from app.agents.masterplan import masterplan_agent
from app.agents.briefing import briefing_agent
from app.agents.rules import rule_agent
from app.agents.topology import topology_agent
from app.agents.strategy import layout_strategy_agent
from app.agents.layout import layout_agent
from app.agents.process import process_layout_agent
from app.state import DEMO_MASCHINENPARK


SITE_IDS = ["A_kompakt", "B_langgezogen", "C_unregelmaessig"]
VARIANT_ORDER = ["A_Materialfluss", "B_Erweiterbarkeit", "C_Ausgewogen"]
MAX_ASPECT_RATIO = 4.0

BASE_INPUT: dict[str, Any] = {
    "nutzungstyp": "Produktion",
    "produktionsflaeche": 3000,
    "lager_rohstoffe": 600,
    "lager_fertigwaren": 600,
    "wareneingang": 250,
    "versand": 250,
    "qualitaetssicherung": 150,
    "buero_nuf2": 300,
    "buero_geschosse": 2,
    "technikflaeche_tf": None,
    "sozialraeume_nuf7": None,
    "sonderbedingungen": None,
    "kranbahn_erforderlich": False,
    "mep_lueftung": "mechanisch",
    "mep_sprinkler": False,
    "mep_druckluft": True,
    "mep_kaelte": False,
    "mep_usv_notstrom": False,
    "mep_it_kategorie": "basis",
    "tragwerk_typologie": "stahl",
    "tragwerk_lastklasse": "mittel",
}

AGENT_REFS = {
    "masterplan": "app/agents/masterplan.py::masterplan_agent",
    "briefing": "app/agents/briefing.py::briefing_agent",
    "rules": "app/agents/rules.py::rule_agent",
    "topology": "app/agents/topology.py::topology_agent",
    "strategy": "app/agents/strategy.py::layout_strategy_agent",
    "layout": "app/agents/layout.py::layout_agent",
    "process": "app/agents/process.py::process_layout_agent",
}


def _quiet_call(func: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return func(*args, **kwargs)


def _add_error(
    errors: list[dict[str, str]],
    *,
    site_id: str,
    ebene: str,
    message: str,
    reference: str,
    variant: str | None = None,
) -> None:
    errors.append({
        "site": site_id,
        "variant": variant or "-",
        "ebene": ebene,
        "message": message,
        "reference": reference,
    })


def _format_ok(ok: bool) -> str:
    return "OK" if ok else "FEHLER"


def _run_layout_pipeline(site_id: str, site: dict[str, Any], errors: list[dict[str, str]]) -> dict[str, Any] | None:
    state: dict[str, Any] = {
        "user_input": {**BASE_INPUT, "grundstueck_id": site_id},
        "site_geometry": site,
    }
    pipeline: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = [
        ("briefing", briefing_agent),
        ("rules", rule_agent),
        ("topology", topology_agent),
        ("strategy", layout_strategy_agent),
        ("layout", layout_agent),
    ]

    for label, func in pipeline:
        try:
            state.update(_quiet_call(func, state))
        except Exception as exc:
            _add_error(
                errors,
                site_id=site_id,
                ebene="Layoutplanung",
                message=f"Pipeline-Schritt '{label}' fehlgeschlagen: {exc}",
                reference=AGENT_REFS[label],
            )
            traceback.print_exc()
            return None

    return state


def _topology_node_names(state: dict[str, Any]) -> set[str]:
    topology = state.get("topology_diagram") or {}
    return {str(node.get("name")) for node in topology.get("nodes", []) if node.get("name")}


def _functional_zones(variant: dict[str, Any]) -> list[dict[str, Any]]:
    zones = variant.get("zonen") or []
    return [
        z for z in zones
        if not z.get("schraffur") and z.get("din_kategorie") not in {"VF", "AF"}
    ]


def _aspect_ratio_violations(zones: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for zone in zones:
        width = float(zone.get("breite") or zone.get("breite_m") or 0.0)
        depth = float(zone.get("tiefe") or zone.get("tiefe_m") or 0.0)
        if width <= 0 or depth <= 0:
            violations.append(f"{zone.get('name', '?')}: ungueltige Geometrie {width:.2f}x{depth:.2f}")
            continue
        ratio = max(width, depth) / min(width, depth)
        if ratio > MAX_ASPECT_RATIO:
            violations.append(f"{zone.get('name', '?')}={ratio:.2f}")
    return violations


def _select_process_zone(variant_a: dict[str, Any]) -> dict[str, Any] | None:
    zones = _functional_zones(variant_a)
    production_zones = [
        z for z in zones
        if z.get("din_kategorie") in {"NUF3", "NUF 3"} or "produktion" in str(z.get("name", "")).lower()
    ]
    if production_zones:
        return max(production_zones, key=lambda z: float(z.get("breite", 0)) * float(z.get("tiefe", 0)))
    if zones:
        return max(zones, key=lambda z: float(z.get("breite", 0)) * float(z.get("tiefe", 0)))
    return None


def _run_process_check(site_id: str, variant_a: dict[str, Any], errors: list[dict[str, str]]) -> bool:
    zone = _select_process_zone(variant_a)
    if not zone:
        _add_error(
            errors,
            site_id=site_id,
            ebene="Prozessplanung",
            message="Keine geeignete Zone aus Variante A fuer Prozessplanung gefunden.",
            reference=AGENT_REFS["layout"],
            variant="A_Materialfluss",
        )
        print("  Prozessplanung: FEHLER - keine Produktionszone gefunden")
        return False

    expected = sum(int(machine.get("anzahl", 1)) for machine in DEMO_MASCHINENPARK)
    process_state = {
        "process_input": {
            "zone_name": zone.get("name", "Produktion"),
            "zone_breite_m": float(zone.get("breite") or zone.get("breite_m") or 40.0),
            "zone_tiefe_m": float(zone.get("tiefe") or zone.get("tiefe_m") or 75.0),
            "maschinenpark": DEMO_MASCHINENPARK,
        }
    }

    try:
        result = _quiet_call(process_layout_agent, process_state)
    except Exception as exc:
        _add_error(
            errors,
            site_id=site_id,
            ebene="Prozessplanung",
            message=f"process_layout_agent fehlgeschlagen: {exc}",
            reference=AGENT_REFS["process"],
            variant="A_Materialfluss",
        )
        traceback.print_exc()
        return False

    layout = result.get("process_layout") or {}
    placed = len(layout.get("maschinen") or [])
    kpis = layout.get("kpis") or {}
    ok = placed == expected

    print(
        "  Prozessplanung: "
        f"Zone '{layout.get('zone_name', zone.get('name'))}', "
        f"Durchsatz={kpis.get('durchsatz_teile_pro_schicht', '-')}, "
        f"Engpass=Schritt {kpis.get('engpass_schritt', '-')}, "
        f"Materialflussweg={kpis.get('materialflussweg_m', '-')} m, "
        f"Maschinen={placed}/{expected} ({_format_ok(ok)})"
    )

    if not ok:
        _add_error(
            errors,
            site_id=site_id,
            ebene="Prozessplanung",
            message=f"Nicht alle Maschinen platziert: {placed}/{expected}.",
            reference=AGENT_REFS["process"],
            variant="A_Materialfluss",
        )
    return ok


def main() -> int:
    errors: list[dict[str, str]] = []
    variants_ok = 0
    grz_ok_count = 0
    process_ok_count = 0

    print("=" * 78)
    print("E2E-Diagnose: Masterplanung, Layoutplanung, Prozessplanung")
    print("=" * 78)

    for site_id in SITE_IDS:
        print(f"\nGrundstueck: {site_id}")
        print("-" * 78)
        site = get_demo_site(site_id)

        try:
            masterplan_result = masterplan_agent(site, grz_ziel=0.45)
            masterplan = masterplan_result.get("masterplan") or {}
            bilanz = masterplan.get("flaechenbilanz") or {}
            grz = float(bilanz.get("grz", 0.0))
            gfz = float(bilanz.get("gfz", 0.0))
            versiegelung = float(bilanz.get("versiegelungsgrad", 0.0))
            stellplaetze = int(bilanz.get("stellplaetze_anzahl", 0))
            grz_ok = grz <= 0.60
            if grz_ok:
                grz_ok_count += 1
            else:
                _add_error(
                    errors,
                    site_id=site_id,
                    ebene="Masterplanung",
                    message=f"GRZ {grz:.3f} ueberschreitet BauNVO-Grenzwert 0.60.",
                    reference=AGENT_REFS["masterplan"],
                )
            print(
                "  Masterplanung: "
                f"GRZ={grz:.3f}, GFZ={gfz:.3f}, "
                f"Versiegelung={versiegelung:.1%}, SP={stellplaetze} "
                f"({_format_ok(grz_ok)})"
            )
        except Exception as exc:
            _add_error(
                errors,
                site_id=site_id,
                ebene="Masterplanung",
                message=f"masterplan_agent fehlgeschlagen: {exc}",
                reference=AGENT_REFS["masterplan"],
            )
            traceback.print_exc()
            print(f"  Masterplanung: FEHLER - {exc}")

        state = _run_layout_pipeline(site_id, site, errors)
        if not state:
            continue

        topology_names = _topology_node_names(state)
        variants = state.get("variants") or []
        variant_map = {variant.get("name"): variant for variant in variants}
        print(f"  Layoutplanung: Topologie-Knoten={len(topology_names)}, Varianten={len(variants)}")

        for variant_name in VARIANT_ORDER:
            variant = variant_map.get(variant_name)
            if not variant:
                _add_error(
                    errors,
                    site_id=site_id,
                    ebene="Layoutplanung",
                    message="Variante fehlt im Layout-Ergebnis.",
                    reference=AGENT_REFS["layout"],
                    variant=variant_name,
                )
                print(f"    {variant_name}: FEHLER - Variante fehlt")
                continue

            zones = _functional_zones(variant)
            zone_names = {str(zone.get("name")) for zone in zones if zone.get("name")}
            missing = sorted(topology_names - zone_names)
            ar_violations = _aspect_ratio_violations(zones)
            ok = not missing and not ar_violations
            if ok:
                variants_ok += 1

            if missing:
                _add_error(
                    errors,
                    site_id=site_id,
                    ebene="Layoutplanung",
                    message=f"Topologie-Zonen fehlen im Layout: {', '.join(missing)}.",
                    reference=f"{AGENT_REFS['topology']} -> {AGENT_REFS['layout']}",
                    variant=variant_name,
                )
            if ar_violations:
                _add_error(
                    errors,
                    site_id=site_id,
                    ebene="Layoutplanung",
                    message=f"Aspect-Ratio > {MAX_ASPECT_RATIO:.1f}: {', '.join(ar_violations)}.",
                    reference=AGENT_REFS["layout"],
                    variant=variant_name,
                )

            print(
                f"    {variant_name}: Zonen={len(zones)}, "
                f"alle Zonen={'ja' if not missing else 'nein'}, "
                f"AR-Violations={len(ar_violations)} ({_format_ok(ok)})"
            )
            if missing:
                print(f"      Fehlend: {', '.join(missing)}")
            if ar_violations:
                print(f"      AR: {', '.join(ar_violations)}")

        variant_a = variant_map.get("A_Materialfluss")
        if variant_a and _run_process_check(site_id, variant_a, errors):
            process_ok_count += 1

    print("\n" + "=" * 78)
    print("ZUSAMMENFASSUNG")
    print("=" * 78)
    print(f"Gesamtergebnis: {variants_ok}/9 Varianten OK, {grz_ok_count}/3 Grundstuecke GRZ-konform")
    print(f"Prozessplanung: {process_ok_count}/3 Grundstuecke mit vollstaendig platziertem Maschinenpark")

    if errors:
        print("\nFehler:")
        for idx, err in enumerate(errors, 1):
            print(
                f"  {idx:02d}. [{err['site']} | {err['variant']} | {err['ebene']}] "
                f"{err['message']} ({err['reference']})"
            )
        return 1

    print("\nAlle Checks bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

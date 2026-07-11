"""
Diagnose-Script fuer Rhino.Compute HTTP 500 Fehler.

Testet verschiedene Payload-Formate und Parameter-Namenskonventionen:
  1. Einfacher Test: Kein Python-Script (nur Number/Panel-Komponente via Pointer)
  2. GhPython-Format:  ParamName = "ZoneDataJSON"
  3. Python3-Script-Format: ParamName = "RH_IN:ZoneDataJSON"
  4. Korrekte InnerTree-Struktur: { "{ 0; }": [...] } statt { "0": [...] }

Aufruf: python scripts/debug_compute.py
"""

import base64
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("FEHLER: 'requests' nicht installiert  ->  pip install requests")
    sys.exit(1)

COMPUTE_URL = "http://localhost:5000"
GH_FILE = Path(__file__).parent.parent / "app" / "tools" / "grasshopper" / "layout_renderer.gh"


def _b64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _post(payload: dict, label: str) -> None:
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    try:
        resp = requests.post(
            f"{COMPUTE_URL}/grasshopper",
            json=payload,
            timeout=30,
        )
        print(f"  Status:       {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('Content-Type', '-')}")
        body = resp.text[:500] if resp.text else "(leer)"
        print(f"  Body:         {body}")
        if resp.status_code == 200:
            data = resp.json()
            errors = data.get("errors") or []
            warnings = data.get("warnings") or []
            values = data.get("values") or []
            print(f"  -> Errors:   {errors}")
            print(f"  -> Warnings: {warnings}")
            print(f"  -> Values:   {len(values)} Output-Parameter")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")


# ── Vorbereitung ─────────────────────────────────────────────────────────────

# Minimal-JSON (nur 2 Zonen)
sample_json = json.dumps([
    {
        "name": "Test-Zone",
        "x": 0, "y": 0, "breite": 18, "tiefe": 18,
        "flaeche_m2": 324, "planned_area_m2": 324,
        "din_kategorie": "NUF 4", "farbe": "#5B8DB8",
        "schraffur": False, "floors": 1,
    }
], ensure_ascii=False)

if not GH_FILE.exists():
    print(f"GH-Datei nicht gefunden: {GH_FILE}")
    sys.exit(1)

algo_b64 = _b64_file(GH_FILE)
print(f"GH-Datei: {GH_FILE.name}  ({GH_FILE.stat().st_size:,} Bytes, {len(algo_b64):,} B64-Zeichen)")

# ── Server-Check ─────────────────────────────────────────────────────────────
try:
    ver = requests.get(f"{COMPUTE_URL}/version", timeout=3).json()
    print(f"Server: Rhino {ver.get('rhino')} / Compute {ver.get('compute')}")
except Exception as e:
    print(f"Server nicht erreichbar: {e}")
    sys.exit(1)

# ── Test 1: GhPython-Konvention, alte InnerTree-Key-Syntax ───────────────────
_post({
    "algo": algo_b64,
    "pointer": None,
    "values": [{
        "ParamName": "ZoneDataJSON",
        "InnerTree": {
            "0": [{"type": "System.String", "data": json.dumps(sample_json)}]
        }
    }]
}, 'ParamName="ZoneDataJSON", InnerTree key="0"')

# ── Test 2: GhPython-Konvention, korrekte InnerTree-Key-Syntax ───────────────
_post({
    "algo": algo_b64,
    "pointer": None,
    "values": [{
        "ParamName": "ZoneDataJSON",
        "InnerTree": {
            "{ 0; }": [{"type": "System.String", "data": json.dumps(sample_json)}]
        }
    }]
}, 'ParamName="ZoneDataJSON", InnerTree key="{ 0; }"')

# ── Test 3: Python3-Script-Konvention, RH_IN:-Prefix ────────────────────────
_post({
    "algo": algo_b64,
    "pointer": None,
    "values": [{
        "ParamName": "RH_IN:ZoneDataJSON",
        "InnerTree": {
            "{ 0; }": [{"type": "System.String", "data": json.dumps(sample_json)}]
        }
    }]
}, 'ParamName="RH_IN:ZoneDataJSON", InnerTree key="{ 0; }"')

# ── Test 4: Leere values (keine Inputs) ──────────────────────────────────────
_post({
    "algo": algo_b64,
    "pointer": None,
    "values": []
}, 'Keine Input-Values (leere Liste)')

# ── Test 5: compute-rhino3d Library direkt ───────────────────────────────────
print(f"\n{'='*60}")
print("TEST: compute-rhino3d Python-Library")
try:
    import compute_rhino3d.Util as util
    import compute_rhino3d.Grasshopper as gh
    util.url = f"{COMPUTE_URL}/"
    tree = gh.DataTree("ZoneDataJSON")
    tree.Append([0], [sample_json])
    result = gh.EvaluateDefinition(str(GH_FILE), [tree])
    errors = result.get("errors") or []
    values = result.get("values") or []
    print(f"  -> OK — {len(values)} Values, {len(errors)} Errors")
    if errors:
        print(f"  -> Errors: {errors}")
except ImportError:
    print("  compute-rhino3d nicht installiert")
except Exception as e:
    print(f"  EXCEPTION: {e}")

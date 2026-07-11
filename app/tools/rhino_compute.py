"""
AID Demo — Rhino.Compute Integration

Wrapper für Rhino.Compute REST API (Hops-Bundle, Rhino 8).
Server-URL: http://localhost:5000
Executable:  C:\\Users\\thoma\\AppData\\Roaming\\McNeel\\Rhinoceros\\packages\\8.0\\Hops\\0.16.28\\rhino.compute\\rhino.compute.exe
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

COMPUTE_URL    = "http://localhost:5000/"
COMPUTE_EXE    = Path(r"C:\Users\thoma\AppData\Roaming\McNeel\Rhinoceros\packages\8.0\Hops\0.16.28\rhino.compute\rhino.compute.exe")
GH_TEMPLATE    = Path(__file__).parent / "grasshopper" / "layout_renderer.gh"

try:
    import compute_rhino3d.Util as _util
    import compute_rhino3d.Grasshopper as _gh
    _util.url = COMPUTE_URL
    _CLIENT_AVAILABLE = True
except ImportError:
    _CLIENT_AVAILABLE = False

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Server-Verwaltung
# ---------------------------------------------------------------------------

def is_running(timeout: float = 2.0) -> bool:
    """True wenn Rhino.Compute auf localhost:5000 erreichbar ist."""
    if not _REQUESTS_AVAILABLE:
        return False
    try:
        return _requests.get(f"{COMPUTE_URL}version", timeout=timeout).status_code == 200
    except Exception:
        return False


def server_version() -> dict | None:
    """Gibt {'rhino': '...', 'compute': '...'} zurück, oder None."""
    if not _REQUESTS_AVAILABLE:
        return None
    try:
        resp = _requests.get(f"{COMPUTE_URL}version", timeout=2.0)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


def start_server(wait_seconds: int = 8) -> bool:
    """
    Startet rhino.compute.exe im Hintergrund falls noch nicht aktiv.
    Gibt True zurück wenn der Server danach erreichbar ist.
    """
    if is_running():
        print("[compute] Server läuft bereits.")
        return True

    if not COMPUTE_EXE.exists():
        print(f"[compute] Executable nicht gefunden: {COMPUTE_EXE}")
        return False

    print(f"[compute] Starte: {COMPUTE_EXE}")
    try:
        import os as _os
        _os.startfile(str(COMPUTE_EXE))
    except Exception:
        subprocess.Popen(
            [str(COMPUTE_EXE)],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )

    import time
    for i in range(wait_seconds):
        time.sleep(1)
        if is_running():
            ver = server_version()
            print(f"[compute] Server bereit — Rhino {ver.get('rhino')} / Compute {ver.get('compute')}")
            return True

    print("[compute] Timeout: Server antwortet nicht.")
    return False


# ---------------------------------------------------------------------------
# Grasshopper-Ausführung
# ---------------------------------------------------------------------------

def run_grasshopper_layout(
    zonen: list[dict] | str,
    gh_file: Path | None = None,
) -> dict | None:
    """
    Führt die Grasshopper-Layout-Definition auf Rhino.Compute aus.

    Args:
        zonen:    Zonendaten als Dict-Liste oder JSON-String
        gh_file:  Pfad zur .gh-Datei (Default: app/tools/grasshopper/layout_renderer.gh)

    Returns:
        Rohes Ergebnis-Dict von Compute, oder None bei Fehler.

    Voraussetzungen:
        - Rhino.Compute läuft (start_server() oder manuell)
        - pip install compute-rhino3d
        - GH-Definition vorhanden (siehe grasshopper/SETUP.md)
    """
    gh_path = gh_file or GH_TEMPLATE

    if not gh_path.exists():
        print(f"[compute] GH-Definition fehlt: {gh_path}")
        print("[compute] -> Anleitung: app/tools/grasshopper/SETUP.md")
        return None

    if not is_running():
        print("[compute] Server nicht erreichbar — start_server() aufrufen")
        return None

    if not _CLIENT_AVAILABLE:
        print("[compute] compute-rhino3d fehlt — pip install compute-rhino3d")
        return None

    json_str = json.dumps(zonen, ensure_ascii=False) if isinstance(zonen, list) else zonen

    try:
        _util.url = COMPUTE_URL
        tree = _gh.DataTree("ZoneDataJSON")
        tree.Append([0], [json_str])

        result = _gh.EvaluateDefinition(str(gh_path), [tree])

        errors   = result.get("errors")   or []
        warnings = result.get("warnings") or []
        if errors:
            print(f"[compute] GH-Fehler: {errors}")
        if warnings:
            print(f"[compute] GH-Warnungen: {warnings}")

        values = result.get("values") or []
        print(f"[compute] GH-Auswertung OK — {len(values)} Output-Parameter")
        return result

    except Exception as e:
        print(f"[compute] Fehler bei GH-Auswertung: {e}")
        return None


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

def diagnose() -> None:
    """Zeigt vollständigen Status der Rhino.Compute-Integration."""
    print("=== Rhino.Compute Diagnose ===")
    print(f"  compute-rhino3d:  {'OK' if _CLIENT_AVAILABLE else 'FEHLT -> pip install compute-rhino3d'}")
    print(f"  requests:         {'OK' if _REQUESTS_AVAILABLE else 'FEHLT -> pip install requests'}")
    print(f"  Executable:       {'OK' if COMPUTE_EXE.exists() else 'FEHLT'}")
    print(f"    {COMPUTE_EXE}")
    print(f"  GH-Definition:    {'OK' if GH_TEMPLATE.exists() else 'FEHLT -> SETUP.md'}")
    print(f"    {GH_TEMPLATE}")

    if is_running():
        ver = server_version() or {}
        print(f"  Server:           ERREICHBAR ({COMPUTE_URL})")
        print(f"    Rhino {ver.get('rhino', '?')} / Compute {ver.get('compute', '?')}")
    else:
        print(f"  Server:           NICHT ERREICHBAR ({COMPUTE_URL})")
        print("    -> start_server() aufrufen oder compute.rhino3d.exe manuell starten")
    print("==============================")

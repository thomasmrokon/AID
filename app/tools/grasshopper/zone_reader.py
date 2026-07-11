"""
AID Demo — IronPython 2 Script fuer Grasshopper (GhPython-kompatibel)

Diese Datei in eine "IronPython 2 Script"-Komponente in Grasshopper einfuegen.
Es liest Zone-Daten als JSON und erzeugt 3D-Volumenkörper + Labels.

GhPython Inputs (im Komponenten-Editor definieren):
  ZoneDataJSON  (str)  - Zonen-JSON oder Pfad zur .json-Datei
                         Quelle: outputs/zones_<Variante>.json

GhPython Outputs:
  geometries  (List[Brep])      - Extrudierte 3D-Zonen
  labels      (List[TextDot])   - Zonenbeschriftungen
  colors      (List[Color])     - Farben fuer Custom Preview
  info        (str)             - Statusmeldung

Verbindung im Grasshopper-Canvas:
  File Path --> ZoneDataJSON
  geometries  --> Custom Preview --> Geometry
  colors      --> Custom Preview --> Material / Shader
  labels      --> (optional) TextDot direkt rendern
"""

import json
import io
import Rhino.Geometry as rg
import System.Drawing as sd

# Gebäudehöhen nach DIN-Kategorie (Grundhöhe, × floors)
_HEIGHTS = {
    "NUF 2": 3.5,
    "NUF 3": 9.0,
    "NUF 4": 9.0,
    "NUF 7": 3.5,
    "TF":    4.5,
    "VF":    4.0,
}

_NAME_OVERRIDES = {
    "hochregal":  18.0,
    "whitespace":  4.0,
    "usv":         5.0,
    "kühlung":     5.0,
    "notstrom":    5.0,
}


def _zone_height(din, floors, schraffur, name):
    if schraffur:
        return 0.25
    nl = name.lower()
    for frag, h in _NAME_OVERRIDES.items():
        if frag in nl:
            return h
    return _HEIGHTS.get(din, 5.0) * max(1, floors)


def _hex_color(hex_str):
    h = hex_str.lstrip("#")
    return sd.Color.FromArgb(255, int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _make_box(x, y, w, d, h):
    pts = [
        rg.Point3d(x,     y,     0),
        rg.Point3d(x + w, y,     0),
        rg.Point3d(x + w, y + d, 0),
        rg.Point3d(x,     y + d, 0),
        rg.Point3d(x,     y,     0),
    ]
    profile = rg.PolylineCurve(pts)
    extrusion = rg.Extrusion.Create(profile, h, True)
    return extrusion.ToBrep() if extrusion else None


# ── Hauptlogik ─────────────────────────────────────────────────────────────
# ZoneDataJSON wird von Grasshopper als Input-Parameter injiziert.
# Der Default erlaubt die Datei auch außerhalb von GH zu öffnen (IDE, Tests).
ZoneDataJSON = locals().get("ZoneDataJSON", "[]")  # type: ignore[assignment]

geometries = []
labels     = []
colors     = []
info       = ""

import os

def _load_zones(raw):
    """Akzeptiert einen JSON-String ODER einen Dateipfad zur .json-Datei."""
    raw = str(raw).strip() if raw else ""
    if not raw:
        return []
    # Dateipfad? -> Datei lesen
    if os.path.isfile(raw):
        with io.open(raw, encoding="utf-8") as f:
            return json.loads(f.read())
    # Direkter JSON-String
    return json.loads(raw)

try:
    zones = _load_zones(ZoneDataJSON)
    n_ok  = 0

    for z in zones:
        x   = float(z["x"])
        y   = float(z["y"])
        w   = float(z["breite"])
        d   = float(z["tiefe"])
        h   = _zone_height(
            z.get("din_kategorie", "NUF 4"),
            int(z.get("floors", 1)),
            bool(z.get("schraffur", False)),
            z.get("name", ""),
        )

        brep = _make_box(x, y, w, d, h)
        if brep:
            geometries.append(brep)
            colors.append(_hex_color(z.get("farbe", "#CCCCCC")))

            area    = float(z.get("planned_area_m2") or z.get("flaeche_m2", 0))
            floors  = int(z.get("floors", 1))
            floor_s = " | {}G".format(floors) if floors > 1 else ""
            dot     = rg.TextDot(
                "{}\n{:.0f} m2{}".format(z["name"], area, floor_s),
                rg.Point3d(x + w / 2, y + d / 2, h + 0.5),
            )
            labels.append(dot)
            n_ok += 1

    info = "OK - {}/{} Zonen geladen".format(n_ok, len(zones))

except ValueError as e:
    ghenv.Component.AddRuntimeMessage(
        ghenv.Component.RuntimeMessageLevel.Error,
        "JSON-Fehler: {}".format(e),
    )
    info = "JSON-Fehler: {}".format(e)

except Exception as e:
    ghenv.Component.AddRuntimeMessage(
        ghenv.Component.RuntimeMessageLevel.Warning,
        "Fehler: {}".format(e),
    )
    info = "Fehler: {}".format(e)

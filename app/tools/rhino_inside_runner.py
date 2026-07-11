"""
AID Demo — rhinoinside Geometry Runner

Fuehrt die Zone-Geometrieerzeugung direkt in Python via rhinoinside aus,
ohne Rhino.Compute-Server oder Grasshopper. Erzeugt Brep-Volumen und
exportiert vollstaendige .3dm-Dateien mit Rhino-nativer IO.

Voraussetzung: pip install rhinoinside  (schon installiert)
               Rhino 8 unter C:/Program Files/Rhino 8/System/
"""

from __future__ import annotations

import json
import os
from pathlib import Path

RHINO8_SYSTEM_PATH = r"C:\Program Files\Rhino 8\System"

_loaded = False
_available: bool | None = None


def ist_verfuegbar() -> bool:
    """True wenn rhinoinside + Rhino 8 geladen werden koennen."""
    global _available
    if _available is not None:
        return _available
    try:
        _ensure_loaded()
        _available = True
    except Exception as e:
        print(f"[rhinoinside] Nicht verfuegbar: {e}")
        _available = False
    return _available


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    import rhinoinside
    rhinoinside.load(RHINO8_SYSTEM_PATH)
    _loaded = True


# ---------------------------------------------------------------------------
# Geometrie-Erzeugung (portiert aus zone_reader.py)
# ---------------------------------------------------------------------------

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


def _zone_height(din: str, floors: int, schraffur: bool, name: str) -> float:
    if schraffur:
        return 0.25
    nl = name.lower()
    for frag, h in _NAME_OVERRIDES.items():
        if frag in nl:
            return h
    return _HEIGHTS.get(din, 5.0) * max(1, floors)


def _hex_to_argb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def run_zone_geometry(zonen: list[dict]) -> dict:
    """
    Erzeugt Rhino-Geometrie aus Zonendaten.

    Returns:
        {"breps": [...], "labels": [...], "colors": [...], "info": str}
    """
    _ensure_loaded()

    import Rhino.Geometry as rg

    breps  = []
    labels = []
    colors = []

    for z in zonen:
        x  = float(z["x"])
        y  = float(z["y"])
        w  = float(z["breite"])
        d  = float(z["tiefe"])
        h  = _zone_height(
            z.get("din_kategorie", "NUF 4"),
            int(z.get("floors", 1)),
            bool(z.get("schraffur", False)),
            z.get("name", ""),
        )

        box  = rg.Box(
            rg.Plane.WorldXY,
            rg.Interval(x, x + w),
            rg.Interval(y, y + d),
            rg.Interval(0, h),
        )
        brep = rg.Brep.CreateFromBox(box)
        if brep:
            breps.append(brep)
            r, g_val, b = _hex_to_argb(z.get("farbe", "#CCCCCC"))
            colors.append((r, g_val, b))

            area    = float(z.get("planned_area_m2") or z.get("flaeche_m2", 0))
            floors  = int(z.get("floors", 1))
            floor_s = f" | {floors}G" if floors > 1 else ""
            dot = rg.TextDot(
                f"{z['name']}\n{area:.0f} m\xb2{floor_s}",
                rg.Point3d(x + w / 2, y + d / 2, h + 0.5),
            )
            labels.append(dot)

    info = f"OK — {len(breps)}/{len(zonen)} Zonen"
    return {"breps": breps, "labels": labels, "colors": colors, "info": info}


# ---------------------------------------------------------------------------
# 3DM-Export mit nativer Rhino-IO
# ---------------------------------------------------------------------------

def export_3dm(
    variante_name: str,
    zonen: list[dict],
    site_breite: float,
    site_tiefe: float,
    output_path: Path,
) -> bool:
    """
    Exportiert vollstaendige .3dm-Datei mit Rhino-nativer IO (besser als rhino3dm).
    Layer-Struktur: Site / Zonen / Labels
    """
    _ensure_loaded()

    import Rhino
    import Rhino.Geometry as rg
    import Rhino.DocObjects as rdo
    import System.Drawing as sd

    doc = Rhino.RhinoDoc.CreateHeadless(None)
    if doc is None:
        print("[rhinoinside] CreateHeadless fehlgeschlagen")
        return False

    try:
        # Site-Umriss
        site_layer_idx = doc.Layers.Add("Site", sd.Color.FromArgb(255, 80, 80, 80))
        site_rect  = rg.Rectangle3d(rg.Plane.WorldXY, site_breite, site_tiefe)
        site_curve = site_rect.ToNurbsCurve()
        a_site = Rhino.DocObjects.ObjectAttributes()
        a_site.LayerIndex = site_layer_idx
        doc.Objects.AddCurve(site_curve, a_site)

        # Zonen-Layer
        zonen_layer_idx = doc.Layers.Add("Zonen", sd.Color.FromArgb(255, 60, 120, 200))
        label_layer_idx = doc.Layers.Add("Labels", sd.Color.FromArgb(255, 40, 40, 40))

        geo_result = run_zone_geometry(zonen)

        for i, (brep, col) in enumerate(zip(geo_result["breps"], geo_result["colors"])):
            r, g_val, b = col
            attr = Rhino.DocObjects.ObjectAttributes()
            attr.LayerIndex = zonen_layer_idx
            attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
            attr.ObjectColor = sd.Color.FromArgb(200, r, g_val, b)
            doc.Objects.AddBrep(brep, attr)

        for dot in geo_result["labels"]:
            a_lbl = Rhino.DocObjects.ObjectAttributes()
            a_lbl.LayerIndex = label_layer_idx
            doc.Objects.AddTextDot(dot, a_lbl)

        doc.Notes = f"AID Demo — Variante {variante_name}\n{geo_result['info']}"

        opts = Rhino.FileIO.FileWriteOptions()
        ok = doc.WriteFile(str(output_path), opts)
        return ok

    finally:
        doc.Dispose()


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

def diagnose() -> None:
    print("=== rhinoinside Diagnose ===")
    try:
        import rhinoinside
        print(f"  rhinoinside:      OK (installiert)")
    except ImportError:
        print("  rhinoinside:      FEHLT — pip install rhinoinside")
        return

    system_path = Path(RHINO8_SYSTEM_PATH)
    print(f"  Rhino 8 System:   {'OK' if system_path.exists() else 'FEHLT'}")
    print(f"    {system_path}")

    if ist_verfuegbar():
        import Rhino
        print(f"  Rhino-Version:    {Rhino.RhinoApp.Version}")
        print("  Status:           BEREIT")
    else:
        print("  Status:           NICHT VERFUEGBAR")
    print("============================")

"""
AID Demo — Rhino 3DM Geometrie-Export

Erzeugt Rhino 3D-Modelle aus Zone-Daten ohne Rhino.Compute (rhino3dm, lizenzfrei).
Jede Zone wird als extrudierter Volumenkörper mit typspezifischer Gebäudehöhe modelliert.

Coordinate System:
  X = Ost (Breite), Y = Nord (Tiefe), Z = Höhe
  Entspricht Rhino-Draufsicht (Top View).
"""

from __future__ import annotations

from pathlib import Path

try:
    import rhino3dm
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

from app.tools.geometry import Zone


# ---------------------------------------------------------------------------
# Gebäudehöhen nach DIN-Kategorie (Grundhöhe in Metern, × floors)
# ---------------------------------------------------------------------------

_BASE_HEIGHTS: dict[str, float] = {
    "NUF 2": 3.5,   # Büro / Verwaltung pro Geschoss
    "NUF 3": 9.0,   # Produktion, Whitespace IT
    "NUF 4": 9.0,   # Lager, Logistik
    "NUF 7": 3.5,   # Sozialräume pro Geschoss
    "TF":    4.5,   # Technikfläche
    "VF":    4.0,   # Verkehrs- / Erschließungsfläche
}

_NAME_HEIGHT_OVERRIDES: dict[str, float] = {
    "hochregal": 18.0,
    "whitespace": 4.0,
    "usv":        5.0,
    "kühlung":    5.0,
    "kühl":       5.0,
    "notstrom":   5.0,
    "generator":  5.0,
}

_EXPANSION_HEIGHT = 0.25  # Erweiterungszone: nur Bodenmarkierung


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _zone_hoehe(zone: Zone) -> float:
    """Bestimmt die Gebäudehöhe einer Zone in Metern."""
    if zone.schraffur:
        return _EXPANSION_HEIGHT
    name_lower = zone.name.lower()
    for fragment, h in _NAME_HEIGHT_OVERRIDES.items():
        if fragment in name_lower:
            return h
    base = _BASE_HEIGHTS.get(zone.din_kategorie, 5.0)
    return base * max(1, zone.floors)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _set_layer_color(layer, r: int, g: int, b: int) -> None:
    try:
        layer.Color = (r, g, b, 255)
    except (TypeError, AttributeError):
        try:
            layer.Color = rhino3dm.Color.FromArgb(255, r, g, b)
        except Exception:
            pass


def _set_object_color(attrs, r: int, g: int, b: int) -> None:
    try:
        attrs.ObjectColor = (r, g, b, 255)
        attrs.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
    except (TypeError, AttributeError):
        try:
            attrs.ObjectColor = rhino3dm.Color.FromArgb(255, r, g, b)
            attrs.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
        except Exception:
            pass


def _add_layer(model, name: str, r: int, g: int, b: int) -> int:
    layer = rhino3dm.Layer()
    layer.Name = name
    _set_layer_color(layer, r, g, b)
    return model.Layers.Add(layer)


# ---------------------------------------------------------------------------
# Geometrie-Bausteine
# ---------------------------------------------------------------------------

def _add_site_boundary(model, site_breite: float, site_tiefe: float, layer_idx: int) -> None:
    pts = [
        rhino3dm.Point3d(0, 0, 0),
        rhino3dm.Point3d(site_breite, 0, 0),
        rhino3dm.Point3d(site_breite, site_tiefe, 0),
        rhino3dm.Point3d(0, site_tiefe, 0),
        rhino3dm.Point3d(0, 0, 0),
    ]
    curve = rhino3dm.PolylineCurve(pts)
    attrs = rhino3dm.ObjectAttributes()
    attrs.LayerIndex = layer_idx
    attrs.Name = "Site_Grenze"
    model.Objects.AddCurve(curve, attrs)


def _add_raster_lines(
    model,
    site_breite: float,
    site_tiefe: float,
    raster_x: float,
    raster_y: float,
    layer_idx: int,
) -> None:
    attrs = rhino3dm.ObjectAttributes()
    attrs.LayerIndex = layer_idx

    x = raster_x
    while x < site_breite - 0.1:
        line = rhino3dm.LineCurve(
            rhino3dm.Point3d(x, 0, 0),
            rhino3dm.Point3d(x, site_tiefe, 0),
        )
        model.Objects.AddCurve(line, attrs)
        x += raster_x

    y = raster_y
    while y < site_tiefe - 0.1:
        line = rhino3dm.LineCurve(
            rhino3dm.Point3d(0, y, 0),
            rhino3dm.Point3d(site_breite, y, 0),
        )
        model.Objects.AddCurve(line, attrs)
        y += raster_y


def _add_zone_volume(model, zone: Zone, height: float, layer_idx: int) -> None:
    """Fügt eine Zone als extrudierten Volumenkörper ein."""
    x, y, w, d = zone.x, zone.y, zone.breite, zone.tiefe
    r, g, b = _hex_to_rgb(zone.farbe)

    attrs = rhino3dm.ObjectAttributes()
    attrs.LayerIndex = layer_idx
    attrs.Name = zone.name
    _set_object_color(attrs, r, g, b)

    # Profilkurve (geschlossenes Rechteck in XY-Ebene)
    pts = [
        rhino3dm.Point3d(x, y, 0),
        rhino3dm.Point3d(x + w, y, 0),
        rhino3dm.Point3d(x + w, y + d, 0),
        rhino3dm.Point3d(x, y + d, 0),
        rhino3dm.Point3d(x, y, 0),
    ]
    profile = rhino3dm.PolylineCurve(pts)

    # Extrusion bevorzugen (leichtgewichtiger als Mesh)
    try:
        extrusion = rhino3dm.Extrusion.Create(profile, height, True)
        if extrusion:
            model.Objects.AddExtrusion(extrusion, attrs)
            return
    except Exception:
        pass

    # Fallback: Mesh-Box
    mesh = rhino3dm.Mesh()
    for vx, vy, vz in [
        (x,     y,     0), (x + w, y,     0), (x + w, y + d, 0), (x,     y + d, 0),
        (x,     y,     height), (x + w, y,     height), (x + w, y + d, height), (x, y + d, height),
    ]:
        mesh.Vertices.Add(vx, vy, vz)

    mesh.Faces.AddFace(0, 3, 2, 1)  # Boden
    mesh.Faces.AddFace(4, 5, 6, 7)  # Dach
    mesh.Faces.AddFace(0, 1, 5, 4)  # Süd
    mesh.Faces.AddFace(1, 2, 6, 5)  # Ost
    mesh.Faces.AddFace(2, 3, 7, 6)  # Nord
    mesh.Faces.AddFace(3, 0, 4, 7)  # West
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    model.Objects.AddMesh(mesh, attrs)


def _add_zone_label(model, zone: Zone, height: float, layer_idx: int) -> None:
    """Fügt ein TextDot-Label in der Zonenmitte ein."""
    cx = zone.x + zone.breite / 2
    cy = zone.y + zone.tiefe / 2
    z_label = height + 0.5

    planned = zone.planned_area_m2 or zone.flaeche_m2
    lines = [zone.name, f"{planned:.0f} m2"]
    if zone.floors > 1:
        lines.append(f"{zone.floors} Geschosse")
    if zone.schraffur:
        lines.append("(Erweiterungsreserve)")
    label_text = " | ".join(lines)

    try:
        attrs = rhino3dm.ObjectAttributes()
        attrs.LayerIndex = layer_idx
        attrs.Name = f"Label_{zone.name}"
        # AddTextDot(text: str, location: Point3d, attributes)
        model.Objects.AddTextDot(label_text, rhino3dm.Point3d(cx, cy, z_label), attrs)
    except Exception:
        pass


def _add_compass(model, site_breite: float, site_tiefe: float, layer_idx: int) -> None:
    """Fügt einen Nordpfeil rechts neben dem Grundstück ein."""
    px = site_breite + 4.0
    py_base = site_tiefe * 0.75
    py_tip  = py_base + 8.0

    attrs = rhino3dm.ObjectAttributes()
    attrs.LayerIndex = layer_idx
    attrs.Name = "Nordpfeil"

    try:
        shaft = rhino3dm.LineCurve(
            rhino3dm.Point3d(px, py_base, 0),
            rhino3dm.Point3d(px, py_tip, 0),
        )
        model.Objects.AddCurve(shaft, attrs)
        model.Objects.AddTextDot("N", rhino3dm.Point3d(px, py_tip + 1.5, 0), attrs)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Haupt-Export
# ---------------------------------------------------------------------------

def exportiere_rhino_3dm(
    variante_name: str,
    zonen: list[Zone],
    site_breite: float,
    site_tiefe: float,
    raster_x: float,
    raster_y: float,
    output_path: Path,
) -> bool:
    """
    Exportiert ein Grundrisslayout als Rhino 3DM-Datei.

    Erzeugt 3D-Volumenkörper pro Zone mit typspezifischen Gebäudehöhen,
    Stützenraster, Grundstücksgrenze, Nordpfeil und TextDot-Labels.

    Benötigt: pip install rhino3dm
    Keine Rhino-Lizenz erforderlich.

    Returns:
        True wenn erfolgreich, False wenn rhino3dm nicht installiert.
    """
    if not _AVAILABLE:
        print("[rhino3dm] Bibliothek nicht installiert — pip install rhino3dm")
        return False

    model = rhino3dm.File3dm()
    model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters

    # --- Layer-Struktur ---
    layer_site   = _add_layer(model, "Site_Grenze",   80,  80,  80)
    layer_raster = _add_layer(model, "Stuetzenraster", 190, 190, 190)
    layer_labels = _add_layer(model, "Beschriftungen",  30,  30,  30)
    layer_compass = _add_layer(model, "Nordpfeil",      50,  50,  50)

    # Zonen-Layer (ein Layer pro DIN-Kategorie)
    din_layers: dict[str, int] = {}

    def _zone_layer(zone: Zone) -> int:
        key = zone.din_kategorie
        if key not in din_layers:
            r, g, b = _hex_to_rgb(zone.farbe)
            din_layers[key] = _add_layer(model, key, r, g, b)
        return din_layers[key]

    # --- Geometrie ---
    _add_site_boundary(model, site_breite, site_tiefe, layer_site)
    _add_raster_lines(model, site_breite, site_tiefe, raster_x, raster_y, layer_raster)
    _add_compass(model, site_breite, site_tiefe, layer_compass)

    for zone in zonen:
        lyr  = _zone_layer(zone)
        hoehe = _zone_hoehe(zone)
        _add_zone_volume(model, zone, hoehe, lyr)
        _add_zone_label(model, zone, hoehe, layer_labels)

    # --- Schreiben ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = model.Write(str(output_path), 7)  # Rhino 7/8 Format
    if ok:
        print(f"[rhino3dm] 3DM gespeichert: {output_path}")
    else:
        print(f"[rhino3dm] Schreibfehler: {output_path}")
    return bool(ok)


def ist_verfuegbar() -> bool:
    """True wenn rhino3dm installiert ist."""
    return _AVAILABLE

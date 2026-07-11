"""
AID Demo – Geometrie-Hilfsfunktionen
Einfache Rechteck-Utilities auf Basis lokaler Meter-Koordinaten.
Shapely wird für Flächenberechnungen und Schnittprüfungen genutzt.
"""

from __future__ import annotations
import functools
import math
from dataclasses import dataclass, field
from pathlib import Path
from shapely.geometry import box as shapely_box, Point

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore


# ---------------------------------------------------------------------------
# Datenstruktur: Zone
# CONTRACT: Owner = Claude Code. Felder nicht umbenennen/entfernen ohne Koordination.
# Consumer: layout.py, evaluation.py, drawing.py, viewer3d.py, scoring.py, rhino_geometry.py
# Neue optionale Felder (mit Default) können hinzugefügt werden. Siehe AGENTS.md → Contract B.
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    name:          str
    x:             float          # linke untere Ecke (m)
    y:             float          # linke untere Ecke (m)
    breite:        float          # Breite in m (West–Ost)
    tiefe:         float          # Tiefe in m (Süd–Nord)
    flaeche_m2:    float          # tatsächliche Fläche aus Briefing
    din_kategorie: str            # z.B. "NUF 3", "NUF 4", "TF"
    farbe:         str = "#CCCCCC"
    schraffur:     bool = False   # True = Erweiterungszone
    floors:         int = 1        # Anzahl Geschosse fuer diese Funktion
    planned_area_m2: float | None = None
    delta_m2:       float = 0.0
    delta_pct:      float = 0.0

    @property
    def polygon(self):
        return shapely_box(self.x, self.y, self.x + self.breite, self.y + self.tiefe)

    @property
    def centroid(self) -> tuple[float, float]:
        return (self.x + self.breite / 2, self.y + self.tiefe / 2)

    @property
    def gezeichnete_flaeche(self) -> float:
        return self.breite * self.tiefe


CONVENTIONS_RULES_PATH = Path(__file__).parent.parent / "data" / "rules_conventions.yaml"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Kanonische Raumhöhe je Zone (aus rules_conventions.yaml)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _load_hoehen_config() -> dict:
    p = Path(__file__).parent.parent / "data" / "rules_conventions.yaml"
    try:
        if _yaml is None:
            return {}
        with open(p, encoding="utf-8") as f:
            return (_yaml.safe_load(f) or {}).get("lichte_raumhoehe_m", {})
    except Exception:
        return {}


def zone_height(
    zone: "Zone",
    tragwerk_config: dict | None = None,
    nutzungstyp: str = "Produktion",
) -> float:
    """Kanonische lichte Raumhöhe für eine Zone.

    Priorität:
    1. Tragwerk-Config (traufhoehe_standard_m) für Hallenkategorien
    2. Nutzungstyp-Override aus rules_conventions.yaml
    3. Default aus rules_conventions.yaml
    4. Fallback 6.0 m
    """
    din = zone.din_kategorie
    if din == "VF":
        return 0.0
    cfg       = _load_hoehen_config()
    defaults  = cfg.get("default", {})
    overrides = cfg.get("nutzungstyp_overrides", {}).get(nutzungstyp, {})
    base: float = overrides.get(din) or defaults.get(din) or 6.0

    HALLEN_DIN = {"NUF 3", "NUF 4", "TF"}
    if din in HALLEN_DIN and tragwerk_config:
        trauf = tragwerk_config.get("traufhoehe_standard_m")
        if trauf:
            base = float(trauf)

    STAPELBARE_DIN = {"NUF 2", "NUF 7"}
    floors = max(1, zone.floors or 1)
    if din in STAPELBARE_DIN:
        return round(base * floors, 2)
    return round(base, 2)


# ---------------------------------------------------------------------------
# Site-Dimensionen aus Gesamt-NUF berechnen
# ---------------------------------------------------------------------------

def berechne_site_dimensionen(bgf_m2: float, aspekt: float = 1.5) -> tuple[float, float]:
    """
    Berechnet Site-Breite und -Tiefe aus der Brutto-Grundfläche.
    aspekt = Breite / Tiefe (Default 1.5 – typisch für Industriehallen)
    Ergebnis wird auf 6 m aufgerundet (kleinste Stützenrastereinheit).
    """
    tiefe  = math.sqrt(bgf_m2 / aspekt)
    breite = bgf_m2 / tiefe
    # Auf nächste 6 m aufrunden
    breite = math.ceil(breite / 6) * 6
    tiefe  = math.ceil(tiefe  / 6) * 6
    return breite, tiefe


# ---------------------------------------------------------------------------
# Stützenraster-Ausrichtung prüfen
# ---------------------------------------------------------------------------

def berechne_raster_score(zonen: list[Zone], raster_x: float, raster_y: float) -> float:
    """
    Bewertet, wie gut Zonengrenzen mit dem Stützenraster übereinstimmen.
    Score 0.0–1.0: Anteil der ausgerichteten Kanten.
    Koordinaten werden relativ zum Gebäude-Ursprung (min x/y) gemessen,
    damit der Envelope-Versatz im Site-Kontext das Ergebnis nicht verfälscht.
    """
    non_hatch = [z for z in zonen if not z.schraffur]
    if not non_hatch:
        return 1.0

    origin_x = min(z.x for z in non_hatch)
    origin_y = min(z.y for z in non_hatch)

    def snap_fehler(wert: float, raster: float) -> float:
        return min(wert % raster, raster - wert % raster)

    kanten = []
    for z in non_hatch:
        kanten += [
            snap_fehler(z.x - origin_x,              raster_x),
            snap_fehler(z.x + z.breite - origin_x,   raster_x),
            snap_fehler(z.y - origin_y,              raster_y),
            snap_fehler(z.y + z.tiefe - origin_y,    raster_y),
        ]

    toleranz = 0.5  # m – Kante gilt als ausgerichtet wenn Abstand < 0.5 m
    ausgerichtet = sum(1 for e in kanten if e <= toleranz)
    return round(ausgerichtet / len(kanten), 3)


# ---------------------------------------------------------------------------
# Gemeinsame Wandlänge zweier Zonen
# ---------------------------------------------------------------------------

def shared_wall(a: "Zone", b: "Zone", tol: float = 0.5) -> float:
    """Gibt die Länge der gemeinsamen Wand zurück (0 = kein Kontakt).

    Vier Fälle: a über b, a unter b, a rechts von b, a links von b.
    Die Wandlänge ist die Überlappung der jeweils senkrechten Ausdehnung.
    """
    # a oben / b unten
    if abs((a.y + a.tiefe) - b.y) < tol:
        overlap = min(a.x + a.breite, b.x + b.breite) - max(a.x, b.x)
        if overlap > tol:
            return overlap
    # a unten / b oben
    if abs(a.y - (b.y + b.tiefe)) < tol:
        overlap = min(a.x + a.breite, b.x + b.breite) - max(a.x, b.x)
        if overlap > tol:
            return overlap
    # a rechts / b links
    if abs((a.x + a.breite) - b.x) < tol:
        overlap = min(a.y + a.tiefe, b.y + b.tiefe) - max(a.y, b.y)
        if overlap > tol:
            return overlap
    # a links / b rechts
    if abs(a.x - (b.x + b.breite)) < tol:
        overlap = min(a.y + a.tiefe, b.y + b.tiefe) - max(a.y, b.y)
        if overlap > tol:
            return overlap
    return 0.0


# ---------------------------------------------------------------------------
# Pfadlänge entlang einer Zone-Sequenz
# ---------------------------------------------------------------------------

def berechne_pfadlaenge(zonen_dict: dict[str, Zone], pfad: list[str]) -> float:
    """
    Summiert die Distanzen zwischen den Zentroiden der Zonen entlang eines Pfades.
    Nicht gefundene Zonen werden übersprungen.
    """
    punkte = [zonen_dict[n].centroid for n in pfad if n in zonen_dict]
    if len(punkte) < 2:
        return 0.0
    return sum(
        math.dist(punkte[i], punkte[i + 1])
        for i in range(len(punkte) - 1)
    )


# ---------------------------------------------------------------------------
# Freie Fassaden berechnen
# ---------------------------------------------------------------------------

def berechne_freie_ostfassade(zonen: list[Zone], site_breite: float, site_tiefe: float,
                               puffer_m: float = 1.0) -> float:
    """Rückwärtskompatibel: Anteil der Ostfassade ohne permanente Zonen."""
    fraction, _ = berechne_beste_freie_fassade(zonen, site_breite, site_tiefe, puffer_m,
                                                _only_side="east")
    return fraction


def berechne_beste_freie_fassade(
    zonen: list[Zone],
    site_breite: float,
    site_tiefe: float,
    puffer_m: float = 1.0,
    _only_side: str | None = None,
) -> tuple[float, str]:
    """Gibt (freier_Anteil, Himmelsrichtung) für die am wenigsten belegte Fassade zurück.

    Erweiterungszonen (schraffur=True) zählen als frei.
    """

    def _side_free(side: str) -> float:
        if side == "east":
            grenze = site_breite - puffer_m
            belegte = sum(
                min(z.y + z.tiefe, site_tiefe) - max(z.y, 0.0)
                for z in zonen
                if not z.schraffur and z.x + z.breite >= grenze
            )
            return max(0.0, 1.0 - belegte / max(1.0, site_tiefe))
        if side == "west":
            grenze = puffer_m
            belegte = sum(
                min(z.y + z.tiefe, site_tiefe) - max(z.y, 0.0)
                for z in zonen
                if not z.schraffur and z.x <= grenze
            )
            return max(0.0, 1.0 - belegte / max(1.0, site_tiefe))
        if side == "north":
            grenze = site_tiefe - puffer_m
            belegte = sum(
                min(z.x + z.breite, site_breite) - max(z.x, 0.0)
                for z in zonen
                if not z.schraffur and z.y + z.tiefe >= grenze
            )
            return max(0.0, 1.0 - belegte / max(1.0, site_breite))
        if side == "south":
            grenze = puffer_m
            belegte = sum(
                min(z.x + z.breite, site_breite) - max(z.x, 0.0)
                for z in zonen
                if not z.schraffur and z.y <= grenze
            )
            return max(0.0, 1.0 - belegte / max(1.0, site_breite))
        return 0.0

    if _only_side:
        return round(_side_free(_only_side), 3), _only_side

    results = {s: _side_free(s) for s in ("east", "west", "north", "south")}
    best = max(results, key=results.__getitem__)
    return round(results[best], 3), best

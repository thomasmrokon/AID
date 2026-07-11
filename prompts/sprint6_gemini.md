# Sprint 6A – Gemini: GIS-Erweiterung (`gis.py` + `pyproject.toml`)

## Kontext

Du arbeitest an einem Python-Projekt (LangGraph + Streamlit) zur KI-gestützten Industriebau-Planung.
Deine Aufgabe ist eng begrenzt: **zwei Änderungen**, kein anderer Code wird angefasst.

---

## Aufgabe 1: `pyproject.toml` — Dependency ergänzen

Datei: `pyproject.toml`

Im `[project]` → `dependencies`-Array die folgende Zeile **hinzufügen** (alphabetisch zwischen `shapely` und `python-dotenv` einfügen oder ans Ende der Liste):

```toml
"streamlit-folium>=0.15",
```

Aktueller Stand der dependencies (zur Orientierung):

```toml
dependencies = [
    "langgraph>=0.2",
    "langchain>=0.3",
    "langchain-openai>=0.2",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "matplotlib>=3.8",
    "shapely>=2.0",
    "python-dotenv>=1.0",
    "rhino3dm>=8.0",
    "requests>=2.28",
    "pyproj>=3.0",
    "plotly>=5.0",
    "langchain-anthropic>=0.1",
]
```

---

## Aufgabe 2: `app/tools/gis.py` — neue Funktion `fetch_all_parcels_osm`

### Bestehende Datei (vollständig, zur Orientierung)

```python
"""
AID Demo – GIS-Client
Bezieht Grundstücksdaten (Geometrie, Nutzung) über Nominatim und Overpass API.
"""

from __future__ import annotations
import time
import math
import requests
import pyproj
from shapely.geometry import Polygon

USER_AGENT = "AID-Demo/1.0 (thomas.mrokon@gmail.com)"

def geocode_address(address: str) -> tuple[float, float] | None:
    """Nominatim → (lat, lon). Gibt None bei Fehler."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}
    try:
        time.sleep(1)
        response = requests.get(url, params=params, headers=headers, timeout=8)
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"[gis] Warnung: {e}")
        return None

def wgs84_polygon_to_local_meters(coords_lonlat: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """EPSG:4326 (lon,lat) → lokale Meterkoordinaten (SW-Ursprung = 0,0)."""
    try:
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
        local_coords = [(transformer.transform(lon, lat)) for lon, lat in coords_lonlat]
        if not local_coords:
            return []
        min_east = min(c[0] for c in local_coords)
        min_north = min(c[1] for c in local_coords)
        return [(c[0] - min_east, c[1] - min_north) for c in local_coords]
    except Exception as e:
        print(f"[gis] Warnung: {e}")
        return []

def fetch_parcel_osm(lat: float, lon: float, radius_m: float = 500) -> dict | None:
    """Overpass API → site_geometry-Dict. Gibt NUR das nächste Polygon zurück."""
    url = "https://overpass-api.de/api/interpreter"
    query = (
        f"[out:json][timeout:15];"
        f"(way[landuse](around:{radius_m},{lat},{lon}););"
        f"out geom;"
    )
    try:
        time.sleep(1)
        response = requests.get(url, params={"data": query},
                                headers={"User-Agent": USER_AGENT}, timeout=15)
        response.raise_for_status()
        data = response.json()
        elements = data.get("elements", [])
        if not elements:
            return None

        best_element = None
        min_dist = float('inf')
        for element in elements:
            if element.get("type") != "way" or "geometry" not in element:
                continue
            geom = element["geometry"]
            if len(geom) < 4:
                continue
            coords_lonlat = [(n["lon"], n["lat"]) for n in geom]
            local = wgs84_polygon_to_local_meters(coords_lonlat)
            if len(local) >= 3 and Polygon(local).area < 500:
                continue
            avg_lat = sum(n["lat"] for n in geom) / len(geom)
            avg_lon = sum(n["lon"] for n in geom) / len(geom)
            dist = math.hypot(avg_lat - lat, avg_lon - lon)
            if dist < min_dist:
                min_dist = dist
                best_element = element

        if not best_element:
            return None
        return _element_to_site(best_element)

    except Exception as e:
        print(f"[gis] Warnung: {e}")
        return None

def site_from_address(address: str) -> dict | None:
    """Orchestriert: geocode → fetch_parcel_osm → Fallback None."""
    coords = geocode_address(address)
    if not coords:
        return None
    lat, lon = coords
    return fetch_parcel_osm(lat, lon)
```

### Was du hinzufügst

**1. Hilfsfunktion `_element_to_site`** (Refactoring: den bestehenden "Element → Dict"-Code aus `fetch_parcel_osm` extrahieren).

Der Code, der aus einem OSM-Element ein `site_geometry`-Dict baut, steht aktuell inline in `fetch_parcel_osm`. Extrahiere ihn als private Hilfsfunktion:

```python
def _element_to_site(element: dict) -> dict | None:
    """Konvertiert ein Overpass-Way-Element in ein site_geometry-Dict."""
    coords_lonlat = [(node["lon"], node["lat"]) for node in element["geometry"]]
    local_coords = wgs84_polygon_to_local_meters(coords_lonlat)
    if len(local_coords) < 3:
        return None
    poly = Polygon(local_coords)
    area_m2 = poly.area
    min_x, min_y, max_x, max_y = poly.bounds
    width_m = max_x - min_x
    depth_m = max_y - min_y
    tags = element.get("tags", {})
    name = tags.get("name") or "Gewerbegebiet (OSM)"
    access_point = [width_m / 2.0, depth_m]
    return {
        "id": f"osm_{element['id']}",
        "name": name,
        "beschreibung": f"Automatisch generiertes Grundstück aus OSM ({tags.get('landuse', 'industrial')})",
        "area_m2": round(area_m2, 2),
        "width_m": round(width_m, 2),
        "depth_m": round(depth_m, 2),
        "polygon": [[round(x, 2), round(y, 2)] for x, y in local_coords],
        "access_points": [
            {"id": "Z1", "side": "north",
             "point": [round(access_point[0], 2), round(access_point[1], 2)],
             "width_m": 7.5}
        ],
        "planning": {
            "grz": 0.8, "gfz": 2.4, "abstandsfaktor": 0.4,
            "max_gebaeudehoehe_m": 12.0, "regelgeschoss_hoehe_m": 3.5,
        },
        "source": "osm",
    }
```

**2. Neue Funktion `fetch_all_parcels_osm`** (nach `fetch_parcel_osm` einfügen):

```python
def fetch_all_parcels_osm(lat: float, lon: float, radius_m: float = 400) -> list[dict]:
    """Overpass API → Liste aller Landuse-Polygone im Radius (nach Distanz sortiert).

    Filtert Polygone < 500 m². Gibt maximal 10 Ergebnisse zurück.
    Jedes Element hat dieselbe Struktur wie fetch_parcel_osm() → site_geometry-Dict.
    """
    url = "https://overpass-api.de/api/interpreter"
    query = (
        f"[out:json][timeout:15];"
        f"(way[landuse](around:{radius_m},{lat},{lon}););"
        f"out geom;"
    )
    try:
        time.sleep(1)
        response = requests.get(url, params={"data": query},
                                headers={"User-Agent": USER_AGENT}, timeout=15)
        response.raise_for_status()
        data = response.json()
        elements = data.get("elements", [])
    except Exception as e:
        print(f"[gis] Warnung: {e}")
        return []

    candidates: list[tuple[float, dict]] = []  # (dist, site_dict)

    for element in elements:
        if element.get("type") != "way" or "geometry" not in element:
            continue
        geom = element["geometry"]
        if len(geom) < 4:
            continue

        # Mindestfläche prüfen (lokale Koordinaten nötig)
        coords_lonlat = [(n["lon"], n["lat"]) for n in geom]
        local = wgs84_polygon_to_local_meters(coords_lonlat)
        if len(local) < 3 or Polygon(local).area < 500:
            continue

        site = _element_to_site(element)
        if site is None:
            continue

        avg_lat = sum(n["lat"] for n in geom) / len(geom)
        avg_lon = sum(n["lon"] for n in geom) / len(geom)
        dist = math.hypot(avg_lat - lat, avg_lon - lon)
        candidates.append((dist, site))

    # Nach Distanz sortieren, maximal 10 zurückgeben
    candidates.sort(key=lambda x: x[0])
    return [site for _, site in candidates[:10]]
```

**3. `fetch_parcel_osm` refactoren**: den inline Konvertierungscode durch `_element_to_site(best_element)` ersetzen, sodass keine Duplikation entsteht.

### Vollständige finale `gis.py` — Struktur

```
geocode_address()
wgs84_polygon_to_local_meters()
_element_to_site()          ← neu (private helper)
fetch_parcel_osm()          ← refactored (nutzt _element_to_site)
fetch_all_parcels_osm()     ← neu
site_from_address()         ← unverändert
```

---

## Verifikation

Teste mit einem kurzen Python-Snippet (nicht als Datei speichern, nur lokal ausführen):

```python
from app.tools.gis import fetch_all_parcels_osm
results = fetch_all_parcels_osm(48.1351, 11.5820, radius_m=400)  # München
print(f"Gefunden: {len(results)} Parzellen")
for r in results:
    print(f"  - {r['name']} ({r['area_m2']:.0f} m²)")
```

Erwartung: Liste mit 0–10 Dicts, jeder mit Keys `id`, `name`, `area_m2`, `polygon`, `access_points`, `planning`.

---

## Wichtig: Was du NICHT änderst

- `site_from_address()` — bleibt unverändert
- `geocode_address()` — bleibt unverändert
- Alle anderen Dateien im Projekt

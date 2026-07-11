"""
AID Demo – GIS-Client
Bezieht Grundstücksdaten (Geometrie, Nutzung) über:
  1. ALKIS WFS  – amtliche Flurstückgeometrien (anmeldefrei, Open Data, länderspezifisch)
  2. OSM/Overpass – Fallback für nicht abgedeckte Bundesländer

ALKIS-Quellen (anmeldefrei):
  NW – opengeodata.nrw.de / wfs.nrw.de
  HE – gds.hessen.de (HVBG)
  BW – opengeodata.lgl-bw.de (OGC API Features)
  BE – FIS-Broker Berlin
  BB – Datenadler.de / geobasis-bb.de
  SH – geodienste.sh (LVermGeo SH)
  TH – geoportal.thueringen.de
"""

from __future__ import annotations
import time
import math
import xml.etree.ElementTree as ET
import requests
import pyproj
from shapely.geometry import Polygon

USER_AGENT = "AID-Demo/1.0 (thomas.mrokon@gmail.com)"

# ---------------------------------------------------------------------------
# ALKIS WFS Registry
# ---------------------------------------------------------------------------

_BUNDESLAND_CODES: dict[str, str] = {
    "Nordrhein-Westfalen": "NW",
    "Hessen": "HE",
    "Baden-Württemberg": "BW",
    "Berlin": "BE",
    "Brandenburg": "BB",
    "Hamburg": "HH",
    "Schleswig-Holstein": "SH",
    "Thüringen": "TH",
    "Sachsen-Anhalt": "ST",
    "Bayern": "BY",
    "Niedersachsen": "NI",
    "Sachsen": "SN",
    "Rheinland-Pfalz": "RP",
    "Mecklenburg-Vorpommern": "MV",
    "Bremen": "HB",
    "Saarland": "SL",
}

# (wfs_base_url, typename, srsname)
# WFS 2.0.0 GetFeature-Endpunkte, alle anmeldefrei.
# Reihenfolge: verlässlichste Endpunkte zuerst getestet.
_ALKIS_WFS: dict[str, tuple[str, str, str]] = {
    "NW": (
        "https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_vereinfacht",
        "ave:Flurstueck",
        "EPSG:25832",
    ),
    "HE": (
        "https://gds.hessen.de/arcgis/services/Inspire/ALKIS/MapServer/WFSServer",
        "ALKIS:Flurstueck",
        "EPSG:25832",
    ),
    "BW": (
        "https://owsproxy.lgl-bw.de/owsproxy/ows/WFS_LGL-BW_ALKIS_Flurstuecke",
        "adv:AX_Flurstueck",
        "EPSG:25832",
    ),
    "BE": (
        "https://fbinter.stadt-berlin.de/fb/berlin/service_intern.jsp"
        "?id=s_alkis_flurstuecksflaechen@senstadt&type=WFS",
        "fis:s_alkis_flurstuecksflaechen",
        "EPSG:25833",
    ),
    "BB": (
        "https://isk.geobasis-bb.de/mapproxy/alkis_vereinfacht/service/wfs",
        "alkis_vereinfacht:alkis_flurstueck",
        "EPSG:25833",
    ),
    "SH": (
        "https://service.gdi-sh.de/WFS_SH_ALKIS_Flurstuecke",
        "adv:AX_Flurstueck",
        "EPSG:25832",
    ),
    "TH": (
        "https://www.geoproxy.geoportal-th.de/geoproxy/services/ALKIS_NAS_Flurstueck",
        "adv:AX_Flurstueck",
        "EPSG:25832",
    ),
    "HH": (
        "https://geodienste.hamburg.de/HH_WFS_ALKIS_Basiskarte",
        "de.hh.up:flurstueck_hh",
        "EPSG:25832",
    ),
}


def _reverse_geocode_bundesland(lat: float, lon: float) -> str | None:
    """Reverse-Geocoding via Nominatim → Bundesland-Kürzel ('NW', 'BE', …)."""
    try:
        time.sleep(0.5)
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 5},
            headers={"User-Agent": USER_AGENT},
            timeout=6,
        )
        resp.raise_for_status()
        state = resp.json().get("address", {}).get("state", "")
        return _BUNDESLAND_CODES.get(state)
    except Exception:
        return None


def _parse_gml_features(gml_text: str) -> list[dict]:
    """Parst WFS 2.0 GML 3.2 → GeoJSON-ähnliche Feature-Liste.

    Liest gml:posList aus Polygon/MultiSurface-Geometrien.
    Namespace-agnostisch für Feature-Properties (ave:, adv:, fis: etc.).
    """
    _GML = "http://www.opengis.net/gml/3.2"
    _WFS = "http://www.opengis.net/wfs/2.0"
    try:
        root = ET.fromstring(gml_text)
    except ET.ParseError:
        return []

    features: list[dict] = []
    for member in root.findall(f"{{{_WFS}}}member"):
        feature_elem = next(iter(member), None)
        if feature_elem is None:
            continue

        props: dict[str, str] = {}
        geometry_coords: list[tuple[float, float]] | None = None

        for child in feature_elem:
            poslist_elem = child.find(f".//{{{_GML}}}posList")
            if poslist_elem is not None and poslist_elem.text:
                vals = list(map(float, poslist_elem.text.split()))
                dim = int(poslist_elem.get("srsDimension", "2"))
                coords = [(vals[i], vals[i + 1]) for i in range(0, len(vals) - dim + 1, dim)]
                if len(coords) >= 3:
                    geometry_coords = coords
                continue

            local_name = child.tag.split("}")[1] if "}" in child.tag else child.tag
            if child.text and child.text.strip():
                props[local_name] = child.text.strip()

        if geometry_coords:
            features.append({
                "geometry": {"type": "Polygon", "coordinates": [geometry_coords]},
                "properties": props,
            })

    return features


def _wfs_gml_request(
    wfs_url: str,
    typename: str,
    bbox_str: str,
    count: int = 100,
) -> list[dict]:
    """Direkte GML-Anfrage ohne JSON-Fallback — für Tiling-Sub-Requests."""
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": typename,
        "BBOX": bbox_str,
        "COUNT": str(count),
    }
    try:
        resp = requests.get(
            wfs_url, params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=14,
        )
        if resp.status_code == 200:
            return _parse_gml_features(resp.text)
    except Exception:
        pass
    return []


def _wfs_fetch_features(
    wfs_url: str,
    typename: str,
    srsname: str,
    lat: float,
    lon: float,
    radius_m: float = 300,
) -> list[dict] | None:
    """WFS 2.0.0 GetFeature mit BBOX → Feature-Liste.

    Versucht zuerst JSON; bei HTTP 4xx oder nicht-JSON-Antwort zweiter
    Versuch ohne outputFormat → GML 3.2, geparst mit _parse_gml_features.
    Gibt None zurück wenn kein Endpoint antwortet oder keine Features.
    """
    try:
        transformer = pyproj.Transformer.from_crs("EPSG:4326", srsname, always_xy=True)
        cx, cy = transformer.transform(lon, lat)
        bbox_str = (
            f"{cx - radius_m:.2f},{cy - radius_m:.2f},"
            f"{cx + radius_m:.2f},{cy + radius_m:.2f},{srsname}"
        )
    except Exception:
        return None

    base_params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": typename,
        "BBOX": bbox_str,
        "COUNT": "100",
    }
    try:
        time.sleep(0.5)
        # Versuch 1: JSON (für WFS-Endpoints die es unterstützen)
        resp = requests.get(
            wfs_url,
            params={**base_params, "outputFormat": "application/json"},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=12,
        )
        ct = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and ("json" in ct or resp.text.strip().startswith("{")):
            feats = resp.json().get("features") or []
            if feats:
                return feats

        # Versuch 2: GML (Standard-Ausgabe der deutschen ALKIS-WFS)
        time.sleep(0.3)
        resp_gml = requests.get(
            wfs_url,
            params=base_params,
            headers={"User-Agent": USER_AGENT},
            timeout=14,
        )
        if resp_gml.status_code == 200:
            feats = _parse_gml_features(resp_gml.text)
            if feats:
                return feats

        return None
    except Exception:
        return None


def _wfs_features_to_sites(
    features: list[dict],
    srsname: str,
    lat: float,
    lon: float,
) -> list[dict]:
    """Konvertiert WFS-GeoJSON-Features in site_geometry-Dicts."""
    results: list[tuple[float, dict]] = []

    try:
        to_wgs84 = pyproj.Transformer.from_crs(srsname, "EPSG:4326", always_xy=True)
    except Exception:
        return []

    for feat in features:
        geom = feat.get("geometry") or {}
        geo_type = geom.get("type", "")
        raw_coords = geom.get("coordinates", [])

        if geo_type == "Polygon":
            outer_ring = raw_coords[0] if raw_coords else []
        elif geo_type == "MultiPolygon":
            # Größtes Teilpolygon
            outer_ring = max(raw_coords, key=lambda r: len(r[0]), default=[[]])[0]
        else:
            continue

        if len(outer_ring) < 3:
            continue

        # Koordinaten → WGS84 → lokale Meter
        if srsname == "EPSG:4326":
            coords_lonlat = [(float(c[0]), float(c[1])) for c in outer_ring]
        else:
            coords_lonlat = [to_wgs84.transform(float(c[0]), float(c[1])) for c in outer_ring]

        local_coords = wgs84_polygon_to_local_meters(coords_lonlat)
        if len(local_coords) < 3:
            continue

        poly = Polygon(local_coords)
        if poly.area < 300:
            continue

        props = feat.get("properties") or {}
        # Property-Keys variieren je Bundesland/WFS-Provider
        zaehler  = (props.get("zaehler") or props.get("ZAEHLER")
                    or props.get("flstnrzae") or props.get("zae") or "").strip()
        nenner   = (props.get("nenner")  or props.get("NENNER")
                    or props.get("flstnrnen") or props.get("nen") or "").strip()
        kennz    = (props.get("flurstueckskennzeichen") or props.get("kennzeichen")
                    or props.get("flstkennz") or props.get("FLSTKENNZ") or "").rstrip("_")
        gemarkung = (props.get("gemarkung") or props.get("GEMARKUNG") or "").strip()
        flur      = (props.get("flur") or props.get("FLUR") or "").strip()

        # Menschenlesbare Nummer bevorzugen (Gemarkung + Flur + Zähler[/Nenner])
        if zaehler:
            fs_nr = f"{zaehler}/{nenner}" if (nenner and nenner not in ("0", "00", "000")) else zaehler
            if gemarkung and flur:
                name = f"{gemarkung} Fl.{flur} Nr.{fs_nr}"
            elif flur:
                name = f"Flur {flur}, Flurstück {fs_nr}"
            else:
                name = f"Flurstück {fs_nr}"
        elif kennz:
            name = f"Flurstück {kennz}"
        else:
            name = "ALKIS-Flurstück"

        min_x, min_y, max_x, max_y = poly.bounds
        width_m = max_x - min_x
        depth_m = max_y - min_y

        avg_lon = sum(c[0] for c in coords_lonlat) / len(coords_lonlat)
        avg_lat = sum(c[1] for c in coords_lonlat) / len(coords_lonlat)
        dist = math.hypot(avg_lat - lat, avg_lon - lon)

        results.append((dist, {
            "id": f"alkis_{kennz or int(time.time())}",
            "name": name,
            "beschreibung": "ALKIS-Flurstück (amtliche Geometrie, Open Data)",
            "area_m2": round(poly.area, 2),
            "width_m": round(width_m, 2),
            "depth_m": round(depth_m, 2),
            "polygon": [[round(x, 2), round(y, 2)] for x, y in local_coords],
            "polygon_wgs84": [[round(la, 7), round(lo, 7)] for lo, la in coords_lonlat],
            "access_points": [
                {
                    "id": "Z1",
                    "side": "north",
                    "point": [round(width_m / 2, 2), round(depth_m, 2)],
                    "width_m": 7.5,
                }
            ],
            "planning": {
                "grz": 0.8, "gfz": 2.4, "abstandsfaktor": 0.4,
                "max_gebaeudehoehe_m": 12.0, "regelgeschoss_hoehe_m": 3.5,
            },
            "source": "alkis",
        }))

    results.sort(key=lambda t: t[0])
    return [site for _, site in results]


def fetch_parcel_alkis(
    lat: float,
    lon: float,
    radius_m: float = 300,
    bundesland: str | None = None,
) -> dict | None:
    """ALKIS WFS → nächstgelegenes Flurstück als site_geometry-Dict.

    Versucht zuerst den passenden Landes-WFS; fällt auf OSM zurück wenn
    kein Endpunkt vorhanden oder der WFS keine Daten liefert.

    Args:
        bundesland: optionaler Override, z.B. 'NW'. Wird sonst per
                    Reverse-Geocoding bestimmt.
    """
    bl = bundesland or _reverse_geocode_bundesland(lat, lon)
    if bl and bl in _ALKIS_WFS:
        wfs_url, typename, srsname = _ALKIS_WFS[bl]
        try:
            features = _wfs_fetch_features(wfs_url, typename, srsname, lat, lon, radius_m)
            if features:
                sites = _wfs_features_to_sites(features, srsname, lat, lon)
                if sites:
                    print(f"[gis] ALKIS WFS {bl}: {len(features)} Features, 1 ausgewählt")
                    return sites[0]
        except Exception as e:
            print(f"[gis] WFS {bl} Fehler: {e}")

    print(f"[gis] Fallback OSM Overpass für ({lat:.5f}, {lon:.5f})")
    return fetch_parcel_osm(lat, lon, radius_m)


def fetch_all_parcels_alkis(
    lat: float,
    lon: float,
    radius_m: float = 600,
    bundesland: str | None = None,
) -> list[dict]:
    """ALKIS WFS → Liste aller Flurstücke im Radius via 4-Quadrant-Tiling.

    Teilt den Suchbereich in 4 überlappende Quadranten auf, um den
    server-seitigen COUNT-Limit zu umgehen. Dedupliziert über flstkennz.
    Fallback: OSM wenn kein ALKIS-Endpunkt oder WFS liefert nichts.
    """
    bl = bundesland or _reverse_geocode_bundesland(lat, lon)
    if bl and bl in _ALKIS_WFS:
        wfs_url, typename, srsname = _ALKIS_WFS[bl]
        try:
            transformer = pyproj.Transformer.from_crs("EPSG:4326", srsname, always_xy=True)
            cx, cy = transformer.transform(lon, lat)
        except Exception as e:
            print(f"[gis] CRS-Transform {bl}: {e}")
            return fetch_all_parcels_osm(lat, lon, radius_m)

        # 4 Quadrant-Mittelpunkte + 15% Überlappung für lückenlose Abdeckung
        offset = radius_m / 2
        sub_r = radius_m / 2 * 1.15
        tile_offsets = [(offset, offset), (-offset, offset), (offset, -offset), (-offset, -offset)]

        all_features: list[dict] = []
        seen_keys: set[str] = set()

        for dx, dy in tile_offsets:
            tx, ty = cx + dx, cy + dy
            bbox_str = (
                f"{tx - sub_r:.2f},{ty - sub_r:.2f},"
                f"{tx + sub_r:.2f},{ty + sub_r:.2f},{srsname}"
            )
            feats = _wfs_gml_request(wfs_url, typename, bbox_str)
            for feat in feats:
                props = feat.get("properties", {})
                key = (props.get("flstkennz") or props.get("flurstueckskennzeichen")
                       or props.get("idflurst") or props.get("oid") or "")
                if not key:
                    coords = feat.get("geometry", {}).get("coordinates", [[]])[0]
                    key = f"{coords[0][0]:.1f},{coords[0][1]:.1f}" if coords else None
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    all_features.append(feat)
            time.sleep(0.3)

        if all_features:
            sites = _wfs_features_to_sites(all_features, srsname, lat, lon)
            if sites:
                print(f"[gis] ALKIS WFS {bl}: {len(sites)} Flurstücke (4-Quadrant-Tiling)")
                return sites[:100]

    return fetch_all_parcels_osm(lat, lon, radius_m)


# ---------------------------------------------------------------------------
# Nominatim & Overpass (bestehend, OSM-Fallback)
# ---------------------------------------------------------------------------

def geocode_address(address: str) -> tuple[float, float] | None:
    """Nominatim → (lat, lon). Gibt None bei Fehler."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": USER_AGENT
    }
    try:
        time.sleep(1)  # Rate-Limit
        response = requests.get(url, params=params, headers=headers, timeout=8)
        response.raise_for_status()
        data = response.json()
        if not data:
            print(f"[gis] Warnung: Keine Ergebnisse für Adresse '{address}' gefunden.")
            return None
        
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon
    except requests.exceptions.RequestException as e:
        print(f"[gis] Warnung: Netzwerkfehler bei Nominatim Geocoding: {e}")
        return None
    except Exception as e:
        print(f"[gis] Warnung: Fehler beim Parsen der Nominatim-Antwort: {e}")
        return None

def wgs84_polygon_to_local_meters(coords_lonlat: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """EPSG:4326 (lon,lat) → lokale Meterkoordinaten (SW-Ursprung = 0,0)."""
    try:
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
        local_coords = []
        for lon, lat in coords_lonlat:
            easting, northing = transformer.transform(lon, lat)
            local_coords.append((easting, northing))
            
        if not local_coords:
            return []
            
        min_east = min(c[0] for c in local_coords)
        min_north = min(c[1] for c in local_coords)
        
        normalized_coords = [(c[0] - min_east, c[1] - min_north) for c in local_coords]
        return normalized_coords
    except Exception as e:
        print(f"[gis] Warnung: Fehler bei der Koordinatentransformation: {e}")
        return []

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
        "polygon_wgs84": [[round(node["lat"], 7), round(node["lon"], 7)] for node in element["geometry"]],
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

def fetch_parcel_osm(lat: float, lon: float, radius_m: float = 500) -> dict | None:
    """Overpass API → site_geometry-Dict. Primäre Datenquelle."""
    url = "https://overpass-api.de/api/interpreter"
    query = (
        f"[out:json][timeout:15];"
        f"(way[landuse](around:{radius_m},{lat},{lon}););"
        f"out geom;"
    )
    try:
        time.sleep(1)  # Rate-Limit
        # GET statt POST vermeidet 406-Fehler bei manchen Overpass-Instanzen
        response = requests.get(url, params={"data": query},
                                headers={"User-Agent": USER_AGENT}, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        elements = data.get("elements", [])
        if not elements:
            print(f"[gis] Warnung: Kein Gewerbegebiet im Umkreis von {radius_m}m gefunden.")
            return None
            
        best_element = None
        min_dist = float('inf')

        for element in elements:
            if element.get("type") != "way" or "geometry" not in element:
                continue
            geom = element["geometry"]
            if len(geom) < 4:
                continue
            # Grobe Fläche prüfen (zu kleine Polygone ignorieren)
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
        
    except requests.exceptions.RequestException as e:
        print(f"[gis] Warnung: Netzwerkfehler bei Overpass API: {e}")
        return None
    except Exception as e:
        print(f"[gis] Warnung: Fehler beim Verarbeiten der OSM-Daten: {e}")
        return None

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

def fetch_street_angles(lat: float, lon: float, radius_m: float = 150) -> list[dict]:
    """OSM Overpass → dominante Straßenrichtungen in der Nähe des Grundstücks.

    Gibt eine Liste zurück, sortiert nach Gewicht (Streckenlänge * Anzahl Segmente):
        {"angle_deg": float, "name": str, "weight": float}
    angle_deg ∈ [0°, 180°): 0° = West-Ost-Orientierung, 90° = Nord-Süd.
    """
    url = "https://overpass-api.de/api/interpreter"
    query = (
        f"[out:json][timeout:10];"
        f"way[highway~'^(primary|secondary|tertiary|residential|service|unclassified|trunk)$']"
        f"(around:{radius_m},{lat},{lon});"
        f"out geom;"
    )
    try:
        time.sleep(0.3)
        resp = requests.get(url, params={"data": query},
                            headers={"User-Agent": USER_AGENT}, timeout=12)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception:
        return []

    try:
        proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
    except Exception:
        return []

    # Bucket-Akkumulator: Winkel in 5°-Bins → gewichtete Länge
    bucket_weight: dict[int, float] = {}
    bucket_name:   dict[int, str]   = {}

    for elem in elements:
        geom = elem.get("geometry", [])
        if len(geom) < 2:
            continue
        name = elem.get("tags", {}).get("name", "")

        # Projiziere Knoten nach EPSG:25832 für metergenaue Winkelberechnung
        pts = [proj.transform(n["lon"], n["lat"]) for n in geom]

        for i in range(len(pts) - 1):
            dx = pts[i + 1][0] - pts[i][0]
            dy = pts[i + 1][1] - pts[i][1]
            seg_len = math.hypot(dx, dy)
            if seg_len < 2:
                continue
            # Orientierungswinkel [0°, 180°): 0° = West-Ost
            angle_norm = math.degrees(math.atan2(dy, dx)) % 180
            bucket = int(round(angle_norm / 5) * 5) % 180
            bucket_weight[bucket] = bucket_weight.get(bucket, 0.0) + seg_len
            if name and bucket not in bucket_name:
                bucket_name[bucket] = name

    if not bucket_weight:
        return []

    # Benachbarte Bins (±10°) zusammenführen
    merged: dict[int, float] = {}
    merged_name: dict[int, str] = {}
    for bucket, w in sorted(bucket_weight.items(), key=lambda x: -x[1]):
        absorbed = False
        for existing in list(merged):
            diff = min(abs(bucket - existing), 180 - abs(bucket - existing))
            if diff <= 10:
                merged[existing] += w
                absorbed = True
                break
        if not absorbed:
            merged[bucket] = w
            merged_name[bucket] = bucket_name.get(bucket, "Straße")

    results = sorted(
        [{"angle_deg": float(b), "name": merged_name.get(b, "Straße"), "weight": w}
         for b, w in merged.items()],
        key=lambda x: -x["weight"],
    )
    return results[:4]


def drawn_feature_to_site(feature: dict) -> dict | None:
    """Konvertiert ein Folium-Draw GeoJSON-Feature in ein site_geometry-Dict.

    Erwartet ein GeoJSON Feature mit geometry.type == "Polygon" oder "Rectangle"
    und Koordinaten als [[lon, lat], ...] (GeoJSON Standard).
    """
    import time as _time
    geometry = feature.get("geometry", {})
    geo_type = geometry.get("type", "")
    if geo_type not in ("Polygon", "Rectangle"):
        return None

    outer_ring = geometry.get("coordinates", [[]])[0]
    if len(outer_ring) < 3:
        return None

    # GeoJSON: [lon, lat] → wgs84_polygon_to_local_meters erwartet (lon, lat)
    coords_lonlat = [(c[0], c[1]) for c in outer_ring]
    local_coords = wgs84_polygon_to_local_meters(coords_lonlat)
    if len(local_coords) < 3:
        return None

    poly = Polygon(local_coords)
    area_m2 = poly.area
    if area_m2 < 100:
        return None

    min_x, min_y, max_x, max_y = poly.bounds
    width_m = max_x - min_x
    depth_m = max_y - min_y

    # WGS84 für Folium-Anzeige: [[lat, lon], ...]
    polygon_wgs84 = [[c[1], c[0]] for c in outer_ring]

    return {
        "id": f"drawn_{int(_time.time())}",
        "name": "Eigenes Grundstück",
        "beschreibung": "Manuell auf der Karte eingezeichnet",
        "area_m2": round(area_m2, 1),
        "width_m": round(width_m, 1),
        "depth_m": round(depth_m, 1),
        "polygon": [[round(x, 2), round(y, 2)] for x, y in local_coords],
        "polygon_wgs84": polygon_wgs84,
        "access_points": [
            {
                "id": "Z1",
                "side": "north",
                "point": [round(width_m / 2, 2), round(depth_m, 2)],
                "width_m": 7.5,
            }
        ],
        "planning": {
            "grz": 0.8,
            "gfz": 2.4,
            "abstandsfaktor": 0.4,
            "max_gebaeudehoehe_m": 12.0,
            "regelgeschoss_hoehe_m": 3.5,
        },
        "source": "drawn",
    }


def site_from_address(address: str) -> dict | None:
    """Orchestriert: geocode → ALKIS WFS (Bundesland-abhängig) → OSM-Fallback."""
    coords = geocode_address(address)
    if not coords:
        print(f"[gis] Warnung: Konnte Adresse '{address}' nicht geocoden.")
        return None

    lat, lon = coords
    site = fetch_parcel_alkis(lat, lon)
    if not site:
        print(f"[gis] Warnung: Keine Grundstücksdaten für '{address}' ({lat:.5f}, {lon:.5f}).")
        return None

    return site

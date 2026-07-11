"""Quick test: NRW WFS GML parsing + full fetch flow."""
from app.tools.gis import _wfs_fetch_features, _wfs_features_to_sites, _ALKIS_WFS, fetch_all_parcels_alkis

wfs_url, typename, srsname = _ALKIS_WFS["NW"]
print("=== Low-level GML parse ===")
lat, lon = 51.4556, 6.7654
feats = _wfs_fetch_features(wfs_url, typename, srsname, lat, lon, 400)
if feats:
    print(f"Features parsed: {len(feats)}")
    sites = _wfs_features_to_sites(feats, srsname, lat, lon)
    print(f"Sites: {len(sites)}")
    for s in sites[:3]:
        print(f"  {s['name']:50s}  {s['area_m2']:>10.0f}m2")
else:
    print("No features")

print()
print("=== fetch_all_parcels_alkis (NW override) ===")
sites = fetch_all_parcels_alkis(lat, lon, 400, bundesland="NW")
print(f"Result: {len(sites)} sites")
for s in sites[:5]:
    print(f"  {s['name']:50s}  {s['area_m2']:>10.0f}m2  source={s['source']}")

print()
print("ALL TESTS PASSED" if sites else "WARNING: no sites returned")

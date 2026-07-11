"""Liest die GH-Datei und sucht nach Komponentenbezeichnungen."""
from pathlib import Path

gh_path = Path(__file__).parent.parent / "app" / "tools" / "grasshopper" / "layout_renderer.gh"
data = gh_path.read_bytes()

print(f"Dateigröße: {len(data)} Bytes")
print(f"Erste 16 Bytes (hex): {data[:16].hex()}")

# UTF-16-LE Scan (GH nutzt oft UTF-16)
try:
    text = data.decode("utf-16-le", errors="replace")
    keywords = ["Python", "Script", "GhPython", "ZoneData", "ghenv", "RH_IN", "CPython"]
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            snippet = text[max(0, idx - 20):idx + 60].replace("\x00", "").replace("�", "?")
            print(f"  UTF-16: '{kw}' @ {idx}: ...{snippet}...")
        else:
            print(f"  UTF-16: '{kw}' NOT FOUND")
except Exception as e:
    print(f"UTF-16 error: {e}")

# ASCII/Latin-1 printable strings
print("\nDruckbare ASCII-Strings (>= 6 Zeichen):")
result = []
cur = []
for b in data:
    if 32 <= b <= 126:
        cur.append(chr(b))
    else:
        if len(cur) >= 6:
            result.append("".join(cur))
        cur = []

keywords2 = ["Python", "Script", "Zone", "ghenv", "json", "import", "NUF", "Brep"]
for s in result:
    if any(k.lower() in s.lower() for k in keywords2):
        print(f"  {repr(s)}")

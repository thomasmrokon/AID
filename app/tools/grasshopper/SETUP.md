# Grasshopper Layout Renderer — Einrichtung

## Voraussetzungen

| Was | Version | Zweck |
|---|---|---|
| Rhino 8 Vollversion | 8.x | Grundlage |
| Rhino.Compute Package | via PackageManager | REST-API-Server |
| `compute-rhino3d` (Python) | ≥ 3.0 | Python-Client |

```bash
pip install compute-rhino3d
```

---

## Schritt 1 — Rhino.Compute installieren

1. **Rhino 8 starten**
2. Befehl eingeben: `_PackageManager`
3. Suche: `rhino.compute` → **Installieren**
4. **Rhino 8 neu starten**

---

## Schritt 2 — compute.rhino3d.exe starten

Pfad (bereits installiert über Hops-Plugin):
```
C:\Users\thoma\AppData\Roaming\McNeel\Rhinoceros\packages\8.0\Hops\0.16.28\rhino.compute\rhino.compute.exe
```

Direkt ausführen — der Server startet auf **http://localhost:5000**.

Per Python starten (falls nicht aktiv):
```python
from app.tools.rhino_compute import start_server
start_server()   # wartet 8 Sekunden und prüft Erreichbarkeit
```

Status prüfen:
```python
from app.tools.rhino_compute import diagnose
diagnose()
```

---

## Schritt 3 — Grasshopper-Definition erstellen

> **Wichtig:** Unbedingt die **GhPython**-Komponente verwenden (nicht "Python 3 Script").
> Rhino.Compute (Hops 0.16.28 / Compute 8.0.0.0) unterstützt nur GhPython (IronPython).
> Die "Python 3 Script"-Komponente verursacht HTTP 500 beim Compute-API-Aufruf.

### 3a. Neue GH-Definition öffnen

In Rhino 8: **Ctrl + Shift + B** oder Menü → Extras → Grasshopper

### 3b. Komponenten platzieren

```
┌──────────────────┐     ┌───────────────────────────────┐
│  File Path       │────▶│  GhPython  (NICHT Py3 Script) │
│  (params → file) │     │  Script: zone_reader.py        │
│  Pfad:           │     │  Input:  ZoneDataJSON (str)    │
│  outputs/zones_* │     │  Output: geometries            │
│  .json           │     │          labels                │
└──────────────────┘     │          colors                │
                         │          info                  │
                         └──────────────────────┬─────────┘
                                                │
                         ┌──────────────────────▼─────────┐
                         │  Custom Preview                  │
                         │  Geometry <- geometries          │
                         │  Shader   <- colors (per-item)  │
                         └──────────────────────────────────┘
```

**Detaillierte Schritte:**

1. **Params → Input → File Path** platzieren
   - Rechtsklick → "Select File" → `outputs/zones_A_Materialfluss.json`
   - Rechtsklick → "Read File" aktivieren
   - Hinweis: liefert den PFAD als String — zone_reader.py liest die Datei selbst

2. **Maths → Script → GhPython** platzieren (**nicht** "Python 3 Script"!)
   - Doppelklick → Inhalt von `zone_reader.py` einfügen
   - Input `a` umbenennen zu **`ZoneDataJSON`** (Rechtsklick → Rename Parameter)
   - Outputs umbenennen: `a`→`geometries`, `b`→`labels`, `c`→`colors`, `d`→`info`
   - Der Name `ZoneDataJSON` muss exakt stimmen (wird von der Compute-API so adressiert)

3. **Display → Preview → Custom Preview** platzieren
   - Geometry-Input verbinden mit `geometries`
   - Shader: `colors`-Liste direkt verbinden

4. Optional: `labels`-Output direkt rendern → zeigt Zonenbeschriftungen

### 3c. Als layout_renderer.gh speichern

```
Datei → Speichern unter → app/tools/grasshopper/layout_renderer.gh
```

Die bisherige Datei (mit Python 3 Script) überschreiben.

---

## Schritt 4 — Python-Pipeline-Integration testen

Die Pipeline exportiert automatisch JSON-Dateien je Variante:
- `outputs/zones_A_Materialfluss.json`
- `outputs/zones_B_Erweiterbarkeit.json`
- `outputs/zones_C_Ausgewogen.json`

Grasshopper mit `File Read` auf diese Dateien zeigen lassen.
Bei erneutem Pipeline-Lauf aktualisiert GH die Geometrie automatisch
(wenn "Read File" aktiv und GH auf "Auto"-Update steht).

---

## Tipps für die Darstellung

### Materialien per DIN-Kategorie

In GH: **Dispatch** nach DIN-Kategorie → verschiedene **Custom Material** Komponenten

### Schnittdarstellung

Clipping Plane in Rhino oder **Section**-Komponente in GH für Schnittansichten.

### Bemaßung

**Dimension**-Komponente in GH + Linien aus den Zone-Grenzen.

### Export aus GH

- **3DM:** `File` → `Bake` + Speichern in Rhino
- **DXF:** `Export → DXF` (Rhino-Menü nach Bake)
- **IFC:** Rhino.Inside.Revit oder VisualARQ-Plugin

---

## Diagnose

```python
from app.tools.rhino_compute import diagnose
diagnose()
```

Gibt aus:
```
=== Rhino.Compute Diagnose ===
  compute-rhino3d Client: installiert
  Rhino.Compute Server:   ERREICHBAR (Version: 8.x.y)
  GH-Definition:          app/tools/grasshopper/layout_renderer.gh
==============================
```

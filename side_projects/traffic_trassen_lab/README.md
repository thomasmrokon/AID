# Traffic & Trassen Lab

Isoliertes Side-Projekt für die interaktive Verkehrs- und Trassenplanung.

Ziel: Die Erschließungslogik ohne Masterplan-Ballast neu aufbauen und fachlich
prüfen.

## Start

```bash
.venv/bin/streamlit run side_projects/traffic_trassen_lab/app.py --server.port 8502 --server.address 0.0.0.0
```

## Konzept

1. Grundstück als Polygon
2. Zufahrten und Nutzungsprofil
3. Zielzonen: Pforte, Andienhof, PKW, Medienknoten, Baufeldkern
4. Kandidaten: Stichhof, Frontspange, Mittelspange, Loop
5. Fitness: Anbindung, Straßenfläche, Rechteckigkeit, Teilbarkeit
6. SVG-Ausgabe mit Zoom/Pan

Dieses Lab ist bewusst nicht mit dem Haupt-Masterplan-Agenten gekoppelt.

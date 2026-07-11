# Strategisches Briefing — AID Demo Architektur-Refactoring

**Version:** 1.0 — Entwurf zur Freigabe  
**Datum:** 2026-05-13  
**Status:** ⬜ Entwurf · ⬜ In Review · ⬜ Freigegeben

---

## 1. Ausgangslage

Das AID Demo System erzeugt heute aus einem Nutzerbriefing drei Layoutvarianten für Industriegebäude (Produktion, Logistik, Datacenter). Die Pipeline läuft als LangGraph-Graph durch acht Agenten und erzeugt PNG-Renderings, 3DM-Dateien und einen Markdown-Bericht.

Die technische Basis funktioniert. Die inhaltliche Qualität der Layoutvarianten ist jedoch eingeschränkt, weil drei strukturelle Mängel die Differenzierung zwischen den Varianten und die Planungstiefe begrenzen.

---

## 2. Problemdiagnose

### 2.1 State ist zu flach

Regeln, Strategie und Layout werden einmal berechnet und für alle drei Varianten geteilt. Unterschiede entstehen nur durch numerische Parameter (`process_pull`, `compactness`) — nicht durch wirklich verschiedene Planungsentscheidungen. Variante A braucht inhaltlich andere Rastermaße als Variante B; das ist im aktuellen Modell nicht abbildbar.

### 2.2 Wissensbasis und Interpretation sind vermischt

Die YAML-Datei (`demo_rules.yaml`) enthält feste Einzelwerte wie `raster_standard_x_m: 18`, die in Wirklichkeit kontextabhängige Entscheidungen sind. Es gibt keine Trennung zwischen dem, was das System *weiß* (Gesetze, Normen, Erfahrungswerte) und dem, was es für diesen konkreten Fall *entscheidet* (welches Raster bei dieser Variante sinnvoll ist).

### 2.3 Topologie und Layout sind zu direkt verbunden

Zwischen „welche Räume brauche ich" (Topologie) und „wo stehen sie geometrisch" (Layout) fehlt eine Schicht: **welche Räume spielen welche Rolle in welcher Typologiestruktur**. Deshalb produziert die aktuelle Pipeline drei Varianten, die sich optisch kaum unterscheiden — alle laufen durch denselben Slicing-Algorithmus mit leicht verschiedenen Parametern, nicht durch drei echte Planungstypologien.

---

## 3. Zielbild

### 3.1 Architektonisches Leitprinzip

> LLMs entscheiden **was** (Planungsurteil, Abwägung, Interpretation).  
> Deterministischer Code macht **wie** (Koordinaten, Snapping, Constraints).

### 3.2 Ziel-Pipeline

```
Briefing
    │
    ▼
rule_agent / LLM-Planungsrat
    │  → interpretierte Regeln pro Variante (nicht mehr: eine feste Konfiguration)
    ▼
topology_agent / LLM-flexibel
    │  → bedarfsgerechter Graph (nicht mehr: hardcoded pro Nutzungstyp)
    ▼
strategy_agent / LLM-erweitert
    │  → Typologiewahl + Zonenzuweisung pro Variante
    ▼
layout_agent / 3 Typologiefunktionen
    │  → Kamm · Block+Reserve · Kreuzgang (nicht mehr: ein Algorithmus)
    ▼
evaluation_agent / hart + weich getrennt
    │  → Gesetze als Constraints · Konventionen als Hinweise
    ▼
analyse_agent / LLM-Argumentation
    │  → Variantenvergleich mit Begründungen (nicht mehr: Zahlentabelle)
    ▼
report_agent / LLM-Narration
       → Beratungstext mit Planungsrational (nicht mehr: strukturierter Bericht)
```

### 3.3 Rollen im LLM-Planungsrat (Rule Agent)

Fünf Kerndisziplinen, situativ ergänzt:

| Rolle | Immer aktiv | Bedingt aktiv |
|---|---|---|
| Tragwerk | ✓ | — |
| Brandschutz | ✓ | — |
| Materialfluss | ✓ | — |
| Erschließung | ✓ | — |
| Erweiterbarkeit | ✓ | — |
| Arbeitsstättenrecht | — | Büroanteil > 15 % BGF |
| TGA / Haustechnik | — | Datacenter, energieintensive Produktion |

### 3.4 Regelkategorien

| Kategorie | Beispiele | LLM-Verhalten |
|---|---|---|
| **Gesetzlich bindend** | Fluchtwegabstand ≤ 35 m (ArbStättV), Mindestausgänge | Constraint, unveränderlich |
| **Konditionell hart** | Brandabschnitt 5.000 m² → 10.000 m² mit Sprinkler | LLM entscheidet ob Kompensation sinnvoll |
| **Planungskonventionen** | Rastermaß, freie Fassadenprozente, Materialflusslänge | LLM wählt aus Wertebereich + begründet |

---

## 4. Arbeitspakete

### P1 — State-Schema erweitern
**Fundament. Muss vor P3–P5 abgeschlossen sein.**

Neue Felder in `PlanningState`:

```python
interpreted_rules: dict[str, dict]
# Schlüssel: Variantenname ("A_Materialfluss", ...)
# Wert: vollständige Regelkonfiguration für diese Variante
# Beispiel: interpreted_rules["A_Materialfluss"]["tragwerk"]["raster_x_m"] = 24

zone_roles: dict[str, dict[str, str]]
# Schlüssel: Variantenname
# Wert: Zonename → Rolle ("spine", "tooth", "quadrant_NW", "reserve", ...)
# Beispiel: zone_roles["A_Materialfluss"]["Produktion"] = "tooth_2"

typology_assignments: dict[str, str]
# Schlüssel: Variantenname
# Wert: Bezeichner der Typologiefunktion
# Beispiel: typology_assignments["A_Materialfluss"] = "kamm"

reasoning_log: list[dict]
# Gesammelte Entscheidungsketten aller LLM-Agenten
# Format: {agent, schritt, entscheidung, begruendung, variante}
```

**Deliverable:** Erweiterte `PlanningState`-Typdefinition, alle bestehenden Agenten weiterhin lauffähig (keine breaking changes).

---

### P2 — Wissensbasis neu strukturieren
**Fundament. Parallel zu P1 umsetzbar.**

Das bestehende YAML wird aufgeteilt:

**`rules_hard.yaml`** — Gesetze und Normen, unveränderlich, mit Quellenangabe:
```yaml
brandschutz:
  fluchtweg_max_laenge_m:
    wert: 35
    quelle: "ArbStättV §15 Abs. 1"
    kompensation: null   # keine Abweichung möglich
  brandabschnitt_max_m2:
    wert: 5000
    quelle: "MBO §40"
    kompensation:
      massnahme: "Sprinkleranlage VdS CEA 4001"
      wert_mit_kompensation: 10000
```

**`rules_conventions.yaml`** — Planungskonventionen mit Wertebereichen:
```yaml
tragwerk:
  raster_x_m:
    default: 18
    range: [12, 18, 24, 27]
    treiber:
      kranbahn_erforderlich: 24
      hochregallager: 24
      nur_buero: 12
    quelle: "Erfahrungswert Stahlhallenbau DE"
```

**Deliverable:** Zwei neue YAML-Dateien, angepasster Rule-Agent-Lader, bestehende Funktionalität erhalten.

---

### P3 — LLM-Planungsrat (Rule Agent)
**Abhängig von P1 und P2.**

Der Rule Agent wird von einem YAML-Lader zu einem LLM-Planungsrat. Implementierung als **Single Call mit erzwungener Rollentrennung** (Hybrid-Ansatz):

```
SystemPrompt:
  "Du bist ein Planungsrat. Antworte in klar getrennten Abschnitten —
   erst jede Disziplin einzeln, dann Synthese pro Variante.
   Jede Disziplin analysiert unabhängig, ohne Kompromiss.
   Die Synthese gewichtet nach den übergebenen Variantengewichtungen."

Input:
  briefing + rules_hard (als Constraints) + rules_conventions (als Wertebereich)
  + Variantengewichtungen (Materialfluss/Erweiterbarkeit/Tragwerk)

Output:
  interpreted_rules pro Variante (befüllt P1-State-Feld)
  reasoning_log-Einträge pro Disziplin und Synthese
```

Deterministischer Fallback: YAML-Default-Werte wie heute, wenn LLM nicht verfügbar.

**Deliverable:** Neuer `rule_agent` mit LLM-Planungsrat, Fallback auf YAML-Defaults, `reasoning_log`-Befüllung.

---

### P4 — Topology flexibler + Strategy reicher
**Abhängig von P3.**

**Topology Agent:**  
Heute hardcoded pro Nutzungstyp (9 feste Knoten für Produktion). Ziel: LLM kann Knoten ergänzen oder weglassen wenn das Briefing es verlangt (z. B. Reinraumbereich, Staging-Zone, Umspannwerk). Basisgraph bleibt als Fallback erhalten.

**Strategy Agent:**  
Schema-Erweiterung: Output enthält jetzt `zone_roles` (welche Zone = welche Typologieposition) und `typology_assignments` (welche Funktion für welche Variante). Heute enthält der Output Typologie-Labels (`linear_process`), die der Layout-Agent weitgehend ignoriert — das wird behoben.

**Deliverable:** Erweiterter Strategy-Output mit `zone_roles` und `typology_assignments`, angepasster Topology-Agent mit LLM-Erweiterbarkeit.

---

### P5 — Drei Typologie-Funktionen (Layout Agent)
**Abhängig von P4.**

Drei dedizierte Funktionen ersetzen den generischen `_sliced_building_layout`-Algorithmus:

| Funktion | Typologie | Struktur |
|---|---|---|
| `_kamm_layout()` | A — Materialfluss | Rücken (Support-Band) + Zähne (Prozessmodule) |
| `_block_mit_reserve_layout()` | B — Erweiterbarkeit | Kompakter Block + schraffierte Erweiterungszone |
| `_kreuzgang_layout()` | C — Ausgewogen | EW-Korridor + 4 Quadranten (NW/NE/SW/SE) |

Jede Funktion empfängt `zone_roles` aus P4 als Input — das LLM hat bereits entschieden, welche Zone in welchen Bereich der Typologie gehört. Die Funktion berechnet nur noch die Koordinaten.

**Deliverable:** Drei neue Layout-Funktionen, alter Algorithmus als Fallback erhalten, visuelle Unterscheidbarkeit der drei Varianten deutlich verbessert.

---

### P6 — Analyse und Report als LLM
**Weitgehend unabhängig, parallel zu P3–P5 startbar.**

**Analyse Agent:**  
Statt Zahlentabellen: argumentativer Variantenvergleich. Das LLM bekommt die Evaluationsergebnisse + `reasoning_log` und formuliert: *„Variante A bevorzugt Prozesseffizienz, erkauft dies aber mit eingeschränkter Erweiterbarkeit an der Ostfassade — bei geplantem Wachstum in 5 Jahren architektonisch risikobehaftet."*

**Report Agent:**  
Beratungsnarrativ statt strukturierter Bericht. Der `reasoning_log` ermöglicht es, die Planungsentscheidungen zu erklären: *„Das Stützenraster wurde auf 24 m gesetzt, weil die genannte Kranbahn (20 t) diesen Mindestabstand erfordert und gleichzeitig die angestrebte Erweiterbarkeit in Variante B davon profitiert."*

**Deliverable:** LLM-getriebener Analyse-Agent, erweiterter Report-Agent mit Reasoning-Narrativ.

---

### P7 — Observability: Reasoning Log
**Querschnittsthema, in P1 vorbereitet, in P3–P6 befüllt.**

Alle LLM-Agenten schreiben strukturierte Einträge in `reasoning_log`:

```python
{
    "agent": "rule_agent",
    "disziplin": "Brandschutz",
    "variante": "A_Materialfluss",
    "entscheidung": "Sprinkleranlage empfohlen",
    "begruendung": "Prozesspfad 140 m überschreitet 5.000 m²-Limit ohne Sprinkler",
    "regelref": "MBO §40 + VdS CEA 4001",
    "wert_vorher": 5000,
    "wert_nachher": 10000,
}
```

Zweck: Debugging, Demo-Wert (zeigt Planungsrational), Basis für Report-Narrativ.

**Deliverable:** Befüllter `reasoning_log` im State nach jedem LLM-Agenten, Ausgabe im Report.

---

### P8 — Fallback-Strategie systematisieren
**Querschnittsthema, begleitend zu P3–P6.**

Heute haben einige Agenten Fallbacks, andere nicht. Ziel: Jeder LLM-Agent hat einen definierten deterministischen Fallback, der beim Fehlen eines API-Keys oder bei LLM-Fehler greift — und das transparent im `reasoning_log` vermerkt.

Standard-Muster für alle LLM-Agenten:
```python
try:
    result = _llm_call(...)
    reasoning_log.append({..., "quelle": "llm"})
except Exception:
    result = _deterministic_fallback(...)
    reasoning_log.append({..., "quelle": "fallback", "grund": str(e)})
```

**Deliverable:** Konsistentes Fallback-Muster in allen LLM-Agenten, kein Agent wirft unkontrollierte Fehler.

---

### P9 — Briefing Agent: Bewusst ausgeklammert
**Nicht in diesem Zug.**

Der Briefing Agent ist der Einstiegspunkt der Pipeline. Ein Fehler dort bricht alles ab. Er wird erst angepasst, wenn P1–P5 stabil und getestet sind. Bis dahin bleibt er deterministisch.

**Begründung:** Minimierung des Risikos in der Stabilisierungsphase.

---

## 5. Abhängigkeiten und empfohlene Reihenfolge

```
Phase 1 (Fundament):
  P1 State-Schema    ──┐
  P2 Wissensbasis    ──┴──► abgeschlossen bevor Phase 2 beginnt

Phase 2 (LLM-Kern):
  P3 Rule Agent/LLM  ──────► P4 Topology+Strategy  ──► P5 Layout-Typologien

Phase 2 parallel:
  P6 Analyse+Report  (unabhängig von P3–P5, kann parallel starten)
  P7 Reasoning Log   (begleitend, wird in P3–P6 befüllt)
  P8 Fallbacks       (begleitend, parallel zu jedem LLM-Agenten)

Phase 3 (später):
  P9 Briefing Agent  (nach Stabilisierung P1–P5)
```

---

## 6. Schnittstellen zwischen Paketen

| Von | An | Übergabe |
|---|---|---|
| P2 (YAML) | P3 (Rule/LLM) | `rules_hard` + `rules_conventions` als strukturierter Input |
| P3 (Rule/LLM) | P4 (Strategy) | `interpreted_rules` im State (pro Variante) |
| P4 (Strategy) | P5 (Layout) | `zone_roles` + `typology_assignments` im State |
| P7 (Log) | P6 (Report) | `reasoning_log` als strukturierte Liste im State |
| P8 (Fallback) | alle LLM-Agenten | Gemeinsames Wrapper-Muster |

---

## 7. Nicht-Ziele

Die folgenden Punkte sind **bewusst nicht** Teil dieses Refactorings:

- **Briefing Agent Umbau** (P9) — erst nach Stabilisierung P1–P5
- **Rhino.Compute REST API** — der Compute-Server liefert HTTP 500 (Hops-Bundle unterstützt keine externen GH-Evaluierungen); bleibt dokumentiert als zukünftige Erweiterung
- **Neue Nutzungstypen** — kein neuer Nutzungstyp (z. B. Gesundheitsbau, Einzelhandel) in diesem Zug
- **UI / Frontend** — kein Web-Interface, Pipeline bleibt CLI
- **Detailplanung** — keine Ausführungsplanung, Statik, TGA-Dimensionierung; Vorentwurfsniveau
- **Kostenschätzung** — keine BGF-basierte Kostenermittlung
- **Human-in-the-Loop** — iterativer Dialog mit Nutzer (LangGraph-Feature) ist konzeptuell vorbereitet, aber nicht implementiert

---

## 8. Risiken

| Risiko | Wahrscheinlichkeit | Maßnahme |
|---|---|---|
| LLM-Output außerhalb Schema | mittel | Pydantic-Validierung + Fallback (P8) |
| Latenz durch mehr LLM-Calls | hoch | Parallelisierung wo möglich, Caching |
| Inkonsistente `zone_roles` zwischen Varianten | mittel | Validierung in Evaluation Agent |
| Layout-Typologiefunktionen produzieren Überlappungen | mittel | Bestehender Overlap-Resolver bleibt erhalten |
| YAML-Trennung hart/weich unvollständig | niedrig | Review vor P3-Start |

---

## 9. Offene Fragen und Entscheidungen

1. **Modellwahl für LLM-Planungsrat:** ✅ **Entschieden.**  
   Demo: Bestehendes OpenAI-Modell aus `.env` (`OPENAI_MODEL`, Default `gpt-4o-mini`).  
   Keine Änderung an `app/llm.py` im Rahmen dieses Refactorings.  
   Perspektivisch: Modellauswahl pro Agent als konfigurierbare Option (z. B. stärkeres Modell für Planungsrat, schnelles Modell für Report) — als separates Paket nach Stabilisierung.

2. **Parallelisierung der Disziplinen:** Im Hybrid-Ansatz (Single Call) läuft alles sequenziell. Falls Qualität nicht ausreicht → Umstieg auf parallele Calls pro Disziplin. Entscheidung nach erstem Test von P3.

3. **Reasoning Log im Bericht:** ✅ **Entschieden.**  
   Nur Zusammenfassung im Bericht. Vollständiger Log wird als `outputs/reasoning_log.json` gespeichert, aber nicht in den Markdown-Report übernommen.

4. **Testdaten:** ✅ **Entschieden.**  
   Nach Abschluss von P1–P5 werden neue Testbriefings erstellt, die die drei Typologien (Kamm, Block+Reserve, Kreuzgang) gezielt triggern. Je ein Briefing pro Nutzungstyp (Produktion, Logistik, Datacenter), jeweils mit Sonderbedingungen die Regelkonflikte erzeugen.

---

## 10. Freigabe

| | Name | Datum | Unterschrift |
|---|---|---|---|
| Erstellt | — | 2026-05-13 | — |
| Geprüft | | | |
| Freigegeben | | | |

Nach Freigabe: Umsetzung startet mit **P1 (State-Schema)** und **P2 (Wissensbasis)** parallel.

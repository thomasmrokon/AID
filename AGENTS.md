# AGENTS.md — Multi-AI Collaboration Guide

Dieses Projekt wird mit drei KI-Assistenten parallel entwickelt.
Diese Datei definiert **Modulverantwortung**, **Interface-Contracts** und **Arbeitsregeln**,
damit Änderungen konfliktfrei parallel entstehen können.

---

## Assistenten & Stärken

| Assistent | VS Code Extension | Stärke |
|-----------|------------------|--------|
| **Claude Code** | Claude Code (Anthropic) | Architektur, komplexe Algorithmen, State-Contracts, autonomes Write/Run |
| **GitHub Copilot** | GitHub Copilot Chat | Inline-Completion, musterhafter Rendering-Code, Boilerplate, Test-Skripte |
| **Gemini Code Assist** | Google Cloud Code | YAML/JSON-Transformation, LLM-Prompt-Engineering, Report-Generierung |

---

## Modulverantwortung

### Claude Code (Owner)
```
app/state.py                      ← Contract-Owner, einziger Schreiber
app/agents/layout.py              ← Kern-Layout-Engine (bestehende Typologien)
app/agents/layout_optimizer.py    ← Slicing-Floorplan-Optimizer
app/agents/layout_recursive.py    ← Rekursiver Raumteiler
app/agents/strategy.py            ← Typologiezuweisung
app/agents/masterplan.py          ← Masterplanung-Agent (Sprint R)
app/agents/process.py             ← Prozessplanung-Agent / Strip-Packing (Sprint Q)
streamlit_app.py                  ← UI-Orchestrator (tightly coupled)
app/graph.py                      ← Pipeline-Reihenfolge
```

### GitHub Copilot (Owner)
```
app/tools/drawing.py            ← Matplotlib-Rendering (Grundriss)
app/tools/masterplan_viz.py     ← Masterplan-Lageplan Matplotlib (Sprint R)
app/tools/process_viz.py        ← Maschinenlayout + Sankey (Sprint Q)
app/tools/viewer3d.py           ← Plotly 3D-Viewer
app/tools/graph_viz.py          ← Interaktiver Funktionsgraph
app/agents/evaluation.py        ← Deterministische Scoring-Logik
app/tools/scoring.py            ← Scoring-Formeln
scripts/                        ← Test-Skripte, Debugging
```

### Gemini Code Assist (Owner)
```
app/agents/rules.py             ← YAML-Loading + LLM Planning Council
app/agents/topology.py          ← Prozessdiagramm-Generierung
app/agents/briefing.py          ← Pydantic-Validierung + LLM-Parsing
app/agents/analyse.py           ← Qualitative LLM-Analyse
app/agents/report.py            ← Markdown + Artefakt-Export
app/tools/site.py               ← Demo-Grundstücke + Envelope
app/data/*.yaml                 ← Regelwerk-Daten
app/llm.py                      ← LLM-Abstraktion (inkl. Anthropic-Support)
```

### Geteilte Tools (alle: nur lesen, Änderungen via Claude koordinieren)
```
app/tools/geometry.py           ← Zone dataclass + Geometrie-Utilities
app/tools/rules_ui.py           ← Streamlit-Regelwerk-UI
app/tools/rhino_*.py            ← 3D-Export (isoliert, kein Upstream-Impact)
```

---

## Interface-Contracts (nicht einseitig ändern)

### Contract A: PlanningState (`app/state.py`)
- **Owner**: Claude Code
- **Regel**: Jeder neue State-Key bekommt einen Ownership-Kommentar:
  ```python
  # Owner: claude | Readers: layout, evaluation
  new_key: list[str]
  ```
- **Änderung**: Nur Claude darf Felder hinzufügen/umbenennen. Andere Assistenten
  stellen einen Pull-Request-Vorschlag (Markdown-Kommentar) bereit.

### Contract B: Zone Dataclass (`app/tools/geometry.py`)
- **Owner**: Claude Code (Koordination)
- **Consumer**: `layout.py`, `evaluation.py`, `drawing.py`, `viewer3d.py`, `scoring.py`, `rhino_geometry.py`
- **Regel**: Felder nicht umbenennen/entfernen ohne alle Consumer gleichzeitig anzupassen.
  Neue optionale Felder (mit Default) sind erlaubt.

### Contract C: Agent-Signatur-Standard
Jeder Agent dokumentiert am Anfang der Funktion, was er liest und schreibt:
```python
def agent_name(state: PlanningState) -> dict[str, Any]:
    # READS:  state["structured_briefing"], state["rules"]
    # WRITES: {"my_output_key": computed_value}
    # DEPENDS_ON: briefing_agent, rules_agent
```

### Contract E: OptimizationResult (`app/agents/layout_optimizer.py`)
- **Owner**: Claude Code
- **Consumer (lesen)**:
  - Copilot → `evaluation.py` / `scoring.py`: liest `objective_components`, `zone_decisions[].area_delta_pct`
  - Gemini  → `rules.py` / Prompts: liest `zone_decisions[].human_reason`-Kontext für LLM-Begründungen
  - `drawing.py` (Copilot): liest `tree_topology`, `envelope_used.rotation_deg` für Overlay
- **Regel**: `OptimizationResult`-Felder nicht umbenennen ohne alle Consumer zu informieren.
  Neue optionale Felder (mit Default) sind erlaubt.
- **Tragwerk-Integration**: `TragwerkConstraints` kommt von Gemini (`briefing.py`/`rules.py`)
  und wird als Parameter an `optimize_layout()` übergeben — kein direkter State-Zugriff.

### Contract D: Pipeline-Reihenfolge (`app/graph.py`)
- **Owner**: Claude Code
- **Regel**: Reihenfolge der LangGraph-Nodes nicht ändern ohne End-to-End-Test.
  Neuen Node immer am Ende der Pipeline einfügen.

---

## Git Worktree Setup

```bash
# Im Hauptverzeichnis (Claude arbeitet hier):
cd c:/DEV/dreso-industriebau-demo

# Copilot-Worktree anlegen:
git worktree add ../dreso-copilot feature/copilot-viz

# Gemini-Worktree anlegen:
git worktree add ../dreso-gemini feature/gemini-rules

# Übersicht:
git worktree list
```

Nach dem Sprint — Merge in main:
```bash
git merge feature/copilot-viz
git merge feature/gemini-rules
```

---

## Sprint-Workflow

1. **Zu Sprintbeginn**: Tasks in GitHub Issues oder dieser Datei definieren (je Assistent)
2. **Parallel arbeiten**: Jeder Assistent in seinem Worktree-Verzeichnis
3. **Contract-Änderungen**: Über Claude koordinieren, AGENTS.md + state.py zuerst aktualisieren
4. **Integration**: `git merge` + End-to-End-Test (`streamlit run streamlit_app.py`)
5. **Review**: Alle drei Assistenten können gegenseitig Reviews geben (Chat-basiert)

---

## Kurzfristiger Einstieg (ohne Worktrees)

Copilot und Gemini als Review-Partner:
- Claude schreibt Code → Gemini/Copilot im Chat fragen: *"Was würdest du hier anders machen?"*
- Claude entscheidet, ob der Vorschlag übernommen wird
- Kein Merge-Risiko, keine Einrichtung nötig

---

## Aktueller Stand (Stand: 2026-05-27)

Abgeschlossene Sprints: M · N · O · P · Q · R · S · **T**  
Worktrees vorhanden: `../dreso-copilot` (feature/copilot-viz) · `../dreso-gemini` (feature/gemini-rules)  
Workspace: `dreso.code-workspace` ✅

### Sprint T (abgeschlossen — Claude, 2026-05-27)

| Tag | Feature | Dateien |
|-----|---------|---------|
| F1 | Plotly 3D-Viewer: VF als transparente Bodenplatte, Techniktrassen immer sichtbar (Modus A+B), kameraadaptive Perspektive | `app/tools/viewer3d.py`, `app/tools/geometry.py` |
| F2 | Funktionsgraph interaktiv: Kanten/Knoten per Klick auswählbar (`on_select="rerun"`), Kontextpanel mit Slider + Verbindungs-Dialog | `app/tools/graph_viz.py`, `streamlit_app.py` |
| C1 | VF-Zone als Korridor: `ax.annotate` Richtungspfeile, warmer Sandton `#F0EAD8`, gepunktete Kontur | `app/tools/drawing.py` |
| C2 | pytest-Grundgerüst: session-scoped Fixtures, 26 Tests (briefing/rules/layout/drawing/evaluation/masterplan) | `tests/` (neu) |
| P0 | P0-Verifikation Layout-Vollständigkeit: 9/9 Zonen in 3 Varianten × 3 Grundstücken bestätigt; `test_layout_all_topology_nodes_present` | `tests/test_layout.py` |
| P0 | P0-Verifikation Stellplatz-Grenzen: 0 Boundary-Violations; `_polygon_effective_south`-Tests | `tests/test_drawing.py` |

Testsuite: **26/26 grün** (`python -m pytest tests/ -q`)

---

### Nächster Sprint — offene Tasks

| Prio | Assistent | Task | Datei |
|------|-----------|------|-------|
| P2 | **Claude** | Regelwerk-Katalog (Schritt 5): Zwei-Phasen-UI statt YAML-Editor | `app/tools/rules_ui.py` (neu), `streamlit_app.py` |
| P3 | **Gemini** | Claude/Anthropic-Modell-Support | `app/llm.py`, `pyproject.toml` |
| P3 | **Claude** | Erschließung als Verbinder (VF als Graph-Attribut, nicht Zone) | `app/agents/layout.py`, `app/tools/scoring.py` |

Worktrees vor Sprint-Start auf main-Stand bringen:
```bash
# Im dreso-copilot Verzeichnis:
git rebase main

# Im dreso-gemini Verzeichnis:
git rebase main
```

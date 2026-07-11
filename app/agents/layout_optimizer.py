"""
AID Demo – Slicing-Floorplan-Optimizer

Isotroper Layoutgenerator auf Basis rekursiver Rechteck-Partitionierung (Slicing Floorplan)
und scipy.optimize. Ersetzt die festen Typologien (Kamm, Kreuzgang, block_reserve) durch
einen einheitlichen Optimierer, der Topologie aus dem Funktionsgraphen ableitet.

ARCHITEKTUR (zwei Ebenen):
  Äußere Ebene  → optimize_envelope()  : Gebäudeposition + Rotation auf Grundstück
  Innere Ebene  → optimize_layout()    : Zonenorganisation im Envelope

OWNER: Claude Code
READS:  topology_diagram, adjacency_weights, interpreted_rules, site_geometry
WRITES: list[Zone], OptimizationResult (→ Entscheidungsprotokoll)

CONTRACT:
  - Zone-Dataclass (geometry.py) wird nicht verändert. Alle Ausgaben sind list[Zone].
  - OptimizationResult ist additiv — bestehende State-Keys bleiben kompatibel.
  - TragwerkConstraints kommen aus interpreted_rules["tragwerk"]; Fallback = Defaults unten.
  - Copilot: scoring.py + evaluation.py konsumieren OptimizationResult.objective_components.
  - Gemini:  rules.py + briefing.py liefern TragwerkConstraints; Prompts für
             OptimizationResult.zone_decisions (Entscheidungsprotokoll).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import scipy.optimize

from app.tools.geometry import Zone


# ---------------------------------------------------------------------------
# Öffentliche Datenstrukturen  (Consumer: evaluation.py, drawing.py, rules.py)
# ---------------------------------------------------------------------------

@dataclass
class TragwerkConstraints:
    """Tragwerks-Parameter als harte Constraints in der Objective Function.

    Owner: Claude (Definition). Befüllung durch Gemini (briefing.py / rules.py).
    """
    raster_x_m:      float = 9.0    # Stützenraster West–Ost [m]
    raster_y_m:      float = 9.0    # Stützenraster Süd–Nord [m]
    traufhoehe_m:    float = 8.0    # Lichte Traufhöhe Hallenbereich [m]
    max_aspect_ratio: float = 4.0   # Maximales Seitenverhältnis einer Zone

    @classmethod
    def from_interpreted_rules(cls, rules: dict) -> "TragwerkConstraints":
        """Extrahiert Constraints aus interpreted_rules[variante]["tragwerk"]."""
        t = rules if rules else {}
        return cls(
            raster_x_m=float(t.get("raster_standard_x_m") or t.get("raster_x_m") or 9.0),
            raster_y_m=float(t.get("raster_standard_y_m") or t.get("raster_y_m") or 9.0),
            traufhoehe_m=float(t.get("traufhoehe_standard_m") or t.get("traufhoehe") or 8.0),
            max_aspect_ratio=float(t.get("max_aspect_ratio") or 4.0),
        )


@dataclass
class OptimizationWeights:
    """Steuert die Prioritäten der Objective Function.

    Jede Variante hat ein eigenes Gewichtsprofil (analog zu VARIANT_SETTINGS).
    Owner: Claude. Copilot liest objective_components für Scoring.
    """
    area_delta:    float = 1.0   # Flächentreue (immer hoch)
    adjacency:     float = 1.5   # Nähe gewichtiger Nachbarn lt. Funktionsgraph
    aspect_ratio:  float = 0.8   # Penalty für extreme Seitenverhältnisse
    grid_snap:     float = 0.6   # Penalty für Abweichung vom Tragwerksraster
    compactness:   float = 0.4   # Penalty für fragmentierten Fußabdruck
    expansion:     float = 0.0   # Bonus für freie Erweiterungsfassade (Variante B)

    @classmethod
    def for_variant(cls, variante_key: str) -> "OptimizationWeights":
        """Voreinstellungen je Variante — analog zu VARIANT_SETTINGS in layout.py.

        area_delta und aspect_ratio sind beide NICHT durch n geteilt → direkt vergleichbar.
        AR-Penalties sind ~10× stärker wenn verletzt → automatische Priorisierung.
        """
        presets = {
            "A_Materialfluss": cls(
                area_delta=2.0, adjacency=1.5, aspect_ratio=3.0,
                grid_snap=0.3, compactness=0.3, expansion=0.0,
            ),
            "B_Erweiterbarkeit": cls(
                area_delta=2.0, adjacency=0.8, aspect_ratio=2.5,
                grid_snap=0.3, compactness=0.8, expansion=1.0,
            ),
            "C_Ausgewogen": cls(
                area_delta=2.0, adjacency=1.0, aspect_ratio=3.0,
                grid_snap=0.4, compactness=0.5, expansion=0.3,
            ),
        }
        return presets.get(variante_key, cls())


@dataclass
class ZoneDecision:
    """Begründung für die Platzierung einer Zone. → Entscheidungsprotokoll.

    Gemini befüllt human_reason aus LLM-Prompt auf Basis der technischen Felder.
    """
    zone_name:       str
    position:        tuple[float, float]   # (x, y) Zentroid
    area_delta_pct:  float
    adjacency_score: float                 # 0–1: wie gut sind Nachbarn erfüllt
    aspect_ratio:    float
    grid_deviation_m: float                # mittlere Abweichung vom Raster
    human_reason:    str = ""              # Gemini: LLM-generierte Begründung


@dataclass
class OptimizationResult:
    """Vollständiges Ergebnis des Optimierers. Stabiler Contract für alle Consumer.

    Owner: Claude. Copilot liest objective_components + iterations.
    Gemini liest zone_decisions für Prompt-Kontext.
    """
    zones:               list[Zone]
    objective_value:     float
    objective_components: dict[str, float]  # {"area_delta": 0.12, "adjacency": 0.34, ...}
    zone_decisions:      list[ZoneDecision]
    tree_topology:       str               # z.B. "H(Prod|V(WE|Versand))|H(Büro|Sozial)"
    envelope_used:       dict              # {"width_m": 66, "depth_m": 54, "rotation_deg": 12}
    iterations:          int
    converged:           bool
    warnings:            list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Slicing-Tree — interne Darstellung des Layouts
# ---------------------------------------------------------------------------

@dataclass
class SlicingNode:
    """Knoten im binären Slicing-Baum.

    Blattknoten: zone_name gesetzt, ratio/direction/left/right = None.
    Interne Knoten: direction + ratio gesetzt, zone_name = None.

    ratio ∈ [0.15, 0.85]: Anteil des linken/unteren Teilrechtecks an Breite (H) bzw. Tiefe (V).
    """
    # Interner Knoten
    direction: Literal["H", "V"] | None = None  # H = horizontaler Schnitt, V = vertikal
    ratio:     float | None = None               # Optimierungsvariable
    left:      "SlicingNode | None" = None
    right:     "SlicingNode | None" = None
    # Blattknoten
    zone_name: str | None = None

    @property
    def is_leaf(self) -> bool:
        return self.zone_name is not None

    def to_str(self) -> str:
        """Kompakte Darstellung für Entscheidungsprotokoll."""
        if self.is_leaf:
            return self.zone_name or "?"
        d = self.direction or "?"
        l = self.left.to_str() if self.left else "?"
        r = self.right.to_str() if self.right else "?"
        return f"{d}({l}|{r})"

    def collect_ratios(self) -> list[float]:
        """Alle Ratio-Werte in Pre-Order — Reihenfolge für scipy.optimize x-Vektor."""
        if self.is_leaf:
            return []
        ratios = [self.ratio or 0.5]
        if self.left:
            ratios.extend(self.left.collect_ratios())
        if self.right:
            ratios.extend(self.right.collect_ratios())
        return ratios

    def apply_ratios(self, ratios: list[float], idx: int = 0) -> int:
        """Schreibt optimierte Ratios zurück in den Baum. Gibt neuen Index zurück."""
        if self.is_leaf:
            return idx
        self.ratio = float(np.clip(ratios[idx], 0.05, 0.95))
        idx += 1
        if self.left:
            idx = self.left.apply_ratios(ratios, idx)
        if self.right:
            idx = self.right.apply_ratios(ratios, idx)
        return idx


# ---------------------------------------------------------------------------
# Öffentliche API  (Consumer: layout.py → _layout_from_topology)
# ---------------------------------------------------------------------------

def optimize_layout(
    *,
    nodes: list[dict],
    topology: dict,
    envelope: dict,
    adjacency_weights: dict[str, float],
    weights: OptimizationWeights,
    tragwerk: TragwerkConstraints,
    n_tree_candidates: int = 12,
    max_iterations: int = 400,
    seed: int = 42,
) -> OptimizationResult:
    """Innere Ebene: Zonenlayout im gegebenen Envelope optimieren.

    Erzeugt N Topologie-Kandidaten aus dem Funktionsgraphen, optimiert die
    Schnittverhältnisse jedes Kandidaten mit scipy.optimize.minimize (L-BFGS-B)
    und gibt das beste Ergebnis zurück.

    Args:
        nodes:              Zonenliste (nach _with_dimensions, aus topology_diagram).
        topology:           topology_diagram (process_order, adjacency, nodes).
        envelope:           Gebäude-Envelope dict (x, y, width_m, depth_m).
        adjacency_weights:  {"{ZoneA}|{ZoneB}": weight} aus state["adjacency_weights"].
        weights:            OptimizationWeights für diese Variante.
        tragwerk:           TragwerkConstraints aus interpreted_rules.
        n_tree_candidates:  Anzahl Topologie-Varianten die probiert werden.
        max_iterations:     Max. scipy-Iterationen pro Kandidat.
        seed:               Seed für Topologie-Generierung (Reproduzierbarkeit).

    Returns:
        OptimizationResult mit zones (list[Zone]), Metriken und Entscheidungsprotokoll.
    """
    candidates = _generate_tree_topologies(
        nodes=nodes,
        topology=topology,
        adjacency_weights=adjacency_weights,
        n=n_tree_candidates,
        seed=seed,
    )

    best: OptimizationResult | None = None
    for tree in candidates:
        result = _optimize_slicing_tree(
            tree=tree,
            nodes=nodes,
            envelope=envelope,
            adjacency_weights=adjacency_weights,
            weights=weights,
            tragwerk=tragwerk,
            max_iterations=max_iterations,
        )
        if best is None or result.objective_value < best.objective_value:
            best = result

    assert best is not None
    return best


def optimize_envelope(
    *,
    nodes: list[dict],
    site_polygon_coords: list[tuple[float, float]],
    total_footprint_m2: float,
    tragwerk: TragwerkConstraints,
    rotation_step_deg: float = 10.0,
    min_coverage: float = 0.90,
) -> dict:
    """Äußere Ebene: Optimales rechteckiges Envelope auf dem Grundstück finden.

    Grid-Search über Rotationswinkel (0°–90°) × Aspect-Ratios (0.5–2.5),
    bewertet nach Coverage (Envelope ∩ Baufeld / Envelope) × Kompaktheit.

    Für jeden Kandidaten (rotation, aspect):
    1. Gebäude-Rechteck aus total_footprint_m2 × aspect berechnen
    2. Kanten auf Tragwerksraster snappen
    3. Zentriert im Baufeld positionieren
    4. Site-Polygon um -rotation drehen (äquivalent zu Gebäuderotation)
    5. Coverage und Score berechnen
    6. Bestes Kandidat-Envelope zurückgeben

    Returns:
        Envelope-Dict: {"x", "y", "width_m", "depth_m", "rotation_deg",
                        "coverage", "area_m2", "max_footprint_m2"}.
    """
    from shapely.geometry import Polygon, box as shapely_box
    from shapely.affinity import rotate as shapely_rotate

    site_poly = Polygon(site_polygon_coords)
    site_cx, site_cy = site_poly.centroid.x, site_poly.centroid.y
    rx = tragwerk.raster_x_m
    ry = tragwerk.raster_y_m

    # Aspect-Ratios: bevorzugt breite Industrie-Grundrisse (1.2–2.5)
    aspect_ratios = [0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5]
    rotations = list(np.arange(0.0, 90.0, rotation_step_deg))

    best: dict | None = None
    best_score = -1.0

    for aspect in aspect_ratios:
        raw_w = math.sqrt(total_footprint_m2 * aspect)
        raw_d = total_footprint_m2 / raw_w
        # Snap auf Raster
        w = max(rx, round(raw_w / rx) * rx)
        d = max(ry, round(raw_d / ry) * ry)
        env_area = w * d

        for rot_deg in rotations:
            # Envelope zentriert im Baufeld-Schwerpunkt (unrotiert)
            env_x = site_cx - w / 2
            env_y = site_cy - d / 2
            envelope_poly = shapely_box(env_x, env_y, env_x + w, env_y + d)

            # Site um -rot_deg drehen (Baufeld in Gebäude-Koordinatensystem)
            rotated_site = shapely_rotate(site_poly, -rot_deg, origin=(site_cx, site_cy))

            intersection = envelope_poly.intersection(rotated_site)
            coverage = intersection.area / max(1.0, env_area)

            if coverage < min_coverage:
                continue

            # Score: Coverage × Kompaktheit (wenig überstehendes Envelope)
            compactness = intersection.area / max(1.0, site_poly.area)
            score = coverage * 0.7 + compactness * 0.3

            if score > best_score:
                best_score = score
                best = {
                    "x": round(env_x, 2),
                    "y": round(env_y, 2),
                    "width_m": w,
                    "depth_m": d,
                    "rotation_deg": rot_deg,
                    "coverage": round(coverage, 3),
                    "area_m2": env_area,
                    "max_footprint_m2": env_area,
                }

    if best is None:
        # Kein Kandidat über min_coverage — bestes ohne Coverage-Filter
        w = max(rx, round(math.sqrt(total_footprint_m2 * 1.5) / rx) * rx)
        d = max(ry, round(total_footprint_m2 / w / ry) * ry)
        env_x = site_cx - w / 2
        env_y = site_cy - d / 2
        best = {
            "x": round(env_x, 2),
            "y": round(env_y, 2),
            "width_m": w,
            "depth_m": d,
            "rotation_deg": 0.0,
            "coverage": 0.0,
            "area_m2": w * d,
            "max_footprint_m2": w * d,
        }

    return best


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen  (nicht Teil des öffentlichen Contracts)
# ---------------------------------------------------------------------------

def _generate_tree_topologies(
    nodes: list[dict],
    topology: dict,
    adjacency_weights: dict[str, float],
    n: int,
    seed: int,
) -> list[SlicingNode]:
    """Erzeugt N Slicing-Tree-Topologien, geleitet durch den Funktionsgraphen.

    Strategie:
    - Kandidat 0:        Prozesslinear — Prozesskette als V-Kette, Supportzonen als H-Schnitt
    - Kandidate 1…N//2:  Adjazenz-gesteuertes greedy-agglomeratives Clustering
    - Kandidate N//2…N:  Zufällige Permutationen mit fixem Seed
    - Alle: Proportions-basierte Ratios als Startwert für scipy (nicht 0.5-flat)
    """
    all_names = [nd["name"] for nd in nodes]
    if not all_names:
        return [SlicingNode(zone_name="?")]
    if len(all_names) == 1:
        return [SlicingNode(zone_name=all_names[0])]

    node_map = {nd["name"]: nd for nd in nodes}
    process_order = topology.get("process_order") or []
    process_set = set(process_order)

    process_names = [name for name in process_order if name in set(all_names)]
    support_names = [name for name in all_names if name not in process_set]

    candidates: list[SlicingNode] = []

    # ── Kandidat 0: Größen-balanciert ─────────────────────────────────────
    tree0 = _build_process_linear_tree(process_names, support_names, node_map)
    _set_proportion_ratios(tree0, node_map)
    candidates.append(tree0)

    # ── Kandidaten 1…N//2: Adjazenz-gesteuertes Clustering ────────────────
    n_adj = max(1, n // 2)
    rng_adj = np.random.default_rng(seed + 100)
    perm = list(all_names)
    for i in range(n_adj):
        if i > 0:
            rng_adj.shuffle(perm)
        tree = _greedy_adjacency_tree(list(perm), adjacency_weights)
        _set_proportion_ratios(tree, node_map)
        candidates.append(tree)
        if len(candidates) >= n:
            break

    # ── Kandidaten N//2…N: Zufällige Permutationen ────────────────────────
    rng_rand = np.random.default_rng(seed)
    while len(candidates) < n:
        perm = list(all_names)
        rng_rand.shuffle(perm)
        tree = _build_balanced_tree(perm)
        _set_proportion_ratios(tree, node_map)
        candidates.append(tree)

    return candidates[:n]


# ---------------------------------------------------------------------------
# Topologie-Bau-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _zone_footprint(name: str, node_map: dict[str, dict]) -> float:
    """Fußabdruck einer Zone = area_m2 / floors (Grundrissfläche)."""
    nd = node_map.get(name, {})
    area = float(nd.get("area_m2", 0) or 0)
    floors = max(1, int(nd.get("floors", 1) or 1))
    return max(1.0, area / floors)


def _subtree_footprint(node: SlicingNode, node_map: dict[str, dict]) -> float:
    """Summe der Fußabdrücke aller Blätter im Teilbaum."""
    if node.is_leaf:
        return _zone_footprint(node.zone_name or "", node_map)
    l = _subtree_footprint(node.left, node_map) if node.left else 0.0
    r = _subtree_footprint(node.right, node_map) if node.right else 0.0
    return l + r


def _set_proportion_ratios(node: SlicingNode, node_map: dict[str, dict]) -> None:
    """Setzt Ratio = linker Fußabdruck / Gesamtfußabdruck (Pre-Order, rekursiv).

    Gibt scipy einen viel besseren Startwert als flat 0.5.
    """
    if node.is_leaf:
        return
    l_fp = _subtree_footprint(node.left,  node_map) if node.left  else 0.0
    r_fp = _subtree_footprint(node.right, node_map) if node.right else 0.0
    total = l_fp + r_fp
    node.ratio = max(0.10, min(0.90, l_fp / total)) if total > 0 else 0.5
    if node.left:
        _set_proportion_ratios(node.left,  node_map)
    if node.right:
        _set_proportion_ratios(node.right, node_map)


def _build_vchain(names: list[str], direction: Literal["H", "V"] = "V") -> SlicingNode:
    """Baut eine rechtslastige Kette: dir(name0 | dir(name1 | dir(name2 | …)))."""
    if len(names) == 1:
        return SlicingNode(zone_name=names[0])
    return SlicingNode(
        direction=direction,
        ratio=0.5,
        left=SlicingNode(zone_name=names[0]),
        right=_build_vchain(names[1:], direction),
    )


def _build_process_linear_tree(
    process_names: list[str],
    support_names: list[str],
    node_map: dict[str, dict] | None = None,
) -> SlicingNode:
    """Kandidat 0: Größen-balanciertes Layout.

    Struktur (V = West-Ost-Schnitt, H = Süd-Nord-Schnitt):
        V(
          V(H(kleine_prozess_zonen) | grosse_prozess_zone),  # Prozessblock
          H(support_zonen),                                    # Support-Band
        )

    Kleine Zonen (Logistik) bilden Tiefenstreifen (H-Kette) neben der großen Halle,
    damit alle Zonen Seitenverhältnisse < 4:1 erreichen.
    """
    node_map = node_map or {}
    all_names = process_names + support_names
    if not all_names:
        return SlicingNode(zone_name="?")
    if len(all_names) == 1:
        return SlicingNode(zone_name=all_names[0])
    if not support_names:
        return _build_size_grouped_process_tree(process_names, node_map)
    if not process_names:
        return _build_vchain(support_names, "H")

    proc_tree = _build_size_grouped_process_tree(process_names, node_map)
    supp_tree = _build_vchain(support_names, "H")  # Tiefenstreifen
    return SlicingNode(direction="V", ratio=0.5, left=proc_tree, right=supp_tree)


def _build_size_grouped_process_tree(
    process_names: list[str],
    node_map: dict[str, dict],
) -> SlicingNode:
    """Drei-Spalten-Layout: mittlere Logistik | kleine Logistik | Großhalle.

    Warum drei Spalten: Kleine Zonen (z.B. QS 150m²) in einer breiten Logistik-
    Spalte erhalten zu wenig Tiefe → Seitenverhältnis > 4:1. Eigene schmalere
    Spalte gibt kleinen Zonen genug Tiefe (AR-konform ohne Area-Kompromiss).

    Struktur:
        V(
          H(mittlere_zonen),                    # z.B. LagRoh | LagFW (breite Spalte)
          V(H(kleine_zonen) | grosse_zone),     # z.B. H(WE|Versand|QS) | Produktion
        )
    """
    if len(process_names) == 1:
        return SlicingNode(zone_name=process_names[0])

    fps = {n: _zone_footprint(n, node_map) for n in process_names}
    total_fp = sum(fps.values()) or 1.0
    sorted_proc = sorted(process_names, key=lambda n: fps[n], reverse=True)

    # Groß: fp > 40 % → Haupthalle (eigene Spalte rechts)
    big = [n for n in sorted_proc if fps[n] > 0.40 * total_fp]
    rest = [n for n in sorted_proc if n not in big]

    if not big or not rest:
        return _build_vchain(sorted_proc, "H")

    big_tree = (SlicingNode(zone_name=big[0]) if len(big) == 1
                else _build_vchain(big, "H"))

    # Unter den verbleibenden: mittel (> 10 % Gesamt-fp) vs klein (≤ 10 %)
    # 10 %-Grenze trennt LagRoh/LagFW (≥ 12 %) von WE/Versand/QS (< 10 %)
    medium = [n for n in rest if fps[n] > 0.10 * total_fp]
    small  = [n for n in rest if n not in medium]

    if not medium:
        return SlicingNode(direction="V", ratio=0.5,
                           left=_build_vchain(small, "H"), right=big_tree)
    if not small:
        return SlicingNode(direction="V", ratio=0.5,
                           left=_build_vchain(medium, "H"), right=big_tree)

    # Dreigeteilte Struktur: V(medium_col | V(small_col | big_hall))
    medium_tree = _build_vchain(medium, "H")
    small_tree  = _build_vchain(small, "H")
    inner = SlicingNode(direction="V", ratio=0.5, left=small_tree, right=big_tree)
    return SlicingNode(direction="V", ratio=0.5, left=medium_tree, right=inner)


def _greedy_adjacency_tree(
    names: list[str],
    adjacency_weights: dict[str, float],
) -> SlicingNode:
    """Greedy agglomeratives Clustering: merget Paare mit höchster Adjazenz.

    Beginn: jede Zone = Blatt. Pro Schritt: Cluster-Paar mit höchstem
    kombiniertem Adjazenz-Gewicht → neuer interner Knoten.
    Richtung wechselt je Tiefe (V/H) für kompaktere Layouts.
    """
    clusters: list[SlicingNode] = [SlicingNode(zone_name=name) for name in names]
    cluster_sets: list[list[str]] = [[name] for name in names]
    depth = 0

    while len(clusters) > 1:
        best_i, best_j, best_w = 0, 1, -1.0
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                w = sum(
                    adjacency_weights.get(f"{a}|{b}", 0.0)
                    + adjacency_weights.get(f"{b}|{a}", 0.0)
                    for a in cluster_sets[i]
                    for b in cluster_sets[j]
                )
                if w > best_w:
                    best_w, best_i, best_j = w, i, j

        direction: Literal["H", "V"] = "V" if depth % 2 == 0 else "H"
        merged = SlicingNode(
            direction=direction,
            ratio=0.5,
            left=clusters[best_i],
            right=clusters[best_j],
        )
        merged_names = cluster_sets[best_i] + cluster_sets[best_j]
        keep = [k for k in range(len(clusters)) if k not in (best_i, best_j)]
        clusters = [clusters[k] for k in keep] + [merged]
        cluster_sets = [cluster_sets[k] for k in keep] + [merged_names]
        depth += 1

    return clusters[0]


def _build_balanced_tree(names: list[str]) -> SlicingNode:
    """Baut einen balancierten Slicing-Baum aus einer Zonenliste (Hilfsfunktion)."""
    if len(names) == 1:
        return SlicingNode(zone_name=names[0])
    mid = len(names) // 2
    direction: Literal["H", "V"] = "V" if len(names) > 2 else "H"
    return SlicingNode(
        direction=direction,
        ratio=0.5,
        left=_build_balanced_tree(names[:mid]),
        right=_build_balanced_tree(names[mid:]),
    )


def _optimize_slicing_tree(
    tree: SlicingNode,
    nodes: list[dict],
    envelope: dict,
    adjacency_weights: dict[str, float],
    weights: OptimizationWeights,
    tragwerk: TragwerkConstraints,
    max_iterations: int,
) -> OptimizationResult:
    """Optimiert die Ratio-Werte eines gegebenen Slicing-Trees mit L-BFGS-B.

    Objective Function:
        f(x) = w_area   × Σ |actual_i - target_i| / target_i
              + w_adj   × Σ dist(centroid_a, centroid_b) × edge_weight_ab
              + w_asp   × Σ max(0, aspect_i - max_aspect)²
              + w_grid  × Σ snap_deviation_i / raster
              + w_comp  × perimeter² / (4π × area)   [Isoperimetric ratio]
              - w_exp   × free_facade_fraction

    Keine Überlappungsconstraints: Die Baumstruktur garantiert Überlappungsfreiheit
    per Konstruktion — jedes Blatt erhält exakt ein Teilrechteck.

    TODO (Claude Sprint A): Vollständige Implementierung.
    """
    node_map = {n["name"]: n for n in nodes}
    bw = float(envelope["width_m"])
    bd = float(envelope["depth_m"])
    bx = float(envelope.get("x", 0.0))
    by = float(envelope.get("y", 0.0))

    x0 = np.array(tree.collect_ratios(), dtype=float)
    if len(x0) == 0:
        # Einzelzone — kein Optimierer nötig
        zones = _build_zones_from_tree(tree, x0, node_map, bx, by, bw, bd)
        return _build_result(tree, zones, x0, node_map, adjacency_weights, weights,
                             tragwerk, envelope, iterations=0, converged=True)

    bounds = [(0.10, 0.90)] * len(x0)

    def objective(x: np.ndarray) -> float:
        tree.apply_ratios(x.tolist())
        # rounded=False: exact floats prevent quantization → optimizer sees real gradient
        zones = _build_zones_from_tree(tree, x, node_map, bx, by, bw, bd, rounded=False)
        return _compute_objective(zones, node_map, adjacency_weights, weights, tragwerk)

    opt_kw = {"maxiter": max_iterations, "ftol": 1e-9, "gtol": 1e-8}
    res = scipy.optimize.minimize(
        fun=objective, x0=x0, method="L-BFGS-B", bounds=bounds, options=opt_kw,
    )

    # Second pass from perturbed x0 — breaks symmetry at proportional stationary points
    rng = np.random.default_rng(abs(hash(tree.to_str())) % (2 ** 31))
    x1 = np.clip(res.x + rng.uniform(-0.07, 0.07, size=len(res.x)), 0.10, 0.90)
    res2 = scipy.optimize.minimize(
        fun=objective, x0=x1, method="L-BFGS-B", bounds=bounds, options=opt_kw,
    )
    if res2.fun < res.fun:
        res = res2

    tree.apply_ratios(res.x.tolist())
    zones = _build_zones_from_tree(tree, res.x, node_map, bx, by, bw, bd)
    return _build_result(tree, zones, res.x, node_map, adjacency_weights, weights,
                         tragwerk, envelope, iterations=res.nit, converged=res.success)


def _build_zones_from_tree(
    tree: SlicingNode,
    ratios: np.ndarray,
    node_map: dict[str, dict],
    x: float,
    y: float,
    w: float,
    h: float,
    rounded: bool = True,
) -> list[Zone]:
    """Traversiert den Slicing-Baum und erzeugt Zone-Objekte aus den Teilrechtecken.

    rounded=False: exakte Floats (für Optimizer-Objective, verhindert Gradient=0
                   durch Quantisierungseffekte beim Runden auf 1mm/0.01m²).
    rounded=True:  gerundete Werte für Darstellung und Export.
    """
    zones: list[Zone] = []
    _traverse(tree, node_map, x, y, w, h, zones, rounded=rounded)
    return zones


def _traverse(
    node: SlicingNode,
    node_map: dict[str, dict],
    x: float, y: float, w: float, h: float,
    out: list[Zone],
    rounded: bool = True,
) -> None:
    if node.is_leaf:
        name = node.zone_name or ""
        raw = node_map.get(name, {})
        target = float(raw.get("area_m2", w * h))
        floors = int(raw.get("floors", 1))
        actual = w * h * max(1, floors)
        delta = actual - target
        if rounded:
            out.append(Zone(
                name=name,
                x=round(x, 3), y=round(y, 3),
                breite=round(w, 3), tiefe=round(h, 3),
                flaeche_m2=target,
                din_kategorie=raw.get("din_kategorie", "NUF"),
                farbe=raw.get("farbe", "#CCCCCC"),
                floors=floors,
                planned_area_m2=round(actual, 2),
                delta_m2=round(delta, 2),
                delta_pct=round(delta / target * 100 if target else 0, 1),
            ))
        else:
            out.append(Zone(
                name=name,
                x=x, y=y, breite=w, tiefe=h,
                flaeche_m2=target,
                din_kategorie=raw.get("din_kategorie", "NUF"),
                farbe=raw.get("farbe", "#CCCCCC"),
                floors=floors,
                planned_area_m2=actual,
                delta_m2=delta,
                delta_pct=delta / target * 100 if target else 0.0,
            ))
        return

    ratio = float(node.ratio or 0.5)
    if node.direction == "V":
        w_left = w * ratio
        _traverse(node.left,  node_map, x,          y, w_left,    h, out, rounded)
        _traverse(node.right, node_map, x + w_left, y, w - w_left, h, out, rounded)
    else:  # "H"
        h_bot = h * ratio
        _traverse(node.left,  node_map, x, y,          w, h_bot,     out, rounded)
        _traverse(node.right, node_map, x, y + h_bot,  w, h - h_bot, out, rounded)


def _compute_objective(
    zones: list[Zone],
    node_map: dict[str, dict],
    adjacency_weights: dict[str, float],
    weights: OptimizationWeights,
    tragwerk: TragwerkConstraints,
) -> float:
    """Berechnet den skalaren Objective-Wert (minimieren = besser).

    TODO (Claude Sprint A): Vollständige Implementierung aller Terme.
    """
    total = 0.0

    # Term 1: Flächentreue (NOT divided by n — balanciert gegen AR-Term)
    area_penalty = 0.0
    max_area_excess = 0.0
    for z in zones:
        target = z.flaeche_m2
        if target > 0:
            rel = abs((z.planned_area_m2 or 0) - target) / target
            area_penalty += rel
            max_area_excess = max(max_area_excess, rel)
    area_penalty += max_area_excess  # Extra-Gewicht auf schlimmsten Ausreißer
    total += weights.area_delta * area_penalty

    # Term 2: Adjazenz (Schwerpunktabstand gewichteter Nachbarn)
    adj_penalty = 0.0
    zone_map = {z.name: z for z in zones}
    for key, w in adjacency_weights.items():
        if "|" not in key:
            continue
        a, b = key.split("|", 1)
        za, zb = zone_map.get(a), zone_map.get(b)
        if za and zb and w > 0:
            dx = za.centroid[0] - zb.centroid[0]
            dy = za.centroid[1] - zb.centroid[1]
            dist = math.sqrt(dx * dx + dy * dy)
            adj_penalty += w * dist
    if adjacency_weights:
        max_dist = math.sqrt(sum(
            (z.breite ** 2 + z.tiefe ** 2) for z in zones
        ) / max(1, len(zones)))
        adj_penalty /= max(1, max_dist * sum(adjacency_weights.values()))
    total += weights.adjacency * adj_penalty

    # Term 3: Aspect-Ratio-Penalty (sum NOT divided by zone count — stronger gradient)
    # Safety margin: penalty activates 0.1 below the hard limit so that after grid-
    # snapping the final zones always satisfy max_aspect_ratio (accounts for fp-rounding).
    asp_penalty = 0.0
    max_excess = 0.0
    ar_soft_limit = tragwerk.max_aspect_ratio - 0.1   # target < 3.9 → snapped ≤ 4.0
    for z in zones:
        if z.tiefe > 0 and z.breite > 0:
            asp = max(z.breite / z.tiefe, z.tiefe / z.breite)
            excess = max(0.0, asp - ar_soft_limit)
            asp_penalty += excess ** 2 + 10.0 * excess ** 3
            max_excess = max(max_excess, excess)
    asp_penalty += 20.0 * max_excess ** 2  # Strong extra term for worst offender
    total += weights.aspect_ratio * asp_penalty

    # Term 4: Tragwerksraster-Snap-Penalty
    grid_penalty = 0.0
    for z in zones:
        dev_w = (z.breite % tragwerk.raster_x_m) / tragwerk.raster_x_m
        dev_h = (z.tiefe  % tragwerk.raster_y_m) / tragwerk.raster_y_m
        grid_penalty += min(dev_w, 1 - dev_w) ** 2 + min(dev_h, 1 - dev_h) ** 2
    total += weights.grid_snap * grid_penalty / max(1, len(zones))

    return total


def _build_result(
    tree: SlicingNode,
    zones: list[Zone],
    ratios: np.ndarray,
    node_map: dict[str, dict],
    adjacency_weights: dict[str, float],
    weights: OptimizationWeights,
    tragwerk: TragwerkConstraints,
    envelope: dict,
    iterations: int,
    converged: bool,
) -> OptimizationResult:
    """Baut OptimizationResult aus Optimizer-Output zusammen."""
    obj = _compute_objective(zones, node_map, adjacency_weights, weights, tragwerk)

    zone_map = {z.name: z for z in zones}
    decisions = []
    for z in zones:
        adj_score = _zone_adjacency_score(z, zone_map, adjacency_weights)
        asp = max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe))
        dev_w = (z.breite % tragwerk.raster_x_m) / tragwerk.raster_x_m
        dev_h = (z.tiefe  % tragwerk.raster_y_m) / tragwerk.raster_y_m
        grid_dev = (min(dev_w, 1 - dev_w) * tragwerk.raster_x_m
                    + min(dev_h, 1 - dev_h) * tragwerk.raster_y_m) / 2
        decisions.append(ZoneDecision(
            zone_name=z.name,
            position=z.centroid,
            area_delta_pct=z.delta_pct,
            adjacency_score=adj_score,
            aspect_ratio=round(asp, 2),
            grid_deviation_m=round(grid_dev, 2),
        ))

    components = {
        "area_delta":   weights.area_delta   * sum(abs(z.delta_pct or 0) for z in zones) / max(1, len(zones)) / 100,
        "adjacency":    0.0,   # TODO: aufschlüsseln
        "aspect_ratio": weights.aspect_ratio * sum(max(0, max(z.breite, z.tiefe) / max(0.1, min(z.breite, z.tiefe)) - tragwerk.max_aspect_ratio) for z in zones),
        "grid_snap":    0.0,   # TODO: aufschlüsseln
    }

    return OptimizationResult(
        zones=zones,
        objective_value=obj,
        objective_components=components,
        zone_decisions=decisions,
        tree_topology=tree.to_str(),
        envelope_used={
            "width_m":       envelope.get("width_m", 0),
            "depth_m":       envelope.get("depth_m", 0),
            "rotation_deg":  envelope.get("rotation_deg", 0),
        },
        iterations=iterations,
        converged=converged,
    )


def _zone_adjacency_score(
    zone: Zone,
    zone_map: dict[str, Zone],
    adjacency_weights: dict[str, float],
) -> float:
    """0..1: Anteil der gewichteten Nachbarn die tatsächlich angrenzen."""
    relevant = {k: v for k, v in adjacency_weights.items()
                if zone.name in k.split("|")}
    if not relevant:
        return 1.0
    total_w = sum(relevant.values())
    touching_w = 0.0
    for key, w in relevant.items():
        other_name = key.replace(zone.name, "").strip("|")
        other = zone_map.get(other_name)
        if other and _zones_touch(zone, other):
            touching_w += w
    return touching_w / max(0.01, total_w)


def _zones_touch(a: Zone, b: Zone, eps: float = 0.5) -> bool:
    """True wenn zwei Zonen eine gemeinsame Kante haben (Toleranz eps m)."""
    x_overlap = a.x < b.x + b.breite + eps and b.x < a.x + a.breite + eps
    y_overlap = a.y < b.y + b.tiefe  + eps and b.y < a.y + a.tiefe  + eps
    x_touch   = abs(a.x + a.breite - b.x) < eps or abs(b.x + b.breite - a.x) < eps
    y_touch   = abs(a.y + a.tiefe  - b.y) < eps or abs(b.y + b.tiefe  - a.y) < eps
    return (x_touch and y_overlap) or (y_touch and x_overlap)

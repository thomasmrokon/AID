"""
AID Demo – Rekursiver Raumteiler (Space Grammar Layout).

Ersetzt die handkodierten Typologien (Kamm / Block / Kreuzgang) durch einen
einzigen rekursiven Algorithmus. Varianten entstehen durch unterschiedliche
Schnitt-Prioritäten, nicht durch verschiedene Funktionen.

Schnitt-Grammatik:
  1. partition_zones()  → Zonen-Clustering via Adjazenz-Graph
  2. decide_axis()      → H oder V schneiden?
  3. decide_position()  → Schnittposition (flächenproportional)
  4. insert_corridor()  → Korridor an der Schnittkante
  5. Rekursion links/rechts
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field

from app.tools.geometry import Zone


# ---------------------------------------------------------------------------
# Konfiguration je Variante
# ---------------------------------------------------------------------------

@dataclass
class SplitConfig:
    """Steuert das rekursive Splitting für eine Layoutvariante."""
    split_priority: str = "process_sequence"
    # "process_sequence" – Prozessreihenfolge als Partition-Achse
    # "reserve_east"     – Ost-Seite für Erweiterungsreserve freihalten
    # "balanced_cut"     – minimaler Graph-Cut, gleiche Flächenhälften
    # "mep_central"      – TF-Zone zentral positionieren
    # "compact"          – kompakteste Aufteilung (quadratische Zonen)
    reserve_direction: str | None = "east"   # für "reserve_east"
    corridor_ratio: float = 0.08             # Korridor-Anteil an der Gebäudetiefe
    max_depth: int = 5                       # maximale Rekursionstiefe
    aspect_bias: float = 1.0                 # Seitenverhältnis-Bias (>1 = breiter)


SPLIT_PRESETS: dict[str, SplitConfig] = {
    "A_Materialfluss": SplitConfig(
        split_priority="process_sequence",
        reserve_direction=None,
        corridor_ratio=0.09,
        aspect_bias=1.15,
    ),
    "B_Erweiterbarkeit": SplitConfig(
        split_priority="reserve_east",
        reserve_direction="east",
        corridor_ratio=0.09,
        aspect_bias=1.0,
    ),
    "C_Ausgewogen": SplitConfig(
        split_priority="balanced_cut",
        reserve_direction=None,
        corridor_ratio=0.08,
        aspect_bias=1.0,
    ),
}

# Zusatz-Presets für neue Projektziele
SPLIT_PRESETS["techniktrassen"] = SplitConfig(
    split_priority="mep_central",
    reserve_direction=None,
    corridor_ratio=0.08,
    aspect_bias=0.95,
)
SPLIT_PRESETS["kompaktheit"] = SplitConfig(
    split_priority="compact",
    reserve_direction=None,
    corridor_ratio=0.07,
    aspect_bias=1.0,
)


# ---------------------------------------------------------------------------
# Seitenverhältnis-Limits je DIN-Kategorie
# ---------------------------------------------------------------------------

MAX_AR_PER_DIN: dict[str, float] = {
    "NUF 2": 3.0,   # Büro / Verwaltung
    "NUF 3": 4.0,   # Produktion / IT-Whitespace
    "NUF 4": 5.0,   # Lager / Logistik (Hochregal-Toleranz)
    "NUF 7": 3.0,   # Sozialräume / Sanitär
    "TF":    3.0,   # Technikräume
    "VF":   10.0,   # Erschließung (Gänge dürfen schmal sein)
}
_DEFAULT_MAX_AR = 4.0


def _group_max_ar(nodes: list[dict]) -> float:
    """Restriktivster AR-Wert für eine Zonengruppe."""
    if not nodes:
        return _DEFAULT_MAX_AR
    return min(MAX_AR_PER_DIN.get(n.get("din_kategorie", "NUF 3"), _DEFAULT_MAX_AR) for n in nodes)


# ---------------------------------------------------------------------------
# Hilfsdatenstruktur: Rechteck
# ---------------------------------------------------------------------------

@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def aspect(self) -> float:
        return self.w / max(0.01, self.h)


# ---------------------------------------------------------------------------
# Zone-Clustering (Partition)
# ---------------------------------------------------------------------------

def _zone_footprint(node: dict) -> float:
    return float(node.get("planned_area_m2", node.get("area_m2", 0))) / max(1, node.get("floors", 1))


def _partition_graph_guided(
    nodes: list[dict],
    process_order: list[str],
    graph_weights: dict[str, float],
) -> tuple[list[dict], list[dict]]:
    """Graph-gesteuerte Partition (Kernighan-Lin, 1 Pass greedy).

    Startet mit prozessreihenfolgebasierter Aufteilung, verbessert durch
    paarweise Knotentausche die den gewichteten Schnitt minimieren.
    Ohne graph_weights: reiner Prozessreihenfolge-Split.
    """
    if not nodes:
        return [], []
    if len(nodes) <= 2:
        half = max(1, len(nodes) // 2)
        return nodes[:half], nodes[half:]

    # ── Initiale Aufteilung nach Prozessreihenfolge ────────────────────────
    order_idx = {name: i for i, name in enumerate(process_order)}
    proc_set = set(process_order)
    proc_nodes = sorted(
        [n for n in nodes if n["name"] in proc_set],
        key=lambda n: order_idx.get(n["name"], 999),
    )
    supp_nodes = [n for n in nodes if n["name"] not in proc_set]

    split = max(1, math.ceil(len(proc_nodes) / 2))
    supp_split = len(supp_nodes) // 2
    left  = proc_nodes[:split] + supp_nodes[:supp_split]
    right = proc_nodes[split:] + supp_nodes[supp_split:]
    if not left:
        left, right = right[:1], right[1:]
    if not right:
        right, left = left[-1:], left[:-1]

    # ── KL-Verbesserung (nur wenn Graph-Gewichte vorhanden) ───────────────
    if not graph_weights:
        return left, right

    def w(a: str, b: str) -> float:
        return graph_weights.get(f"{a}__{b}", 0.0) + graph_weights.get(f"{b}__{a}", 0.0)

    left_names:  set[str] = {n["name"] for n in left}
    right_names: set[str] = {n["name"] for n in right}
    node_by_name: dict[str, dict] = {n["name"]: n for n in nodes}

    for _ in range(len(nodes)):  # max n Iterationen
        # D(v) = ext(v) – int(v)
        d: dict[str, float] = {}
        for name in left_names:
            d[name] = (sum(w(name, r) for r in right_names)
                       - sum(w(name, l) for l in left_names if l != name))
        for name in right_names:
            d[name] = (sum(w(name, l) for l in left_names)
                       - sum(w(name, r) for r in right_names if r != name))

        # Bester Tausch: gain = D(a) + D(b) – 2·w(a,b)
        best_gain = 1e-6  # nur tauschen bei echtem Gewinn
        best_pair: tuple[str, str] | None = None
        for a in list(left_names):
            for b in list(right_names):
                gain = d[a] + d[b] - 2 * w(a, b)
                if gain > best_gain:
                    best_gain = gain
                    best_pair = (a, b)

        if best_pair is None:
            break
        a, b = best_pair
        left_names.discard(a)
        left_names.add(b)
        right_names.discard(b)
        right_names.add(a)

    # Reihenfolge innerhalb jeder Hälfte nach Prozessreihenfolge
    sort_key = lambda n: order_idx.get(n["name"], 999)
    left_nodes  = sorted([node_by_name[n] for n in left_names  if n in node_by_name], key=sort_key)
    right_nodes = sorted([node_by_name[n] for n in right_names if n in node_by_name], key=sort_key)

    if not left_nodes:
        left_nodes, right_nodes = right_nodes[:1], right_nodes[1:]
    if not right_nodes:
        right_nodes, left_nodes = left_nodes[-1:], left_nodes[:-1]
    return left_nodes, right_nodes


def _partition_balanced(
    nodes: list[dict],
    graph_weights: dict[str, float],
) -> tuple[list[dict], list[dict]]:
    """Greedy-Partition: minimiert Flächendifferenz zwischen beiden Hälften."""
    if not nodes:
        return [], []
    sorted_nodes = sorted(nodes, key=_zone_footprint, reverse=True)
    left: list[dict] = []
    right: list[dict] = []
    left_fp = right_fp = 0.0
    for n in sorted_nodes:
        fp = _zone_footprint(n)
        if left_fp <= right_fp:
            left.append(n)
            left_fp += fp
        else:
            right.append(n)
            right_fp += fp
    if not left:
        left, right = right[:1], right[1:]
    if not right:
        right, left = left[-1:], left[:-1]
    return left, right


def _partition_mep_central(
    nodes: list[dict],
    process_order: list[str],
) -> tuple[list[dict], list[dict]]:
    """TF-Zone in Mitte: alles links der TF, alles rechts."""
    tf_nodes = [n for n in nodes if n.get("din_kategorie") == "TF"]
    rest     = [n for n in nodes if n.get("din_kategorie") != "TF"]
    # TF geht in linke Gruppe (wird später zentral positioniert via Korridor)
    left, right = _partition_balanced(rest, {})
    left = tf_nodes + left
    return left, right


def _partition_zones(
    nodes: list[dict],
    process_order: list[str],
    graph_weights: dict[str, float],
    config: SplitConfig,
) -> tuple[list[dict], list[dict]]:
    if config.split_priority == "mep_central":
        return _partition_mep_central(nodes, process_order)
    # process_sequence immer graph-guided; andere Strategien nur wenn Gewichte vorhanden
    if config.split_priority == "process_sequence" or graph_weights:
        return _partition_graph_guided(nodes, process_order, graph_weights)
    # balanced_cut / compact / reserve_east ohne Graph-Gewichte: Flächen-Balance
    return _partition_balanced(nodes, graph_weights)


# ---------------------------------------------------------------------------
# Achsen-Entscheidung
# ---------------------------------------------------------------------------

def _decide_axis(
    rect: Rect,
    nodes: list[dict],
    process_order: list[str],
    config: SplitConfig,
    depth: int,
) -> str:
    """Gibt 'H' (horizontaler Schnitt = Bänder N/S) oder 'V' (vertikale Streifen) zurück."""
    # Reservierung: erstes Level bestimmt Richtung
    if config.split_priority == "reserve_east" and depth == 0:
        return "V"
    if config.split_priority == "reserve_free" and depth == 0:
        return "V" if rect.w >= rect.h else "H"
    # Prozesssequenz: V-Schnitt bei geradem Depth (Prozessrichtung W→O / N→S)
    if config.split_priority == "process_sequence":
        return "V" if depth % 2 == 0 else "H"
    # Kompakt: immer längs der längsten Seite
    if rect.aspect > 1.2 * config.aspect_bias:
        return "V"
    if rect.aspect < 0.8 / config.aspect_bias:
        return "H"
    # Default: vertikal
    return "V"


# ---------------------------------------------------------------------------
# Schnittposition
# ---------------------------------------------------------------------------

def _snap(value: float, grid: float) -> float:
    if grid <= 0:
        return value
    return round(value / grid) * grid


def _decide_position(
    rect: Rect,
    left_nodes: list[dict],
    right_nodes: list[dict],
    axis: str,
    grid: float,
    config: SplitConfig,
    reserve_fraction: float = 0.0,
) -> float:
    """Berechnet die Schnittposition (absolute Koordinate)."""
    total_fp = sum(_zone_footprint(n) for n in left_nodes + right_nodes)
    left_fp  = sum(_zone_footprint(n) for n in left_nodes)
    fraction = left_fp / max(1.0, total_fp)

    if axis == "V":
        available = rect.w
        base      = rect.x
    else:
        available = rect.h
        base      = rect.y

    # Reserve: mindestens reserve_fraction für die reservierte Seite
    if config.split_priority in ("reserve_east", "reserve_free") and axis == "V":
        fraction = min(fraction, 1.0 - reserve_fraction)
    elif config.split_priority == "reserve_free" and axis == "H":
        fraction = min(fraction, 1.0 - reserve_fraction)

    raw_pos = base + available * fraction
    snapped = _snap(raw_pos - base, grid) + base
    # Sicherstellen, dass beide Seiten mindestens 2 Grid-Einheiten haben
    min_dim = grid * 4
    snapped = max(base + min_dim, min(base + available - min_dim, snapped))
    return snapped


# ---------------------------------------------------------------------------
# Korridor-Einfügung
# ---------------------------------------------------------------------------

def _corridor_width(rect: Rect, axis: str, grid: float, config: SplitConfig) -> float:
    """Korridorbreite/-höhe an der Schnittkante."""
    dim = rect.h if axis == "V" else rect.w
    raw = dim * config.corridor_ratio
    snapped = _snap(raw, grid)
    return max(grid * 2, snapped)


def _make_corridor(rect: Rect, axis: str, split_pos: float, corr_dim: float) -> Zone:
    """Erzeugt die Erschließungszone an der Schnittkante."""
    if axis == "V":
        return Zone(
            name="Erschließung",
            x=round(split_pos, 2),
            y=round(rect.y, 2),
            breite=round(corr_dim, 2),
            tiefe=round(rect.h, 2),
            flaeche_m2=round(corr_dim * rect.h, 2),
            din_kategorie="VF",
            farbe="#C9CDD2",
            planned_area_m2=round(corr_dim * rect.h, 2),
        )
    else:
        return Zone(
            name="Erschließung",
            x=round(rect.x, 2),
            y=round(split_pos, 2),
            breite=round(rect.w, 2),
            tiefe=round(corr_dim, 2),
            flaeche_m2=round(rect.w * corr_dim, 2),
            din_kategorie="VF",
            farbe="#C9CDD2",
            planned_area_m2=round(rect.w * corr_dim, 2),
        )


# ---------------------------------------------------------------------------
# Zone zuweisen (Blatt-Knoten)
# ---------------------------------------------------------------------------

def _assign_zones_row(nodes: list[dict], rect: Rect, grid: float) -> list[Zone]:
    """Legt alle Knoten in einer einzigen horizontalen Reihe nebeneinander."""
    if not nodes:
        return []
    total_fp = sum(_zone_footprint(n) for n in nodes)
    zones: list[Zone] = []
    cursor_x = rect.x
    for idx, node in enumerate(nodes):
        if idx == len(nodes) - 1:
            w = max(grid * 2, rect.x + rect.w - cursor_x)
        else:
            frac = _zone_footprint(node) / max(1.0, total_fp)
            w = _snap(rect.w * frac, grid)
            remaining = len(nodes) - idx - 1
            w = max(grid * 2, min(w, rect.x + rect.w - cursor_x - remaining * grid * 2))

        floors = max(1, node.get("floors", 1))
        planned = round(w * rect.h * floors, 1)
        briefing_area = float(node.get("area_m2", planned))
        delta   = planned - briefing_area
        delta_pct = (delta / briefing_area) * 100 if briefing_area else 0.0
        zones.append(Zone(
            name=node["name"],
            x=round(cursor_x, 2),
            y=round(rect.y, 2),
            breite=round(w, 2),
            tiefe=round(rect.h, 2),
            flaeche_m2=round(briefing_area, 1),
            din_kategorie=node.get("din_kategorie", "NUF 3"),
            farbe=node.get("farbe", "#AAAAAA"),
            floors=floors,
            planned_area_m2=round(planned, 1),
            delta_m2=round(delta, 1),
            delta_pct=round(delta_pct, 1),
        ))
        cursor_x += w
    return zones


def _assign_zones(nodes: list[dict], rect: Rect, grid: float) -> list[Zone]:
    """Teilt ein Rechteck unter den Knoten auf; mehrere Zeilen wenn AR-Limit überschritten.

    Benötigte Zeilenanzahl: n_rows ≥ sqrt(n · h / (max_ar · w))
    Zonen werden konsekutiv auf Zeilen verteilt (Prozessreihenfolge bleibt erhalten).
    """
    if not nodes:
        return []

    n = len(nodes)
    max_ar = _group_max_ar(nodes)

    # Anzahl Zeilen berechnen, damit AR-Limit eingehalten wird
    if rect.w > 0 and rect.h > 0:
        n_rows = max(1, math.ceil(math.sqrt(n * rect.h / max(0.001, max_ar * rect.w))))
    else:
        n_rows = 1
    n_rows = min(n_rows, n)  # nie mehr Zeilen als Zonen

    if n_rows == 1:
        return _assign_zones_row(nodes, rect, grid)

    # Konsekutive Gruppen (Prozessreihenfolge innerhalb jeder Zeile erhalten)
    nodes_per_row = math.ceil(n / n_rows)
    groups = [nodes[i: i + nodes_per_row] for i in range(0, n, nodes_per_row)]
    total_fp = sum(_zone_footprint(nd) for nd in nodes)

    zones: list[Zone] = []
    cursor_y = rect.y
    for row_idx, group in enumerate(groups):
        if not group:
            continue
        is_last = row_idx == len(groups) - 1
        if is_last:
            row_h = max(grid * 2, rect.y + rect.h - cursor_y)
        else:
            group_fp = sum(_zone_footprint(nd) for nd in group)
            row_h = _snap(rect.h * group_fp / max(1.0, total_fp), grid)
            row_h = max(grid * 2, row_h)
        zones += _assign_zones_row(group, Rect(rect.x, cursor_y, rect.w, row_h), grid)
        cursor_y += row_h

    return zones


# ---------------------------------------------------------------------------
# Rekursiver Kern
# ---------------------------------------------------------------------------

def _recursive_split(
    nodes: list[dict],
    rect: Rect,
    process_order: list[str],
    graph_weights: dict[str, float],
    config: SplitConfig,
    grid: float,
    depth: int = 0,
    reserve_fraction: float = 0.32,
) -> list[Zone]:
    """Hauptrekursion. Gibt Liste von Zonen zurück."""
    if not nodes:
        return []

    # Basisfall: 1-2 Knoten oder maximale Tiefe → direkt zuweisen
    if len(nodes) <= 2 or depth >= config.max_depth:
        return _assign_zones(nodes, rect, grid)

    # Erweiterungsreserve: am ersten Level freie Seite abschneiden
    if config.split_priority in ("reserve_east", "reserve_free") and depth == 0:
        # reserve_free: längere Seite wählen (Ost bei Breitenüberhang, Nord bei Tiefenüberhang)
        use_east = (config.split_priority == "reserve_east") or (rect.w >= rect.h)
        if use_east:
            reserve_w = _snap(rect.w * reserve_fraction, grid)
            block_w   = rect.w - reserve_w
            reserve_rect = Rect(rect.x + block_w, rect.y, reserve_w, rect.h)
            block_rect   = Rect(rect.x, rect.y, block_w, rect.h)
        else:
            reserve_h = _snap(rect.h * reserve_fraction, grid)
            block_h   = rect.h - reserve_h
            reserve_rect = Rect(rect.x, rect.y + block_h, rect.w, reserve_h)
            block_rect   = Rect(rect.x, rect.y, rect.w, block_h)
        reserve_zone = Zone(
            name="Erweiterungsreserve",
            x=round(reserve_rect.x, 2),
            y=round(reserve_rect.y, 2),
            breite=round(reserve_rect.w, 2),
            tiefe=round(reserve_rect.h, 2),
            flaeche_m2=round(reserve_rect.area, 1),
            din_kategorie="NUF 4",
            farbe="#AAAAAA",
            schraffur=True,
            planned_area_m2=round(reserve_rect.area, 1),
        )
        block_zones = _recursive_split(
            nodes, block_rect, process_order, graph_weights, config, grid, depth + 1
        )
        return block_zones + [reserve_zone]

    # Partitionierung
    left_nodes, right_nodes = _partition_zones(nodes, process_order, graph_weights, config)

    # Achse bestimmen
    axis = _decide_axis(rect, nodes, process_order, config, depth)

    # Schnittpunkt
    split_pos = _decide_position(rect, left_nodes, right_nodes, axis, grid, config, reserve_fraction)

    # ── Korridorentscheidung aus Graph-Gewichten ──────────────────────────
    # depth > 1: kein Korridor (zu fein granular)
    # depth == 0: Haupterschließung immer (Hauptgang)
    # depth == 1: Korridor nur bei mittlerer Verbindungsstärke zwischen den Gruppen
    #   cross_weight ≥ CORR_SHARED_WALL → geteilte Wand (kein Platz verlieren)
    #   cross_weight <  CORR_MIN        → keine direkte Verbindung nötig
    #   Dazwischen                      → Korridor als Übergangsbereich
    CORR_SHARED_WALL = 0.70  # stark verbunden → direkte Wandöffnung, kein Korridor
    CORR_MIN         = 0.25  # schwach verbunden → kein Korridor nötig

    if depth > 1:
        add_corridor = False
    elif depth == 0 and not graph_weights:
        add_corridor = True   # ohne Gewichte: Haupterschließungsachse immer
    else:
        # Korridor nur bei mittlerer Verbindungsstärke über die Partitionsgrenze
        cross_weight = max(
            (graph_weights.get(f"{ln['name']}__{rn['name']}", 0.0) +
             graph_weights.get(f"{rn['name']}__{ln['name']}", 0.0)
             for ln in left_nodes for rn in right_nodes),
            default=0.0,
        )
        add_corridor = CORR_MIN <= cross_weight < CORR_SHARED_WALL

    corr_dim = _corridor_width(rect, axis, grid, config) if add_corridor else 0.0

    # Teil-Rechtecke
    if axis == "V":
        left_rect  = Rect(rect.x,                  rect.y, split_pos - rect.x,             rect.h)
        right_rect = Rect(split_pos + corr_dim,     rect.y, rect.x + rect.w - split_pos - corr_dim, rect.h)
    else:
        left_rect  = Rect(rect.x, rect.y,                  rect.w, split_pos - rect.y)
        right_rect = Rect(rect.x, split_pos + corr_dim,     rect.w, rect.y + rect.h - split_pos - corr_dim)

    # Degenerierte Rechtecke vermeiden
    min_dim = grid * 2
    if left_rect.w < min_dim or left_rect.h < min_dim:
        return _assign_zones(nodes, rect, grid)
    if right_rect.w < min_dim or right_rect.h < min_dim:
        return _assign_zones(nodes, rect, grid)

    zones: list[Zone] = []
    if add_corridor:
        zones.append(_make_corridor(rect, axis, split_pos, corr_dim))

    zones += _recursive_split(left_nodes,  left_rect,  process_order, graph_weights, config, grid, depth + 1)
    zones += _recursive_split(right_nodes, right_rect, process_order, graph_weights, config, grid, depth + 1)

    return zones


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def recursive_split_layout(
    *,
    nodes: list[dict],
    topology: dict,
    envelope: dict,
    graph_weights: dict[str, float] | None = None,
    variante_key: str = "A_Materialfluss",
    split_priority: str | None = None,
    reserve_fraction: float = 0.32,
    raster_x: float = 12.0,
    raster_y: float = 9.0,
) -> list[Zone]:
    """Erzeugt ein Layout durch rekursives Splitting.

    Args:
        nodes:           Zonen-Dicts (mit planned_area_m2, din_kategorie, farbe, floors …)
        topology:        Topologie-Diagramm (process_order, edges …)
        envelope:        Gebäude-Envelope (x, y, width_m, depth_m)
        graph_weights:   Kantengewichte aus dem Funktionsgraph {src__tgt: weight}
        variante_key:    "A_Materialfluss" | "B_Erweiterbarkeit" | "C_Ausgewogen"
        split_priority:  Override für SplitConfig.split_priority
        reserve_fraction: Anteil Ost-Reserve (nur für reserve_east)
        raster_x/y:      Tragwerksraster für Grid-Snapping
    """
    config = deepcopy(SPLIT_PRESETS.get(variante_key, SPLIT_PRESETS["C_Ausgewogen"]))
    if split_priority:
        config.split_priority = split_priority

    grid = max(3.0, min(raster_x, raster_y) / 4)
    rect = Rect(
        x=envelope["x"],
        y=envelope["y"],
        w=envelope["width_m"],
        h=envelope["depth_m"],
    )
    process_order = topology.get("process_order", [])
    gw = graph_weights or {}

    zones = _recursive_split(
        nodes=nodes,
        rect=rect,
        process_order=process_order,
        graph_weights=gw,
        config=config,
        grid=grid,
        depth=0,
        reserve_fraction=reserve_fraction,
    )

    # Erschließungszonen deduplizieren (bei mehreren Korridoren → behalten, aber zusammenführen)
    seen_corridors = 0
    deduped: list[Zone] = []
    for z in zones:
        if z.din_kategorie == "VF" and not z.schraffur:
            seen_corridors += 1
            if seen_corridors > 1:
                z = Zone(
                    name=f"Erschließung_{seen_corridors}",
                    x=z.x, y=z.y, breite=z.breite, tiefe=z.tiefe,
                    flaeche_m2=z.flaeche_m2, din_kategorie="VF",
                    farbe=z.farbe, planned_area_m2=z.planned_area_m2,
                )
        deduped.append(z)

    return deduped

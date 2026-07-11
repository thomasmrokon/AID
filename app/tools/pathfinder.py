"""
AID Demo — A*-Pathfinder für Erschließungs-Korridore (Sprint C)

Berechnet Pfadgeometrie im freien Raum zwischen zwei Zonen, umgeht dabei
alle anderen Zonen als Hindernisse.

PUBLIC:
  find_corridor_path(zone_a, zone_b, all_zones, envelope, cell_size) -> dict
"""

from __future__ import annotations

import heapq
import math

import numpy as np


def find_corridor_path(
    zone_a: dict,
    zone_b: dict,
    all_zones: list[dict],
    envelope: dict,
    cell_size: float = 1.0,
) -> dict:
    """
    A*-Pathfinder im freien Raum zwischen zwei Zonen.

    Returns:
        {
            "pfad_punkte":   list[tuple[float, float]],  # Wegpunkte in Metern (x, y)
            "pfad_laenge_m": float,
        }
    Fallback bei unerreichbarem Ziel: gerade Linie zwischen Zentroiden.
    """
    origin = (float(envelope.get("x", 0.0)), float(envelope.get("y", 0.0)))
    width  = float(envelope.get("width_m",  60.0))
    depth  = float(envelope.get("depth_m",  40.0))

    grid = _build_grid(all_zones, origin, width, depth, cell_size)
    rows, cols = grid.shape

    cx_a, cy_a = _centroid(zone_a)
    cx_b, cy_b = _centroid(zone_b)

    start = _nearest_free(grid, _to_grid(cx_a, cy_a, origin, cell_size), rows, cols)
    end   = _nearest_free(grid, _to_grid(cx_b, cy_b, origin, cell_size), rows, cols)

    raw_path = _astar(grid, start, end)

    if raw_path is None or len(raw_path) < 2:
        # Fallback: gerade Luftlinie
        pts = [(cx_a, cy_a), (cx_b, cy_b)]
        return {
            "pfad_punkte":   pts,
            "pfad_laenge_m": round(math.hypot(cx_b - cx_a, cy_b - cy_a), 1),
        }

    world_pts = [_to_world(r, c, origin, cell_size) for r, c in raw_path]
    simplified = _simplify_path(world_pts)
    length = sum(
        math.hypot(simplified[i + 1][0] - simplified[i][0],
                   simplified[i + 1][1] - simplified[i][1])
        for i in range(len(simplified) - 1)
    )
    return {
        "pfad_punkte":   simplified,
        "pfad_laenge_m": round(length, 1),
    }


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _centroid(zone: dict) -> tuple[float, float]:
    x = float(zone.get("x", 0))
    y = float(zone.get("y", 0))
    w = float(zone.get("breite", 1))
    d = float(zone.get("tiefe", 1))
    return x + w / 2, y + d / 2


def _build_grid(
    zones: list[dict],
    origin: tuple[float, float],
    width: float,
    depth: float,
    cell_size: float,
) -> np.ndarray:
    """True = Hindernis (Zone-Inneres), False = freier Raum."""
    cols = max(1, math.ceil(width  / cell_size))
    rows = max(1, math.ceil(depth  / cell_size))
    grid = np.zeros((rows, cols), dtype=bool)

    tol = 0.1  # Wandzellen passierbar lassen
    for z in zones:
        if z.get("schraffur"):
            continue
        zx0 = float(z.get("x", 0)) + tol - origin[0]
        zy0 = float(z.get("y", 0)) + tol - origin[1]
        zx1 = zx0 + float(z.get("breite", 0)) - 2 * tol
        zy1 = zy0 + float(z.get("tiefe",  0)) - 2 * tol

        c0 = max(0, math.floor(zx0 / cell_size))
        c1 = min(cols, math.ceil(zx1 / cell_size))
        r0 = max(0, math.floor(zy0 / cell_size))
        r1 = min(rows, math.ceil(zy1 / cell_size))
        if c1 > c0 and r1 > r0:
            grid[r0:r1, c0:c1] = True

    return grid


def _to_grid(x: float, y: float, origin: tuple[float, float], cell_size: float) -> tuple[int, int]:
    col = int((x - origin[0]) / cell_size)
    row = int((y - origin[1]) / cell_size)
    return row, col


def _to_world(row: int, col: int, origin: tuple[float, float], cell_size: float) -> tuple[float, float]:
    x = origin[0] + (col + 0.5) * cell_size
    y = origin[1] + (row + 0.5) * cell_size
    return x, y


def _nearest_free(
    grid: np.ndarray,
    rc: tuple[int, int],
    rows: int,
    cols: int,
) -> tuple[int, int]:
    """Gibt nächste freie Zelle zurück (BFS-Suche von rc aus)."""
    r, c = max(0, min(rows - 1, rc[0])), max(0, min(cols - 1, rc[1]))
    if not grid[r, c]:
        return r, c
    visited = {(r, c)}
    queue = [(r, c)]
    while queue:
        next_queue = []
        for nr, nc in queue:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1),
                           (-1, -1), (-1, 1), (1, -1), (1, 1)):
                rr, cc = nr + dr, nc + dc
                if (rr, cc) in visited:
                    continue
                if 0 <= rr < rows and 0 <= cc < cols:
                    visited.add((rr, cc))
                    if not grid[rr, cc]:
                        return rr, cc
                    next_queue.append((rr, cc))
        queue = next_queue
    return r, c  # Fallback: Ursprungszelle (auch wenn Hindernis)


_DIAG_COST = math.sqrt(2)

def _astar(
    grid: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
) -> list[tuple[int, int]] | None:
    """A* mit 8-Connectivity. Gibt Pfad als Zellliste zurück oder None."""
    rows, cols = grid.shape
    if start == end:
        return [start]

    def h(r: int, c: int) -> float:
        return math.hypot(end[0] - r, end[1] - c)

    open_heap: list[tuple[float, tuple[int, int]]] = []
    heapq.heappush(open_heap, (h(*start), start))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g: dict[tuple[int, int], float] = {start: 0.0}

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == end:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path

        cr, cc = current
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            nr, nc = cr + dr, cc + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if grid[nr, nc]:
                continue
            step_cost = _DIAG_COST if dr != 0 and dc != 0 else 1.0
            ng = g[current] + step_cost
            nb = (nr, nc)
            if ng < g.get(nb, math.inf):
                came_from[nb] = current
                g[nb] = ng
                heapq.heappush(open_heap, (ng + h(nr, nc), nb))

    return None


def _simplify_path(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Entfernt Zwischenpunkte auf geraden Segmenten (Richtungsfilter)."""
    if len(points) <= 2:
        return points
    result = [points[0]]
    for i in range(1, len(points) - 1):
        px, py = points[i - 1]
        cx, cy = points[i]
        nx, ny = points[i + 1]
        dx1, dy1 = cx - px, cy - py
        dx2, dy2 = nx - cx, ny - cy
        # Richtungsänderung → Punkt behalten
        if abs(dx1 * dy2 - dy1 * dx2) > 1e-9:
            result.append(points[i])
    result.append(points[-1])
    return result

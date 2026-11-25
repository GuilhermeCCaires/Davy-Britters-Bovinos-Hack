"""Funções geométricas simples (sem dependências externas)."""
from __future__ import annotations

from typing import Iterable, Sequence

Point = Sequence[float]
Polygon = Sequence[Point]


def point_in_polygon(x: float, y: float, polygon: Polygon) -> bool:
    """Ray casting: True se (x, y) está dentro do polígono."""
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def denormalize(polygon: Iterable[Point], width: int, height: int) -> list[tuple[float, float]]:
    """Converte polígono em coordenadas normalizadas (0-1) para pixels."""
    return [(float(px) * width, float(py) * height) for px, py in polygon]


def foot_point(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """Ponto dos pés da pessoa (centro da base da caixa) – melhor para zonas no chão."""
    return ((x1 + x2) / 2.0, y2)


def center_point(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

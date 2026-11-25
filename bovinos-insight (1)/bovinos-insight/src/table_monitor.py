"""Estado das mesas: livre -> ocupada -> suja -> livre.

Usa a contagem de pessoas e de itens de louça (copo, tigela, talher, garrafa...)
dentro do polígono de cada mesa. Mede quanto tempo cada mesa ficou suja.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .geometry import point_in_polygon

LIVRE, OCUPADA, SUJA = "livre", "ocupada", "suja"


@dataclass
class TableEvent:
    mesa: str
    praca: str
    tipo: str          # "mesa_limpa" | "sentou_em_mesa_suja"
    t_inicio: float    # momento em que a mesa ficou suja
    t_fim: float

    @property
    def duracao_s(self) -> float:
        return self.t_fim - self.t_inicio


class _Debounce:
    """Só confirma uma condição depois que ela se mantém por `hold_s` segundos."""

    def __init__(self, hold_s: float):
        self.hold_s = hold_s
        self.since: float | None = None

    def check(self, cond: bool, t: float) -> bool:
        if not cond:
            self.since = None
            return False
        if self.since is None:
            self.since = t
        return t - self.since >= self.hold_s


class TableMonitor:
    def __init__(
        self,
        tables: list[dict],
        occupy_hold_s: float = 20.0,
        empty_hold_s: float = 10.0,
        clean_hold_s: float = 5.0,
    ) -> None:
        self.tables = [z for z in tables if z.get("type") == "table"]
        self.state = {z["name"]: LIVRE for z in self.tables}
        self.dirty_since: dict[str, float] = {}
        self.events: list[TableEvent] = []
        self._occ = {z["name"]: _Debounce(occupy_hold_s) for z in self.tables}
        self._empty = {z["name"]: _Debounce(empty_hold_s) for z in self.tables}
        self._clean = {z["name"]: _Debounce(clean_hold_s) for z in self.tables}

    def update(
        self,
        t: float,
        persons: Iterable[tuple[float, float]],
        items: Iterable[tuple[float, float]],
    ) -> None:
        persons = list(persons)
        items = list(items)
        for z in self.tables:
            name, poly = z["name"], z["poly_px"]
            n_p = sum(point_in_polygon(x, y, poly) for x, y in persons)
            n_i = sum(point_in_polygon(x, y, poly) for x, y in items)
            st = self.state[name]

            if st == LIVRE:
                if self._occ[name].check(n_p > 0, t):
                    self.state[name] = OCUPADA
            elif st == OCUPADA:
                if self._empty[name].check(n_p == 0, t):
                    if n_i > 0:
                        self.state[name] = SUJA
                        # a mesa ficou suja quando as pessoas saíram
                        self.dirty_since[name] = self._empty[name].since or t
                    else:
                        self.state[name] = LIVRE
                    self._occ[name].since = None
            elif st == SUJA:
                if self._clean[name].check(n_i == 0 and n_p == 0, t):
                    self.events.append(TableEvent(name, z.get("praca", ""), "mesa_limpa",
                                                  self.dirty_since.pop(name), t))
                    self.state[name] = LIVRE
                    self._empty[name].since = None
                elif self._occ[name].check(n_p > 0, t):
                    self.events.append(TableEvent(name, z.get("praca", ""), "sentou_em_mesa_suja",
                                                  self.dirty_since.pop(name), t))
                    self.state[name] = OCUPADA
                    self._empty[name].since = None

    def dirty_now(self, t: float) -> dict[str, float]:
        """Mesas sujas agora e há quanto tempo (s)."""
        return {m: t - since for m, since in self.dirty_since.items()}

    def summary(self) -> dict[str, int]:
        out = {LIVRE: 0, OCUPADA: 0, SUJA: 0}
        for s in self.state.values():
            out[s] += 1
        return out

"""Métricas de fila por zona: quantas pessoas, tempo de espera, desistências.

Entrada por quadro: tempo `t` (segundos) e uma lista de (track_id, x, y) em pixels
(ponto dos pés de cada pessoa rastreada). Funciona com qualquer detector/rastreador.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from .geometry import point_in_polygon


@dataclass
class ZoneEvent:
    track_id: int
    zone: str
    t_in: float
    t_out: float

    @property
    def dwell_s(self) -> float:
        return self.t_out - self.t_in


@dataclass
class Balk:
    """Cliente que entrou na zona de entrada e foi embora sem pegar prato."""
    track_id: int
    t_first_seen: float
    t_last_seen: float


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


class QueueAnalytics:
    """Acompanha a permanência de cada pessoa em cada zona de fila.

    Parâmetros
    ----------
    zones: lista de dicts com `name`, `type == "queue"`, `role` opcional e `poly_px`.
    grace_s: tolerância (s) para a pessoa "piscar" fora da zona sem encerrar a permanência.
    lost_timeout_s: após esse tempo sem ver a pessoa, o rastro é encerrado.
    window_s: janela para médias móveis de espera concluída e taxa de chegada.
    entry_role / buffet_role: papéis usados para detectar desistência.
    min_entry_dwell_s: permanência mínima na entrada para contar como desistência
        (evita contar quem só passou na frente da porta).
    """

    def __init__(
        self,
        zones: list[dict],
        grace_s: float = 2.0,
        lost_timeout_s: float = 6.0,
        window_s: float = 300.0,
        entry_role: str = "entrada",
        buffet_role: str = "buffet",
        min_entry_dwell_s: float = 3.0,
    ) -> None:
        self.zones = [z for z in zones if z.get("type", "queue") == "queue"]
        self.grace_s = grace_s
        self.lost_timeout_s = lost_timeout_s
        self.window_s = window_s
        self.entry_role = entry_role
        self.buffet_role = buffet_role
        self.min_entry_dwell_s = min_entry_dwell_s

        self.inside: dict[str, dict[int, list[float]]] = {z["name"]: {} for z in self.zones}
        self.events: list[ZoneEvent] = []
        self.balks: list[Balk] = []

        self._first_seen: dict[int, float] = {}
        self._last_seen: dict[int, float] = {}
        self._roles_visited: dict[int, set[str]] = defaultdict(set)
        self._last_roles: dict[int, set[str]] = {}
        self._entry_dwell: dict[int, float] = defaultdict(float)
        self._closed: set[int] = set()
        self._entries: dict[str, list[float]] = defaultdict(list)

    # ------------------------------------------------------------------ update
    def update(self, t: float, detections: Iterable[tuple[int, float, float]]) -> None:
        for tid, x, y in detections:
            if tid in self._closed:
                continue
            self._first_seen.setdefault(tid, t)
            self._last_seen[tid] = t
            roles_now: set[str] = set()
            for z in self.zones:
                if not point_in_polygon(x, y, z["poly_px"]):
                    continue
                name = z["name"]
                role = z.get("role", name)
                roles_now.add(role)
                rec = self.inside[name].get(tid)
                if rec is None:
                    self.inside[name][tid] = [t, t]
                    self._entries[name].append(t)
                else:
                    rec[1] = t
                self._roles_visited[tid].add(role)
            self._last_roles[tid] = roles_now
        self._close_stale(t)

    def _close_stale(self, t: float) -> None:
        for name, members in self.inside.items():
            role = next((z.get("role", name) for z in self.zones if z["name"] == name), name)
            for tid, (t_in, last) in list(members.items()):
                if t - last > self.grace_s:
                    self.events.append(ZoneEvent(tid, name, t_in, last))
                    if role == self.entry_role:
                        self._entry_dwell[tid] += last - t_in
                    del members[tid]

        for tid, last in list(self._last_seen.items()):
            if tid in self._closed or t - last <= self.lost_timeout_s:
                continue
            self._closed.add(tid)
            visited = self._roles_visited.get(tid, set())
            last_roles = self._last_roles.get(tid, set())
            # Desistência: passou pela entrada, nunca chegou ao buffet e sumiu
            # a partir da própria entrada (voltou para a rua). Exigir que o último
            # ponto seja a entrada reduz falsos positivos por troca de ID no salão.
            if (
                self.entry_role in visited
                and self.buffet_role not in visited
                and self.entry_role in last_roles
                and self._entry_dwell[tid] >= self.min_entry_dwell_s
            ):
                self.balks.append(Balk(tid, self._first_seen[tid], last))

    def flush(self, t: float) -> None:
        """Encerra tudo (fim do vídeo)."""
        self._close_stale(t + max(self.grace_s, self.lost_timeout_s) + 1)

    # ---------------------------------------------------------------- métricas
    def snapshot(self, t: float) -> dict[str, dict[str, float]]:
        """Métricas atuais por zona."""
        out: dict[str, dict[str, float]] = {}
        for z in self.zones:
            name = z["name"]
            members = self.inside[name]
            current_waits = [t - t_in for t_in, _ in members.values()]
            recent = [
                e.dwell_s for e in self.events
                if e.zone == name and t - e.t_out <= self.window_s
            ]
            arrivals = [a for a in self._entries[name] if t - a <= self.window_s]
            span = min(self.window_s, max(t, 1e-6))
            lam = len(arrivals) / span  # pessoas/s
            L = len(members)
            out[name] = {
                "pessoas": float(L),
                "espera_atual_media_s": mean(current_waits) if current_waits else 0.0,
                "espera_atual_max_s": max(current_waits) if current_waits else 0.0,
                "espera_concluida_media_s": mean(recent) if recent else 0.0,
                "espera_concluida_p90_s": _percentile(recent, 0.9),
                "chegadas_por_min": lam * 60,
                # Lei de Little: W = L / λ (estimativa de espera para quem chega agora)
                "espera_estimada_little_s": (L / lam) if lam > 0 else 0.0,
            }
        out["_global"] = {"desistencias": float(len(self.balks))}
        return out

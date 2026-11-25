"""Simula pessoas andando pelas zonas do salão e roda o MESMO motor de análise
do vídeo (QueueAnalytics + TableMonitor + AlertEngine). Serve para:
  * testar a lógica sem GPU nem vídeo;
  * gerar os CSVs da aba "Filas e mesas" do dashboard para a demo.

    python -m src.simulate_salao --minutos 90 --out outputs
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .alerts import AlertEngine
from .config import load_zones
from .queue_analytics import QueueAnalytics
from .table_monitor import TableMonitor
from .video_pipeline import _write_csv

W, H = 1280, 720


def _ponto_em(zone: dict, rng) -> tuple[float, float]:
    xs = [p[0] for p in zone["poly_px"]]
    ys = [p[1] for p in zone["poly_px"]]
    return float(rng.uniform(min(xs) + 3, max(xs) - 3)), float(rng.uniform(min(ys) + 3, max(ys) - 3))


def simular(zones_path: str, minutos: int, start: str, out: str, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    zones = load_zones(zones_path, W, H)
    by = {z["name"]: z for z in zones}
    tables = [z for z in zones if z["type"] == "table"]
    qa, tm, al = QueueAnalytics(zones), TableMonitor(zones), AlertEngine(zones)
    t0 = datetime.fromisoformat(start)
    dur = minutos * 60

    # Roteiro de cada pessoa: lista de (zona, t_inicio, t_fim)
    pessoas = []
    t = 0.0
    tid = 1
    while t < dur:
        frac = t / dur
        taxa = 2.0 + 6.0 * np.exp(-((frac - 0.45) ** 2) / 0.03)  # pico no meio do vídeo (pessoas/min)
        t += rng.exponential(60.0 / taxa)
        fila = taxa / 2.0
        if rng.random() < 0.06 + 0.02 * max(0, fila - 2):   # desistência: espia e volta
            dwell = rng.uniform(5, 25)
            pessoas.append((tid, [("escada_entrada", t, t + dwell)]))
        else:
            e1 = rng.uniform(4, 10) + 3 * fila
            b1 = rng.uniform(60, 150) + 10 * fila
            rota = [("escada_entrada", t, t + e1), ("inicio_buffet", t + e1, t + e1 + b1)]
            if rng.random() < 0.85:
                g = rng.uniform(70, 110) + 25 * fila
                rota.append(("_corredor", t + e1 + b1, t + e1 + b1 + 20))  # caminhando até o grill
                rota.append(("churrasqueira", t + e1 + b1 + 20, t + e1 + b1 + 20 + g))
            pessoas.append((tid, rota))
        tid += 1

    # Mesas: grupos sentam, saem, garçom limpa depois de um tempo
    mesas_ocup = []
    for z in tables:
        tt = rng.uniform(0, 300)
        while tt < dur:
            fica = rng.uniform(900, 1500)
            limpa = rng.uniform(60, 420)
            mesas_ocup.append((z["name"], tt, tt + fica, tt + fica + limpa))
            tt += fica + limpa + rng.uniform(30, 300)

    metric_rows, next_s = [], 0.0
    for step in range(int(dur) + 60):
        t = float(step)
        dets = []
        for pid, rota in pessoas:
            for zn, a, b in rota:
                if a <= t <= b:
                    pt = (W * 0.55, H * 0.56) if zn == "_corredor" else _ponto_em(by[zn], rng)
                    dets.append((pid, *pt))
                    break
        persons, items = [], []
        for mesa, a, b, c in mesas_ocup:
            if a <= t <= b:
                persons += [_ponto_em(by[mesa], rng) for _ in range(2)]
            if a <= t <= c:
                items += [_ponto_em(by[mesa], rng) for _ in range(3)]
        qa.update(t, dets)
        tm.update(t, persons, items)
        snap = qa.snapshot(t)
        al.evaluate(t, snap, tm.dirty_now(t))
        if t >= next_s:
            ts = (t0 + timedelta(seconds=t)).isoformat(timespec="seconds")
            for zn, m in snap.items():
                if not zn.startswith("_"):
                    metric_rows.append({"timestamp": ts, "zona": zn, **{k: round(v, 2) for k, v in m.items()}})
            next_s += 5
    qa.flush(t)

    def ts(sec):
        return (t0 + timedelta(seconds=sec)).isoformat(timespec="seconds")

    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    _write_csv(o / "metricas_fila.csv", metric_rows)
    _write_csv(o / "permanencias.csv", [{"track_id": e.track_id, "zona": e.zone, "entrada": ts(e.t_in),
                                         "saida": ts(e.t_out), "permanencia_s": round(e.dwell_s, 1)} for e in qa.events])
    _write_csv(o / "desistencias.csv", [{"track_id": b.track_id, "chegou": ts(b.t_first_seen),
                                         "foi_embora": ts(b.t_last_seen)} for b in qa.balks])
    _write_csv(o / "eventos_mesas.csv", [{"mesa": e.mesa, "praca": e.praca, "tipo": e.tipo, "suja_desde": ts(e.t_inicio),
                                          "fim": ts(e.t_fim), "duracao_s": round(e.duracao_s, 1)} for e in tm.events])
    _write_csv(o / "alertas.csv", [{"timestamp": ts(a.t), "tipo": a.tipo, "zona": a.zona,
                                    "mensagem": a.mensagem} for a in al.history])
    esperado = sum(1 for _, r in pessoas if len(r) == 1)
    return {"pessoas": len(pessoas), "desistencias_simuladas": esperado, "desistencias_detectadas": len(qa.balks),
            "eventos_mesa": len(tm.events), "alertas": len(al.history)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--zones", default="config/zones.json")
    p.add_argument("--minutos", type=int, default=90)
    p.add_argument("--start", default="2026-11-24T11:50:00")
    p.add_argument("--out", default="outputs")
    a = p.parse_args()
    print(simular(a.zones, a.minutos, a.start, a.out))


if __name__ == "__main__":
    main()

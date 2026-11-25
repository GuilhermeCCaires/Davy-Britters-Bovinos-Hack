"""Cena animada do salão (vista de cima) para o vídeo de demonstração.

Os clientes são simulados (chegada, fila na escada, buffet, fila do grill,
desistências, mesas), mas TODA a análise é feita pelo motor real do projeto:
QueueAnalytics, TableMonitor, AlertEngine e draw_overlay, os mesmos usados
no vídeo das câmeras.
"""
from __future__ import annotations

import sys
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.alerts import AlertEngine  # noqa: E402
from src.config import load_zones  # noqa: E402
from src.queue_analytics import QueueAnalytics  # noqa: E402
from src.table_monitor import TableMonitor  # noqa: E402
from src.video_pipeline import _ascii, draw_overlay  # noqa: E402

W, H = 1280, 720


def P(x, y):
    return (x * W, y * H)


class Agente:
    def __init__(self, aid, t_arr, rng):
        self.id = aid
        self.t_arr = t_arr
        self.rng = rng
        self.balk = False
        self.grill = rng.random() < 0.85
        self.jy = rng.uniform(-0.04, 0.04)


def planejar(dur_s: float, seed: int = 3):
    """Fila em série: escada (1 atendente, pega prato) -> buffet -> grill (3 churrasqueiros)."""
    rng = np.random.default_rng(seed)
    ags, t, aid = [], 0.0, 1
    while t < dur_s:
        frac = t / dur_s
        taxa = 1.2 + 5.8 * np.exp(-((frac - 0.45) ** 2) / 0.02)  # pessoas/min
        t += rng.exponential(60.0 / taxa)
        ags.append(Agente(aid, t, rng))
        aid += 1
    escada_livre = 0.0
    grill_livres = [0.0, 0.0, 0.0]
    for a in ags:
        na_fila = sum(1 for b in ags if b is not a and not b.balk and b.t_arr <= a.t_arr
                      and getattr(b, "esc_fim", 0) > a.t_arr)
        if na_fila >= 4 and rng.random() < 0.5:
            a.balk = True
            a.saida = a.t_arr + rng.uniform(9, 16)
            continue
        a.esc_ini = max(a.t_arr, escada_livre)
        a.esc_fim = a.esc_ini + rng.uniform(9, 14)  # pega prato e talheres, conversando
        escada_livre = a.esc_fim
        a.buf_fim = a.esc_fim + rng.uniform(70, 120)
        if a.grill:
            a.gr_cheg = a.buf_fim + 8
            k = int(np.argmin(grill_livres))
            a.gr_srv = k
            a.gr_ini = max(a.gr_cheg, grill_livres[k])
            a.gr_fim = a.gr_ini + rng.uniform(40, 56)
            grill_livres[k] = a.gr_fim
            a.saida = a.gr_fim + 8
        else:
            a.saida = a.buf_fim + 10
    return ags


def _lerp(p0, p1, f):
    f = min(max(f, 0.0), 1.0)
    return (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)


def posicoes(ags, t):
    """Posição normalizada de cada agente visível no tempo t."""
    out = {}
    fila_esc = sorted([a for a in ags if not a.balk and a.t_arr <= t < a.esc_ini], key=lambda a: a.t_arr)
    fila_esc_ids = {a.id: i for i, a in enumerate(fila_esc)}
    fila_gr = sorted([a for a in ags if a.grill and not a.balk and a.gr_cheg <= t < a.gr_ini],
                     key=lambda a: a.gr_cheg)
    fila_gr_ids = {a.id: i for i, a in enumerate(fila_gr)}
    n_fila_esc = len(fila_esc)
    for a in ags:
        if t < a.t_arr or t >= a.saida + 0.01:
            continue
        if a.balk:
            pos_fila = n_fila_esc
            if t < a.saida - 4:
                out[a.id] = (0.08 + 0.05 * (a.id % 2), max(0.60, 0.93 - 0.06 * min(pos_fila, 6)))
            else:
                out[a.id] = _lerp((0.10, 0.80), (0.10, 1.08), (t - (a.saida - 4)) / 4)
            continue
        if t < a.esc_ini:
            k = fila_esc_ids.get(a.id, 0)
            out[a.id] = (0.07 + 0.06 * (k % 2), max(0.60, 0.94 - 0.05 * k))
        elif t < a.esc_fim:
            out[a.id] = (0.18, 0.60)
        elif t < a.buf_fim:
            f = (t - a.esc_fim) / (a.buf_fim - a.esc_fim)
            out[a.id] = (0.26 + 0.22 * f, 0.62 + a.jy * 2)
        elif a.grill and t < a.gr_cheg:
            out[a.id] = _lerp((0.48, 0.60), (0.63, 0.47), (t - a.buf_fim) / 8)
        elif a.grill and t < a.gr_ini:
            k = fila_gr_ids.get(a.id, 0)
            out[a.id] = (0.64 + 0.035 * (k % 9), 0.46 - 0.06 * (k // 9))
        elif a.grill and t < a.gr_fim:
            out[a.id] = (0.70 + 0.09 * a.gr_srv, 0.25)
        else:
            ini = a.gr_fim if a.grill else a.buf_fim
            p0 = (0.70 + 0.09 * a.gr_srv, 0.27) if a.grill else (0.48, 0.60)
            out[a.id] = _lerp(p0, (1.03, 0.56), (t - ini) / (a.saida - ini))
    return out


def mesas_plano(tables, dur_s, seed=5):
    rng = np.random.default_rng(seed)
    plano = []
    for z in tables:
        tt = rng.uniform(60, 400)
        while tt < dur_s:
            fica = rng.uniform(600, 1100)
            limpa = rng.uniform(90, 420)
            plano.append((z, tt, tt + fica, tt + fica + limpa))
            tt += fica + limpa + rng.uniform(60, 300)
    return plano


def _centro(z):
    xs = [p[0] for p in z["poly_px"]]
    ys = [p[1] for p in z["poly_px"]]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def fundo(zones) -> np.ndarray:
    """Planta baixa estilizada (BGR)."""
    img = np.full((H, W, 3), (232, 240, 246), np.uint8)
    cv2.rectangle(img, (0, 0), (W, H), (232, 240, 246), -1)
    # rua
    cv2.rectangle(img, (0, int(0.985 * H)), (int(0.24 * W), H), (150, 150, 150), -1)
    # degraus da escada
    for i in range(6):
        y = int((0.60 + i * 0.065) * H)
        cv2.line(img, (int(0.03 * W), y), (int(0.21 * W), y), (200, 205, 210), 2)
    # balcões do buffet
    cv2.rectangle(img, (int(0.25 * W), int(0.50 * H)), (int(0.49 * W), int(0.56 * H)), (175, 195, 215), -1)
    cv2.rectangle(img, (int(0.25 * W), int(0.69 * H)), (int(0.49 * W), int(0.74 * H)), (175, 195, 215), -1)
    # churrasqueira
    cv2.rectangle(img, (int(0.62 * W), int(0.07 * H)), (int(0.95 * W), int(0.14 * H)), (60, 70, 140), -1)
    # mesas
    for z in zones:
        if z["type"] == "table":
            cx, cy = _centro(z)
            cv2.rectangle(img, (int(cx - 50), int(cy - 30)), (int(cx + 50), int(cy + 30)), (150, 180, 205), -1)
    # balanças
    for i in range(3):
        x = int((0.53 + 0.035 * i) * W)
        cv2.rectangle(img, (x, int(0.86 * H)), (x + 30, int(0.90 * H)), (120, 120, 120), -1)
    txt = [("RUA AUGUSTA", (0.03, 0.975)), ("BALCAO SALADAS / QUENTES", (0.255, 0.535)),
           ("CHURRASQUEIRA (BALCAO)", (0.64, 0.115)), ("SALAO", (0.73, 0.88)), ("BALANCAS", (0.53, 0.94))]
    for s, (x, y) in txt:
        cor = (255, 255, 255) if s.startswith("CHURRAS") else (90, 90, 90)
        cv2.putText(img, s, (int(x * W), int(y * H)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 1, cv2.LINE_AA)
    return img


def gerar_frames(dur_s=2700.0, n_frames=1125, start="2026-11-24T11:50:00", seed=3):
    """Gera (frame_bgr, t) de uma simulação de `dur_s` segundos em `n_frames` quadros."""
    zones = load_zones(ROOT / "config" / "zones.json", W, H)
    tables = [z for z in zones if z["type"] == "table"]
    qa, tm, al = QueueAnalytics(zones), TableMonitor(zones), AlertEngine(zones)
    ags = planejar(dur_s, seed)
    plano = mesas_plano(tables, dur_s)
    base = fundo(zones)
    t0 = datetime.fromisoformat(start)
    passo = dur_s / n_frames
    sub = 4
    ultimo_alerta = None
    for fi in range(n_frames):
        for s in range(sub):
            t = fi * passo + s * passo / sub
            pos = posicoes(ags, t)
            dets = [(aid, *P(x, y)) for aid, (x, y) in pos.items() if 0 <= x <= 1 and 0 <= y <= 1]
            persons, items = [], []
            for z, a, b, c in plano:
                cx, cy = _centro(z)
                if a <= t <= b:
                    persons += [(cx - 25, cy), (cx + 25, cy)]
                if a <= t <= c:
                    items += [(cx - 15, cy - 8), (cx + 15, cy + 8), (cx, cy)]
            qa.update(t, dets)
            tm.update(t, persons, items)
            snap = qa.snapshot(t)
            novos = al.evaluate(t, snap, tm.dirty_now(t))
            if novos:
                ultimo_alerta = novos[-1]
        frame = base.copy()
        # pessoas
        for aid, x, y in dets:
            cor = (40, 40, 160) if any(b.id == aid for b in ags if b.balk) else (60, 60, 60)
            cv2.circle(frame, (int(x), int(y)), 8, cor, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(x), int(y)), 8, (255, 255, 255), 1, cv2.LINE_AA)
        for z, a, b, c in plano:
            cx, cy = _centro(z)
            if a <= t <= b:
                for dx in (-25, 25):
                    cv2.circle(frame, (int(cx + dx), int(cy)), 8, (60, 60, 60), -1, cv2.LINE_AA)
            if a <= t <= c:
                for dx, dy in ((-15, -8), (15, 8), (0, 0)):
                    cv2.circle(frame, (int(cx + dx), int(cy + dy)), 5, (250, 250, 250), -1, cv2.LINE_AA)
        clock = (t0 + timedelta(seconds=t)).strftime("%H:%M")
        draw_overlay(frame, zones, snap, tm.state, len(qa.balks), clock)
        # caixa de alerta (como chega no celular do maître)
        if ultimo_alerta is not None and t - ultimo_alerta.t < 90:
            x0, y0, x1, y1 = int(0.26 * W), int(0.83 * H), int(0.99 * W), int(0.985 * H)
            x0 = int(0.62 * W)
            cv2.rectangle(frame, (x0, y0), (x1, y1), (30, 27, 155), -1)
            hora = (t0 + timedelta(seconds=ultimo_alerta.t)).strftime("%H:%M")
            msg = _ascii(ultimo_alerta.mensagem).encode("ascii", "ignore").decode().strip()
            linhas = [f"ALERTA {hora} -> celular do maitre"] + textwrap.wrap(msg, 50)[:3]
            for i, ln in enumerate(linhas):
                cv2.putText(frame, ln, (x0 + 12, y0 + 26 + i * 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                            (255, 255, 255), 1, cv2.LINE_AA)
        yield frame, t, qa, tm, al

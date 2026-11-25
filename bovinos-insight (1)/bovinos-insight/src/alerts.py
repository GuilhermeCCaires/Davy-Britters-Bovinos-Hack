"""Regras de alerta e envio opcional para o Telegram (sem dependências externas).

Variáveis de ambiente para envio real:
    TELEGRAM_TOKEN=<token do bot>  TELEGRAM_CHAT_ID=<id do grupo dos gerentes>
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass
class Alert:
    t: float
    tipo: str
    zona: str
    mensagem: str


def _min(seg: float) -> str:
    """Minutos com vírgula decimal: 150 s -> '2,5'."""
    return f"{seg / 60:.1f}".replace(".", ",")


class AlertEngine:
    def __init__(self, zones: list[dict], table_dirty_alert_s: float = 180.0, cooldown_s: float = 120.0):
        self.zones = {z["name"]: z for z in zones}
        self.table_dirty_alert_s = table_dirty_alert_s
        self.cooldown_s = cooldown_s
        self._last: dict[tuple[str, str], float] = {}
        self.history: list[Alert] = []

    def _fire(self, t: float, tipo: str, zona: str, msg: str) -> Alert | None:
        key = (tipo, zona)
        if key in self._last and t - self._last[key] < self.cooldown_s:
            return None
        self._last[key] = t
        a = Alert(t, tipo, zona, msg)
        self.history.append(a)
        return a

    def evaluate(self, t: float, snapshot: dict, dirty_tables: dict[str, float] | None = None) -> list[Alert]:
        fired: list[Alert] = []
        for name, m in snapshot.items():
            z = self.zones.get(name)
            if not z:
                continue
            lim_count = z.get("alert_count")
            lim_wait = z.get("alert_wait_s")
            if lim_count and m["pessoas"] >= lim_count:
                a = self._fire(t, "fila_longa", name,
                               f"⚠️ {z.get('label', name)}: {int(m['pessoas'])} pessoas na fila "
                               f"(limite {lim_count}). Abrir apoio / direcionar clientes.")
                if a:
                    fired.append(a)
            # espera: maior entre quem está na fila agora e quem saiu nos últimos minutos
            espera = max(m["espera_atual_media_s"], m["espera_concluida_media_s"])
            if lim_wait and espera >= lim_wait:
                a = self._fire(t, "espera_alta", name,
                               f"⏱️ {z.get('label', name)}: espera média {_min(espera)} min "
                               f"(meta {_min(lim_wait)} min). Reforçar atendimento.")
                if a:
                    fired.append(a)
        for mesa, secs in (dirty_tables or {}).items():
            if secs >= self.table_dirty_alert_s:
                praca = self.zones.get(mesa, {}).get("praca", "").replace("_", " ").replace("salao", "salão")
                nome = mesa.removeprefix("mesa_")
                a = self._fire(t, "mesa_suja", mesa,
                               f"🧽 Mesa {nome} ({praca}) suja há {_min(secs)} min.")
                if a:
                    fired.append(a)
        return fired


def send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=5) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False

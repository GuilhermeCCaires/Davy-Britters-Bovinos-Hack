"""Gera dados SINTÉTICOS no formato de comandas do JS SoftCom (+ bip de entrada
e mix do prato estimado pela câmera da balança), para o dashboard e para testes.

Números de calibração vindos da conversa com a Bovinos (Augusta):
  ~600 clientes/dia útil, ~250 no sábado e no domingo, pico 12h10–13h20,
  R$ 119/kg, 10% de desconto antes das 12h e depois das 13h30,
  casa aberta 11h30–15h30, chuva e feriado derrubam o movimento,
  terça (comida árabe) é o melhor dia.
Custos por kg e demais parâmetros são HIPOTÉTICOS: troque pelos reais.

    python -m src.simulate_softcom --inicio 2026-10-26 --dias 28 --out data/comandas.csv
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PRECO_KG = 119.0
CATEGORIAS = ["carne_grill", "arroz_feijao", "pratos_quentes", "saladas", "sobremesas"]
CUSTO_KG = {  # R$/kg – hipotético
    "carne_grill": 62.0, "arroz_feijao": 7.0, "pratos_quentes": 16.0, "saladas": 12.0, "sobremesas": 18.0,
}
TEMA_DIA = {0: "Virado à paulista", 1: "Comida árabe", 2: "Feijoada", 3: "Italiano",
            4: "Frutos do mar", 5: "Feijoada", 6: "Variado"}
FERIADOS = {date(2026, 11, 2), date(2026, 11, 20), date(2026, 12, 25), date(2027, 1, 1)}
PRACAS = ["salao_superior", "salao_inferior", "salao_principal"]
ABRE = datetime.min.replace(hour=11, minute=30)


def _clientes_do_dia(d: date, chuva: bool, rng: np.random.Generator) -> int:
    dow = d.weekday()
    base = 600 if dow < 5 else 250
    if dow == 1:
        base *= 1.08
    if chuva:
        base *= 0.82
    if d in FERIADOS:
        base *= 0.55
    return int(base * rng.normal(1.0, 0.05))


def _minutos_chegada(n: int, fim_de_semana: bool, rng: np.random.Generator) -> np.ndarray:
    """Minutos após 11h30 (0 a 225 = 15h15)."""
    if fim_de_semana:
        m = rng.normal(95, 40, n)
    else:
        pico = rng.random(n) < 0.8
        m = np.where(pico, rng.normal(72, 22, n), rng.uniform(0, 225, n))
    fora = (m < 0) | (m > 225)
    m[fora] = rng.uniform(0, 225, int(fora.sum()))  # sem acumular gente na abertura/fechamento
    return m


def gerar(inicio: date, dias: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    linhas = []
    for k in range(dias):
        d = inicio + timedelta(days=k)
        dow = d.weekday()
        chuva = bool(rng.random() < 0.3)
        n = _clientes_do_dia(d, chuva, rng)
        chegada = np.sort(_minutos_chegada(n, dow >= 5, rng))
        # congestionamento: chegadas nos 10 minutos anteriores
        idx_10 = np.searchsorted(chegada, chegada - 10)
        taxa = (np.arange(n) - idx_10) / 10.0  # pessoas/min
        for i in range(n):
            pegou_carne = rng.random() < (0.85 if dow < 5 else 0.9)
            fila_buffet = 0.35 * max(0.0, taxa[i] - 3.0)
            fila_grill = (0.6 + 0.45 * max(0.0, taxa[i] - 3.0) + rng.exponential(0.4)) if pegou_carne else 0.0
            tempo_buffet = rng.lognormal(np.log(3.2), 0.25) + fila_buffet + fila_grill
            permanencia = max(12.0, rng.normal(24 if dow < 5 else 38, 6))

            entrada = datetime.combine(d, ABRE.time()) + timedelta(minutes=float(chegada[i]))
            pesagem = entrada + timedelta(minutes=float(tempo_buffet))
            pagamento = pesagem + timedelta(minutes=float(permanencia))

            peso = float(np.clip(rng.normal(0.52 if dow < 5 else 0.60, 0.15), 0.15, 1.4))
            alpha = np.array([3.0 if pegou_carne else 0.15, 2.2, 2.2, 2.0, 0.6])
            if dow in (1, 2, 5):            # árabe / feijoada puxam os quentes
                alpha[2] += 0.8
            if taxa[i] > 5:                 # no pico, fila do grill desestimula carne
                alpha[0] *= 0.9
            mix = rng.dirichlet(alpha * 3)
            gramas = dict(zip(CATEGORIAS, (mix * peso * 1000).round()))

            h = entrada.hour + entrada.minute / 60
            desconto = 0.10 if (h < 12.0 or h >= 13.5) else 0.0
            valor_comida = round(peso * PRECO_KG * (1 - desconto), 2)
            bebida = round(float(rng.uniform(7, 14)), 2) if rng.random() < 0.55 else 0.0
            custo = sum(gramas[c] / 1000 * CUSTO_KG[c] for c in CATEGORIAS)

            linhas.append({
                "data": d.isoformat(), "dia_semana": dow, "tema_dia": TEMA_DIA[dow],
                "chuva": chuva, "feriado": d in FERIADOS,
                "comanda": int(rng.integers(1, 10000)), "praca": PRACAS[int(rng.integers(0, 3))],
                "entrada": entrada, "pesagem": pesagem, "pagamento": pagamento,
                "tempo_buffet_min": round(tempo_buffet, 2), "permanencia_min": round(permanencia, 2),
                "tempo_total_min": round(tempo_buffet + permanencia, 2),
                "peso_kg": round(peso, 3), "desconto_pct": desconto * 100,
                "valor_comida": valor_comida, "valor_bebida": bebida,
                **{f"g_{c}": gramas[c] for c in CATEGORIAS},
                "custo_estimado": round(custo, 2),
            })
    return pd.DataFrame(linhas)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inicio", default="2026-10-26")
    p.add_argument("--dias", type=int, default=28)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="data/comandas.csv")
    a = p.parse_args()
    df = gerar(date.fromisoformat(a.inicio), a.dias, a.seed)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(f"{len(df)} comandas em {a.dias} dias -> {a.out}")


if __name__ == "__main__":
    main()

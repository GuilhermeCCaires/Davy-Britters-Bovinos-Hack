"""Previsão de clientes por dia (dia da semana + chuva + feriado) e sugestão de escala.

    python -m src.forecast --comandas data/comandas.csv --dias 7 --chuva 0,1,0,0,0,0,0

Os coeficientes de escala (clientes por garçom/churrasqueiro no pico) são
parâmetros de negócio: ajuste com a gerência.
"""
from __future__ import annotations

import argparse
import math
from datetime import date, timedelta

import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from .simulate_softcom import FERIADOS

CLIENTES_PICO_POR_GARCOM = 50      # por hora de pico (hipótese)
CLIENTES_PICO_POR_CHURRASQUEIRO = 90


def _features(datas: list[date], chuva: list[int]) -> pd.DataFrame:
    df = pd.DataFrame({"data": datas, "chuva": chuva})
    df["dow"] = [d.weekday() for d in datas]
    df["feriado"] = [int(d in FERIADOS) for d in datas]
    df["fim_semana"] = (df["dow"] >= 5).astype(int)
    for k in range(7):
        df[f"dow_{k}"] = (df["dow"] == k).astype(int)
    return df


FEATS = ["chuva", "feriado", "fim_semana"] + [f"dow_{k}" for k in range(7)]


def treinar(comandas: pd.DataFrame):
    comandas = comandas.copy()
    comandas["entrada"] = pd.to_datetime(comandas["entrada"])
    diario = comandas.groupby("data").agg(clientes=("comanda", "size"), chuva=("chuva", "first")).reset_index()
    diario["data"] = pd.to_datetime(diario["data"]).dt.date
    X = _features(list(diario["data"]), list(diario["chuva"].astype(int)))
    model = GradientBoostingRegressor(random_state=0, n_estimators=200, max_depth=2)
    model.fit(X[FEATS], diario["clientes"])
    # fração dos clientes do dia que chega na hora mais cheia
    comandas["hora"] = comandas["entrada"].dt.floor("h")
    pico = comandas.groupby(["data", "hora"]).size().groupby("data").max()
    frac_pico = float((pico / comandas.groupby("data").size()).mean())
    return model, frac_pico


def prever(model, frac_pico: float, inicio: date, dias: int, chuva: list[int]) -> pd.DataFrame:
    datas = [inicio + timedelta(days=i) for i in range(dias)]
    X = _features(datas, chuva)
    y = model.predict(X[FEATS]).round().astype(int)
    out = pd.DataFrame({"data": datas, "chuva": chuva, "feriado": X["feriado"], "clientes_previstos": y})
    out["clientes_hora_pico"] = (out["clientes_previstos"] * frac_pico).round().astype(int)
    out["garcons_sugeridos"] = out["clientes_hora_pico"].apply(lambda c: max(4, math.ceil(c / CLIENTES_PICO_POR_GARCOM)))
    out["churrasqueiros_no_atendimento"] = out["clientes_hora_pico"].apply(
        lambda c: max(2, math.ceil(c / CLIENTES_PICO_POR_CHURRASQUEIRO)))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--comandas", default="data/comandas.csv")
    p.add_argument("--inicio", default=None)
    p.add_argument("--dias", type=int, default=7)
    p.add_argument("--chuva", default="", help="lista 0/1 por dia, ex: 0,1,0,0,0,0,0")
    a = p.parse_args()
    com = pd.read_csv(a.comandas)
    model, frac = treinar(com)
    inicio = date.fromisoformat(a.inicio) if a.inicio else date.fromisoformat(com["data"].max()) + timedelta(days=1)
    chuva = [int(c) for c in a.chuva.split(",")] if a.chuva else [0] * a.dias
    chuva = (chuva + [0] * a.dias)[: a.dias]
    print(prever(model, frac, inicio, a.dias, chuva).to_string(index=False))


if __name__ == "__main__":
    main()

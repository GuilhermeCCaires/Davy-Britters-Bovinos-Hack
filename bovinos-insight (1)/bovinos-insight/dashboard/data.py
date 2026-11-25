"""Preparação de dados do dashboard (só pandas – testável sem Streamlit)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CATS = ["carne_grill", "arroz_feijao", "pratos_quentes", "saladas", "sobremesas"]
NOMES_CAT = {"carne_grill": "Carne (grill)", "arroz_feijao": "Arroz e feijão", "pratos_quentes": "Pratos quentes",
             "saladas": "Saladas", "sobremesas": "Sobremesas"}
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
ROOT = Path(__file__).resolve().parents[1]


def load_comandas(path: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(path or ROOT / "data" / "comandas.csv", parse_dates=["entrada", "pesagem", "pagamento"])
    df["data"] = pd.to_datetime(df["data"]).dt.date
    df["slot15"] = df["entrada"].dt.floor("15min").dt.strftime("%H:%M")
    df["hora"] = df["entrada"].dt.strftime("%H:00")
    df["dia"] = df["dia_semana"].map(dict(enumerate(DIAS)))
    df["ticket"] = df["valor_comida"] + df["valor_bebida"]
    return df


def kpis(df: pd.DataFrame) -> dict[str, float]:
    dias = df["data"].nunique() or 1
    peso_total_g = df["peso_kg"].sum() * 1000
    return {
        "clientes_dia": len(df) / dias,
        "ticket_medio": df["ticket"].mean(),
        "peso_medio_g": df["peso_kg"].mean() * 1000,
        "tempo_buffet_min": df["tempo_buffet_min"].mean(),
        "tempo_total_min": df["tempo_total_min"].mean(),
        "pct_carne": df["g_carne_grill"].sum() / peso_total_g * 100,
        "cmv_estimado_pct": df["custo_estimado"].sum() / df["valor_comida"].sum() * 100,
    }


def fluxo_por_slot(df: pd.DataFrame) -> pd.DataFrame:
    dias = df["data"].nunique() or 1
    g = df.groupby("slot15").agg(entradas=("comanda", "size"), tempo_buffet=("tempo_buffet_min", "mean"),
                                 p90_buffet=("tempo_buffet_min", lambda s: s.quantile(0.9))).reset_index()
    g["entradas_por_dia"] = g["entradas"] / dias
    return g


def mix_por(df: pd.DataFrame, col: str) -> pd.DataFrame:
    g = df.groupby(col)[[f"g_{c}" for c in CATS]].sum()
    pct = g.div(g.sum(axis=1), axis=0) * 100
    pct.columns = [NOMES_CAT[c] for c in CATS]
    if col == "dia":
        pct = pct.reindex([d for d in DIAS if d in pct.index])
    return pct.reset_index().melt(id_vars=col, var_name="categoria", value_name="pct")


def cmv_por(df: pd.DataFrame, col: str) -> pd.DataFrame:
    g = df.groupby(col).agg(custo=("custo_estimado", "sum"), receita=("valor_comida", "sum"),
                            carne_g=("g_carne_grill", "sum"), peso=("peso_kg", "sum")).reset_index()
    g["cmv_pct"] = g["custo"] / g["receita"] * 100
    g["pct_carne"] = g["carne_g"] / (g["peso"] * 1000) * 100
    return g


def diario(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(["data", "dia", "chuva", "feriado"]).agg(
        clientes=("comanda", "size"), ticket=("ticket", "mean")).reset_index()


def load_video_outputs(folder: Path | None = None) -> dict[str, pd.DataFrame]:
    folder = folder or ROOT / "outputs"
    out = {}
    for name in ["metricas_fila", "permanencias", "desistencias", "eventos_mesas", "alertas"]:
        p = folder / f"{name}.csv"
        if p.exists() and p.stat().st_size > 0:
            out[name] = pd.read_csv(p)
    return out

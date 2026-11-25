"""Cria o banco da demo (SQLite) a partir de db/schema.sql e carrega os CSVs gerados.

    python -m src.db                       # cria db/bovinos_insight.db
    sqlite3 db/bovinos_insight.db "SELECT * FROM vw_cmv_dia LIMIT 5;"

Em produção o mesmo schema roda em PostgreSQL (TimescaleDB nas tabelas de série temporal).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

from .plate_mix import DENSIDADE
from .simulate_softcom import CATEGORIAS, CUSTO_KG, PRECO_KG

ROOT = Path(__file__).resolve().parents[1]


def _sqlite_ddl(sql: str) -> str:
    sql = re.sub(r"\bBIGSERIAL PRIMARY KEY\b", "INTEGER PRIMARY KEY", sql)
    sql = re.sub(r"\bSERIAL PRIMARY KEY\b", "INTEGER PRIMARY KEY", sql)
    return sql


def build(db_path: Path, comandas_csv: Path, outputs: Path, zones_json: Path) -> dict[str, int]:
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(_sqlite_ddl((ROOT / "db" / "schema.sql").read_text(encoding="utf-8")))

    con.execute("INSERT INTO unidade (nome, preco_kg) VALUES (?, ?)", ("Bovinos Grill & Beer – Augusta", PRECO_KG))
    con.executemany("INSERT INTO custo_categoria VALUES (?, ?, ?)",
                    [(c, CUSTO_KG[c], DENSIDADE[c]) for c in CATEGORIAS])
    for z in json.loads(zones_json.read_text(encoding="utf-8"))["zones"]:
        con.execute("INSERT INTO zona VALUES (?,?,?,?,?,?,?)",
                    (z["name"], z["type"], z.get("role"), z.get("praca"), z.get("alert_count"),
                     z.get("alert_wait_s"), json.dumps(z["polygon"])))

    df = pd.read_csv(comandas_csv)
    df = df.reset_index().rename(columns={"index": "id"})
    df["id"] += 1
    visita_cols = ["id", "data", "comanda", "praca", "tema_dia", "chuva", "feriado", "entrada", "pesagem",
                   "pagamento", "peso_kg", "desconto_pct", "valor_comida", "valor_bebida"]
    df[visita_cols].to_sql("visita", con, if_exists="append", index=False)
    mix = df.melt(id_vars="id", value_vars=[f"g_{c}" for c in CATEGORIAS], var_name="categoria", value_name="gramas")
    mix["categoria"] = mix["categoria"].str.removeprefix("g_")
    mix = mix[mix["gramas"] > 0].rename(columns={"id": "visita_id"})
    mix.to_sql("prato_mix", con, if_exists="append", index=False)

    mapping = {"metricas_fila": "fila_metrica", "permanencias": "permanencia", "desistencias": "desistencia",
               "eventos_mesas": "evento_mesa", "alertas": "alerta"}
    for csv_name, table in mapping.items():
        p = outputs / f"{csv_name}.csv"
        if p.exists() and p.stat().st_size > 0:
            t = pd.read_csv(p)
            if table == "fila_metrica":
                t = t.rename(columns={"timestamp": "ts"})
            if table == "alerta":
                t = t.rename(columns={"timestamp": "ts"})
            t.to_sql(table, con, if_exists="append", index=False)
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["visita", "prato_mix", "fila_metrica", "permanencia", "desistencia", "evento_mesa", "alerta"]}
    con.close()
    return counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(ROOT / "db" / "bovinos_insight.db"))
    p.add_argument("--comandas", default=str(ROOT / "data" / "comandas.csv"))
    p.add_argument("--outputs", default=str(ROOT / "outputs"))
    p.add_argument("--zones", default=str(ROOT / "config" / "zones.json"))
    a = p.parse_args()
    print(build(Path(a.db), Path(a.comandas), Path(a.outputs), Path(a.zones)))


if __name__ == "__main__":
    main()

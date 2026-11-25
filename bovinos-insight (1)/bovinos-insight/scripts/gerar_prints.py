"""Gera as 5 capturas de tela da entrega em docs/prints/.

    python scripts/gerar_prints.py

Usa os dados gerados pelo projeto (data/comandas.csv e outputs/*.csv) e as
mesmas funções do dashboard (dashboard/data.py). Os painéis reproduzem as abas
do dashboard Streamlit; depois de rodar `streamlit run dashboard/app.py`,
vocês podem trocar estes prints por capturas do navegador.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dashboard import data as D  # noqa: E402
from src.forecast import prever, treinar  # noqa: E402
from telas import (CINZA, CLARO, CORES_CAT, CSS_BASE, ESCURO, OURO, VERMELHO, fig_b64,  # noqa: E402
                   img_b64, plt, shot)

OUT = ROOT / "docs" / "prints"
W, H = 1600, 1000
ABAS = ["⏱️ Jornada e fluxo", "🍽️ Mix do prato (CMV)", "🎥 Filas e mesas (câmeras)", "🔮 Previsão"]


def pagina(aba: int, kpis_html: str, corpo: str) -> str:
    tabs = "".join(f'<div class="tab{" on" if i == aba else ""}">{t}</div>' for i, t in enumerate(ABAS))
    return f"""<html><head><meta charset="utf-8"><style>{CSS_BASE}
.side {{ position:absolute; left:0; top:0; bottom:0; width:250px; background:#EFE7DC; padding:28px 22px; }}
.side h4 {{ margin:0 0 18px 0; font-size:17px; }}
.side .f {{ font-size:13px; color:#4A3F3A; margin:14px 0 6px; font-weight:600; }}
.side .in {{ background:#fff; border:1px solid #DDD0C0; border-radius:8px; padding:9px 10px; font-size:13px; }}
.chip {{ display:inline-block; background:{VERMELHO}; color:#fff; border-radius:6px; padding:3px 7px; font-size:12px; margin:3px 3px 0 0; }}
.main {{ position:absolute; left:250px; right:0; top:0; bottom:0; padding:26px 40px; background:{CLARO}; }}
.title {{ font-size:34px; margin:0; color:{ESCURO}; }}
.cap {{ font-size:13px; color:{CINZA}; margin:4px 0 16px; }}
.kpis {{ display:grid; grid-template-columns:repeat(7,1fr); gap:12px; margin-bottom:16px; }}
.k {{ background:#fff; border:1px solid #E4D8C8; border-radius:10px; padding:10px 14px; }}
.k .l {{ font-size:12px; color:{CINZA}; }} .k .v {{ font-size:25px; font-weight:700; margin-top:2px; }}
.tabs {{ display:flex; gap:6px; border-bottom:2px solid #E4D8C8; margin-bottom:16px; }}
.tab {{ padding:9px 14px; font-size:14px; color:{CINZA}; }} .tab.on {{ color:{VERMELHO}; border-bottom:3px solid {VERMELHO}; font-weight:700; margin-bottom:-2px; }}
.g2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.card {{ background:#fff; border:1px solid #E4D8C8; border-radius:10px; padding:10px; }}
.card img {{ width:100%; display:block; }}
.info {{ background:#FBF1D9; border-left:4px solid {OURO}; padding:10px 14px; font-size:14px; border-radius:6px; margin-top:14px; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }} th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid #EEE6DC; }}
th {{ color:{CINZA}; font-weight:600; }}
</style></head><body>
<div class="side"><h4>Filtros</h4>
<div class="f">Período</div><div class="in">26/10/2026 – 22/11/2026</div>
<div class="f">Dias da semana</div><div>{''.join(f'<span class="chip">{d}</span>' for d in D.DIAS)}</div>
<div class="f">☑ Excluir feriados</div>
<div class="f" style="margin-top:40px; color:{CINZA}; font-weight:400">Dados da demo: sintéticos, calibrados com os números da Bovinos.</div>
</div>
<div class="main">
<h1 class="title">🥩 Bovinos Insight – Grill &amp; Beer Augusta</h1>
<p class="cap">Almoço por quilo · dados de comanda (JS SoftCom + bip de entrada) e visão computacional do salão</p>
{kpis_html}
<div class="tabs">{tabs}</div>
{corpo}
</div></body></html>"""


def kpis_html(df: pd.DataFrame) -> str:
    k = D.kpis(df)
    items = [("Clientes/dia", f"{k['clientes_dia']:.0f}"), ("Ticket médio", f"R$ {k['ticket_medio']:.2f}"),
             ("Peso médio", f"{k['peso_medio_g']:.0f} g"), ("Entrada → balança", f"{k['tempo_buffet_min']:.1f} min"),
             ("Tempo na casa", f"{k['tempo_total_min']:.0f} min"), ("% carne no prato", f"{k['pct_carne']:.1f}%"),
             ("CMV estimado", f"{k['cmv_estimado_pct']:.1f}%")]
    return '<div class="kpis">' + "".join(
        f'<div class="k"><div class="l">{a}</div><div class="v">{b.replace(".", ",")}</div></div>' for a, b in items) + "</div>"


def print_jornada(df):
    f = D.fluxo_por_slot(df)
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    cores = [OURO if "12:00" <= s < "13:30" else VERMELHO for s in f["slot15"]]
    ax.bar(f["slot15"], f["entradas_por_dia"], color=cores)
    ax.set_title("Chegadas a cada 15 min (média por dia)")
    ax.set_ylabel("clientes")
    ax.tick_params(axis="x", rotation=60, labelsize=9)
    ax.text(0.99, 0.95, "em dourado: pico 12h–13h30", transform=ax.transAxes, ha="right", fontsize=9, color=CINZA)
    c1 = fig_b64(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.plot(f["slot15"], f["tempo_buffet"], marker="o", color=VERMELHO, label="média")
    ax.plot(f["slot15"], f["p90_buffet"], marker="o", color=CINZA, ls="--", label="p90 (1 em cada 10)")
    ax.set_title("Tempo da entrada até a balança (min)")
    ax.tick_params(axis="x", rotation=60, labelsize=9)
    ax.legend(frameon=False, fontsize=10)
    c2 = fig_b64(fig)

    dd = D.diario(df)
    g = dd.groupby(["dia", "chuva"])["clientes"].mean().unstack().reindex(D.DIAS)
    fig, ax = plt.subplots(figsize=(13.2, 2.0))
    x = np.arange(len(g))
    ax.bar(x - 0.2, g.get(False, pd.Series(0, index=g.index)), 0.4, color=VERMELHO, label="sem chuva")
    ax.bar(x + 0.2, g.get(True, pd.Series(0, index=g.index)), 0.4, color="#BFB2A5", label="com chuva")
    ax.set_xticks(x, g.index)
    ax.set_title("Clientes por dia da semana – efeito da chuva")
    ax.legend(frameon=False, fontsize=10, loc="upper right")
    c3 = fig_b64(fig)
    corpo = f"""<div class="g2"><div class="card"><img src="{c1}"></div><div class="card"><img src="{c2}"></div></div>
<div class="card" style="margin-top:16px"><img src="{c3}"></div>"""
    shot(pagina(0, kpis_html(df), corpo), OUT / "01_dashboard_jornada.png", W, H)


def print_mix(df):
    m = D.mix_por(df, "dia").pivot(index="dia", columns="categoria", values="pct").reindex(D.DIAS)
    ordem = [D.NOMES_CAT[c] for c in D.CATS]
    fig, ax = plt.subplots(figsize=(6.4, 3.3))
    base = np.zeros(len(m))
    for cat, cor in zip(ordem, CORES_CAT):
        ax.bar(m.index, m[cat], bottom=base, color=cor, label=cat)
        base += m[cat].values
    ax.set_ylim(0, 100)
    ax.set_title("Composição do prato por dia (% do peso)")
    ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    c1 = fig_b64(fig)

    cm = D.cmv_por(df, "hora")
    fig, ax = plt.subplots(figsize=(6.4, 3.3))
    bars = ax.bar(cm["hora"], cm["cmv_pct"], color=VERMELHO)
    for b, v in zip(bars, cm["cmv_pct"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.3, f"{v:.1f}%".replace(".", ","), ha="center", fontsize=10)
    ax.set_title("CMV estimado por hora de chegada")
    ax.set_ylim(0, cm["cmv_pct"].max() * 1.2)
    c2 = fig_b64(fig)

    cd = D.cmv_por(df, "dia").set_index("dia").reindex(D.DIAS)
    fig, ax = plt.subplots(figsize=(13.2, 1.9))
    ax.scatter(cd["pct_carne"], cd["cmv_pct"], s=cd["receita"] / cd["receita"].max() * 600, color=VERMELHO, alpha=0.8)
    desloc = {"Seg": (-30, 8), "Ter": (10, -14), "Qua": (10, 6), "Qui": (12, 10), "Sex": (12, -16), "Sáb": (10, 6), "Dom": (-40, 4)}
    for d, r in cd.iterrows():
        ax.annotate(d, (r["pct_carne"], r["cmv_pct"]), xytext=desloc.get(d, (8, 6)), textcoords="offset points", fontsize=11)
    ax.set_xlabel("% de carne no prato")
    ax.set_ylabel("CMV %")
    ax.set_title("% de carne no prato × CMV estimado, por dia (tamanho = faturamento)")
    c3 = fig_b64(fig)
    corpo = f"""<div class="g2"><div class="card"><img src="{c1}"></div><div class="card"><img src="{c2}"></div></div>
<div class="card" style="margin-top:16px"><img src="{c3}"></div>"""
    shot(pagina(1, kpis_html(df), corpo), OUT / "02_dashboard_mix_cmv.png", W, H)


def print_filas(df):
    v = D.load_video_outputs()
    mf = v["metricas_fila"].copy()
    mf["timestamp"] = pd.to_datetime(mf["timestamp"])
    nomes = {"escada_entrada": "Escada / entrada", "inicio_buffet": "Início do buffet", "churrasqueira": "Churrasqueira"}
    cores = {"escada_entrada": VERMELHO, "inicio_buffet": OURO, "churrasqueira": "#D9822B"}
    fig, ax = plt.subplots(figsize=(6.4, 3.5))
    for z, g in mf.groupby("zona"):
        ax.plot(g["timestamp"], g["pessoas"], color=cores.get(z, CINZA), label=nomes.get(z, z), lw=1.6)
    ax.set_title("Pessoas na fila por zona")
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    ax.legend(frameon=False, fontsize=9)
    c1 = fig_b64(fig)
    fig, ax = plt.subplots(figsize=(6.4, 3.5))
    for z, g in mf.groupby("zona"):
        ax.plot(g["timestamp"], g["espera_concluida_media_s"] / 60, color=cores.get(z, CINZA), label=nomes.get(z, z), lw=1.6)
    ax.axhline(2.5, color=VERMELHO, ls="--", lw=1.2)
    ax.text(mf["timestamp"].min(), 2.6, "meta do grill: 2,5 min", color=VERMELHO, fontsize=9)
    ax.set_title("Espera média (min, janela de 5 min)")
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    ax.legend(frameon=False, fontsize=9)
    c2 = fig_b64(fig)
    des, me, al = v["desistencias"], v["eventos_mesas"], v["alertas"]
    gr = mf[mf["zona"] == "churrasqueira"]["espera_concluida_media_s"].max() / 60
    kp = [("Desistências na escada", f"{len(des)}"), ("Espera máx. no grill", f"{gr:.1f} min".replace(".", ",")),
          ("Tempo médio de mesa suja", f"{me['duracao_s'].mean() / 60:.1f} min".replace(".", ",")),
          ("Alertas enviados", f"{len(al)}")]
    k2 = '<div class="kpis" style="grid-template-columns:repeat(4,1fr)">' + "".join(
        f'<div class="k"><div class="l">{a}</div><div class="v">{b}</div></div>' for a, b in kp) + "</div>"
    sel = pd.concat([al[al.tipo == t].iloc[[0, -1]] for t in ["fila_longa", "espera_alta", "mesa_suja"]]).sort_values("timestamp")
    linhas = "".join(f"<tr><td>{r.timestamp[11:16]}</td><td>{r.tipo}</td><td>{r.mensagem}</td></tr>"
                     for r in sel.itertuples())
    corpo = f"""{k2}<div class="g2"><div class="card"><img src="{c1}"></div><div class="card"><img src="{c2}"></div></div>
<div class="card" style="margin-top:14px"><b style="font-size:14px">Alertas enviados ao maître</b>
<table><tr><th>hora</th><th>tipo</th><th>mensagem</th></tr>{linhas}</table></div>"""
    html = pagina(2, "", corpo).replace('<p class="cap">', '<p class="cap">Simulação de 90 min do salão processada pelo motor de filas · ', 1)
    shot(html, OUT / "03_dashboard_filas_mesas.png", W, H)


def print_video():
    from cena_salao import gerar_frames
    # escolhe um quadro do pico com fila na escada, mesa suja e alerta na tela
    escolhido = None
    for i, (frame, t, qa, tm, al) in enumerate(gerar_frames()):
        snap = qa.snapshot(t)
        ok = (snap["escada_entrada"]["pessoas"] >= 3 and snap["churrasqueira"]["pessoas"] >= 7
              and "suja" in tm.state.values() and al.history and t - al.history[-1].t < 60)
        if ok or i == 760:
            escolhido = frame
            if ok:
                break
    cv2.imwrite(str(OUT / "_frame.png"), escolhido)
    html = f"""<html><head><meta charset="utf-8"><style>{CSS_BASE}
body {{ background:{ESCURO}; color:{CLARO}; padding:36px 48px; }}
.t {{ font-size:40px; margin:0; }} .s {{ color:#E8DCCB; font-size:17px; margin:6px 0 20px; }}
img {{ width:1280px; border-radius:8px; display:block; }}
.leg {{ display:flex; gap:28px; margin-top:16px; font-size:15px; color:#E8DCCB; }}
.dot {{ display:inline-block; width:14px; height:14px; border-radius:3px; margin-right:6px; vertical-align:-2px; }}
</style></head><body>
<h2 class="t">Fila Zero + Mesa Pronta · análise do salão em tempo real</h2>
<p class="s">Saída do <b>src/video_pipeline</b> (desenho das zonas, contagem, espera, desistências, estado das mesas e alerta). Cena simulada; com o vídeo real da Bovinos, o YOLO + ByteTrack substituem a simulação.</p>
<img src="{img_b64(OUT / '_frame.png')}">
<div class="leg"><span><span class="dot" style="background:#E05A4F"></span>zona de entrada (desistência)</span>
<span><span class="dot" style="background:#F2B233"></span>zonas de fila do buffet e grill</span>
<span><span class="dot" style="background:#3BA3E8"></span>mesa ocupada</span><span><span class="dot" style="background:#E03030"></span>mesa suja</span>
<span><span class="dot" style="background:#2FA84F"></span>mesa livre</span></div>
</body></html>"""
    shot(html, OUT / "04_video_analise_salao.png", 1376, 960)
    (OUT / "_frame.png").unlink()


def print_previsao(df_all):
    model, frac = treinar(df_all.assign(data=df_all["data"].astype(str)))
    inicio = df_all["data"].max() + pd.Timedelta(days=1)
    chuva = [0, 1, 0, 0, 0, 0, 0]
    prev = prever(model, frac, inicio, 7, chuva)
    prev["dia"] = [f"{D.DIAS[d.weekday()]} {d:%d/%m}" for d in prev["data"]]
    prev["rot"] = [f"{D.DIAS[d.weekday()]}\n{d:%d/%m}" for d in prev["data"]]
    fig, ax = plt.subplots(figsize=(7.6, 3.0))
    cores = ["#BFB2A5" if c else VERMELHO for c in prev["chuva"]]
    bars = ax.bar(prev["rot"], prev["clientes_previstos"], color=cores)
    ax.set_ylim(0, prev["clientes_previstos"].max() * 1.15)
    for b, v in zip(bars, prev["clientes_previstos"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 8, str(v), ha="center", fontsize=11)
    ax.set_title("Clientes previstos – próximos 7 dias (cinza: chuva prevista)")
    c1 = fig_b64(fig)
    linhas = "".join(f"<tr><td>{r.dia}</td><td>{'🌧️' if r.chuva else '☀️'}</td><td>{r.clientes_previstos}</td>"
                     f"<td>{r.clientes_hora_pico}</td><td>{r.garcons_sugeridos}</td><td>{r.churrasqueiros_no_atendimento}</td></tr>"
                     for r in prev.itertuples())
    al = D.load_video_outputs()["alertas"]
    sel = pd.concat([al[al.tipo == t].head(2) for t in ["fila_longa", "espera_alta", "mesa_suja"]]).sort_values("timestamp")
    msgs = "".join(f'<div class="msg"><div class="mt">{r.mensagem}</div><div class="mh">{r.timestamp[11:16]}</div></div>'
                   for r in sel.itertuples())
    corpo = f"""<div style="display:grid; grid-template-columns:1fr 360px; gap:22px">
<div><div class="card"><img src="{c1}"></div>
<div class="card" style="margin-top:14px"><table><tr><th>dia</th><th>clima</th><th>clientes</th><th>na hora de pico</th><th>garçons sugeridos</th><th>churrasqueiros no atendimento</th></tr>{linhas}</table></div></div>
<div class="phone"><div class="ph">🤖 Bovinos Insight · Gerência Augusta</div>{msgs}</div></div>
<style>.phone {{ background:#1B2A33; border-radius:34px; padding:18px 14px; border:8px solid #111; height:640px; overflow:hidden; }}
.ph {{ color:#fff; font-weight:700; font-size:14px; padding:6px 6px 14px; border-bottom:1px solid #2E4350; margin-bottom:12px; }}
.msg {{ background:#2B5278; color:#fff; border-radius:12px; padding:10px 12px; margin:0 0 10px 30px; font-size:13.5px; }}
.mh {{ font-size:11px; color:#B8D0E6; text-align:right; margin-top:4px; }}</style>"""
    html = pagina(3, kpis_html(df_all[~df_all["feriado"]]), corpo)
    shot(html, OUT / "05_previsao_e_alertas.png", W, H)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df_all = D.load_comandas()
    df = df_all[~df_all["feriado"]]
    print_jornada(df)
    print_mix(df)
    print_filas(df)
    print_video()
    print_previsao(df_all)
    print("Prints em", OUT)


if __name__ == "__main__":
    main()

"""Dashboard Bovinos Insight.   streamlit run dashboard/app.py"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard import data as D  # noqa: E402
from src.forecast import prever, treinar  # noqa: E402

st.set_page_config(page_title="Bovinos Insight", page_icon="🥩", layout="wide")
VERMELHO, CINZA = "#9B1B1E", "#6B6B6B"
CORES_CAT = ["#9B1B1E", "#C9A227", "#D9822B", "#5B8C3A", "#7A5C8E"]

st.title("🥩 Bovinos Insight – Grill & Beer Augusta")
st.caption("Almoço por quilo · dados de comanda (JS SoftCom + bip de entrada) e visão computacional do salão. "
           "Dados da demo são sintéticos.")

df_all = D.load_comandas()
with st.sidebar:
    st.header("Filtros")
    dmin, dmax = df_all["data"].min(), df_all["data"].max()
    periodo = st.date_input("Período", (dmin, dmax), min_value=dmin, max_value=dmax)
    dias_sel = st.multiselect("Dias da semana", D.DIAS, default=D.DIAS)
    excluir_feriado = st.checkbox("Excluir feriados", value=True)
if isinstance(periodo, tuple) and len(periodo) == 2:
    df = df_all[(df_all["data"] >= periodo[0]) & (df_all["data"] <= periodo[1])]
else:
    df = df_all
df = df[df["dia"].isin(dias_sel)]
if excluir_feriado:
    df = df[~df["feriado"]]
if df.empty:
    st.warning("Sem dados para o filtro.")
    st.stop()

k = D.kpis(df)
c = st.columns(7)
c[0].metric("Clientes/dia", f"{k['clientes_dia']:.0f}")
c[1].metric("Ticket médio", f"R$ {k['ticket_medio']:.2f}")
c[2].metric("Peso médio", f"{k['peso_medio_g']:.0f} g")
c[3].metric("Entrada → balança", f"{k['tempo_buffet_min']:.1f} min")
c[4].metric("Tempo na casa", f"{k['tempo_total_min']:.0f} min")
c[5].metric("% carne no prato", f"{k['pct_carne']:.1f}%")
c[6].metric("CMV estimado", f"{k['cmv_estimado_pct']:.1f}%")

aba = st.tabs(["⏱️ Jornada e fluxo", "🍽️ Mix do prato (CMV)", "🎥 Filas e mesas (câmeras)", "🔮 Previsão"])

# --------------------------------------------------------------- Jornada
with aba[0]:
    f = D.fluxo_por_slot(df)
    l, r = st.columns(2)
    fig = px.bar(f, x="slot15", y="entradas_por_dia", title="Chegadas por 15 min (média/dia)",
                 color_discrete_sequence=[VERMELHO], labels={"slot15": "", "entradas_por_dia": "clientes"})
    fig.add_vrect(x0="12:00", x1="13:30", fillcolor="#C9A227", opacity=0.12, line_width=0,
                  annotation_text="pico", annotation_position="top left")
    l.plotly_chart(fig, use_container_width=True)
    fig = px.line(f, x="slot15", y=["tempo_buffet", "p90_buffet"], markers=True,
                  title="Tempo da entrada até a balança (min)",
                  labels={"slot15": "", "value": "min", "variable": ""},
                  color_discrete_sequence=[VERMELHO, CINZA])
    r.plotly_chart(fig, use_container_width=True)
    st.info("💡 Janelas com desconto de 10% (antes das 12h e depois das 13h30) têm espera bem menor. "
            "O **Termômetro Bovinos** divulga esse tempo para o executivo escolher a hora de sair.")
    dd = D.diario(df)
    fig = px.box(dd, x="dia", y="clientes", color="chuva", category_orders={"dia": D.DIAS},
                 title="Clientes por dia – efeito da chuva", color_discrete_map={True: CINZA, False: VERMELHO})
    st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------------- Mix
with aba[1]:
    l, r = st.columns(2)
    m = D.mix_por(df, "dia")
    fig = px.bar(m, x="dia", y="pct", color="categoria", title="Composição do prato por dia (% do peso)",
                 color_discrete_sequence=CORES_CAT, labels={"pct": "%", "dia": ""})
    l.plotly_chart(fig, use_container_width=True)
    cm = D.cmv_por(df, "hora")
    fig = px.bar(cm, x="hora", y="cmv_pct", title="CMV estimado por hora de chegada (%)",
                 color_discrete_sequence=[VERMELHO], labels={"cmv_pct": "%", "hora": ""}, text_auto=".1f")
    r.plotly_chart(fig, use_container_width=True)
    cd = D.cmv_por(df, "dia").set_index("dia").reindex([d for d in D.DIAS if d in set(df["dia"])]).reset_index()
    fig = px.scatter(cd, x="pct_carne", y="cmv_pct", text="dia", size="receita",
                     title="% de carne no prato × CMV estimado, por dia", color_discrete_sequence=[VERMELHO],
                     labels={"pct_carne": "% de carne no prato", "cmv_pct": "CMV estimado %"})
    fig.update_traces(textposition="top center")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Mix estimado pela câmera sobre a balança (segmentação + peso real da balança). "
               "Custos por kg da demo são hipotéticos.")

# --------------------------------------------------------------- Câmeras
with aba[2]:
    v = D.load_video_outputs()
    if not v:
        st.warning("Rode `python -m src.video_pipeline --video SEU_VIDEO.mp4` ou `python -m src.simulate_salao`.")
    else:
        mf = v.get("metricas_fila", pd.DataFrame())
        des = v.get("desistencias", pd.DataFrame())
        me = v.get("eventos_mesas", pd.DataFrame())
        c = st.columns(4)
        c[0].metric("Desistências na escada", len(des))
        if not mf.empty:
            gr = mf[mf["zona"] == "churrasqueira"]
            if not gr.empty:
                c[1].metric("Espera média no grill (pico)", f"{gr['espera_concluida_media_s'].max()/60:.1f} min",
                            help="Meta da casa: 2,5 min")
        if not me.empty:
            c[2].metric("Tempo médio de mesa suja", f"{me['duracao_s'].mean()/60:.1f} min")
            c[3].metric("Clientes em mesa suja", int((me["tipo"] == "sentou_em_mesa_suja").sum()))
        if not mf.empty:
            mf["timestamp"] = pd.to_datetime(mf["timestamp"])
            l, r = st.columns(2)
            fig = px.line(mf, x="timestamp", y="pessoas", color="zona", title="Pessoas na fila por zona",
                          color_discrete_sequence=CORES_CAT)
            l.plotly_chart(fig, use_container_width=True)
            fig = px.line(mf, x="timestamp", y="espera_concluida_media_s", color="zona",
                          title="Espera média (s, janela de 5 min)", color_discrete_sequence=CORES_CAT)
            fig.add_hline(y=150, line_dash="dash", line_color=VERMELHO, annotation_text="meta grill 2,5 min")
            r.plotly_chart(fig, use_container_width=True)
        if not me.empty:
            fig = px.bar(me.assign(minutos=me["duracao_s"] / 60), x="suja_desde", y="minutos", color="mesa",
                         title="Minutos com mesa suja (por ocorrência)", labels={"suja_desde": ""})
            st.plotly_chart(fig, use_container_width=True)
        if "alertas" in v:
            st.subheader("Alertas enviados ao maître")
            st.dataframe(v["alertas"], use_container_width=True, hide_index=True)

# --------------------------------------------------------------- Previsão
with aba[3]:
    model, frac = treinar(df_all.assign(data=df_all["data"].astype(str), entrada=df_all["entrada"]))
    inicio = df_all["data"].max() + pd.Timedelta(days=1)
    st.write("Marque os dias com previsão de chuva (no produto: API Open-Meteo):")
    dias = [inicio + pd.Timedelta(days=i) for i in range(7)]
    cols = st.columns(7)
    chuva = [int(cols[i].checkbox(f"{D.DIAS[d.weekday()]} {d:%d/%m}", key=f"ch{i}")) for i, d in enumerate(dias)]
    prev = prever(model, frac, inicio, 7, chuva)
    prev["dia"] = [f"{D.DIAS[d.weekday()]} {d:%d/%m}" for d in prev["data"]]
    fig = px.bar(prev, x="dia", y="clientes_previstos", text="clientes_previstos",
                 title="Clientes previstos – próximos 7 dias", color_discrete_sequence=[VERMELHO])
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(prev[["dia", "chuva", "feriado", "clientes_previstos", "clientes_hora_pico",
                       "garcons_sugeridos", "churrasqueiros_no_atendimento"]], hide_index=True,
                 use_container_width=True)
    st.caption("Escala sugerida usa parâmetros ajustáveis em src/forecast.py.")

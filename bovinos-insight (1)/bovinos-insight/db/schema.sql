-- =====================================================================
-- Bovinos Insight – modelo de dados
-- Alvo de produção: PostgreSQL 15+ (TimescaleDB opcional nas tabelas de série temporal)
-- O mesmo modelo roda em SQLite para a demo: python -m src.db
-- =====================================================================

-- ---------- Cadastros ------------------------------------------------
CREATE TABLE IF NOT EXISTS unidade (
    id            SERIAL PRIMARY KEY,
    nome          TEXT NOT NULL,             -- 'Bovinos Grill & Beer – Augusta'
    preco_kg      NUMERIC(8,2) NOT NULL      -- 119.00
);

CREATE TABLE IF NOT EXISTS zona (
    nome          TEXT PRIMARY KEY,          -- 'churrasqueira', 'mesa_S01'
    tipo          TEXT NOT NULL CHECK (tipo IN ('queue','table')),
    papel         TEXT,                      -- 'entrada' | 'buffet'
    praca         TEXT,                      -- 'salao_superior'...
    alerta_pessoas INTEGER,
    alerta_espera_s INTEGER,
    poligono_json TEXT NOT NULL              -- coordenadas normalizadas 0-1
);

CREATE TABLE IF NOT EXISTS custo_categoria (
    categoria     TEXT PRIMARY KEY,          -- carne_grill, arroz_feijao, pratos_quentes, saladas, sobremesas
    custo_kg      NUMERIC(8,2) NOT NULL,
    densidade_rel NUMERIC(4,2) NOT NULL      -- usada pelo Prato Inteligente
);

-- ---------- M5 · Jornada pela comanda (JS SoftCom + bip na porta) -----
CREATE TABLE IF NOT EXISTS visita (
    id            BIGSERIAL PRIMARY KEY,
    data          DATE NOT NULL,
    comanda       INTEGER NOT NULL,          -- 1..9999 (reutilizada!)
    praca         TEXT,
    tema_dia      TEXT,
    chuva         BOOLEAN,
    feriado       BOOLEAN,
    entrada       TIMESTAMP,                 -- bip na porta (novo)
    pesagem       TIMESTAMP,                 -- balança -> JS SoftCom (existe)
    pagamento     TIMESTAMP,                 -- caixa/totem (existe)
    peso_kg       NUMERIC(6,3),
    desconto_pct  NUMERIC(5,2),
    valor_comida  NUMERIC(8,2),
    valor_bebida  NUMERIC(8,2),
    UNIQUE (data, comanda, entrada)          -- comanda é única só dentro da visita
);

-- ---------- M1 · Prato Inteligente ------------------------------------
CREATE TABLE IF NOT EXISTS prato_mix (
    visita_id     BIGINT REFERENCES visita(id),
    categoria     TEXT REFERENCES custo_categoria(categoria),
    gramas        NUMERIC(7,1) NOT NULL,
    PRIMARY KEY (visita_id, categoria)
);

-- ---------- M2 · Fila Zero --------------------------------------------
CREATE TABLE IF NOT EXISTS fila_metrica (          -- hypertable no TimescaleDB
    ts                        TIMESTAMP NOT NULL,
    zona                      TEXT REFERENCES zona(nome),
    pessoas                   INTEGER,
    espera_atual_media_s      NUMERIC(8,2),
    espera_atual_max_s        NUMERIC(8,2),
    espera_concluida_media_s  NUMERIC(8,2),
    espera_concluida_p90_s    NUMERIC(8,2),
    chegadas_por_min          NUMERIC(8,2),
    espera_estimada_little_s  NUMERIC(8,2),
    PRIMARY KEY (ts, zona)
);

CREATE TABLE IF NOT EXISTS permanencia (
    track_id      INTEGER NOT NULL,          -- ID anônimo e temporário do rastreador
    zona          TEXT REFERENCES zona(nome),
    entrada       TIMESTAMP NOT NULL,
    saida         TIMESTAMP NOT NULL,
    permanencia_s NUMERIC(8,1) NOT NULL
);

CREATE TABLE IF NOT EXISTS desistencia (
    track_id      INTEGER NOT NULL,
    chegou        TIMESTAMP NOT NULL,
    foi_embora    TIMESTAMP NOT NULL
);

-- ---------- M3 · Mesa Pronta -------------------------------------------
CREATE TABLE IF NOT EXISTS evento_mesa (
    mesa          TEXT REFERENCES zona(nome),
    praca         TEXT,
    tipo          TEXT CHECK (tipo IN ('mesa_limpa','sentou_em_mesa_suja')),
    suja_desde    TIMESTAMP NOT NULL,
    fim           TIMESTAMP NOT NULL,
    duracao_s     NUMERIC(8,1) NOT NULL
);

-- ---------- Alertas -----------------------------------------------------
CREATE TABLE IF NOT EXISTS alerta (
    ts            TIMESTAMP NOT NULL,
    tipo          TEXT NOT NULL,             -- fila_longa | espera_alta | mesa_suja
    zona          TEXT,
    mensagem      TEXT NOT NULL
);

-- ---------- M4 · Buffet Vivo e M6 · Voz do cliente (roadmap) ----------
CREATE TABLE IF NOT EXISTS reposicao_cuba (
    ts            TIMESTAMP NOT NULL,
    cuba          TEXT NOT NULL,             -- 'arroz_branco', 'lasanha'...
    estacao       TEXT                       -- saladas | quentes | sobremesas
);

CREATE TABLE IF NOT EXISTS nps (
    visita_id     BIGINT REFERENCES visita(id),
    ts            TIMESTAMP NOT NULL,
    nota          SMALLINT CHECK (nota BETWEEN 0 AND 10),
    comentario    TEXT
);

-- ---------- Visões para o dashboard -----------------------------------
CREATE VIEW vw_cmv_dia AS
WITH custo AS (
    SELECT m.visita_id,
           SUM(m.gramas / 1000.0 * c.custo_kg)                              AS custo,
           SUM(CASE WHEN m.categoria = 'carne_grill' THEN m.gramas ELSE 0 END) AS carne_g,
           SUM(m.gramas)                                                    AS total_g
    FROM prato_mix m
    JOIN custo_categoria c ON c.categoria = m.categoria
    GROUP BY m.visita_id
)
SELECT v.data,
       COUNT(*)                                   AS clientes,
       ROUND(SUM(custo.custo), 2)                 AS custo_estimado,
       ROUND(SUM(v.valor_comida), 2)              AS receita_comida,
       ROUND(SUM(custo.custo) * 100.0 / SUM(v.valor_comida), 2) AS cmv_pct,
       ROUND(SUM(custo.carne_g) * 100.0 / SUM(custo.total_g), 2) AS pct_carne
FROM visita v
JOIN custo ON custo.visita_id = v.id
GROUP BY v.data;

CREATE VIEW vw_desistencias_dia AS
SELECT DATE(chegou) AS data, COUNT(*) AS desistencias
FROM desistencia
GROUP BY DATE(chegou);

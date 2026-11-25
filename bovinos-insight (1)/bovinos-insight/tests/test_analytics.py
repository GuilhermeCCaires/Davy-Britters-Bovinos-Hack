"""Testes da lógica de fila, desistência e mesas (rodar: python -m pytest -q)."""
from src.alerts import AlertEngine
from src.geometry import point_in_polygon
from src.queue_analytics import QueueAnalytics
from src.table_monitor import TableMonitor

SQ = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # noqa: E731

ZONES = [
    {"name": "escada", "type": "queue", "role": "entrada", "poly_px": SQ(0, 0, 10, 10), "alert_count": 3},
    {"name": "buffet", "type": "queue", "role": "buffet", "poly_px": SQ(20, 0, 30, 10)},
    {"name": "grill", "type": "queue", "role": "buffet", "poly_px": SQ(40, 0, 50, 10), "alert_wait_s": 60},
    {"name": "mesa1", "type": "table", "praca": "superior", "poly_px": SQ(0, 20, 10, 30)},
]


def test_point_in_polygon():
    assert point_in_polygon(5, 5, SQ(0, 0, 10, 10))
    assert not point_in_polygon(15, 5, SQ(0, 0, 10, 10))


def test_permanencia_e_desistencia():
    qa = QueueAnalytics(ZONES, grace_s=2, lost_timeout_s=5, min_entry_dwell_s=3)
    for t in range(0, 100):
        dets = []
        if t < 10:
            dets.append((1, 5, 5))          # pessoa 1: escada 0-9s
        elif t < 15:
            dets.append((1, 15, 5))         # corredor
        elif t < 75:
            dets.append((1, 45, 5))         # grill 15-74s
        if 20 <= t < 30:
            dets.append((2, 5, 5))          # pessoa 2: espia 10s e vai embora
        if 40 <= t < 41:
            dets.append((3, 5, 5))          # pessoa 3: só passou pela porta (1s)
        qa.update(float(t), dets)
    qa.flush(100.0)
    grill = [e for e in qa.events if e.zone == "grill"]
    assert len(grill) == 1 and abs(grill[0].dwell_s - 59) < 1e-6
    assert [b.track_id for b in qa.balks] == [2]


def test_troca_de_id_no_salao_nao_conta_desistencia():
    qa = QueueAnalytics(ZONES, grace_s=2, lost_timeout_s=5)
    for t in range(0, 40):
        dets = []
        if t < 10:
            dets.append((1, 5, 5))
        elif t < 15:
            dets.append((1, 15, 5))         # ID 1 some no corredor (troca de ID)
        elif t < 30:
            dets.append((9, 25, 5))         # volta como ID 9 no buffet
        qa.update(float(t), dets)
    qa.flush(40.0)
    assert qa.balks == []


def test_alerta_fila_e_cooldown():
    qa = QueueAnalytics(ZONES)
    al = AlertEngine(ZONES, cooldown_s=120)
    fired = []
    for t in range(0, 30):
        qa.update(float(t), [(i, 2 + i, 5) for i in range(4)])
        fired += al.evaluate(float(t), qa.snapshot(float(t)))
    assert len([a for a in fired if a.tipo == "fila_longa"]) == 1


def test_mesa_suja_e_limpa():
    tm = TableMonitor(ZONES, occupy_hold_s=5, empty_hold_s=3, clean_hold_s=2)
    for t in range(0, 100):
        persons = [(5, 25)] if 0 <= t < 40 else []
        items = [(6, 26)] if 0 <= t < 70 else []
        tm.update(float(t), persons, items)
    ev = tm.events
    assert len(ev) == 1 and ev[0].tipo == "mesa_limpa"
    assert 28 <= ev[0].duracao_s <= 35       # saiu ~40s, limpou ~70s
    assert tm.state["mesa1"] == "livre"

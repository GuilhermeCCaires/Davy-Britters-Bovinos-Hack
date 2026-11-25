"""Processa um vídeo (ou stream RTSP da câmera Intelbras) e gera métricas de fila,
desistência e mesas, além de um vídeo anotado para o pitch.

Exemplos
--------
    python -m src.video_pipeline --video data/salao.mp4 --zones config/zones.json
    python -m src.video_pipeline --video "rtsp://user:senha@IP:554/cam/realmonitor?channel=1&subtype=0" --show

Saídas em outputs/: video_anotado.mp4, metricas_fila.csv, permanencias.csv,
desistencias.csv, eventos_mesas.csv, alertas.csv
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path

import unicodedata

import cv2
import numpy as np

from .alerts import AlertEngine, send_telegram
from .config import load_zones
from .geometry import center_point, foot_point
from .queue_analytics import QueueAnalytics
from .table_monitor import TableMonitor

PERSON = 0
# Classes COCO que indicam louça/restos sobre a mesa
ITEM_CLASSES = {39: "garrafa", 40: "taca", 41: "copo", 42: "garfo", 43: "faca", 44: "colher", 45: "tigela"}

COLORS = {"entrada": (0, 0, 255), "buffet": (0, 200, 255), "table": (255, 160, 0)}


def _ascii(text: str) -> str:
    """As fontes do OpenCV não têm acentos: 'início' vira 'inicio'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def draw_overlay(frame, zones, snap, table_states, balks, clock: str):
    for z in zones:
        pts = np.array(z["poly_px"], dtype=np.int32)
        if z.get("type") == "table":
            st = table_states.get(z["name"], "livre")
            color = {"livre": (0, 180, 0), "ocupada": (255, 160, 0), "suja": (0, 0, 255)}[st]
            label = f"{z['name']}: {st}"
        else:
            color = COLORS.get(z.get("role", ""), (200, 200, 200))
            m = snap.get(z["name"], {})
            label = (f"{z.get('label', z['name'])}: {int(m.get('pessoas', 0))} pess. | "
                     f"espera {m.get('espera_atual_media_s', 0)/60:.1f} min")
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], color)
        cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
        cv2.polylines(frame, [pts], True, color, 2)
        x, y = pts[0]
        label = _ascii(label)
        cv2.putText(frame, label, (int(x) + 4, int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        cv2.putText(frame, label, (int(x) + 4, int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    banner = _ascii(f"Bovinos Insight | {clock} | desistências: {balks}")
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 28), (20, 20, 20), -1)
    cv2.putText(frame, banner, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)


def run(args) -> None:
    from ultralytics import YOLO  # import tardio: o resto do projeto roda sem GPU/torch

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"Não consegui abrir {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    zones = load_zones(args.zones, w, h)
    qa = QueueAnalytics(zones)
    tm = TableMonitor(zones)
    alerts = AlertEngine(zones, table_dirty_alert_s=args.dirty_alert_s)
    start = datetime.fromisoformat(args.start)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    writer = None
    if not args.no_video:
        writer = cv2.VideoWriter(str(out_dir / "video_anotado.mp4"),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps / args.stride, (w, h))

    model = YOLO(args.model)
    classes = [PERSON] + list(ITEM_CLASSES)
    metric_rows: list[dict] = []
    next_sample = 0.0
    t = 0.0

    results = model.track(source=args.video, stream=True, persist=True, tracker=args.tracker,
                          classes=classes, conf=args.conf, vid_stride=args.stride, verbose=False)
    for i, r in enumerate(results):
        t = i * args.stride / fps
        persons_track, persons_pts, items_pts = [], [], []
        b = r.boxes
        if b is not None and len(b):
            xyxy = b.xyxy.cpu().numpy()
            cls = b.cls.cpu().numpy().astype(int)
            ids = b.id.cpu().numpy().astype(int) if b.id is not None else [None] * len(cls)
            for (x1, y1, x2, y2), c, tid in zip(xyxy, cls, ids):
                if c == PERSON:
                    fx, fy = foot_point(x1, y1, x2, y2)
                    persons_pts.append(center_point(x1, y1, x2, y2))
                    if tid is not None:
                        persons_track.append((int(tid), fx, fy))
                else:
                    items_pts.append(center_point(x1, y1, x2, y2))

        qa.update(t, persons_track)
        tm.update(t, persons_pts, items_pts)
        snap = qa.snapshot(t)
        for a in alerts.evaluate(t, snap, tm.dirty_now(t)):
            msg = f"[{(start + timedelta(seconds=a.t)):%H:%M:%S}] {a.mensagem}"
            print(msg)
            if args.telegram:
                send_telegram(msg)

        if t >= next_sample:
            ts = start + timedelta(seconds=t)
            for zname, m in snap.items():
                if zname.startswith("_"):
                    continue
                metric_rows.append({"timestamp": ts.isoformat(timespec="seconds"), "zona": zname,
                                    **{k: round(v, 2) for k, v in m.items()}})
            next_sample += args.sample_s

        if writer is not None or args.show:
            frame = r.plot(labels=False, conf=False) if args.boxes else r.orig_img.copy()
            draw_overlay(frame, zones, snap, tm.state, len(qa.balks),
                         (start + timedelta(seconds=t)).strftime("%H:%M:%S"))
            if writer is not None:
                writer.write(frame)
            if args.show:
                cv2.imshow("Bovinos Insight", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    qa.flush(t)
    if writer is not None:
        writer.release()
    if args.show:
        cv2.destroyAllWindows()

    def ts(sec: float) -> str:
        return (start + timedelta(seconds=sec)).isoformat(timespec="seconds")

    _write_csv(out_dir / "metricas_fila.csv", metric_rows)
    _write_csv(out_dir / "permanencias.csv", [
        {"track_id": e.track_id, "zona": e.zone, "entrada": ts(e.t_in), "saida": ts(e.t_out),
         "permanencia_s": round(e.dwell_s, 1)} for e in qa.events])
    _write_csv(out_dir / "desistencias.csv", [
        {"track_id": b.track_id, "chegou": ts(b.t_first_seen), "foi_embora": ts(b.t_last_seen)} for b in qa.balks])
    _write_csv(out_dir / "eventos_mesas.csv", [
        {"mesa": e.mesa, "praca": e.praca, "tipo": e.tipo, "suja_desde": ts(e.t_inicio),
         "fim": ts(e.t_fim), "duracao_s": round(e.duracao_s, 1)} for e in tm.events])
    _write_csv(out_dir / "alertas.csv", [
        {"timestamp": ts(a.t), "tipo": a.tipo, "zona": a.zona, "mensagem": a.mensagem} for a in alerts.history])
    print(f"Pronto. {len(qa.events)} permanências, {len(qa.balks)} desistências, "
          f"{len(tm.events)} eventos de mesa, {len(alerts.history)} alertas -> {out_dir}/")


def _write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("")
            return
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Bovinos Insight – análise de vídeo do salão")
    p.add_argument("--video", required=True, help="arquivo de vídeo ou URL RTSP")
    p.add_argument("--zones", default="config/zones.json")
    p.add_argument("--model", default="yolov8n.pt", help="yolov8n.pt (leve) ou yolov8s.pt (mais preciso)")
    p.add_argument("--tracker", default="bytetrack.yaml")
    p.add_argument("--conf", type=float, default=0.3)
    p.add_argument("--stride", type=int, default=2, help="processa 1 a cada N quadros")
    p.add_argument("--start", default="2026-11-24T12:00:00", help="horário real do início do vídeo")
    p.add_argument("--sample-s", type=float, default=5.0, help="intervalo de gravação das métricas")
    p.add_argument("--dirty-alert-s", type=float, default=180.0)
    p.add_argument("--out", default="outputs")
    p.add_argument("--show", action="store_true")
    p.add_argument("--boxes", action="store_true", help="desenha as caixas do YOLO")
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--telegram", action="store_true")
    run(p.parse_args())


if __name__ == "__main__":
    main()

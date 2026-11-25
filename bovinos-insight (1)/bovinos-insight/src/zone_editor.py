"""Desenhe as zonas clicando sobre um quadro do vídeo.

    python -m src.zone_editor --video data/salao.mp4 --out config/zones.json

Clique esquerdo: adiciona ponto | ENTER: fecha o polígono (pede nome/tipo no terminal)
U: desfaz ponto | S: salva | Q: sai
Tipos: queue (fila) ou table (mesa). Papéis de fila: entrada | buffet
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--frame", type=int, default=0)
    p.add_argument("--out", default="config/zones.json")
    a = p.parse_args()

    cap = cv2.VideoCapture(a.video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, a.frame)
    ok, base = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("Não consegui ler o quadro.")
    h, w = base.shape[:2]
    zones: list[dict] = []
    current: list[tuple[int, int]] = []

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            current.append((x, y))

    cv2.namedWindow("zonas")
    cv2.setMouseCallback("zonas", on_mouse)
    while True:
        img = base.copy()
        for z in zones:
            pts = np.array([(int(px * w), int(py * h)) for px, py in z["polygon"]], np.int32)
            cv2.polylines(img, [pts], True, (0, 255, 0), 2)
            cv2.putText(img, z["name"], tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        if current:
            cv2.polylines(img, [np.array(current, np.int32)], False, (0, 0, 255), 2)
        cv2.imshow("zonas", img)
        k = cv2.waitKey(30) & 0xFF
        if k == 13 and len(current) >= 3:
            name = input("Nome da zona: ").strip()
            ztype = input("Tipo [queue/table]: ").strip() or "queue"
            z = {"name": name, "type": ztype,
                 "polygon": [[round(x / w, 4), round(y / h, 4)] for x, y in current]}
            if ztype == "queue":
                z["role"] = input("Papel [entrada/buffet/outro]: ").strip() or name
                z["label"] = input("Rótulo para exibição: ").strip() or name
                lim = input("Alerta: nº de pessoas (enter = sem): ").strip()
                if lim:
                    z["alert_count"] = int(lim)
                lim = input("Alerta: espera média em segundos (enter = sem): ").strip()
                if lim:
                    z["alert_wait_s"] = int(lim)
            else:
                z["praca"] = input("Praça: ").strip()
            zones.append(z)
            current.clear()
        elif k == ord("u") and current:
            current.pop()
        elif k == ord("s"):
            Path(a.out).write_text(json.dumps({"zones": zones}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Salvo em {a.out}")
        elif k == ord("q"):
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

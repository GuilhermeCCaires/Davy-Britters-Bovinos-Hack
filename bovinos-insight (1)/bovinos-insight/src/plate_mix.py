"""Prato Inteligente – estima a composição do prato pela foto da balança.

Protótipo zero-shot (sem treino): YOLO-World encontra os alimentos pelo nome,
MobileSAM recorta a área de cada um e o peso real da balança é distribuído
entre as categorias (área × densidade relativa). Para produção: treinar um
modelo de segmentação com fotos rotuladas dos pratos da casa.

    python -m src.plate_mix --img data/pratos/prato1.jpg --peso 0.62 --tema "Comida árabe"
    python -m src.plate_mix --pasta data/pratos --pesos data/pratos/pesos.csv

Saída: JSON com gramas e % por categoria + imagem anotada em outputs/pratos/.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

# Prompts em inglês (YOLO-World foi treinado em inglês) -> categoria de custo
PROMPTS = {
    "carne_grill": ["grilled meat", "steak", "sausage", "grilled chicken", "barbecue meat"],
    "arroz_feijao": ["white rice", "black beans", "beans"],
    "pratos_quentes": ["lasagna", "pasta", "stew", "fried potatoes", "farofa", "fried food"],
    "saladas": ["salad", "lettuce", "tomato", "vegetables", "cucumber"],
    "sobremesas": ["cake", "pudding", "dessert", "fruit"],
}
# Pratos do dia (cardápio rotativo) reforçam os prompts e reduzem confusões
TEMA_EXTRA = {
    "Comida árabe": {"pratos_quentes": ["kibbeh", "esfiha", "tabbouleh", "hummus"]},
    "Feijoada": {"arroz_feijao": ["feijoada", "black bean stew"], "pratos_quentes": ["collard greens"]},
    "Italiano": {"pratos_quentes": ["risotto", "spaghetti", "gnocchi"]},
    "Frutos do mar": {"pratos_quentes": ["paella", "codfish", "shrimp"]},
    "Virado à paulista": {"pratos_quentes": ["pork chop", "fried egg", "fried banana"]},
}
# Densidade relativa (g por unidade de área visível) – calibrar com pratos pesados um a um
DENSIDADE = {"carne_grill": 1.6, "arroz_feijao": 1.3, "pratos_quentes": 1.2, "saladas": 0.5, "sobremesas": 1.0}
CORES = {"carne_grill": (30, 27, 155), "arroz_feijao": (39, 162, 201), "pratos_quentes": (43, 130, 217),
         "saladas": (58, 140, 91), "sobremesas": (142, 92, 122)}


class PlateMix:
    def __init__(self, det_model: str = "yolov8s-worldv2.pt", sam_model: str = "mobile_sam.pt", conf: float = 0.12):
        from ultralytics import SAM, YOLOWorld
        self.det = YOLOWorld(det_model)
        self.sam = SAM(sam_model)
        self.conf = conf

    def _prompts(self, tema: str | None):
        lista, alvo = [], []
        for cat, ps in PROMPTS.items():
            extra = TEMA_EXTRA.get(tema or "", {}).get(cat, [])
            for p in ps + extra:
                lista.append(p)
                alvo.append(cat)
        return lista, alvo

    def analisar(self, img_bgr: np.ndarray, peso_kg: float, tema: str | None = None) -> dict:
        prompts, alvo = self._prompts(tema)
        self.det.set_classes(prompts)
        r = self.det.predict(img_bgr, conf=self.conf, verbose=False)[0]
        h, w = img_bgr.shape[:2]
        if r.boxes is None or len(r.boxes) == 0:
            return {"peso_g": peso_kg * 1000, "categorias": {}, "aviso": "nenhum alimento detectado"}
        boxes = r.boxes.xyxy.cpu().numpy()
        cls = r.boxes.cls.cpu().numpy().astype(int)
        conf = r.boxes.conf.cpu().numpy()
        sr = self.sam(img_bgr, bboxes=boxes.tolist(), verbose=False)[0]
        masks = sr.masks.data.cpu().numpy().astype(bool) if sr.masks is not None else np.zeros((0, h, w), bool)

        # cada pixel fica com a detecção de maior confiança que o cobre
        label = np.full((h, w), -1, np.int32)
        best = np.zeros((h, w), np.float32)
        for i, m in enumerate(masks):
            m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
            upd = m & (conf[i] > best)
            label[upd] = i
            best[upd] = conf[i]

        area = {c: 0 for c in PROMPTS}
        for i in range(len(masks)):
            area[alvo[cls[i]]] += int((label == i).sum())
        massa = {c: area[c] * DENSIDADE[c] for c in area}
        total = sum(massa.values()) or 1
        cats = {c: {"pct": round(massa[c] / total * 100, 1), "g": round(massa[c] / total * peso_kg * 1000)}
                for c in massa if massa[c] > 0}

        anot = img_bgr.copy()
        for i in range(len(masks)):
            sel = label == i
            anot[sel] = (0.55 * anot[sel] + 0.45 * np.array(CORES[alvo[cls[i]]])).astype(np.uint8)
        y = 24
        for c, v in sorted(cats.items(), key=lambda kv: -kv[1]["g"]):
            cv2.putText(anot, f"{c}: {v['g']} g ({v['pct']}%)", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
            cv2.putText(anot, f"{c}: {v['g']} g ({v['pct']}%)", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, CORES[c], 2)
            y += 24
        return {"peso_g": round(peso_kg * 1000), "categorias": cats, "_anotada": anot}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--img")
    p.add_argument("--peso", type=float, help="peso da balança em kg")
    p.add_argument("--pasta", help="pasta com fotos; use --pesos com colunas arquivo,peso_kg")
    p.add_argument("--pesos")
    p.add_argument("--tema", default=None, help="tema do dia, ex.: 'Comida árabe'")
    p.add_argument("--out", default="outputs/pratos")
    a = p.parse_args()

    itens: list[tuple[Path, float]] = []
    if a.img:
        itens.append((Path(a.img), a.peso or 0.5))
    if a.pasta and a.pesos:
        with open(a.pesos, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                itens.append((Path(a.pasta) / row["arquivo"], float(row["peso_kg"])))
    if not itens:
        raise SystemExit("Informe --img/--peso ou --pasta/--pesos")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pm = PlateMix()
    resultados = []
    for path, peso in itens:
        img = cv2.imread(str(path))
        res = pm.analisar(img, peso, a.tema)
        anot = res.pop("_anotada", None)
        if anot is not None:
            cv2.imwrite(str(out / f"{path.stem}_mix.jpg"), anot)
        res["arquivo"] = path.name
        resultados.append(res)
        print(json.dumps(res, ensure_ascii=False))
    (out / "mix.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

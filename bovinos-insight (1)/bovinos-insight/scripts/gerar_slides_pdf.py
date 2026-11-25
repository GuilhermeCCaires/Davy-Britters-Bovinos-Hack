"""Renderiza os 5 slides (docs/slides/) em PDF e PNG: docs/apresentacao_5_slides.pdf.

    python scripts/gerar_slides_pdf.py

Os slides são os mesmos do deck online; aqui as fontes são trocadas pelas
instaladas localmente (Anton/Inter) e as imagens apontam para docs/prints/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from telas import img_b64, pdf, shot  # noqa: E402

SL = ROOT / "docs" / "slides"
ORDEM = ["capa", "passos", "estrutura", "integracao", "final"]
IMAGENS = {  # asset do deck online -> arquivo local
    "63eaa5054ad47224b7396807e5f46f22": "04_video_analise_salao.png",
    "f16374fe2d31a65ad7f827ae326f4859": "01_dashboard_jornada.png",
    "c322278971d57b0d74f67eff5eb757fb": "02_dashboard_mix_cmv.png",
    "bd75e8166de72ab2e536a8d20f4c68fb": "03_dashboard_filas_mesas.png",
    "4b426cbf3b868b2b54f49d531ffec23f": "../slides/img/yolo_exemplo_1.png",
    "9ec1fe1a025a5fa091bda3dff895eaab": "../slides/img/ocupacao_mesas_exemplo.png",
}


def montar(ids: list[str]) -> str:
    css = (SL / "deck.css").read_text(encoding="utf-8")
    css = css.replace("'Oswald'", "'Anton'").replace("'Public Sans'", "'Inter'")
    secoes = []
    for sid in ids:
        h = (SL / "slides" / f"{sid}.html").read_text(encoding="utf-8")
        h = re.sub(r"<aside>.*?</aside>", "", h, flags=re.S)
        h = re.sub(r'<x-shape kind="arrow-right"[^>]*></x-shape>',
                   '<span style="font-size:56px; color:#E0B84A; font-weight:700">→</span>', h)
        for blob, arq in IMAGENS.items():
            h = h.replace(f"/_blob/{blob}", img_b64(ROOT / "docs" / "prints" / arq))
        secoes.append(h)
    return f"""<html><head><meta charset="utf-8"><style>
@page {{ size:1920px 1080px; margin:0; }}
html, body {{ margin:0; padding:0; }}
section {{ width:1920px; height:1080px; box-sizing:border-box; overflow:hidden; page-break-after:always; }}
h2 {{ font-weight:400; }} h1 {{ font-weight:400; }}
{css}
.card, .zone, .phase, .box, .bar, .step, .key, .shot {{ animation:none !important; }}
</style></head><body>{''.join(secoes)}</body></html>"""


def main():
    out = ROOT / "docs" / "apresentacao_5_slides.pdf"
    pdf(montar(ORDEM), out, 1920, 1080)
    for i, sid in enumerate(ORDEM, 1):
        shot(montar([sid]), ROOT / "docs" / "slides" / "png" / f"{i:02d}_{sid}.png", 1920, 1080)
    print("PDF:", out)


if __name__ == "__main__":
    main()

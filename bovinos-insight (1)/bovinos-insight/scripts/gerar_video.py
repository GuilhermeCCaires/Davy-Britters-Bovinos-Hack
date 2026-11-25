"""Gera o vídeo de demonstração (até 2 min) em docs/video/bovinos_insight_demo.mp4.

    python scripts/gerar_video.py

Roteiro: abertura -> problema -> solução -> demo do motor de filas/mesas
(cena simulada processada pelo código real) -> dashboard -> previsão -> fechamento.
O vídeo é mudo e legendado; o roteiro de narração está em docs/ROTEIRO_VIDEO.md
para quem quiser gravar a voz por cima.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cena_salao import gerar_frames  # noqa: E402
from telas import CSS_BASE, ESCURO, img_b64, shot  # noqa: E402

FPS = 25
W, H = 1280, 720
PRINTS = ROOT / "docs" / "prints"
OUT = ROOT / "docs" / "video" / "bovinos_insight_demo.mp4"


def _fonte(peso="Regular", tam=26):
    for p in (f"/usr/share/fonts/opentype/inter/Inter-{peso}.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, tam)
    return ImageFont.load_default()


def card_html(eyebrow: str, titulo: str, corpo: str, fundo: str = ESCURO) -> str:
    return f"""<html><head><meta charset="utf-8"><style>{CSS_BASE}
body {{ width:{W}px; height:{H}px; background:{fundo}; color:#FAF6F0; padding:70px 84px; display:flex; flex-direction:column; }}
.e {{ color:#E0B84A; font-weight:700; letter-spacing:.14em; font-size:18px; text-transform:uppercase; margin:0 0 14px; }}
h1 {{ font-size:76px; line-height:1.02; margin:0 0 26px; text-transform:uppercase; }}
h2 {{ font-size:50px; line-height:1.05; margin:0 0 30px; }}
p {{ color:#E8DCCB; font-size:24px; line-height:1.45; margin:0; }}
.g {{ display:grid; gap:18px; }} .c {{ background:#2B1F1D; border:2px solid #4A3A36; border-radius:14px; padding:18px 20px; }}
.c b {{ color:#E0B84A; display:block; font-size:16px; letter-spacing:.06em; text-transform:uppercase; margin-bottom:6px; }}
.c p {{ font-size:19px; }} .n {{ font-family:'Anton',sans-serif; font-size:46px; color:#E0B84A; }}
.gold {{ color:#E0B84A; }} .sp {{ flex:1; }}
</style></head><body><p class="e">{eyebrow}</p>{titulo}{corpo}</body></html>"""


CARDS = {
    "abertura": card_html("Hackathon FMU TECH × Grupo Bovinos",
                          "<h1>Bovinos<br><span class='gold'>Insight</span></h1>",
                          "<div class='sp'></div><p style='font-size:28px'>Transformando o salão do quilo em dados, sem perder o toque humano.</p>"
                          "<p style='margin-top:10px; color:#B8A898'>Bovinos Grill &amp; Beer · Rua Augusta · demonstração do MVP</p>"),
    "problema": card_html("O problema", "<h2>Hoje, a única métrica usada é o ticket médio</h2>",
                          "<div class='g' style='grid-template-columns:repeat(4,1fr)'>"
                          "<div class='c'><b>Dor 1 · mix do prato</b><p>Sabe-se o peso, não o que foi servido. Impacta o CMV.</p></div>"
                          "<div class='c'><b>Dor 2 · filas</b><p>Grill chega a 4 min (meta 2,5). Fila na escada = cliente perdido.</p></div>"
                          "<div class='c'><b>Dor 3 · mesas</b><p>Mesa suja cobrada no olhômetro.</p></div>"
                          "<div class='c'><b>Dor 4 · comida</b><p>O que sobra no prato se perde no boca a boca.</p></div></div>"
                          "<div class='sp'></div><div class='g' style='grid-template-columns:repeat(3,1fr)'>"
                          "<div><div class='n'>600</div><p>clientes por dia útil</p></div>"
                          "<div><div class='n'>12h10–13h20</div><p>pico concentrado</p></div>"
                          "<div><div class='n'>30–40 min</div><p>para o executivo almoçar</p></div></div>"),
    "solucao": card_html("A solução", "<h2>Seis módulos sobre o hardware que a casa já tem</h2>",
                         "<div class='g' style='grid-template-columns:repeat(3,1fr)'>"
                         "<div class='c'><b>M1 · Prato Inteligente</b><p>Câmera na balança + IA: gramas de carne, arroz, salada… e o CMV de cada prato.</p></div>"
                         "<div class='c'><b>M2 · Fila Zero</b><p>Câmeras atuais medem fila, espera e desistência na escada. Alerta ao maître.</p></div>"
                         "<div class='c'><b>M3 · Mesa Pronta</b><p>Mesa livre, ocupada ou suja, com tempo medido por praça.</p></div>"
                         "<div class='c'><b>M4 · Buffet Vivo</b><p>Reposição de cubas e resto no prato.</p></div>"
                         "<div class='c'><b>M5 · Jornada</b><p>Bip da comanda na porta: entrada → balança → pagamento.</p></div>"
                         "<div class='c'><b>M6 · Voz + previsão</b><p>NPS no QR da comanda e previsão de clientes e escala.</p></div></div>"
                         "<div class='sp'></div><p>Processamento na loja (LGPD): só números saem. Sem catraca, sem mudar o quilo.</p>"),
    "fechamento": card_html("Bovinos Insight", "<h1>Do olhômetro<br><span class='gold'>à métrica</span></h1>",
                            "<div class='sp'></div><p>Respeita o escopo (sem cozinha, estoque ou pagamentos) · mantém o quilo e o acolhimento na porta · usa câmeras, balanças e comanda que já existem.</p>"
                            "<p style='margin-top:14px; color:#B8A898'>Código, banco de dados, testes e documentação no repositório do projeto.</p>"),
}

REFS = ROOT / "docs" / "slides" / "img"


def card_camera(img: Path, passo: str, titulo: str, texto: str) -> str:
    return card_html(f"Como a câmera enxerga · {passo}", f"<h2 style='font-size:40px; margin:0 0 18px'>{titulo}</h2>",
                     f"<img src='{img_b64(img)}' style='width:100%; height:440px; object-fit:contain; background:#140E0E; border-radius:12px'>"
                     f"<p style='margin-top:16px; font-size:21px'>{texto}</p>")


LEGENDAS_SIM = [
    (0.00, "Demo · pico do almoço simulado (11h50–12h35), acelerado ~70×"),
    (0.12, "Cada ponto é uma pessoa rastreada, com ID anônimo e temporário"),
    (0.30, "As zonas medem pessoas na fila e minutos de espera"),
    (0.48, "Quem entra na escada e volta para a rua conta como desistência"),
    (0.66, "Passou do limite? Alerta no celular do maître"),
    (0.82, "Mesas: livre → ocupada → suja → limpa, com o tempo medido"),
]


def legenda(frame_bgr: np.ndarray, texto: str, x=40, y=48) -> np.ndarray:
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img, "RGBA")
    f = _fonte("SemiBold", 24)
    bbox = d.textbbox((0, 0), texto, font=f)
    d.rounded_rectangle((x - 14, y - 10, x + bbox[2] + 14, y + bbox[3] + 12), 10, fill=(30, 20, 20, 225))
    d.text((x, y), texto, font=f, fill=(250, 246, 240))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def print_em_quadro(path: Path, texto: str) -> np.ndarray:
    im = cv2.imread(str(path))
    h, w = im.shape[:2]
    esc = min((W - 40) / w, (H - 96) / h)
    im = cv2.resize(im, (int(w * esc), int(h * esc)), interpolation=cv2.INTER_AREA)
    tela = np.full((H, W, 3), (20, 20, 30), np.uint8)
    tela[:] = (20, 20, 30)
    y0 = 84
    x0 = (W - im.shape[1]) // 2
    tela[y0:y0 + im.shape[0], x0:x0 + im.shape[1]] = im
    return legenda(tela, texto, x=34, y=26)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    cards = {}
    CARDS["camera1"] = card_camera(REFS / "yolo_exemplo_1.png", "1/2", "O YOLO encontra pessoas e objetos em cada quadro",
                                   "Cada caixa é uma detecção com o nome do objeto. No salão, usamos as classes pessoa, copo, tigela e talheres. Imagem de referência.")
    CARDS["camera2"] = card_camera(REFS / "ocupacao_mesas_exemplo.png", "2/2", "Zonas desenhadas sobre a imagem viram estado e tempo",
                                   "Cada mesa (ou fila) é um polígono: livre em verde, ocupada em vermelho, com o tempo contado. É o que o Mesa Pronta e o Fila Zero fazem. Imagem de referência.")
    for nome, html in CARDS.items():
        shot(html, tmp / f"{nome}.png", W, H)
        cards[nome] = cv2.imread(str(tmp / f"{nome}.png"))

    raw = tmp / "raw.mp4"
    vw = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    ultimo = [None]

    def escrever(frame, n=1):
        for _ in range(n):
            vw.write(frame)
        ultimo[0] = frame

    def transicao(prox, seg=0.5):
        if ultimo[0] is None:
            return
        n = int(seg * FPS)
        for i in range(n):
            a = (i + 1) / n
            vw.write(cv2.addWeighted(ultimo[0], 1 - a, prox, a, 0))

    def still(frame, seg):
        transicao(frame)
        escrever(frame, int(seg * FPS))

    still(cards["abertura"], 6)
    still(cards["problema"], 9)
    still(cards["solucao"], 10)
    still(cards["camera1"], 5.5)
    still(cards["camera2"], 5.5)

    n_sim = 40 * FPS
    primeiro = True
    for i, (frame, t, *_r) in enumerate(gerar_frames(n_frames=n_sim)):
        frac = i / n_sim
        txt = [s for f, s in LEGENDAS_SIM if frac >= f][-1]
        fr = legenda(frame, txt, x=40, y=52)
        if primeiro:
            transicao(fr)
            primeiro = False
        escrever(fr)

    still(print_em_quadro(PRINTS / "01_dashboard_jornada.png",
                          "Dashboard · jornada: no pico, chegar à balança leva quase o dobro do tempo"), 7)
    still(print_em_quadro(PRINTS / "02_dashboard_mix_cmv.png",
                          "Dashboard · mix do prato: % de carne e CMV estimado por dia e horário"), 7)
    still(print_em_quadro(PRINTS / "03_dashboard_filas_mesas.png",
                          "Dashboard · filas e mesas: desistências, espera × meta e alertas"), 7)
    still(print_em_quadro(PRINTS / "05_previsao_e_alertas.png",
                          "Previsão de clientes com chuva e feriado + alertas no celular da gerência"), 7)
    still(cards["fechamento"], 6)
    vw.release()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)], check=True)
    else:
        shutil.copy(raw, OUT)
    print("Vídeo:", OUT)


if __name__ == "__main__":
    main()

# Vídeo da solução (≤ 2 min)

**Arquivo:** [`docs/video/bovinos_insight_demo.mp4`](video/bovinos_insight_demo.mp4) · 1 min 55 s · 1280×720 · legendado, sem áudio.
Gerado por `python scripts/gerar_video.py`.

## Como publicar o link
1. Faça upload do MP4 no YouTube como **"Não listado"** (ou no Google Drive com "qualquer pessoa com o link").
2. Copie o link e cole no README, na seção **Vídeo**.
3. Opcional: grave a narração abaixo por cima (YouTube Studio, CapCut ou Clipchamp) para deixar o vídeo mais forte.

## Roteiro e narração sugerida

| Tempo | Tela | Narração sugerida |
|---|---|---|
| 0:00–0:06 | Abertura | "Bovinos Insight: transformamos o salão do quilo em dados, sem perder o toque humano." |
| 0:06–0:16 | O problema | "A Bovinos da Augusta atende 600 executivos por dia num pico de 70 minutos e só mede o ticket médio. Ninguém sabe o que vai no prato, quanto dura a fila nem quantos desistem na escada." |
| 0:16–0:26 | A solução | "Seis módulos sobre o que a casa já tem: câmeras, balanças, comanda e o celular dos garçons. Tudo processado dentro da loja." |
| 0:26–0:32 | Como a câmera enxerga 1/2 | "Primeiro, o YOLO encontra pessoas e objetos em cada quadro e marca cada um com uma caixa." |
| 0:32–0:38 | Como a câmera enxerga 2/2 | "Depois, desenhamos zonas sobre a imagem: cada mesa ou fila vira um estado, livre ou ocupada, com o tempo contado." |
| 0:38–1:19 | Demo do salão | "Aqui, o nosso motor num pico simulado. Cada ponto é uma pessoa com ID anônimo. As zonas medem fila e espera; quem volta da escada conta como desistência; passou do limite, o maître recebe um alerta; e as mesas mudam de livre para ocupada e para suja, com o tempo medido." |
| 1:19–1:26 | Dashboard · jornada | "Com um bip da comanda na porta, temos a jornada de todos: no pico, chegar à balança leva quase o dobro do tempo." |
| 1:26–1:34 | Dashboard · mix | "O Prato Inteligente estima a carne, o arroz e a salada de cada prato, e com isso o CMV." |
| 1:34–1:41 | Dashboard · filas | "Desistências, espera contra a meta de 2,5 minutos no grill e todos os alertas ficam registrados." |
| 1:41–1:49 | Previsão | "Com chuva, feriado e dia da semana, prevemos os clientes de amanhã e sugerimos a escala." |
| 1:49–1:55 | Fechamento | "Bovinos Insight: do olhômetro à métrica." |

> As duas imagens de "Como a câmera enxerga" são referências externas. A cena do salão é simulada, mas toda a análise (zonas, espera, desistências, mesas e alertas) é feita pelo código real do projeto. Com o vídeo de 1h30 da Bovinos, rode `python -m src.video_pipeline --video <arquivo> --boxes` para gerar a versão com imagem real.

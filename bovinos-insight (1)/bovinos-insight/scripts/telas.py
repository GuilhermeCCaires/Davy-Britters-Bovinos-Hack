"""Utilitários para renderizar páginas HTML em PNG (Chrome headless via Playwright)."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

VERMELHO = "#9B1B1E"
OURO = "#C9A227"
ESCURO = "#1E1414"
CLARO = "#FAF6F0"
CINZA = "#7A6A60"
CORES_CAT = ["#9B1B1E", "#C9A227", "#D9822B", "#5B8C3A", "#7A5C8E"]

_fontes = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams.update({
    "font.family": "Inter" if "Inter" in _fontes else "DejaVu Sans",
    "font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#BFB2A5", "axes.labelcolor": "#4A3F3A", "xtick.color": "#4A3F3A",
    "ytick.color": "#4A3F3A", "axes.titleweight": "bold", "axes.titlesize": 14, "axes.titlecolor": ESCURO,
    "axes.titlelocation": "left", "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.grid": True, "grid.color": "#EEE6DC", "grid.linewidth": 0.8, "axes.axisbelow": True,
})

CSS_BASE = f"""
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:'Inter', Arial, sans-serif; color:{ESCURO}; background:#F4EFE8; }}
h1,h2,.disp {{ font-family:'Anton','Oswald',Impact,sans-serif; font-weight:400; letter-spacing:0.01em; }}
"""


def fig_b64(fig, dpi: int = 110) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def img_b64(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def shot(html: str, path: Path, width: int, height: int, scale: float = 1.0) -> Path:
    from playwright.sync_api import sync_playwright

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        exe = None
        for cand in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
            if Path(cand).exists():
                exe = cand
                break
        b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        pg.set_content(html, wait_until="load")
        pg.screenshot(path=str(path), full_page=False)
        b.close()
    return path


def pdf(html: str, path: Path, width_px: int, height_px: int) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(html, wait_until="load")
        pg.pdf(path=str(path), width=f"{width_px}px", height=f"{height_px}px", print_background=True,
               margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        b.close()
    return Path(path)

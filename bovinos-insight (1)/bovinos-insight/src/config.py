from __future__ import annotations

import json
from pathlib import Path

from .geometry import denormalize


def load_zones(path: str | Path, width: int, height: int) -> list[dict]:
    """Lê zones.json e adiciona `poly_px` (polígono em pixels) a cada zona."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    zones = data["zones"]
    for z in zones:
        z["poly_px"] = denormalize(z["polygon"], width, height)
    return zones

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def carregar_regulamento(caminho: str | Path) -> dict[str, Any]:
    path = Path(caminho)
    with path.open("r", encoding="utf-8") as arquivo:
        regulamento = json.load(arquivo)

    if "elegibilidade" not in regulamento:
        raise ValueError("Regulamento sem secao 'elegibilidade'.")
    if "pontuacao" not in regulamento:
        raise ValueError("Regulamento sem secao 'pontuacao'.")
    if "criterios" not in regulamento["pontuacao"]:
        raise ValueError("Regulamento sem lista de criterios de pontuacao.")
    regulamento.setdefault("desempate", [])
    return regulamento


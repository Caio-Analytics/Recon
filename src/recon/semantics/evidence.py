from dataclasses import dataclass
from typing import Any

EIXO_PAPEL = "papel"
EIXO_DOMINIO = "dominio"


_MARGEM_CONCLUSIVA = 0.15


@dataclass(frozen=True)
class Evidencia:
    categoria: str
    eixo: str
    peso: float
    origem: str


def _noisy_or(pesos: list[float]) -> float:
    resultado = 1.0
    for peso in pesos:
        resultado *= 1.0 - max(0.0, min(1.0, peso))
    return 1.0 - resultado


def ranquear(evidencias: list[Evidencia], eixo: str) -> list[dict[str, Any]]:
    por_categoria: dict[str, list[Evidencia]] = {}
    for evidencia in evidencias:
        if evidencia.eixo == eixo:
            por_categoria.setdefault(evidencia.categoria, []).append(evidencia)

    ranking: list[dict[str, Any]] = [
        {
            "categoria": categoria,
            "confianca": round(_noisy_or([e.peso for e in itens]), 4),
            "origens": [e.origem for e in sorted(itens, key=lambda e: -e.peso)],
        }
        for categoria, itens in por_categoria.items()
    ]
    ranking.sort(key=lambda r: -float(r["confianca"]))
    return ranking


def escolher(ranking: list[dict[str, Any]]) -> tuple[str | None, float, str, bool]:
    if not ranking:
        return None, 0.0, "Sem evidência", False
    melhor = ranking[0]
    margem = melhor["confianca"] - (ranking[1]["confianca"] if len(ranking) > 1 else 0.0)
    return (
        melhor["categoria"],
        float(melhor["confianca"]),
        " + ".join(melhor["origens"][:3]),
        bool(margem >= _MARGEM_CONCLUSIVA),
    )

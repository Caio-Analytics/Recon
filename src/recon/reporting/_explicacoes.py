"""Traduções de métricas internas para linguagem de relatório."""

from __future__ import annotations

from typing import Any

_ROTULOS_IMPACTO_SCORE = {
    "Colunas comprometidas": "Problemas encontrados nas colunas",
    "Duplicatas e colunas redundantes": "Linhas duplicadas ou colunas repetidas",
}


def explicar_impacto_score(dimensao: str, pontos_perdidos: float) -> str:
    """Explica em linguagem comum uma parcela da diferença até a nota 100."""
    causa = _ROTULOS_IMPACTO_SCORE.get(dimensao, dimensao)
    return f"{causa} reduziram a nota em {pontos_perdidos:.2f} ponto(s)."


def explicar_estabilidade_temporal(adf: dict[str, Any]) -> str:
    """Leitura do teste ADF sem exigir que a pessoa conheça estatística."""
    if not adf.get("aplicavel"):
        return "Não foi possível avaliar com os períodos disponíveis."
    if adf.get("estacionaria"):
        return "Variação estável; não há mudança persistente detectada no período."
    return "Padrão variável; há indício de mudança persistente ao longo do período."


def explicar_dependencia_temporal(ljung_box: dict[str, Any]) -> str:
    """Leitura do teste de Ljung-Box como sequência, não correlação de colunas."""
    if not ljung_box.get("aplicavel"):
        return "Não foi possível avaliar com os períodos disponíveis."
    if ljung_box.get("autocorrelacionada"):
        return "O período anterior ajuda a explicar o próximo."
    return "Não há efeito detectável do período anterior sobre o próximo."

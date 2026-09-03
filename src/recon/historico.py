"""Limiares reutilizáveis para a evolução longitudinal de qualidade."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PADRAO: dict[str, float] = {
    "queda_score_maxima": 5.0,
    "variacao_volume_maxima_pct": 20.0,
}


def carregar_limiares(caminho: str | None = None) -> dict[str, float]:
    """Lê um YAML simples, mantendo limites seguros para chaves ausentes.

    Exemplo::

        score_minimo: 80
        queda_score_maxima: 3
        variacao_volume_maxima_pct: 15
    """
    limites = dict(_PADRAO)
    if caminho is None:
        return limites
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError("O arquivo de limites do histórico precisa ser um objeto YAML.")
    permitidos = set(_PADRAO) | {"score_minimo"}
    desconhecidos = set(dados) - permitidos
    if desconhecidos:
        raise ValueError(f"Limite(s) desconhecido(s): {', '.join(sorted(desconhecidos))}.")
    for chave, valor in dados.items():
        if not isinstance(valor, (int, float)) or isinstance(valor, bool) or valor < 0:
            raise ValueError(f"'{chave}' precisa ser um número não negativo.")
        limites[chave] = float(valor)
    if limites.get("score_minimo", 0) > 100:
        raise ValueError("'score_minimo' não pode ser maior que 100.")
    return limites


def alertas_da_transicao(
    anterior: dict[str, Any] | None, atual: dict[str, Any], limites: dict[str, float]
) -> list[str]:
    """Compara uma extração com a anterior e com a linha de base configurada."""
    alertas: list[str] = []
    score_minimo = limites.get("score_minimo")
    if score_minimo is not None and float(atual["score"]) < score_minimo:
        alertas.append(
            f"O score de {atual['arquivo']} ({atual['score']:.1f}) ficou abaixo do mínimo "
            f"definido ({score_minimo:.1f})."
        )
    if anterior is None:
        return alertas
    queda = float(atual["score"]) - float(anterior["score"])
    if queda <= -limites["queda_score_maxima"]:
        alertas.append(
            f"A qualidade caiu {abs(queda):.1f} ponto(s): {anterior['arquivo']} → {atual['arquivo']}."
        )
    if atual["colunas"] != anterior["colunas"]:
        alertas.append(
            f"A estrutura mudou de {anterior['colunas']} para {atual['colunas']} coluna(s): "
            f"{anterior['arquivo']} → {atual['arquivo']}."
        )
    if not atual["linhas_total_desconhecido"] and not anterior["linhas_total_desconhecido"]:
        variacao = (atual["linhas"] - anterior["linhas"]) / max(anterior["linhas"], 1)
        maximo = limites["variacao_volume_maxima_pct"] / 100
        if abs(variacao) >= maximo:
            direcao = "cresceu" if variacao > 0 else "caiu"
            alertas.append(
                f"O volume {direcao} {abs(variacao):.1%}: {anterior['linhas']:,} → "
                f"{atual['linhas']:,} linhas ({anterior['arquivo']} → {atual['arquivo']})."
            )
    return alertas

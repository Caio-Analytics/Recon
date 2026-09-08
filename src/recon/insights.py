from __future__ import annotations

from typing import Any

from . import config


def _nomes(colunas: list[dict[str, Any]], limite: int = 3) -> str:
    nomes = [f"`{coluna['Coluna']}`" for coluna in colunas[:limite]]
    if not nomes:
        return ""
    if len(nomes) == 1:
        return nomes[0]
    if len(nomes) == 2:
        return " e ".join(nomes)
    return ", ".join(nomes[:-1]) + f" e {nomes[-1]}"


def gerar_insights_textuais(payload: dict[str, Any]) -> list[str]:
    colunas = payload.get("colunas", [])
    por_semantica: dict[str, list[dict[str, Any]]] = {}
    for coluna in colunas:
        por_semantica.setdefault(coluna.get("Semantica_IA", ""), []).append(coluna)

    ids = [coluna for coluna in colunas if coluna.get("Semantica_IA") == config.SEMANTICA_CHAVE_ID]
    chaves_primarias = [
        coluna for coluna in ids if "Chave Primária Potencial" in coluna.get("Caracteristica", "")
    ]
    valores = por_semantica.get("Valor Financeiro", [])
    atributos = [
        coluna
        for coluna in colunas
        if "Dimensão" in coluna.get("Caracteristica", "")
        or coluna.get("Semantica_IA") == config.SEMANTICA_CATEGORIA
    ]
    dominios = {str(coluna.get("Dominio")) for coluna in colunas if coluna.get("Dominio")}
    insights: list[str] = []

    series_temporais = payload.get("analise_temporal_series") or []
    coluna_temporal = (
        series_temporais[0]["coluna_temporal_referencia"] if series_temporais else None
    )
    medidas_temporais = {serie["coluna"] for serie in series_temporais if serie.get("coluna")}
    valores_temporais = [coluna for coluna in valores if coluna.get("Coluna") in medidas_temporais]

    if "Comercial / CRM" in dominios and valores:
        texto = "A tabela tem sinais de uma base comercial"
        if coluna_temporal:
            texto += f" com uma referência temporal em `{coluna_temporal}`"
        texto += f", pois reúne {_nomes(valores)} como valor financeiro"
        if atributos:
            texto += f" e atributos como {_nomes(atributos)}"
        insights.append(texto + ".")
    elif coluna_temporal and valores_temporais:
        nome_temporal = str(coluna_temporal).lower()
        if any(
            token in nome_temporal for token in ("hire", "admission", "admissao", "contratacao")
        ):
            insights.append(
                f"É possível comparar {_nomes(valores_temporais)} entre coortes de admissão "
                f"usando `{coluna_temporal}`. Isso descreve associação entre coortes, não "
                "evolução salarial individual nem causalidade."
            )
        else:
            insights.append(
                f"É possível resumir {_nomes(valores_temporais)} por período usando "
                f"`{coluna_temporal}`. A leitura é descritiva e não estabelece causalidade."
            )
    elif atributos:
        insights.append(
            f"A base é adequada para segmentação por atributos como {_nomes(atributos)}."
        )

    if chaves_primarias:
        insights.append(
            f"{_nomes(chaves_primarias)} parece identificar cada registro e pode ser avaliada "
            "como chave de integração, após confirmar a unicidade na base completa."
        )
    elif ids:
        insights.append(
            f"A base possui identificadores como {_nomes(ids)}, úteis para ligar registros "
            "a outras tabelas após validar sua cobertura e unicidade."
        )

    score = payload.get("metadados_execucao", {}).get("score_qualidade", {})
    criticas = score.get("colunas_criticas") or []
    if criticas:
        principal = criticas[0]
        motivos = ", ".join(principal.get("motivos") or [])
        insights.append(
            f"O primeiro ponto para tratar é `{principal['coluna']}`: "
            f"{motivos or 'possui achados de qualidade'}."
        )

    return insights

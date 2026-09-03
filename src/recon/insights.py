"""Leituras executivas determinísticas derivadas do payload do profiler.

Não usa modelo externo nem inventa contexto: cada frase é montada apenas com
classificações e métricas que já constam no resultado estruturado.
"""

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
    """Gera um resumo curto com evidências que a pessoa consegue conferir."""
    colunas = payload.get("colunas", [])
    por_semantica: dict[str, list[dict[str, Any]]] = {}
    for coluna in colunas:
        por_semantica.setdefault(coluna.get("Semantica_IA", ""), []).append(coluna)

    ids = [
        coluna for coluna in colunas
        if coluna.get("Semantica_IA") == config.SEMANTICA_CHAVE_ID
    ]
    chaves_primarias = [
        coluna for coluna in ids
        if "Chave Primária Potencial" in coluna.get("Caracteristica", "")
    ]
    datas = por_semantica.get(config.SEMANTICA_DATA_CALENDARIO, [])
    valores = por_semantica.get("Valor Financeiro", [])
    atributos = [
        coluna for coluna in colunas
        if "Dimensão" in coluna.get("Caracteristica", "")
        or coluna.get("Semantica_IA") == config.SEMANTICA_CATEGORIA
    ]
    dominios = {str(coluna.get("Dominio")) for coluna in colunas if coluna.get("Dominio")}
    insights: list[str] = []

    if "Comercial / CRM" in dominios and valores:
        texto = "A tabela tem sinais de uma base comercial"
        if datas:
            texto += " com registro ao longo do tempo"
        texto += f", pois reúne {_nomes(valores)} como valor financeiro"
        if atributos:
            texto += f" e atributos como {_nomes(atributos)}"
        insights.append(texto + ".")
    elif datas and valores:
        insights.append(
            f"A tabela permite acompanhar {_nomes(valores)} ao longo do tempo usando {_nomes(datas)}."
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

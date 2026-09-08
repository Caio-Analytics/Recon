from typing import Any

from .. import config
from .contexto import ContextoSemantico, contexto_atual
from .detectors import (
    PAPEIS_ESTRUTURAIS,
    PerfilConteudo,
    perfil_de_registro,
    por_assinatura_estrutural,
    por_contexto_da_tabela,
    por_fuzzy,
    por_gazetteer,
    por_padrao_conteudo,
    por_token_forte,
)
from .evidence import EIXO_DOMINIO, EIXO_PAPEL, Evidencia, escolher, ranquear
from .tokens import expandir_abreviatura, normalizar, tokenizar
from .vocabularios import (
    carregar_vocabularios,
    exportar_modelo_de_correcoes,
    vocabulario_temporario,
)

__all__ = [
    "Evidencia",
    "PAPEIS_ESTRUTURAIS",
    "PerfilConteudo",
    "expandir_abreviatura",
    "inferir_semantica",
    "inferir_semanticas_da_tabela",
    "normalizar",
    "perfil_de_registro",
    "semanticas_para_gap_analysis",
    "tokenizar",
    "carregar_vocabularios",
    "exportar_modelo_de_correcoes",
    "ContextoSemantico",
    "vocabulario_temporario",
]


_CONFIANCA_MINIMA_CONTEXTO = 0.7


_CONFIANCA_MINIMA_DOMINIO = 0.5

_MAX_HIPOTESES = 4


def _coletar_evidencias(
    nome_col: str,
    detectado_padrao: str,
    perfil: PerfilConteudo | None,
) -> list[Evidencia]:
    tokens = tokenizar(nome_col)
    nome_limpo = normalizar(nome_col)

    evidencias: list[Evidencia] = []
    evidencias += por_padrao_conteudo(detectado_padrao)
    evidencias += por_token_forte(tokens)
    evidencias += por_fuzzy(nome_limpo, tokens)

    if perfil is not None:
        evidencias += por_gazetteer(perfil)
        evidencias += por_assinatura_estrutural(perfil)

    return evidencias


def _refinar_papel(
    papel: str | None, dominio: str | None, perfil: PerfilConteudo | None
) -> str | None:
    if papel == config.SEMANTICA_NOME_PESSOA:
        if dominio is not None and dominio not in config.DOMINIOS_DE_PESSOA:
            return config.SEMANTICA_ROTULO_ENTIDADE
    elif papel == config.SEMANTICA_TEXTO_LIVRE and perfil is not None:
        cardinalidade_de_dimensao = (
            1 < perfil.n_unicos <= config.CARDINALIDADE_MAX_CATEGORIA
            and perfil.ratio_unicidade < 0.5
        )
        if cardinalidade_de_dimensao:
            return config.SEMANTICA_CATEGORIA
    return papel


def _montar_resultado(
    evidencias: list[Evidencia], perfil: PerfilConteudo | None = None
) -> dict[str, Any]:
    ranking_papel = ranquear(evidencias, EIXO_PAPEL)
    ranking_dominio = ranquear(evidencias, EIXO_DOMINIO)

    papel, conf_papel, origem_papel, papel_conclusivo = escolher(ranking_papel)
    dominio, conf_dominio, origem_dominio, _ = escolher(ranking_dominio)

    dominio_incerto = dominio is not None and conf_dominio < _CONFIANCA_MINIMA_DOMINIO
    if dominio_incerto:
        dominio, conf_dominio, origem_dominio = None, 0.0, "Sem evidência"

    papel = _refinar_papel(papel, dominio, perfil)

    if papel in PAPEIS_ESTRUTURAIS:
        semantica, confianca, origem = papel, conf_papel, origem_papel
    elif dominio is not None:
        semantica, confianca, origem = dominio, conf_dominio, origem_dominio
    elif papel is not None:
        semantica, confianca, origem = papel, conf_papel, origem_papel
    else:
        semantica, confianca, origem = config.SEMANTICA_GENERICA, 0.0, "Unmatched"

    hipoteses = sorted(
        [
            {
                "semantica": r["categoria"],
                "eixo": eixo,
                "confianca": r["confianca"],
                "evidencias": r["origens"][:3],
            }
            for eixo, ranking in ((EIXO_PAPEL, ranking_papel), (EIXO_DOMINIO, ranking_dominio))
            for r in ranking
        ],
        key=lambda h: -h["confianca"],
    )[:_MAX_HIPOTESES]

    return {
        "semantica": semantica,
        "papel": papel,
        "dominio": dominio,
        "confianca_score": round(confianca, 4),
        "origem": origem,
        "conclusiva": not (bool(ranking_papel) and not papel_conclusivo) and not dominio_incerto,
        "hipoteses": hipoteses,
    }


def inferir_semantica(
    nome_col: str,
    detectado_padrao: str = "Nenhum",
    perfil: PerfilConteudo | None = None,
) -> dict[str, Any]:
    correcao = contexto_atual().correcoes_colunas.get(nome_col)
    if correcao:
        eixo = EIXO_PAPEL if correcao in PAPEIS_ESTRUTURAIS else EIXO_DOMINIO
        resultado = _montar_resultado(
            [Evidencia(correcao, eixo, 1.0, "correção explícita do vocabulário")], perfil
        )
        resultado["conclusiva"] = True
        return resultado
    return _montar_resultado(_coletar_evidencias(nome_col, detectado_padrao, perfil), perfil)


def inferir_semanticas_da_tabela(entradas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidencias_por_coluna: list[list[Evidencia]] = []
    resultados: list[dict[str, Any]] = []
    for entrada in entradas:
        nome = str(entrada["nome"])
        correcao = contexto_atual().correcoes_colunas.get(nome)
        evidencias = (
            [
                Evidencia(
                    correcao,
                    EIXO_PAPEL if correcao in PAPEIS_ESTRUTURAIS else EIXO_DOMINIO,
                    1.0,
                    "correção explícita do vocabulário",
                )
            ]
            if correcao
            else _coletar_evidencias(nome, entrada.get("padrao", "Nenhum"), entrada.get("perfil"))
        )
        evidencias_por_coluna.append(evidencias)
        resultado = _montar_resultado(evidencias, entrada.get("perfil"))
        if correcao:
            resultado["conclusiva"] = True
        resultados.append(resultado)

    contexto = _perfil_de_assunto(resultados)
    if not contexto:
        return resultados

    for indice, (entrada, resultado) in enumerate(zip(entradas, resultados, strict=True)):
        if resultado["conclusiva"]:
            continue
        extras = por_contexto_da_tabela(tokenizar(str(entrada["nome"])), contexto)
        if not extras:
            continue
        resultados[indice] = _montar_resultado(
            evidencias_por_coluna[indice] + extras, entrada.get("perfil")
        )

    return resultados


def _perfil_de_assunto(resultados: list[dict[str, Any]]) -> dict[str, float]:
    forcas: dict[str, float] = {}
    for resultado in resultados:
        if not resultado["conclusiva"]:
            continue
        for categoria in (resultado["papel"], resultado["dominio"]):
            if not categoria or categoria == config.SEMANTICA_GENERICA:
                continue
            if resultado["confianca_score"] < _CONFIANCA_MINIMA_CONTEXTO:
                continue
            forcas[categoria] = max(forcas.get(categoria, 0.0), resultado["confianca_score"])
    return forcas


def semanticas_para_gap_analysis(registro: dict[str, Any]) -> list[str]:
    return [
        v
        for v in (registro.get("semantica"), registro.get("papel"), registro.get("dominio"))
        if v and v != config.SEMANTICA_GENERICA
    ]

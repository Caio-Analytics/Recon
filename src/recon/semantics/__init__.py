"""Inferência semântica de colunas por acúmulo de evidências.

O modelo tem dois eixos:

- papel: o que a coluna é (identificador, data, valor financeiro,
  quantidade, nome, descrição, contato, flag).
- domínio: sobre o que ela fala (estrutura organizacional, cargo, curso,
  localidade, perfil do colaborador).

`nome_departamento` tem papel "Nome" e domínio "Estrutura Organizacional".

A inferência é uma cascata de detectores independentes, não uma sequência de
`if/elif` em que o primeiro a responder vence. Cada detector emite evidências
com peso, combinadas por noisy-OR, o que deixa pistas fracas se somarem.
Assim `cd_dpto_lot` é classificável mesmo sem o dicionário conhecer o nome: a
abreviatura reconstrói `codigo`/`departamento`/`lotacao`, o conteúdo mostra
baixa cardinalidade e o contexto da tabela confirma o assunto.

A inferência acontece em duas passadas. A primeira classifica o que dá
isoladamente; a segunda usa os domínios já estabelecidos com confiança para
desambiguar o que ficou em cima do muro — `dep` (departamento? dependente?
depósito?) é insolúvel na coluna e trivial na tabela.
"""
from typing import Any

from .. import config
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
from .vocabularios import carregar_vocabularios, vocabulario_temporario

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
    "vocabulario_temporario",
]

# Confiança mínima para um domínio da primeira passada entrar no contexto que
# desambigua as demais colunas. Baixo demais e o contexto propaga o próprio
# erro; alto demais e ele nunca ajuda.
_CONFIANCA_MINIMA_CONTEXTO = 0.7

# Piso para afirmar um domínio. Abaixo dele a categoria continua visível em
# `hipoteses`, mas o campo `dominio` fica vazio.
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


def _refinar_papel(papel: str | None, dominio: str | None, perfil: PerfilConteudo | None) -> str | None:
    """Ajusta o papel com o que os outros dois sinais já sabem.

    O eixo de domínio e a cardinalidade da coluna carregam informação que o
    nome sozinho não dá, e são eles que separam dois pares que o motor
    confundia:

    - nome de gente x nome de coisa: `FULL_NAME` e `DEPARTMENT_NAME` têm o
      mesmo qualificador. O que os separa é o domínio: departamento é
      estrutura organizacional, e nome de departamento não é dado pessoal.
    - descrição x categoria: `JOB_DESCRIPTION` (milhares de valores) é texto
      livre; `SHIFT_TYPE_DESC` (poucos valores numa tabela grande) é uma
      dimensão. Essa diferença está no dado, não no nome.
    """
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

    # Domínio abaixo do piso não é afirmado: continua listado em `hipoteses`,
    # mas não vira fato no relatório. `cod_dep` numa tabela sem nenhuma outra
    # pista de estrutura organizacional é um palpite, não um achado; é esse
    # caso que a segunda passada por contexto resolve, ou deixa em aberto.
    dominio_incerto = dominio is not None and conf_dominio < _CONFIANCA_MINIMA_DOMINIO
    if dominio_incerto:
        dominio, conf_dominio, origem_dominio = None, 0.0, "Sem evidência"

    papel = _refinar_papel(papel, dominio, perfil)

    # O papel estrutural manda porque é ele que decide o tratamento no
    # pipeline. Papel "fraco" (Nome, Texto Descritivo) descreve a forma e não
    # o assunto — aí o domínio é mais informativo.
    if papel in PAPEIS_ESTRUTURAIS:
        semantica, confianca, origem = papel, conf_papel, origem_papel
    elif dominio is not None:
        semantica, confianca, origem = dominio, conf_dominio, origem_dominio
    elif papel is not None:
        semantica, confianca, origem = papel, conf_papel, origem_papel
    else:
        semantica, confianca, origem = config.SEMANTICA_GENERICA, 0.0, "Unmatched"

    hipoteses = sorted(
        [{"semantica": r["categoria"], "eixo": eixo, "confianca": r["confianca"],
          "evidencias": r["origens"][:3]}
         for eixo, ranking in ((EIXO_PAPEL, ranking_papel), (EIXO_DOMINIO, ranking_dominio))
         for r in ranking],
        key=lambda h: -h["confianca"],
    )[:_MAX_HIPOTESES]

    return {
        "semantica": semantica,
        "papel": papel,
        "dominio": dominio,
        "confianca_score": round(confianca, 4),
        "origem": origem,
        # Conclusiva exige os dois eixos resolvidos — mas ambiguidade é ter
        # candidatos empatados, não é não ter candidato nenhum. Uma coluna como
        # `diretoria`, que só tem domínio e nenhum papel, está perfeitamente
        # resolvida e precisa entrar no contexto que desambigua as vizinhas.
        "conclusiva": not (bool(ranking_papel) and not papel_conclusivo) and not dominio_incerto,
        "hipoteses": hipoteses,
    }


def inferir_semantica(
    nome_col: str,
    detectado_padrao: str = "Nenhum",
    perfil: PerfilConteudo | None = None,
) -> dict[str, Any]:
    """Infere papel, domínio e semântica primária de uma coluna isolada.

    `perfil` habilita os detectores de conteúdo (gazetteer e assinatura
    estrutural) — sem ele a inferência é só pelo nome, como antes.
    """
    return _montar_resultado(_coletar_evidencias(nome_col, detectado_padrao, perfil), perfil)


def inferir_semanticas_da_tabela(entradas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infere a semântica de todas as colunas, com desambiguação por contexto.

    Cada entrada é `{"nome": str, "padrao": str, "perfil": PerfilConteudo}`.

    Passada 1 classifica cada coluna isoladamente. Passada 2 monta o perfil de
    assunto da tabela a partir do que ficou confiante e reprocessa apenas as
    colunas cuja escolha não foi conclusiva — é onde `cod_dep` numa tabela de
    RH vira departamento em vez de dependente.
    """
    evidencias_por_coluna: list[list[Evidencia]] = []
    resultados: list[dict[str, Any]] = []
    for entrada in entradas:
        evidencias = _coletar_evidencias(
            str(entrada["nome"]), entrada.get("padrao", "Nenhum"), entrada.get("perfil")
        )
        evidencias_por_coluna.append(evidencias)
        resultados.append(_montar_resultado(evidencias, entrada.get("perfil")))

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
    """Resume de que a tabela trata, a partir das colunas já bem classificadas.

    Só entram categorias estabelecidas com confiança: o contexto serve para
    desempatar, e um contexto construído a partir de palpites propagaria o
    erro para as colunas ambíguas em vez de resolvê-las.
    """
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
    """Todas as semânticas que uma coluna aporta ao gap analysis.

    Uma coluna `cod_departamento` habilita tanto requisitos de "Chave
    Identificadora" quanto de "Estrutura Organizacional" — considerar só a
    semântica primária deixava KPIs bloqueados por engano.
    """
    return [
        v for v in (registro.get("semantica"), registro.get("papel"), registro.get("dominio"))
        if v and v != config.SEMANTICA_GENERICA
    ]

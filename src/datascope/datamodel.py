from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from loguru import logger
from rapidfuzz.distance import JaroWinkler

from . import config
from .semantics import normalizar








CONTENCAO_MINIMA = 0.6
CONTENCAO_MINIMA_COM_APOIO_DE_NOME = 0.35
CONFIANCA_MINIMA_RELACAO = 0.6


MIN_DISTINTOS_CHAVE = 3
MIN_DISTINTOS_SEM_APOIO_DE_NOME = 10


COBERTURA_MINIMA_DA_CHAVE = 0.05
MAX_DISTINTOS_COMPARADOS = 500_000
MAX_ANALISES_SUGERIDAS = 12

_PAPEL_MEDIDA = frozenset({"Valor Financeiro", "Quantidade / Métrica"})


_PRIORIDADE_ATRIBUTO = (
    "Estrutura Organizacional", "Cargo / Função", "Localização Geográfica",
    "Curso / Treinamento", "Perfil do Colaborador", "Resultado de Avaliação",
    "Status / Indicador / Flag",
)
_MAX_CARDINALIDADE_ATRIBUTO = 100



_TOKENS_NAO_ADITIVOS = frozenset({
    "nota", "score", "indice", "taxa", "percentual", "pct", "media", "ratio",
    "proporcao", "nivel", "aderencia", "satisfacao", "avaliacao", "peso",
})


def _agregacao_para(coluna: str) -> str:
    from .semantics import tokenizar
    return "mean" if set(tokenizar(coluna)) & _TOKENS_NAO_ADITIVOS else "sum"


@dataclass
class TabelaCarregada:
    nome: str
    df: pd.DataFrame
    payload: dict[str, Any]
    origem: str = ""

    @property
    def colunas(self) -> list[dict[str, Any]]:
        return self.payload["colunas"]

    def meta(self, coluna: str) -> dict[str, Any] | None:
        for c in self.colunas:
            if c["Coluna"] == coluna:
                return c
        return None


@dataclass
class PerfilTabela:
    nome: str
    papel: str = "Indefinida"
    justificativa: str = ""
    chaves_primarias: list[str] = field(default_factory=list)
    medidas: list[str] = field(default_factory=list)
    atributos: list[str] = field(default_factory=list)
    datas: list[str] = field(default_factory=list)
    fks_saindo: int = 0
    referenciada_por: int = 0




def _chaves_primarias(colunas: list[dict[str, Any]]) -> list[str]:
    candidatas = [c for c in colunas if _e_chave_primaria(c)]
    identificadoras = [
        c["Coluna"] for c in candidatas if c.get("Papel") == config.SEMANTICA_CHAVE_ID
    ]
    return identificadoras or [c["Coluna"] for c in candidatas]


def _e_chave_primaria(meta: dict[str, Any]) -> bool:
    return (
        meta.get("Qtd_Nulos", 1) == 0
        and meta.get("Ratio_Unicidade", 0.0) >= 0.999
        and meta.get("Qtd_Unicos", 0) >= MIN_DISTINTOS_CHAVE
        and meta.get("Tipo_Inferred", "") in config.TIPOS_ELEGIVEIS_CHAVE
    )


def _conjunto_normalizado(serie: pd.Series) -> set[str]:
    limpa = serie.dropna()
    if limpa.empty:
        return set()
    if pd.api.types.is_numeric_dtype(limpa):
        convertida = limpa.map(
            lambda v: str(int(v)) if float(v).is_integer() else str(v)
        )
    else:
        convertida = limpa.astype(str).str.strip()
    distintos = convertida.unique()
    if len(distintos) > MAX_DISTINTOS_COMPARADOS:
        distintos = distintos[:MAX_DISTINTOS_COMPARADOS]
    return set(distintos)


def _contencao_por_linha(serie: pd.Series, valores_referencia: set[str]) -> float:
    limpa = serie.dropna()
    if limpa.empty:
        return 0.0
    if pd.api.types.is_numeric_dtype(limpa):
        convertida = limpa.map(lambda v: str(int(v)) if float(v).is_integer() else str(v))
    else:
        convertida = limpa.astype(str).str.strip()
    return float(convertida.isin(valores_referencia).mean())


def _tipos_incompativeis(serie_a: pd.Series, serie_b: pd.Series) -> bool:
    numerica_a = pd.api.types.is_numeric_dtype(serie_a)
    numerica_b = pd.api.types.is_numeric_dtype(serie_b)
    return numerica_a != numerica_b




def detectar_relacionamentos(tabelas: list[TabelaCarregada]) -> list[dict[str, Any]]:
    if len(tabelas) < 2:
        return []

    conjuntos: dict[tuple[str, str], set[str]] = {}

    def conjunto(tabela: TabelaCarregada, coluna: str) -> set[str]:
        chave = (tabela.nome, coluna)
        if chave not in conjuntos:
            conjuntos[chave] = _conjunto_normalizado(tabela.df[coluna])
        return conjuntos[chave]

    achados: list[dict[str, Any]] = []
    for destino in tabelas:
        pks = _chaves_primarias(destino.colunas)
        for pk in pks:
            valores_pk = conjunto(destino, pk)
            if len(valores_pk) < MIN_DISTINTOS_CHAVE:
                continue

            for origem in tabelas:
                if origem.nome == destino.nome:
                    continue
                for meta_fk in origem.colunas:
                    fk = meta_fk["Coluna"]
                    if meta_fk.get("Qtd_Unicos", 0) < 2:
                        continue
                    if meta_fk.get("Tipo_Inferred", "") not in config.TIPOS_ELEGIVEIS_CHAVE:
                        continue

                    valores_fk = conjunto(origem, fk)
                    if not valores_fk:
                        continue

                    similaridade_nome = JaroWinkler.similarity(normalizar(fk), normalizar(pk))
                    nome_apoia = similaridade_nome >= 0.75

                    
                    
                    
                    
                    contencao = len(valores_fk & valores_pk) / len(valores_fk)
                    limiar = (
                        CONTENCAO_MINIMA_COM_APOIO_DE_NOME if nome_apoia else CONTENCAO_MINIMA
                    )
                    if contencao < limiar:
                        continue

                    
                    
                    
                    if meta_fk.get("Papel") in _PAPEL_MEDIDA and not nome_apoia:
                        continue

                    
                    
                    if len(valores_pk) < MIN_DISTINTOS_SEM_APOIO_DE_NOME and not nome_apoia:
                        continue
                    if (len(valores_fk) / len(valores_pk)) < COBERTURA_MINIMA_DA_CHAVE \
                            and not nome_apoia:
                        continue

                    ambos_chave = (
                        meta_fk.get("Papel") == config.SEMANTICA_CHAVE_ID
                        and (destino.meta(pk) or {}).get("Papel") == config.SEMANTICA_CHAVE_ID
                    )

                    confianca = (
                        0.6 * contencao
                        + 0.25 * similaridade_nome
                        + (0.15 if ambos_chave else 0.0)
                    )
                    if confianca < CONFIANCA_MINIMA_RELACAO:
                        continue

                    
                    
                    
                    
                    contencao_linhas = _contencao_por_linha(origem.df[fk], valores_pk)
                    orfaos = round(1.0 - contencao_linhas, 4)
                    achados.append({
                        "tabela_origem": origem.nome,
                        "coluna_origem": fk,
                        "tabela_destino": destino.nome,
                        "coluna_destino": pk,
                        "cardinalidade": (
                            "1:1" if meta_fk.get("Ratio_Unicidade", 0.0) >= 0.999 else "N:1"
                        ),
                        "contencao": round(contencao, 4),
                        "contencao_linhas": round(contencao_linhas, 4),
                        "confianca": round(confianca, 4),
                        "pct_orfaos": orfaos,
                        "similaridade_nome": round(similaridade_nome, 4),
                        "tipos_incompativeis": _tipos_incompativeis(
                            origem.df[fk], destino.df[pk]
                        ),
                    })

    achados.sort(key=lambda r: -r["confianca"])
    return achados




def _classificar_colunas(tabela: TabelaCarregada, fks: set[str]) -> tuple[list, list, list]:
    medidas, atributos, datas = [], [], []
    for meta in tabela.colunas:
        nome = meta["Coluna"]
        if nome in fks or "🔑" in meta.get("Caracteristica", ""):
            continue
        if "Vazia" in meta.get("Caracteristica", ""):
            continue
        papel = meta.get("Papel")
        if papel == config.SEMANTICA_DATA_CALENDARIO or meta.get("Tipo_Inferred") == config.TIPO_DATA_HORA:
            datas.append(nome)
        elif papel in _PAPEL_MEDIDA and "Número" in meta.get("Tipo_Inferred", ""):
            medidas.append(nome)
        elif 1 < meta.get("Qtd_Unicos", 0) <= _MAX_CARDINALIDADE_ATRIBUTO:
            atributos.append(nome)
    return medidas, atributos, datas


def classificar_papeis(
    tabelas: list[TabelaCarregada], relacionamentos: list[dict[str, Any]]
) -> dict[str, PerfilTabela]:
    perfis: dict[str, PerfilTabela] = {}
    for tabela in tabelas:
        fks = {r["coluna_origem"] for r in relacionamentos if r["tabela_origem"] == tabela.nome}
        medidas, atributos, datas = _classificar_colunas(tabela, fks)
        perfis[tabela.nome] = PerfilTabela(
            nome=tabela.nome,
            chaves_primarias=_chaves_primarias(tabela.colunas),
            medidas=medidas, atributos=atributos, datas=datas,
            fks_saindo=len(fks),
            referenciada_por=sum(
                1 for r in relacionamentos if r["tabela_destino"] == tabela.nome
            ),
        )

    for tabela in tabelas:
        perfil = perfis[tabela.nome]
        n_colunas = len(tabela.colunas)
        if perfil.fks_saindo >= 2 and perfil.medidas:
            perfil.papel = "Fato"
            perfil.justificativa = (
                f"aponta para {perfil.fks_saindo} tabelas e carrega "
                f"{len(perfil.medidas)} medida(s) numérica(s)"
            )
        elif perfil.fks_saindo >= 2 and n_colunas <= perfil.fks_saindo + 1:
            perfil.papel = "Tabela ponte"
            perfil.justificativa = "quase só chaves estrangeiras — liga duas dimensões"
        elif perfil.fks_saindo >= 2:
            perfil.papel = "Fato sem medida (eventos)"
            perfil.justificativa = (
                f"aponta para {perfil.fks_saindo} tabelas; cada linha é uma ocorrência"
            )
        elif perfil.fks_saindo == 1 and perfil.medidas:
            perfil.papel = "Fato"
            perfil.justificativa = "carrega medidas e se liga a uma dimensão"
        elif perfil.referenciada_por >= 1 and perfil.chaves_primarias:
            perfil.papel = "Dimensão"
            perfil.justificativa = (
                f"tem chave própria e é referenciada por {perfil.referenciada_por} coluna(s)"
            )
        elif perfil.chaves_primarias:
            perfil.papel = "Dimensão isolada"
            perfil.justificativa = "tem chave própria, mas nada no conjunto aponta para ela"
        else:
            perfil.papel = "Indefinida"
            perfil.justificativa = "sem chave única nem ligação com as demais"
    return perfis




def _variavel(nome: str) -> str:
    limpo = "".join(ch if ch.isalnum() else "_" for ch in normalizar(nome)).strip("_")
    return limpo or "tabela"


def _prioridade_atributo(meta: dict[str, Any] | None) -> tuple[int, int]:
    if meta is None:
        return (len(_PRIORIDADE_ATRIBUTO), 1)
    eh_codigo = 1 if meta.get("Papel") == config.SEMANTICA_CHAVE_ID else 0
    for i, categoria in enumerate(_PRIORIDADE_ATRIBUTO):
        if categoria in (meta.get("Dominio"), meta.get("Papel"), meta.get("Semantica_IA")):
            return (i, eh_codigo)
    return (len(_PRIORIDADE_ATRIBUTO), eh_codigo)


def _codigo_pandas(
    base: str, joins: list[dict[str, Any]], medida: dict[str, Any] | None,
    atributo: dict[str, Any], agregacao: str,
) -> str:
    linhas = [f"resultado = (\n    {_variavel(base)}"]
    for join in joins:
        linhas.append(
            f'    .merge({_variavel(join["tabela"])}, '
            f'left_on="{join["coluna_origem"]}", right_on="{join["coluna_destino"]}", '
            f'how="left", suffixes=("", "_{_variavel(join["tabela"])[:6]}"))'
        )
    coluna_grupo = atributo["coluna"]
    if medida is None:
        linhas.append(f'    .groupby("{coluna_grupo}", as_index=False).size()')
        linhas.append('    .rename(columns={"size": "qtd_registros"})')
        linhas.append('    .sort_values("qtd_registros", ascending=False)')
    else:
        linhas.append(
            f'    .groupby("{coluna_grupo}", as_index=False)["{medida["coluna"]}"].{agregacao}()'
        )
        linhas.append(f'    .sort_values("{medida["coluna"]}", ascending=False)')
    linhas.append(")")
    return "\n".join(linhas)


def _codigo_sql(
    base: str, joins: list[dict[str, Any]], medida: dict[str, Any] | None,
    atributo: dict[str, Any], agregacao: str,
) -> str:
    alias = {base: "f"}
    for i, join in enumerate(joins):
        alias[join["tabela"]] = f"d{i + 1}"
    coluna_grupo = f'{alias[atributo["tabela"]]}."{atributo["coluna"]}"'
    if medida is None:
        selecao = "COUNT(*) AS qtd_registros"
        ordem = "qtd_registros"
    else:
        agregador = "SUM" if agregacao == "sum" else "AVG"
        selecao = (
            f'{agregador}({alias[medida["tabela"]]}."{medida["coluna"]}") '
            f'AS {agregacao}_{medida["coluna"]}'
        )
        ordem = f'{agregacao}_{medida["coluna"]}'
    partes = [f'SELECT {coluna_grupo} AS {atributo["coluna"]}, {selecao}',
              f'FROM "{base}" f']
    for join in joins:
        partes.append(
            f'LEFT JOIN "{join["tabela"]}" {alias[join["tabela"]]} '
            f'ON f."{join["coluna_origem"]}" = {alias[join["tabela"]]}."{join["coluna_destino"]}"'
        )
    partes.append(f"GROUP BY {coluna_grupo}")
    partes.append(f"ORDER BY {ordem} DESC;")
    return "\n".join(partes)


def sugerir_analises(
    tabelas: list[TabelaCarregada],
    relacionamentos: list[dict[str, Any]],
    perfis: dict[str, PerfilTabela],
) -> list[dict[str, Any]]:
    
    
    
    if not relacionamentos:
        return []

    por_nome = {t.nome: t for t in tabelas}
    sugestoes: list[dict[str, Any]] = []

    fatos = [n for n, p in perfis.items() if p.papel.startswith("Fato")]
    if not fatos:
        
        
        fatos = [
            n for n, p in sorted(
                perfis.items(), key=lambda kv: -kv[1].referenciada_por
            )[:1]
        ]

    for nome_fato in fatos:
        perfil_fato = perfis[nome_fato]
        ligacoes = [r for r in relacionamentos if r["tabela_origem"] == nome_fato]

        
        medidas = [{"tabela": nome_fato, "coluna": c} for c in perfil_fato.medidas]
        atributos = [{"tabela": nome_fato, "coluna": c} for c in perfil_fato.atributos]
        joins_por_tabela: dict[str, dict[str, Any]] = {}

        for ligacao in ligacoes:
            destino = ligacao["tabela_destino"]
            perfil_dim = perfis.get(destino)
            if perfil_dim is None:
                continue
            joins_por_tabela[destino] = {
                "tabela": destino,
                "coluna_origem": ligacao["coluna_origem"],
                "coluna_destino": ligacao["coluna_destino"],
            }
            medidas += [{"tabela": destino, "coluna": c} for c in perfil_dim.medidas]
            atributos += [{"tabela": destino, "coluna": c} for c in perfil_dim.atributos]

        if not atributos:
            continue

        atributos.sort(key=lambda a: _prioridade_atributo(
            por_nome[a["tabela"]].meta(a["coluna"])
        ))

        for atributo in atributos[:5]:
            joins_necessarios = (
                [joins_por_tabela[atributo["tabela"]]]
                if atributo["tabela"] != nome_fato else []
            )
            for medida in medidas[:3]:
                if medida["tabela"] != nome_fato and medida["tabela"] not in joins_por_tabela:
                    continue
                joins = list(joins_necessarios)
                if (medida["tabela"] != nome_fato
                        and medida["tabela"] != atributo["tabela"]):
                    joins.append(joins_por_tabela[medida["tabela"]])
                agregacao = _agregacao_para(medida["coluna"])
                rotulo = "Total" if agregacao == "sum" else "Média"
                verbo = "Soma" if agregacao == "sum" else "Média"
                sugestoes.append({
                    "titulo": f"{rotulo} de {medida['coluna']} por {atributo['coluna']}",
                    "descricao": (
                        f"{verbo} de `{medida['coluna']}` (de `{medida['tabela']}`) agrupada por "
                        f"`{atributo['coluna']}` (de `{atributo['tabela']}`), a partir do fato "
                        f"`{nome_fato}`."
                    ),
                    "tabela_base": nome_fato,
                    "tabelas_envolvidas": sorted(
                        {nome_fato, medida["tabela"], atributo["tabela"]}
                    ),
                    "pandas": _codigo_pandas(nome_fato, joins, medida, atributo, agregacao),
                    "sql": _codigo_sql(nome_fato, joins, medida, atributo, agregacao),
                })

            sugestoes.append({
                "titulo": f"Contagem de registros de {nome_fato} por {atributo['coluna']}",
                "descricao": (
                    f"Quantos registros de `{nome_fato}` existem para cada "
                    f"`{atributo['coluna']}`. Serve de denominador para qualquer taxa."
                ),
                "tabela_base": nome_fato,
                "tabelas_envolvidas": sorted({nome_fato, atributo["tabela"]}),
                "pandas": _codigo_pandas(nome_fato, joins_necessarios, None, atributo, "sum"),
                "sql": _codigo_sql(nome_fato, joins_necessarios, None, atributo, "sum"),
            })

        for data in perfil_fato.datas[:1]:
            for medida in medidas[:1]:
                joins = (
                    [] if medida["tabela"] == nome_fato
                    else [joins_por_tabela[medida["tabela"]]]
                )
                sugestoes.append({
                    "titulo": f"Evolução mensal de {medida['coluna']}",
                    "descricao": (
                        f"Série temporal de `{medida['coluna']}` agregada por mês de "
                        f"`{data}`."
                    ),
                    "tabela_base": nome_fato,
                    "tabelas_envolvidas": sorted({nome_fato, medida["tabela"]}),
                    "pandas": _codigo_pandas(
                        nome_fato, joins, medida,
                        {"tabela": nome_fato, "coluna": "__mes__"},
                        _agregacao_para(medida["coluna"]),
                    ).replace(
                        '.groupby("__mes__"',
                        f'.assign(__mes__=lambda d: pd.to_datetime(d["{data}"]).dt.to_period("M").astype(str))\n'
                        f'    .groupby("__mes__"',
                    ),
                    "sql": (
                        f'SELECT DATE_TRUNC(\'month\', f."{data}") AS mes, '
                        f'SUM({"f" if medida["tabela"] == nome_fato else "d1"}."{medida["coluna"]}") '
                        f'AS total\nFROM "{nome_fato}" f\n'
                        + ("" if medida["tabela"] == nome_fato else
                           f'LEFT JOIN "{medida["tabela"]}" d1 ON '
                           f'f."{joins[0]["coluna_origem"]}" = d1."{joins[0]["coluna_destino"]}"\n')
                        + "GROUP BY mes\nORDER BY mes;"
                    ),
                })

    return sugestoes[:MAX_ANALISES_SUGERIDAS]




def gerar_avisos(
    relacionamentos: list[dict[str, Any]], perfis: dict[str, PerfilTabela]
) -> list[dict[str, Any]]:
    avisos: list[dict[str, Any]] = []

    for relacao in relacionamentos:
        if relacao["pct_orfaos"] > 0:
            avisos.append({
                "severidade": "🔴 ALTA" if relacao["pct_orfaos"] > 0.05 else "🟡 MÉDIA",
                "tipo": "Integridade referencial",
                "mensagem": (
                    f"{relacao['pct_orfaos']:.1%} das linhas de "
                    f"`{relacao['tabela_origem']}.{relacao['coluna_origem']}` apontam para uma "
                    f"chave que não existe em "
                    f"`{relacao['tabela_destino']}.{relacao['coluna_destino']}` "
                    f"({1 - relacao['contencao']:.1%} dos valores distintos). "
                    "Esses registros somem num INNER JOIN."
                ),
            })
        if relacao["tipos_incompativeis"]:
            avisos.append({
                "severidade": "🔴 ALTA",
                "tipo": "Tipo incompatível na chave",
                "mensagem": (
                    f"`{relacao['tabela_origem']}.{relacao['coluna_origem']}` e "
                    f"`{relacao['tabela_destino']}.{relacao['coluna_destino']}` guardam a mesma "
                    "chave com tipos diferentes (texto × número). O join falha silenciosamente "
                    "sem um cast explícito."
                ),
            })

    isoladas = [n for n, p in perfis.items()
                if p.papel in ("Dimensão isolada", "Indefinida")]
    for nome in isoladas:
        avisos.append({
            "severidade": "🟡 MÉDIA",
            "tipo": "Tabela sem ligação",
            "mensagem": (
                f"`{nome}` não se liga a nenhuma outra tabela do conjunto: "
                f"{perfis[nome].justificativa}."
            ),
        })

    return avisos




def analisar_conjunto(tabelas: list[TabelaCarregada], nome_conjunto: str) -> dict[str, Any]:
    from datetime import UTC, datetime

    from . import __version__

    logger.info(f"Procurando chaves entre {len(tabelas)} tabelas...")
    relacionamentos = detectar_relacionamentos(tabelas)

    logger.info("Classificando o papel de cada tabela...")
    perfis = classificar_papeis(tabelas, relacionamentos)

    logger.info("Montando análises sugeridas...")
    analises = sugerir_analises(tabelas, relacionamentos, perfis)
    avisos = gerar_avisos(relacionamentos, perfis)

    granularidades = [
        {"tabela": t.nome, **grao}
        for t in tabelas
        if (grao := detectar_granularidade(t, relacionamentos)) is not None
    ]
    for grao in granularidades:
        if not grao["grao_unico"]:
            avisos.append({
                "severidade": "🔴 ALTA",
                "tipo": "Grão violado",
                "mensagem": (
                    f"`{grao['tabela']}` aparenta ter grão "
                    f"{', '.join(grao['colunas'])}, mas {grao['qtd_linhas_repetindo_grao']:,} "
                    f"linha(s) repetem essa combinação ({grao['pct_repetindo_grao']:.1%}). "
                    "Qualquer contagem por essa chave está inflada."
                ),
            })

    cobertura = analisar_cobertura_temporal(tabelas)
    if cobertura and not cobertura["tem_intersecao"]:
        avisos.append({
            "severidade": "🔴 ALTA", "tipo": "Sem sobreposição temporal",
            "mensagem": cobertura["descricao"],
        })

    return {
        "metadados_execucao": {
            "conjunto": nome_conjunto,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "versao_profiler": __version__,
            "schema_version": config.SCHEMA_VERSION,
            "total_tabelas": len(tabelas),
            "total_relacionamentos": len(relacionamentos),
            "total_analises_sugeridas": len(analises),
        },
        "tabelas": [
            {
                "nome": t.nome,
                "origem": t.origem,
                "linhas": t.payload["metadados_execucao"]["linhas_originais"],
                "colunas": t.payload["metadados_execucao"]["total_colunas"],
                "score_qualidade": t.payload["metadados_execucao"]["score_qualidade"]["score"],
                "papel": perfis[t.nome].papel,
                "justificativa": perfis[t.nome].justificativa,
                "chaves_primarias": perfis[t.nome].chaves_primarias,
                "medidas": perfis[t.nome].medidas,
                "atributos": perfis[t.nome].atributos,
                "datas": perfis[t.nome].datas,
            }
            for t in tabelas
        ],
        "relacionamentos": relacionamentos,
        "granularidade": granularidades,
        "cobertura_temporal": cobertura,
        "analises_sugeridas": analises,
        "avisos": avisos,
    }




def detectar_granularidade(
    tabela: TabelaCarregada, relacionamentos: list[dict[str, Any]]
) -> dict[str, Any] | None:
    fks = [r for r in relacionamentos if r["tabela_origem"] == tabela.nome]
    if not fks:
        return None

    colunas = sorted({r["coluna_origem"] for r in fks})
    if not colunas or any(c not in tabela.df.columns for c in colunas):
        return None

    entidades = []
    for coluna in colunas:
        destino = next(r["tabela_destino"] for r in fks if r["coluna_origem"] == coluna)
        entidades.append(destino)

    duplicadas = int(tabela.df.duplicated(subset=colunas).sum())
    total = len(tabela.df)
    return {
        "colunas": colunas,
        "entidades": entidades,
        "descricao": (
            "Cada linha representa um " + " × ".join(f"`{e}`" for e in entidades)
            + f" (chave de grão: {', '.join(f'`{c}`' for c in colunas)})."
        ),
        "grao_unico": duplicadas == 0,
        "qtd_linhas_repetindo_grao": duplicadas,
        "pct_repetindo_grao": round(duplicadas / total, 4) if total else 0.0,
    }




def analisar_cobertura_temporal(tabelas: list[TabelaCarregada]) -> dict[str, Any] | None:
    periodos: list[dict[str, Any]] = []
    for tabela in tabelas:
        for coluna in tabela.colunas:
            if coluna.get("Tipo_Inferred") != config.TIPO_DATA_HORA:
                continue
            extras = coluna.get("Stats_Extra") or {}
            if "min_data" not in extras:
                continue
            periodos.append({
                "tabela": tabela.nome,
                "coluna": coluna["Coluna"],
                "inicio": str(extras["min_data"])[:10],
                "fim": str(extras["max_data"])[:10],
            })
            break  

    if len(periodos) < 2:
        return None

    inicio_comum = max(p["inicio"] for p in periodos)
    fim_comum = min(p["fim"] for p in periodos)
    tem_intersecao = inicio_comum <= fim_comum
    return {
        "periodos": periodos,
        "intersecao_inicio": inicio_comum if tem_intersecao else None,
        "intersecao_fim": fim_comum if tem_intersecao else None,
        "tem_intersecao": tem_intersecao,
        "descricao": (
            f"As tabelas só se sobrepõem no tempo entre {inicio_comum} e {fim_comum} — "
            "qualquer análise conjunta fora dessa janela fica incompleta."
            if tem_intersecao else
            "As tabelas não têm nenhum período em comum: uma análise conjunta no tempo "
            "não é possível com estes recortes."
        ),
    }




def reconciliar(tabela_a: TabelaCarregada, tabela_b: TabelaCarregada) -> dict[str, Any]:
    colunas_a = {c["Coluna"] for c in tabela_a.colunas}
    colunas_b = {c["Coluna"] for c in tabela_b.colunas}

    resultado: dict[str, Any] = {
        "tabela_a": tabela_a.nome,
        "tabela_b": tabela_b.nome,
        "linhas_a": len(tabela_a.df),
        "linhas_b": len(tabela_b.df),
        "colunas_so_em_a": sorted(colunas_a - colunas_b),
        "colunas_so_em_b": sorted(colunas_b - colunas_a),
        "colunas_comuns": len(colunas_a & colunas_b),
    }

    chaves_a = _chaves_primarias(tabela_a.colunas)
    chave = next((c for c in chaves_a if c in colunas_b), None)
    if chave:
        valores_a = _conjunto_normalizado(tabela_a.df[chave])
        valores_b = _conjunto_normalizado(tabela_b.df[chave])
        resultado["chave_comparada"] = chave
        resultado["chaves_so_em_a"] = len(valores_a - valores_b)
        resultado["chaves_so_em_b"] = len(valores_b - valores_a)
        resultado["chaves_em_ambas"] = len(valores_a & valores_b)

    return resultado

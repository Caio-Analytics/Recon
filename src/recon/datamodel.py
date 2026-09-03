"""Inferência do modelo de dados a partir de um conjunto de tabelas.

Descobre chaves estrangeiras por contenção de valores, classifica cada
tabela como fato ou dimensão, monta o grafo de junção e sugere análises
concretas com o código pronto para rodar.

Usa contenção, não similaridade: uma FK está contida na PK (`FK ⊆ PK`), mas
raramente é igual a ela. Jaccard subestimaria relações em que a dimensão tem
valores não usados pelo fato, que é o caso normal.
"""
import keyword
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from loguru import logger
from rapidfuzz.distance import JaroWinkler

from . import config
from .semantics import normalizar

# ── Limiares ────────────────────────────────────────────────────────────────
# Contenção medida em valores distintos. O limiar é deliberadamente tolerante:
# uma chave estrangeira com 8% de linhas órfãs continua sendo uma chave
# estrangeira, e descartá-la faria o usuário não ver relação nenhuma — pior
# do que vê-la acompanhada de um aviso. O falso positivo é contido pelo
# conjunto de guardas (medida não é chave, cobertura mínima da dimensão,
# apoio do nome) e pelo limiar de confiança combinada.
CONTENCAO_MINIMA = 0.6
CONTENCAO_MINIMA_COM_APOIO_DE_NOME = 0.35
CONFIANCA_MINIMA_RELACAO = 0.6
# Domínios pequenos casam por acaso: qualquer coluna de 1 a 5 "está contida"
# em qualquer outra de 1 a 10. Abaixo disso só reporta se o nome corroborar.
MIN_DISTINTOS_CHAVE = 3
MIN_DISTINTOS_SEM_APOIO_DE_NOME = 10
# Fração mínima da dimensão que a chave estrangeira precisa cobrir para a
# relação ser plausível sem apoio do nome.
COBERTURA_MINIMA_DA_CHAVE = 0.05
MAX_DISTINTOS_COMPARADOS = 500_000
MAX_ANALISES_SUGERIDAS = 12

_PAPEL_MEDIDA = frozenset({"Valor Financeiro", "Quantidade / Métrica"})
# Ordem de interesse para virar eixo de análise: um total por diretoria diz
# mais do que um total por flag de status.
_PRIORIDADE_ATRIBUTO = (
    "Estrutura Organizacional", "Cargo / Função", "Localização Geográfica",
    "Curso / Treinamento", "Perfil do Colaborador", "Resultado de Avaliação",
    "Status / Indicador / Flag",
)
_MAX_CARDINALIDADE_ATRIBUTO = 100

# Medida não-aditiva: a soma não tem significado, a média tem. Medida aditiva
# (horas, valor) soma; razão ou escore não.
_TOKENS_NAO_ADITIVOS = frozenset({
    "nota", "score", "indice", "taxa", "percentual", "pct", "media", "ratio",
    "proporcao", "nivel", "aderencia", "satisfacao", "avaliacao", "peso",
})


def _agregacao_para(coluna: str) -> str:
    from .semantics import tokenizar
    return "mean" if set(tokenizar(coluna)) & _TOKENS_NAO_ADITIVOS else "sum"


@dataclass
class TabelaCarregada:
    """Uma tabela do conjunto: o DataFrame e o perfil que o `DataProfiler` já
    apurou sobre ela."""
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
    """Como a tabela se encaixa no modelo."""
    nome: str
    papel: str = "Indefinida"
    justificativa: str = ""
    chaves_primarias: list[str] = field(default_factory=list)
    medidas: list[str] = field(default_factory=list)
    atributos: list[str] = field(default_factory=list)
    datas: list[str] = field(default_factory=list)
    fks_saindo: int = 0
    referenciada_por: int = 0


# ── Chaves e conjuntos de valores ───────────────────────────────────────────

def _chaves_primarias(colunas: list[dict[str, Any]]) -> list[str]:
    """Candidatas a chave primária, com as identificadoras na frente.

    Um `nome_colaborador` sem repetição é formalmente uma chave candidata, mas
    ninguém usa nome de pessoa como chave. Quando existe alguma coluna com
    papel de identificador, só ela é reportada.
    """
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


def _conjunto_normalizado(
    serie: pd.Series, rotulo: str = "", avisos: list[dict[str, Any]] | None = None
) -> set[str]:
    """Valores distintos como texto canônico.

    A normalização é o que permite casar uma chave que virou `int64` num
    arquivo e ficou `str` no outro — situação corriqueira quando as duas
    extrações vêm de sistemas diferentes, e que faria o join falhar em
    silêncio.
    """
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
        # O corte é necessário (o casamento é por conjunto, em memória), mas em
        # silêncio ele mente: a contenção passa a ser medida contra uma chave
        # incompleta, sai subestimada, e a chave estrangeira pode simplesmente
        # não aparecer no relatório sem que nada explique por quê.
        mensagem = (
            f"`{rotulo or serie.name}` tem {len(distintos):,} valores distintos e o "
            f"casamento de chaves compara no máximo {MAX_DISTINTOS_COMPARADOS:,}. "
            "A contenção medida para esta coluna é um piso, não o valor exato — uma "
            "relação real pode ter ficado de fora."
        )
        logger.warning(mensagem)
        if avisos is not None:
            avisos.append({
                "severidade": "🟡 MÉDIA",
                "tipo": "Chave grande demais para comparar inteira",
                "mensagem": mensagem,
            })
        distintos = distintos[:MAX_DISTINTOS_COMPARADOS]
    return set(distintos)


def _contencao_por_linha(serie: pd.Series, valores_referencia: set[str]) -> float:
    """Fração das linhas preenchidas cujo valor existe na chave referenciada."""
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


# ── Detecção de relacionamentos ─────────────────────────────────────────────

def detectar_relacionamentos(
    tabelas: list[TabelaCarregada], avisos: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Procura chaves estrangeiras entre todas as tabelas do conjunto.

    Para cada coluna candidata a chave primária, testa que colunas das demais
    tabelas têm os seus valores contidos nela. O grau de contenção também mede
    quantos registros do fato apontam para uma chave que não existe na
    dimensão, problema de qualidade que não aparece analisando cada tabela
    isolada.
    """
    if len(tabelas) < 2:
        return []

    conjuntos: dict[tuple[str, str], set[str]] = {}

    def conjunto(tabela: TabelaCarregada, coluna: str) -> set[str]:
        chave = (tabela.nome, coluna)
        if chave not in conjuntos:
            conjuntos[chave] = _conjunto_normalizado(
                tabela.df[coluna], f"{tabela.nome}.{coluna}", avisos
            )
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

                    # O limiar de contenção depende do apoio do nome. Duas
                    # colunas chamadas `matricula` com metade dos valores
                    # batendo são a mesma chave com dado sujo; duas colunas de
                    # nomes distintos com metade batendo são coincidência.
                    contencao = len(valores_fk & valores_pk) / len(valores_fk)
                    limiar = (
                        CONTENCAO_MINIMA_COM_APOIO_DE_NOME if nome_apoia else CONTENCAO_MINIMA
                    )
                    if contencao < limiar:
                        continue

                    # Uma medida não é chave estrangeira. `carga_horaria` (2 a 40)
                    # está inteiramente contida em qualquer `id` sequencial que vá
                    # até 5.000 — contenção perfeita e relação inexistente.
                    if meta_fk.get("Papel") in _PAPEL_MEDIDA and not nome_apoia:
                        continue

                    # Domínio pequeno casa por acaso com domínio grande. Uma FK de
                    # verdade cobre uma fração relevante da dimensão que referencia.
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

                    # Contenção por linha mede quantas linhas se perderiam num
                    # INNER JOIN — métrica que a contenção por valor distinto
                    # distorce quando os órfãos são raros mas variados, ou
                    # frequentes mas repetidos.
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


# ── Chave estrangeira composta ──────────────────────────────────────────────

def _coluna_equivalente(origem: TabelaCarregada, nome: str) -> str | None:
    """Coluna da origem que corresponde a `nome` na tabela de destino."""
    if nome in origem.df.columns:
        return nome
    alvo = normalizar(nome)
    melhor, melhor_score = None, 0.0
    for meta in origem.colunas:
        candidato = meta["Coluna"]
        score = JaroWinkler.similarity(normalizar(candidato), alvo)
        if score > melhor_score:
            melhor, melhor_score = candidato, score
    return melhor if melhor_score >= 0.9 else None


def _tuplas_normalizadas(df: pd.DataFrame, colunas: list[str]) -> set[tuple[str, ...]]:
    recorte = df[colunas].dropna()
    if recorte.empty:
        return set()
    textos = [
        _conjunto_como_serie(recorte[c]) for c in colunas
    ]
    return set(zip(*[s.tolist() for s in textos], strict=True))


def _conjunto_como_serie(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return serie.map(lambda v: str(int(v)) if float(v).is_integer() else str(v))
    return serie.astype(str).str.strip()


def detectar_relacionamentos_compostos(
    tabelas: list[TabelaCarregada], ja_ligadas: set[tuple[str, str]]
) -> list[dict[str, Any]]:
    """Chaves estrangeiras de mais de uma coluna.

    Tabela de evento costuma se ligar à dimensão por um par (`empregado` +
    `curso`, `filial` + `produto`). Procurando só chave de uma coluna, essas
    ligações ficavam invisíveis e a tabela aparecia como "sem ligação com as
    demais" — conclusão errada sobre o modelo inteiro.
    """
    achados: list[dict[str, Any]] = []
    for destino in tabelas:
        for chave in (destino.payload.get("chaves_compostas") or [])[:4]:
            colunas_pk = list(chave.get("colunas") or [])
            if len(colunas_pk) < 2 or any(c not in destino.df.columns for c in colunas_pk):
                continue
            tuplas_pk = _tuplas_normalizadas(destino.df, colunas_pk)
            if len(tuplas_pk) < MIN_DISTINTOS_CHAVE:
                continue

            for origem in tabelas:
                if origem.nome == destino.nome:
                    continue
                if (origem.nome, destino.nome) in ja_ligadas:
                    continue  # já existe ligação simples entre as duas
                equivalentes = [_coluna_equivalente(origem, c) for c in colunas_pk]
                if any(v is None for v in equivalentes):
                    continue
                colunas_fk = [v for v in equivalentes if v is not None]
                if len(set(colunas_fk)) != len(colunas_pk):
                    continue
                tuplas_fk = _tuplas_normalizadas(origem.df, colunas_fk)
                if len(tuplas_fk) < MIN_DISTINTOS_CHAVE:
                    continue
                contencao = len(tuplas_fk & tuplas_pk) / len(tuplas_fk)
                if contencao < CONTENCAO_MINIMA:
                    continue
                achados.append({
                    "tabela_origem": origem.nome,
                    "colunas_origem": colunas_fk,
                    "tabela_destino": destino.nome,
                    "colunas_destino": colunas_pk,
                    "contencao": round(contencao, 4),
                    "pct_orfaos": round(1.0 - contencao, 4),
                    "descricao": (
                        f"`{origem.nome}` se liga a `{destino.nome}` pelo conjunto "
                        f"({', '.join(colunas_fk)}) → ({', '.join(colunas_pk)}): "
                        f"{contencao:.1%} das combinações existem no destino."
                    ),
                })
    achados.sort(key=lambda r: -r["contencao"])
    return achados


# ── Papel de cada tabela ────────────────────────────────────────────────────

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
    """Decide se cada tabela é fato, dimensão, ponte ou avulsa.

    O critério é estrutural, não pelo nome: uma tabela que aponta para várias
    outras e carrega medidas é um fato; uma que é apontada e tem chave própria
    é uma dimensão. Fato sem medida numérica não é anomalia — é tabela de
    evento (cada linha é uma ocorrência), e continua sendo o centro da
    análise.
    """
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


# ── Sugestão de análises ────────────────────────────────────────────────────

def _variavel(nome: str) -> str:
    limpo = "".join(ch if ch.isalnum() else "_" for ch in normalizar(nome)).strip("_")
    if not limpo:
        return "tabela"
    if limpo[0].isdigit() or keyword.iskeyword(limpo):
        return f"tabela_{limpo}"
    return limpo


def _literal_python(valor: str) -> str:
    """Literal seguro para nomes externos em código pandas gerado."""
    return repr(str(valor))


def _identificador_sql(valor: str) -> str:
    """Identificador SQL delimitado, inclusive quando contém aspas duplas."""
    return '"' + str(valor).replace('"', '""') + '"'


def _prioridade_atributo(meta: dict[str, Any] | None) -> tuple[int, int]:
    """Ordena os eixos de análise por utilidade.

    Entre `cd_dpto` e `diretoria` — mesmo domínio, mesma cardinalidade — o
    segundo é infinitamente mais legível num gráfico. Coluna com papel de
    código vai para o fim da fila.
    """
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
            f"    .merge({_variavel(join['tabela'])}, "
            f"left_on={_literal_python(join['coluna_origem'])}, "
            f"right_on={_literal_python(join['coluna_destino'])}, "
            f"how='left', suffixes=('', {_literal_python('_' + _variavel(join['tabela'])[:6])}))"
        )
    coluna_grupo = atributo["coluna"]
    if medida is None:
        linhas.append(f"    .groupby({_literal_python(coluna_grupo)}, as_index=False).size()")
        linhas.append('    .rename(columns={"size": "qtd_registros"})')
        linhas.append('    .sort_values("qtd_registros", ascending=False)')
    else:
        linhas.append(
            f"    .groupby({_literal_python(coluna_grupo)}, as_index=False)"
            f"[{_literal_python(medida['coluna'])}].{agregacao}()"
        )
        linhas.append(f"    .sort_values({_literal_python(medida['coluna'])}, ascending=False)")
    linhas.append(")")
    return "\n".join(linhas)


def _codigo_sql(
    base: str, joins: list[dict[str, Any]], medida: dict[str, Any] | None,
    atributo: dict[str, Any], agregacao: str,
) -> str:
    alias = {base: "f"}
    for i, join in enumerate(joins):
        alias[join["tabela"]] = f"d{i + 1}"
    coluna_grupo = f"{alias[atributo['tabela']]}.{_identificador_sql(atributo['coluna'])}"
    if medida is None:
        selecao = "COUNT(*) AS qtd_registros"
        ordem = "qtd_registros"
    else:
        agregador = "SUM" if agregacao == "sum" else "AVG"
        selecao = (
            f"{agregador}({alias[medida['tabela']]}.{_identificador_sql(medida['coluna'])}) "
            f"AS {_identificador_sql(agregacao + '_' + medida['coluna'])}"
        )
        ordem = _identificador_sql(f"{agregacao}_{medida['coluna']}")
    partes = [f"SELECT {coluna_grupo} AS {_identificador_sql(atributo['coluna'])}, {selecao}",
              f"FROM {_identificador_sql(base)} f"]
    for join in joins:
        partes.append(
            f"LEFT JOIN {_identificador_sql(join['tabela'])} {alias[join['tabela']]} "
            f"ON f.{_identificador_sql(join['coluna_origem'])} = "
            f"{alias[join['tabela']]}.{_identificador_sql(join['coluna_destino'])}"
        )
    partes.append(f"GROUP BY {coluna_grupo}")
    partes.append(f"ORDER BY {ordem} DESC;")
    return "\n".join(partes)


def sugerir_analises(
    tabelas: list[TabelaCarregada],
    relacionamentos: list[dict[str, Any]],
    perfis: dict[str, PerfilTabela],
) -> list[dict[str, Any]]:
    """Monta análises concretas a partir do modelo inferido.

    A medida não precisa morar no fato: numa base de treinamentos, a carga
    horária costuma estar na dimensão do curso, e o fato só registra quem fez
    o quê. Por isso as medidas consideradas incluem as das dimensões ligadas,
    cruzamento que não aparece analisando uma planilha por vez.
    """
    # Sem nenhuma chave em comum não existe análise cruzada — e sugerir
    # agregação de uma tabela só, num relatório que existe para descrever o
    # conjunto, repetiria o que o `perfilar` já entrega.
    if not relacionamentos:
        return []

    por_nome = {t.nome: t for t in tabelas}
    sugestoes: list[dict[str, Any]] = []

    fatos = [n for n, p in perfis.items() if p.papel.startswith("Fato")]
    if not fatos:
        # Sem fato identificado, a tabela mais referenciada ainda ancora as
        # análises do conjunto.
        fatos = [
            n for n, p in sorted(
                perfis.items(), key=lambda kv: -kv[1].referenciada_por
            )[:1]
        ]

    for nome_fato in fatos:
        perfil_fato = perfis[nome_fato]
        ligacoes = [r for r in relacionamentos if r["tabela_origem"] == nome_fato]

        # Medidas e atributos disponíveis a partir deste fato.
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
                        ".groupby('__mes__'",
                        f'.assign(__mes__=lambda d: pd.to_datetime(d["{data}"]).dt.to_period("M").astype(str))\n'
                        "    .groupby('__mes__'",
                    ),
                    # O agregador acompanha `_agregacao_para`: com `SUM` fixo,
                    # o SQL entregue ao lado do pandas somava a nota média — os
                    # dois trechos do mesmo relatório respondiam coisas
                    # diferentes.
                    "sql": (
                        f'SELECT DATE_TRUNC(\'month\', f."{data}") AS mes, '
                        f'{"SUM" if _agregacao_para(medida["coluna"]) == "sum" else "AVG"}'
                        f'({"f" if medida["tabela"] == nome_fato else "d1"}."{medida["coluna"]}") '
                        f'AS {_agregacao_para(medida["coluna"])}_{medida["coluna"]}\n'
                        f'FROM "{nome_fato}" f\n'
                        + ("" if medida["tabela"] == nome_fato else
                           f'LEFT JOIN "{medida["tabela"]}" d1 ON '
                           f'f."{joins[0]["coluna_origem"]}" = d1."{joins[0]["coluna_destino"]}"\n')
                        + "GROUP BY mes\nORDER BY mes;"
                    ),
                })

    return sugestoes[:MAX_ANALISES_SUGERIDAS]


# ── Avisos de integridade entre tabelas ─────────────────────────────────────

def gerar_avisos(
    relacionamentos: list[dict[str, Any]], perfis: dict[str, PerfilTabela],
    compostas: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Problemas que só aparecem quando as tabelas são olhadas juntas."""
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
                if p.papel in ("Dimensão isolada", "Indefinida")
                and n not in (compostas or set())]
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


# ── Orquestração ────────────────────────────────────────────────────────────

def analisar_conjunto(tabelas: list[TabelaCarregada], nome_conjunto: str) -> dict[str, Any]:
    """Produz o payload do modelo de dados inferido para o conjunto."""
    from datetime import UTC, datetime

    from . import __version__

    logger.info(f"Procurando chaves entre {len(tabelas)} tabelas...")
    avisos_chave: list[dict[str, Any]] = []
    relacionamentos = detectar_relacionamentos(tabelas, avisos_chave)

    ligadas = {(r["tabela_origem"], r["tabela_destino"]) for r in relacionamentos}
    compostos = detectar_relacionamentos_compostos(tabelas, ligadas)
    if compostos:
        logger.info(f"{len(compostos)} ligação(ões) por chave composta encontrada(s).")

    logger.info("Classificando o papel de cada tabela...")
    perfis = classificar_papeis(tabelas, relacionamentos)

    logger.info("Montando análises sugeridas...")
    analises = sugerir_analises(tabelas, relacionamentos, perfis)
    nomes_com_composta = {r["tabela_origem"] for r in compostos} | {
        r["tabela_destino"] for r in compostos
    }
    avisos = gerar_avisos(relacionamentos, perfis, nomes_com_composta) + avisos_chave
    for composto in compostos:
        if composto["pct_orfaos"] > 0.05:
            avisos.append({
                "severidade": "🟡 MÉDIA",
                "tipo": "Integridade referencial (chave composta)",
                "mensagem": (
                    f"{composto['pct_orfaos']:.1%} das combinações de "
                    f"({', '.join(composto['colunas_origem'])}) em "
                    f"`{composto['tabela_origem']}` não existem em `{composto['tabela_destino']}`."
                ),
            })

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
        "relacionamentos_compostos": compostos,
        "granularidade": granularidades,
        "cobertura_temporal": cobertura,
        "analises_sugeridas": analises,
        "avisos": avisos,
    }


# ── Granularidade ───────────────────────────────────────────────────────────

def detectar_granularidade(
    tabela: TabelaCarregada, relacionamentos: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Diz, numa frase, o que uma linha da tabela representa.

    "Cada linha é um (colaborador × curso)" sai de graça das chaves
    estrangeiras já detectadas. Junto vem a verificação de que o grão é
    realmente único: se o par se repete, qualquer contagem por colaborador
    está inflada, erro invisível olhando coluna a coluna.
    """
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


# ── Cobertura temporal cruzada ──────────────────────────────────────────────

def analisar_cobertura_temporal(tabelas: list[TabelaCarregada]) -> dict[str, Any] | None:
    """Compara os períodos cobertos por cada tabela do conjunto.

    Cruzar uma base que vai de 2018 a 2024 com outra que só tem 2023-2024 e
    concluir alguma coisa sobre 2019 é um erro clássico — e silencioso, porque
    o join funciona perfeitamente e só devolve menos linhas.
    """
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
            break  # uma coluna temporal por tabela basta para o recorte

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


# ── Reconciliação entre tabelas ─────────────────────────────────────────────

# Variação a partir da qual uma coluna comum entra no relatório de conferência.
VARIACAO_NULOS_RELEVANTE = 5.0     # em pontos percentuais
VARIACAO_CARDINALIDADE_RELEVANTE = 0.2   # 20% a mais ou a menos de valores distintos
MAX_CHAVES_LISTADAS = 20
LIMIAR_DRIFT_NUMERICO_IQR = 0.5
LIMIAR_DRIFT_CATEGORICO = 0.2


def _variacoes_de_coluna(
    tabela_a: TabelaCarregada, tabela_b: TabelaCarregada, comuns: set[str]
) -> list[dict[str, Any]]:
    """O que mudou nas colunas que existem nas duas versões.

    Coluna que sumiu do arquivo é fácil de ver; coluna que continua lá e parou
    de vir preenchida é o defeito silencioso de extração — o relatório da
    versão nova, sozinho, mostra 40% de nulos sem nada com que comparar.
    """
    variacoes: list[dict[str, Any]] = []
    for nome in sorted(comuns):
        meta_a, meta_b = tabela_a.meta(nome), tabela_b.meta(nome)
        if meta_a is None or meta_b is None:
            continue
        delta_nulos = float(meta_b.get("Pct_Nulos", 0)) - float(meta_a.get("Pct_Nulos", 0))
        unicos_a = int(meta_a.get("Qtd_Unicos", 0)) or 1
        unicos_b = int(meta_b.get("Qtd_Unicos", 0))
        delta_unicos = (unicos_b - unicos_a) / unicos_a
        mudou_tipo = meta_a.get("Tipo_Inferred") != meta_b.get("Tipo_Inferred")

        motivos: list[str] = []
        if mudou_tipo:
            motivos.append(
                f"tipo mudou de {meta_a.get('Tipo_Inferred')} para {meta_b.get('Tipo_Inferred')}"
            )
        if abs(delta_nulos) >= VARIACAO_NULOS_RELEVANTE:
            # Nulo subindo é preenchimento caindo: inverter aqui evita a frase
            # "o preenchimento subiu" para uma coluna que parou de vir.
            direcao = "caiu" if delta_nulos > 0 else "subiu"
            motivos.append(
                f"o preenchimento {direcao}: nulos passaram de "
                f"{meta_a.get('Pct_Nulos', 0):.1f}% para {meta_b.get('Pct_Nulos', 0):.1f}%"
            )
        if abs(delta_unicos) >= VARIACAO_CARDINALIDADE_RELEVANTE:
            motivos.append(
                f"valores distintos passaram de {unicos_a:,} para {unicos_b:,}"
            )
        if not motivos:
            continue
        variacoes.append({
            "coluna": nome,
            "tipo_a": meta_a.get("Tipo_Inferred"),
            "tipo_b": meta_b.get("Tipo_Inferred"),
            "pct_nulos_a": round(float(meta_a.get("Pct_Nulos", 0)), 2),
            "pct_nulos_b": round(float(meta_b.get("Pct_Nulos", 0)), 2),
            "unicos_a": unicos_a,
            "unicos_b": unicos_b,
            "mudou_tipo": mudou_tipo,
            "severidade": (
                "🔴 ALTA" if mudou_tipo or abs(delta_nulos) >= 20 else "🟡 MÉDIA"
            ),
            "descricao": "; ".join(motivos).capitalize() + ".",
        })
    return variacoes


def _drifts_de_distribuicao(
    tabela_a: TabelaCarregada, tabela_b: TabelaCarregada, comuns: set[str]
) -> list[dict[str, Any]]:
    """Mudanças relevantes na distribuição, mesmo quando o schema não mudou."""
    achados: list[dict[str, Any]] = []
    for nome in sorted(comuns):
        a, b = tabela_a.df[nome].dropna(), tabela_b.df[nome].dropna()
        if len(a) < 10 or len(b) < 10:
            continue
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            mediana_a, mediana_b = float(a.median()), float(b.median())
            iqr = float(a.quantile(0.75) - a.quantile(0.25))
            if iqr <= 0:
                continue
            intensidade = abs(mediana_b - mediana_a) / iqr
            if intensidade >= LIMIAR_DRIFT_NUMERICO_IQR:
                achados.append({
                    "coluna": nome, "tipo": "Distribuição numérica", "intensidade": round(intensidade, 3),
                    "descricao": (
                        f"Mediana mudou de {mediana_a:,.2f} para {mediana_b:,.2f} "
                        f"({intensidade:.1f} IQR da versão anterior)."
                    ),
                })
            continue
        if a.nunique() > 50 or b.nunique() > 50:
            continue
        pa, pb = a.astype(str).value_counts(normalize=True), b.astype(str).value_counts(normalize=True)
        categorias = pa.index.union(pb.index)
        distancia = 0.5 * sum(abs(float(pa.get(c, 0)) - float(pb.get(c, 0))) for c in categorias)
        if distancia >= LIMIAR_DRIFT_CATEGORICO:
            achados.append({
                "coluna": nome, "tipo": "Composição categórica", "intensidade": round(distancia, 3),
                "descricao": f"A composição das categorias mudou {distancia:.0%} (distância total).",
            })
    return achados


def reconciliar(tabela_a: TabelaCarregada, tabela_b: TabelaCarregada) -> dict[str, Any]:
    """Compara duas versões da mesma base.

    Serve para conferir duas extrações já em mãos — a base de janeiro contra a
    de fevereiro, por exemplo —, não para monitoramento contínuo. Interessa o
    que mudou de schema, quais chaves entraram e saíram, e que colunas mudaram
    de comportamento sem mudar de nome.
    """
    colunas_a = {c["Coluna"] for c in tabela_a.colunas}
    colunas_b = {c["Coluna"] for c in tabela_b.colunas}
    comuns = colunas_a & colunas_b

    linhas_a, linhas_b = len(tabela_a.df), len(tabela_b.df)
    resultado: dict[str, Any] = {
        "tabela_a": tabela_a.nome,
        "tabela_b": tabela_b.nome,
        "linhas_a": linhas_a,
        "linhas_b": linhas_b,
        "variacao_linhas": round((linhas_b - linhas_a) / linhas_a, 4) if linhas_a else None,
        "colunas_so_em_a": sorted(colunas_a - colunas_b),
        "colunas_so_em_b": sorted(colunas_b - colunas_a),
        "colunas_comuns": len(comuns),
        "variacoes_de_coluna": _variacoes_de_coluna(tabela_a, tabela_b, comuns),
        "drifts_de_distribuicao": _drifts_de_distribuicao(tabela_a, tabela_b, comuns),
    }

    chaves_a = _chaves_primarias(tabela_a.colunas)
    chave = next((c for c in chaves_a if c in colunas_b), None)
    if chave:
        valores_a = _conjunto_normalizado(tabela_a.df[chave], f"{tabela_a.nome}.{chave}")
        valores_b = _conjunto_normalizado(tabela_b.df[chave], f"{tabela_b.nome}.{chave}")
        sairam, entraram = valores_a - valores_b, valores_b - valores_a
        resultado.update({
            "chave_comparada": chave,
            "chaves_so_em_a": len(sairam),
            "chaves_so_em_b": len(entraram),
            "chaves_em_ambas": len(valores_a & valores_b),
            "exemplos_sairam": sorted(sairam)[:MAX_CHAVES_LISTADAS],
            "exemplos_entraram": sorted(entraram)[:MAX_CHAVES_LISTADAS],
        })
    else:
        resultado["chave_comparada"] = None
        resultado["motivo_sem_chave"] = (
            "Nenhuma coluna serve de chave nas duas versões (precisa ser única, sem nulo e "
            "existir nos dois arquivos). Sem chave dá para comparar schema e volume, mas não "
            "quais registros entraram e saíram."
        )

    resultado["avisos"] = _avisos_da_conferencia(resultado)
    return resultado


def _avisos_da_conferencia(resultado: dict[str, Any]) -> list[dict[str, Any]]:
    """O que merece atenção antes de usar a versão nova."""
    avisos: list[dict[str, Any]] = []
    if resultado["colunas_so_em_a"]:
        avisos.append({
            "severidade": "🔴 ALTA",
            "tipo": "Coluna sumiu",
            "mensagem": (
                f"{len(resultado['colunas_so_em_a'])} coluna(s) existiam em "
                f"`{resultado['tabela_a']}` e não vieram em `{resultado['tabela_b']}`: "
                f"{', '.join(resultado['colunas_so_em_a'][:6])}. "
                "Qualquer relatório que use essas colunas quebra."
            ),
        })
    if resultado["colunas_so_em_b"]:
        avisos.append({
            "severidade": "🟡 MÉDIA",
            "tipo": "Coluna nova",
            "mensagem": (
                f"{len(resultado['colunas_so_em_b'])} coluna(s) apareceram em "
                f"`{resultado['tabela_b']}`: {', '.join(resultado['colunas_so_em_b'][:6])}."
            ),
        })
    variacao = resultado.get("variacao_linhas")
    if variacao is not None and abs(variacao) >= 0.2:
        avisos.append({
            "severidade": "🔴 ALTA" if abs(variacao) >= 0.5 else "🟡 MÉDIA",
            "tipo": "Volume mudou muito",
            "mensagem": (
                f"O número de linhas {'subiu' if variacao > 0 else 'caiu'} {abs(variacao):.1%} "
                f"({resultado['linhas_a']:,} → {resultado['linhas_b']:,}). Confirme se o "
                "recorte da extração é o mesmo antes de comparar números."
            ),
        })
    graves = [v for v in resultado["variacoes_de_coluna"] if v["severidade"] == "🔴 ALTA"]
    if graves:
        avisos.append({
            "severidade": "🔴 ALTA",
            "tipo": "Coluna mudou de comportamento",
            "mensagem": (
                f"{len(graves)} coluna(s) continuam no arquivo mas mudaram de tipo ou de "
                f"preenchimento: {', '.join(v['coluna'] for v in graves[:6])}. "
                "É o defeito de extração que passa despercebido, porque o nome não mudou."
            ),
        })
    if resultado.get("drifts_de_distribuicao"):
        avisos.append({
            "severidade": "🟡 MÉDIA",
            "tipo": "Distribuição mudou",
            "mensagem": (
                f"{len(resultado['drifts_de_distribuicao'])} coluna(s) mantiveram o schema, "
                "mas mudaram materialmente de distribuição. Confirme se o recorte ou processo mudou."
            ),
        })
    return avisos

"""Relações entre colunas: dependências funcionais, colunas redundantes,
linhas duplicadas, chaves compostas, correlação e séries temporais.

Tudo aqui olha para pares (ou conjuntos) de colunas — por isso saiu de
`quality`, que ficou responsável só por transformar achados em recomendação.
"""
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from . import config, hypothesis

_CARACTERISTICAS_SEM_DADO = ("⚠️ Coluna 100% Vazia", "⚠️ Sem Valores Válidos")
_CORRELACAO_MAX_LINHAS = 50_000
_MAX_COLUNAS_CHAVE_COMPOSTA = 8


# ── Dependências funcionais ─────────────────────────────────────────────────

def _codificar(df: pd.DataFrame, colunas: Sequence[str]) -> dict[str, np.ndarray]:
    """Fatoriza cada coluna uma única vez em códigos inteiros.

    A versão anterior fazia um `groupby().nunique()` completo por par ordenado
    de colunas — o custo de fatorar era pago de novo a cada par. Com N colunas
    candidatas isso é O(N²) groupbys sobre o DataFrame inteiro, e era 17× o
    custo de todas as estatísticas descritivas somadas.
    """
    codigos: dict[str, np.ndarray] = {}
    for coluna in colunas:
        codes, _ = pd.factorize(df[coluna], use_na_sentinel=False)
        codigos[coluna] = np.asarray(codes, dtype=np.int64)
    return codigos


def _determina(codes_a: np.ndarray, codes_b: np.ndarray, n_a: int) -> bool:
    """Verifica se A → B: todo valor de A implica um único valor de B.

    Guarda o primeiro B visto para cada código de A e confere se a coluna
    inteira concorda. É O(n) sem ordenação — o teste equivalente por
    `groupby().nunique()` ou por contagem de pares distintos custa O(n log n)
    e paga overhead de pandas a cada par.
    """
    if n_a <= 0:
        return False
    primeiro = np.full(n_a, -1, dtype=np.int64)
    # Escrita reversa: a última atribuição vence, então percorrer ao contrário
    # deixa a primeira ocorrência de cada código de A registrada.
    primeiro[codes_a[::-1]] = codes_b[::-1]
    return bool(np.all(primeiro[codes_a] == codes_b))


def detectar_dependencias_funcionais(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Detecta `A → B` entre colunas de cardinalidade tratável.

    Uma bijeção (A → B e B → A) é reportada uma única vez como equivalência:
    são duas grafias do mesmo atributo, candidatas a virar uma tabela
    dimensão — semanticamente diferente de uma dependência de mão única.
    """
    candidatas = [
        m["Coluna"] for m in colunas_meta
        if m.get("Qtd_Unicos", 999_999) < config.FD_MAX_CARDINALIDADE
        and m.get("Caracteristica", "") not in _CARACTERISTICAS_SEM_DADO
        and m["Coluna"] in df.columns
    ]
    if len(candidatas) < 2:
        return []

    determinantes_validos = {
        m["Coluna"] for m in colunas_meta
        if m.get("Ratio_Unicidade", 1.0) < config.THRESHOLD_DETERMINANTE_MAX_UNICIDADE
    }
    # Uma coluna constante (Qtd_Unicos <= 1) é trivialmente "determinada" por
    # qualquer outra — não é uma FD interessante, é ruído.
    dependentes_validos = {m["Coluna"] for m in colunas_meta if m.get("Qtd_Unicos", 0) > 1}

    codigos = _codificar(df, candidatas)
    cardinalidades = {c: int(codigos[c].max()) + 1 if codigos[c].size else 0 for c in candidatas}

    achados: dict[tuple[str, str], bool] = {}
    for col_a in candidatas:
        if col_a not in determinantes_validos:
            continue
        for col_b in candidatas:
            if col_a == col_b or col_b not in dependentes_validos:
                continue
            # Condição necessária: A só pode determinar B se tiver ao menos
            # tantos valores distintos quanto B. É uma comparação de inteiros
            # já calculados e descarta cerca de metade dos pares sem tocar
            # nos dados.
            if cardinalidades[col_a] < cardinalidades[col_b]:
                continue
            if _determina(codigos[col_a], codigos[col_b], cardinalidades[col_a]):
                achados[(col_a, col_b)] = True

    dependencias: list[dict[str, Any]] = []
    ja_emitidos: set = set()
    for (col_a, col_b) in achados:
        if (col_a, col_b) in ja_emitidos:
            continue
        if achados.get((col_b, col_a)):
            ja_emitidos.update({(col_a, col_b), (col_b, col_a)})
            dependencias.append({
                "determinante": col_a,
                "dependente": col_b,
                "tipo": "Equivalência (Bijeção)",
                "descricao": (
                    f"'{col_a}' e '{col_b}' são equivalentes (1:1) — duas representações do "
                    "mesmo atributo. Candidatas a virar uma tabela dimensão própria."
                ),
            })
        else:
            ja_emitidos.add((col_a, col_b))
            dependencias.append({
                "determinante": col_a,
                "dependente": col_b,
                "tipo": "Dependência Funcional Direta",
                "descricao": (
                    f"'{col_a}' determina unicamente '{col_b}'. "
                    "Candidata à desnormalização ou chave composta."
                ),
            })
    return dependencias


# ── Linhas duplicadas ───────────────────────────────────────────────────────

def analisar_duplicatas(df: pd.DataFrame) -> dict[str, Any]:
    """Conta linhas integralmente repetidas.

    É a primeira pergunta de qualquer analista diante de uma extração nova, e
    o payload não tinha campo nenhum para ela.
    """
    total = len(df)
    if total == 0:
        return {"qtd_linhas_duplicadas": 0, "pct_linhas_duplicadas": 0.0, "qtd_grupos_duplicados": 0}
    try:
        marcadas = df.duplicated(keep="first")
    except TypeError:
        # Colunas com tipo não-hasheável (lista, dict) impedem a comparação.
        return {"qtd_linhas_duplicadas": 0, "pct_linhas_duplicadas": 0.0,
                "qtd_grupos_duplicados": 0, "motivo": "Colunas com tipos não comparáveis"}
    qtd = int(marcadas.sum())
    grupos = int(df.duplicated(keep=False).sum() - qtd) if qtd else 0
    return {
        "qtd_linhas_duplicadas": qtd,
        "pct_linhas_duplicadas": round(qtd / total, 4),
        "qtd_grupos_duplicados": grupos,
    }


# ── Colunas redundantes ─────────────────────────────────────────────────────

def detectar_colunas_redundantes(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Encontra colunas com conteúdo idêntico linha a linha.

    Compara primeiro por hash agregado (O(n) por coluna) e só confirma com
    igualdade elemento a elemento dentro de cada balde — evita o O(k²) de
    comparar todos os pares.
    """
    if df.shape[1] < 2:
        return []
    baldes: dict[Any, list[str]] = {}
    for coluna in df.columns:
        try:
            assinatura = int(pd.util.hash_pandas_object(df[coluna], index=False).sum())
        except TypeError:
            continue
        baldes.setdefault(assinatura, []).append(str(coluna))

    redundantes: list[dict[str, Any]] = []
    for colunas in baldes.values():
        if len(colunas) < 2:
            continue
        principal = colunas[0]
        for outra in colunas[1:]:
            if df[principal].equals(df[outra]):
                redundantes.append({
                    "coluna": principal,
                    "coluna_redundante": outra,
                    "descricao": f"'{outra}' é idêntica a '{principal}' — candidata a remoção.",
                })
    return redundantes


# ── Chave composta ──────────────────────────────────────────────────────────

def detectar_chaves_compostas(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]], max_pares: int = 3
) -> list[dict[str, Any]]:
    """Procura pares de colunas que juntos identificam a linha.

    Só roda quando nenhuma coluna sozinha é única — se já existe uma chave
    primária natural, a chave composta é informação redundante.
    """
    if any(m.get("Ratio_Unicidade", 0.0) == 1.0 for m in colunas_meta):
        return []
    total = len(df)
    if total < 2:
        return []

    ordenadas = sorted(
        (m for m in colunas_meta
         if m["Coluna"] in df.columns
         and m.get("Caracteristica", "") not in _CARACTERISTICAS_SEM_DADO
         and m.get("Qtd_Unicos", 0) > 1),
        key=lambda m: -m.get("Ratio_Unicidade", 0.0),
    )[:_MAX_COLUNAS_CHAVE_COMPOSTA]

    achados: list[dict[str, Any]] = []
    for i, meta_a in enumerate(ordenadas):
        for meta_b in ordenadas[i + 1:]:
            col_a, col_b = meta_a["Coluna"], meta_b["Coluna"]
            # Condição necessária: o produto das cardinalidades precisa
            # comportar todas as linhas.
            if meta_a.get("Qtd_Unicos", 0) * meta_b.get("Qtd_Unicos", 0) < total:
                continue
            if not df.duplicated(subset=[col_a, col_b]).any():
                achados.append({
                    "colunas": [col_a, col_b],
                    "descricao": (
                        f"'{col_a}' + '{col_b}' identificam unicamente cada linha — "
                        "candidata a chave primária composta."
                    ),
                })
                if len(achados) >= max_pares:
                    return achados
    return achados


# ── Correlação ──────────────────────────────────────────────────────────────

def _v_de_cramer(serie_a: pd.Series, serie_b: pd.Series) -> float | None:
    tabela = pd.crosstab(serie_a, serie_b)
    if tabela.shape[0] < 2 or tabela.shape[1] < 2:
        return None
    chi2 = float(scipy_stats.chi2_contingency(tabela.to_numpy(), correction=False)[0])
    n = int(tabela.to_numpy().sum())
    menor_dim = min(tabela.shape) - 1
    if n <= 0 or menor_dim <= 0:
        return None
    return float(np.sqrt(chi2 / (n * menor_dim)))


def _razao_correlacao(categorica: pd.Series, numerica: pd.Series) -> float | None:
    """Razão de correlação η: quanto da variância da numérica é explicada pela
    categórica. É o análogo do R² para o par categórica × numérica."""
    media_geral = float(numerica.mean())
    variancia_total = float(((numerica - media_geral) ** 2).sum())
    if variancia_total <= 0:
        return None
    grupos = numerica.groupby(categorica, observed=True)
    entre_grupos = float((grupos.count() * (grupos.mean() - media_geral) ** 2).sum())
    return float(np.sqrt(max(entre_grupos / variancia_total, 0.0)))


def analisar_correlacoes(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Mede associação entre pares de colunas, com a métrica adequada a cada
    combinação de tipos.

    Pearson/Spearman só respondem por numérica × numérica. Reduzir o relatório
    a isso deixa de fora exatamente as relações que importam em modelagem
    dimensional — por isso entram também o V de Cramér (categórica ×
    categórica) e a razão de correlação (categórica × numérica).
    """
    if len(df) < config.CORRELACAO_MIN_N:
        return []

    amostra = (
        df.sample(n=_CORRELACAO_MAX_LINHAS, random_state=42)
        if len(df) > _CORRELACAO_MAX_LINHAS else df
    )

    numericas = [
        m["Coluna"] for m in colunas_meta
        if "Número" in m.get("Tipo_Inferred", "")
        and m.get("Qtd_Unicos", 0) > 1
        and m["Coluna"] in df.columns
        and m.get("Dado_Sensivel_LGPD", "Nenhum") == "Nenhum"
    ]
    categoricas = [
        m["Coluna"] for m in colunas_meta
        if 1 < m.get("Qtd_Unicos", 0) <= config.CORRELACAO_MAX_CARDINALIDADE_CAT
        and m["Coluna"] in df.columns
        and m["Coluna"] not in numericas
    ]

    resultados: list[dict[str, Any]] = []

    if len(numericas) >= 2:
        bloco = amostra[numericas].apply(pd.to_numeric, errors="coerce")
        pearson = bloco.corr(method="pearson")
        spearman = bloco.corr(method="spearman")
        for i, col_a in enumerate(numericas):
            for col_b in numericas[i + 1:]:
                r = pearson.loc[col_a, col_b]
                rho = spearman.loc[col_a, col_b]
                if pd.isna(r) or abs(float(r)) < config.CORRELACAO_MIN_ABS:
                    continue
                resultados.append({
                    "coluna_a": col_a, "coluna_b": col_b,
                    "metrica": "Pearson / Spearman",
                    "valor": round(float(r), 4),
                    "valor_secundario": None if pd.isna(rho) else round(float(rho), 4),
                    "forca": "forte" if abs(float(r)) >= 0.9 else "moderada",
                })

    for i, col_a in enumerate(categoricas):
        for col_b in categoricas[i + 1:]:
            try:
                v = _v_de_cramer(amostra[col_a], amostra[col_b])
            except Exception:
                continue
            if v is None or v < config.CORRELACAO_MIN_ABS:
                continue
            resultados.append({
                "coluna_a": col_a, "coluna_b": col_b,
                "metrica": "V de Cramér",
                "valor": round(v, 4),
                "valor_secundario": None,
                "forca": "forte" if v >= 0.9 else "moderada",
            })

    for col_cat in categoricas:
        for col_num in numericas:
            try:
                eta = _razao_correlacao(amostra[col_cat], pd.to_numeric(amostra[col_num], errors="coerce").dropna())
            except Exception:
                continue
            if eta is None or eta < config.CORRELACAO_MIN_ABS:
                continue
            resultados.append({
                "coluna_a": col_cat, "coluna_b": col_num,
                "metrica": "Razão de correlação (η)",
                "valor": round(eta, 4),
                "valor_secundario": None,
                "forca": "forte" if eta >= 0.9 else "moderada",
            })

    resultados.sort(key=lambda r: -abs(r["valor"]))
    return resultados


# ── Séries temporais ────────────────────────────────────────────────────────

_FREQUENCIAS_AGREGACAO = (("D", "diária"), ("W", "semanal"), ("ME", "mensal"))
_MIN_PONTOS_AGREGADOS = config.ADF_MIN_N


def _escolher_coluna_referencia(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> tuple[str, pd.Series] | None:
    candidatas = [
        m for m in colunas_meta
        if m.get("Semantica_IA") == config.SEMANTICA_DATA_CALENDARIO
        or m.get("Papel") == config.SEMANTICA_DATA_CALENDARIO
    ]
    candidatas = [
        m for m in candidatas
        if m.get("Tipo_Inferred") == config.TIPO_DATA_HORA
        or m.get("Alertas", {}).get("data_como_texto") is True
    ]
    if not candidatas:
        return None

    col = min(candidatas, key=lambda m: m["Pct_Nulos"])["Coluna"]
    if col not in df.columns:
        return None

    serie = df[col]
    if pd.api.types.is_datetime64_any_dtype(serie):
        return col, serie

    # Data como texto (típico de CSV). `dayfirst` fixo invertia dia/mês em
    # arquivo com data ISO ou americana e emitia warning; aqui o formato é
    # inferido do próprio conteúdo e só cai para dia-primeiro se a leitura
    # padrão falhar em boa parte das linhas.
    convertida = pd.to_datetime(serie, errors="coerce", format="mixed")
    validas = convertida.notna().sum()
    if validas < len(serie) * 0.5:
        alternativa = pd.to_datetime(serie, errors="coerce", dayfirst=True, format="mixed")
        if alternativa.notna().sum() > validas:
            convertida = alternativa
    if convertida.notna().sum() == 0:
        return None
    return col, convertida


def analisar_series_temporais(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Testa estacionariedade e autocorrelação sobre a série *agregada* por
    período.

    Linhas transacionais não são uma série temporal: há várias linhas na mesma
    data e o espaçamento é irregular. Rodar ADF sobre a ordenação bruta testa a
    ordem arbitrária dentro de cada dia, não a dinâmica temporal. Agregar por
    dia/semana/mês antes é o que torna o teste interpretável.

    Colunas com característica de chave são excluídas: a estacionariedade de
    um ID sequencial não significa nada.
    """
    referencia = _escolher_coluna_referencia(df, colunas_meta)
    if referencia is None:
        return []
    col_referencia, datas = referencia

    colunas_numericas = [
        m["Coluna"] for m in colunas_meta
        if "Número" in m.get("Tipo_Inferred", "")
        and m["Coluna"] != col_referencia
        and m["Coluna"] in df.columns
        and "🔑" not in m.get("Caracteristica", "")
        and m.get("Dado_Sensivel_LGPD", "Nenhum") == "Nenhum"
        and m.get("Qtd_Unicos", 0) > 1
    ]
    if not colunas_numericas:
        return []

    base = pd.DataFrame({"__data__": datas})
    for coluna in colunas_numericas:
        base[coluna] = pd.to_numeric(df[coluna], errors="coerce").to_numpy()
    base = base.dropna(subset=["__data__"]).set_index("__data__").sort_index()
    if base.empty:
        return []

    # Escolhe a menor granularidade que ainda rende pontos suficientes para o
    # teste — diária quando o histórico é longo, mensal quando é curto.
    frequencia = None
    agregado = None
    for codigo, rotulo in _FREQUENCIAS_AGREGACAO:
        candidato = base.resample(codigo).mean()
        candidato = candidato.dropna(how="all")
        if len(candidato) >= _MIN_PONTOS_AGREGADOS:
            frequencia, agregado = rotulo, candidato
            break
    if agregado is None:
        return []
    if len(agregado) > config.ANALISE_TEMPORAL_MAX_PONTOS:
        agregado = agregado.iloc[-config.ANALISE_TEMPORAL_MAX_PONTOS:]

    resultados: list[dict[str, Any]] = []
    for coluna in colunas_numericas:
        serie = agregado[coluna].dropna()
        adf = hypothesis.testar_estacionariedade_adf(serie)
        ljung_box = hypothesis.testar_autocorrelacao_ljungbox(serie)
        if not adf.get("aplicavel") and not ljung_box.get("aplicavel"):
            continue
        resultados.append({
            "coluna": coluna,
            "coluna_temporal_referencia": col_referencia,
            "agregacao": frequencia,
            "n_pontos": int(len(serie)),
            "adf": adf,
            "ljung_box": ljung_box,
        })
    return resultados


# ── Hierarquias ─────────────────────────────────────────────────────────────

def detectar_hierarquias(
    dependencias: list[dict[str, Any]], min_niveis: int = 3
) -> list[dict[str, Any]]:
    """Encadeia dependências funcionais numa hierarquia navegável.

    As FDs já estão calculadas; encadeá-las é de graça e entrega o drill-down
    pronto: `celula → setor → diretoria` é a estrutura que alguém montaria à
    mão depois de olhar a tabela por meia hora.
    """
    proximo: dict[str, str] = {}
    for dep in dependencias:
        if dep["tipo"].startswith("Equivalência"):
            continue
        # Cada determinante aponta para um só nível acima; com vários, fica
        # ambíguo e é melhor não inventar hierarquia.
        if dep["determinante"] in proximo:
            proximo[dep["determinante"]] = ""
        else:
            proximo[dep["determinante"]] = dep["dependente"]

    validos = {k: v for k, v in proximo.items() if v}
    destinos = set(validos.values())
    cadeias: list[list[str]] = []
    for inicio in validos:
        if inicio in destinos:
            continue  # não é a base da cadeia
        cadeia, atual, visitados = [inicio], inicio, {inicio}
        while atual in validos and validos[atual] not in visitados:
            atual = validos[atual]
            cadeia.append(atual)
            visitados.add(atual)
        if len(cadeia) >= min_niveis:
            cadeias.append(cadeia)

    return [
        {
            "niveis": cadeia,
            "descricao": (
                "Hierarquia detectada: " + " → ".join(f"`{c}`" for c in cadeia)
                + ". Serve de caminho de drill-down numa análise."
            ),
        }
        for cadeia in cadeias
    ]


# ── O que explica cada medida ───────────────────────────────────────────────

def explicar_medidas(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]], top_n: int = 3
) -> list[dict[str, Any]]:
    """Ranqueia que atributo categórico melhor explica cada medida numérica.

    A razão de correlação (η) já existe como métrica de par; o que faltava era
    a leitura: em vez de listar pares acima de um limiar, dizer *"salário é
    explicado principalmente por cargo (η²=0,87), depois por diretoria
    (0,31)"*. Isso é insight, não estatística.
    """
    if len(df) < config.CORRELACAO_MIN_N:
        return []

    amostra = (
        df.sample(n=_CORRELACAO_MAX_LINHAS, random_state=42)
        if len(df) > _CORRELACAO_MAX_LINHAS else df
    )
    medidas = [
        m["Coluna"] for m in colunas_meta
        if m.get("Papel") in ("Valor Financeiro", "Quantidade / Métrica")
        and "Número" in m.get("Tipo_Inferred", "")
        and "🔑" not in m.get("Caracteristica", "")
        and m.get("Dado_Sensivel_LGPD", "Nenhum") == "Nenhum"
        and m["Coluna"] in df.columns
    ]
    atributos = [
        m["Coluna"] for m in colunas_meta
        if 1 < m.get("Qtd_Unicos", 0) <= config.CORRELACAO_MAX_CARDINALIDADE_CAT
        and m["Coluna"] in df.columns and m["Coluna"] not in medidas
    ]
    if not medidas or not atributos:
        return []

    resultados: list[dict[str, Any]] = []
    for medida in medidas:
        numerica = pd.to_numeric(amostra[medida], errors="coerce")
        validos = numerica.notna()
        if validos.sum() < config.CORRELACAO_MIN_N:
            continue
        explicacoes = []
        for atributo in atributos:
            try:
                eta = _razao_correlacao(amostra.loc[validos, atributo], numerica[validos])
            except Exception:
                continue
            if eta is None:
                continue
            explicacoes.append({"atributo": atributo, "eta_quadrado": round(eta ** 2, 4)})
        if not explicacoes:
            continue
        explicacoes.sort(key=lambda e: -e["eta_quadrado"])
        principal = explicacoes[0]
        if principal["eta_quadrado"] < 0.1:
            continue
        resultados.append({
            "medida": medida,
            "explicacoes": explicacoes[:top_n],
            "descricao": (
                f"`{medida}` é explicada principalmente por `{principal['atributo']}` "
                f"(η²={principal['eta_quadrado']:.2f}"
                + (f", depois por `{explicacoes[1]['atributo']}` "
                   f"(η²={explicacoes[1]['eta_quadrado']:.2f})" if len(explicacoes) > 1 else "")
                + ")."
            ),
        })
    resultados.sort(key=lambda r: -r["explicacoes"][0]["eta_quadrado"])
    return resultados

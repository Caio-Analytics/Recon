"""Regras de negócio inferidas a partir dos dados.

Uma dependência funcional diz que `cod_depto` determina `nome_depto`. Estas
regras vão além: dizem que `dt_demissao` nunca é anterior a `dt_admissao`,
que `vl_liquido` é `vl_bruto - vl_desconto`, e que `dt_demissao` só é
preenchida quando `status = 'Inativo'`.

São o achado mais acionável que dá para extrair de um profiling, por dois
motivos: descrevem o dado em linguagem de negócio (não de estatística), e as
*violações* são erros concretos com nome e sobrenome — "14 linhas com
demissão antes da admissão" é algo que se conserta hoje.

A regra só é reportada quando vale na esmagadora maioria das linhas. Uma
"regra" que falha em 30% dos casos não é regra, é coincidência.
"""
from itertools import combinations, permutations
from typing import Any

import numpy as np
import pandas as pd

from . import config

# Fração mínima de linhas que precisa obedecer para virar regra reportada.
CONFORMIDADE_MINIMA = 0.95
# Abaixo disso não há linhas suficientes para distinguir regra de acaso.
MIN_LINHAS_REGRA = 20
# Colunas consideradas em cada família — o teste de derivação é O(k³) e não
# vale a pena rodar sobre uma tabela com 80 colunas numéricas.
MAX_COLUNAS_DATA = 8
MAX_COLUNAS_NUMERICAS = 10
MAX_COLUNAS_CONDICIONAIS = 12
_MAX_LINHAS_AMOSTRA = 20_000
_TOLERANCIA_RELATIVA = 1e-6
_MAX_EXEMPLOS = 3


def _amostrar(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) > _MAX_LINHAS_AMOSTRA:
        return df.sample(n=_MAX_LINHAS_AMOSTRA, random_state=42)
    return df


def _colunas_por_tipo(colunas_meta: list[dict[str, Any]], df: pd.DataFrame):
    datas, numericas, categoricas = [], [], []
    for meta in colunas_meta:
        nome = meta["Coluna"]
        if nome not in df.columns or "Vazia" in meta.get("Caracteristica", ""):
            continue
        tipo = meta.get("Tipo_Inferred", "")
        # Data vinda de CSV chega como texto — exigir `Data / Hora` deixaria a
        # regra de ordem cega justamente no formato de entrada mais comum.
        if tipo == config.TIPO_DATA_HORA or meta.get("Alertas", {}).get("data_como_texto"):
            datas.append(nome)
        elif "Número" in tipo and "🔑" not in meta.get("Caracteristica", ""):
            if meta.get("Dado_Sensivel_LGPD", "Nenhum") == "Nenhum":
                numericas.append(nome)
        elif 1 < meta.get("Qtd_Unicos", 0) <= 25:
            categoricas.append(nome)
    return (datas[:MAX_COLUNAS_DATA], numericas[:MAX_COLUNAS_NUMERICAS],
            categoricas[:MAX_COLUNAS_CONDICIONAIS])


# ── Ordem entre datas ───────────────────────────────────────────────────────

def detectar_ordem_entre_datas(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Descobre que uma data sempre precede outra.

    `dt_admissao <= dt_demissao` é uma regra que ninguém escreve em lugar
    nenhum e que todo mundo assume. As violações são erro de digitação de ano
    ou troca de campo na carga — e passam despercebidas porque cada coluna,
    isolada, tem estatística perfeitamente normal.
    """
    datas, _, _ = _colunas_por_tipo(colunas_meta, df)
    if len(datas) < 2:
        return []

    amostra = _amostrar(df)
    # Normaliza para datetime uma única vez: comparar texto de data como
    # string funciona por acidente em ISO e falha em qualquer outro formato.
    convertidas = pd.DataFrame({
        coluna: (amostra[coluna] if pd.api.types.is_datetime64_any_dtype(amostra[coluna])
                 else pd.to_datetime(amostra[coluna], errors="coerce", format="mixed"))
        for coluna in datas
    })

    achados: list[dict[str, Any]] = []
    for col_a, col_b in combinations(datas, 2):
        par = convertidas[[col_a, col_b]].dropna()
        if len(par) < MIN_LINHAS_REGRA:
            continue
        for antes, depois in ((col_a, col_b), (col_b, col_a)):
            conforme = par[antes] <= par[depois]
            taxa = float(conforme.mean())
            if taxa < CONFORMIDADE_MINIMA or taxa == 0.0:
                continue
            violacoes = par[~conforme]
            achados.append({
                "tipo": "Ordem entre datas",
                "regra": f"`{antes}` <= `{depois}`",
                "descricao": (
                    f"'{antes}' nunca é posterior a '{depois}'"
                    if violacoes.empty else
                    f"'{antes}' é posterior a '{depois}' em {len(violacoes)} linha(s)"
                ),
                "conformidade": round(taxa, 4),
                "qtd_violacoes": int(len(violacoes)),
                "exemplos_violacao": [
                    {antes: str(linha[antes]), depois: str(linha[depois])}
                    for _, linha in violacoes.head(_MAX_EXEMPLOS).iterrows()
                ],
            })
            break  # só um sentido pode valer
    return achados


# ── Nulidade condicional ────────────────────────────────────────────────────

def detectar_nulidade_condicional(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Descobre que uma coluna só é preenchida em certos casos.

    `dt_demissao` preenchida apenas quando `status = 'Inativo'` não é dado
    faltante — é a regra de negócio do cadastro. Sem essa leitura, a coluna
    aparece como "93% de nulos" e parece um problema grave quando não é.
    """
    _, _, categoricas = _colunas_por_tipo(colunas_meta, df)
    if not categoricas:
        return []

    amostra = _amostrar(df)
    achados: list[dict[str, Any]] = []
    for meta in colunas_meta:
        alvo = meta["Coluna"]
        if alvo not in amostra.columns or alvo in categoricas:
            continue
        pct_nulos = meta.get("Pct_Nulos", 0.0) / 100
        if not (0.1 < pct_nulos < 0.95):
            continue

        preenchida = amostra[alvo].notna()
        for condicional in categoricas:
            grupos = preenchida.groupby(amostra[condicional], observed=True).mean()
            if len(grupos) < 2:
                continue
            sempre = [str(v) for v, taxa in grupos.items() if taxa >= CONFORMIDADE_MINIMA]
            nunca = [str(v) for v, taxa in grupos.items() if taxa <= 1 - CONFORMIDADE_MINIMA]
            if not sempre or not nunca or len(sempre) + len(nunca) < len(grupos):
                continue
            achados.append({
                "tipo": "Nulidade condicional",
                "regra": f"`{alvo}` preenchida ⟺ `{condicional}` ∈ {{{', '.join(sempre)}}}",
                "descricao": (
                    f"'{alvo}' está preenchida sempre que '{condicional}' é "
                    f"{', '.join(sempre)}, e sempre vazia quando é {', '.join(nunca)}. "
                    f"Os {pct_nulos:.0%} de nulos são regra de negócio, não dado faltante."
                ),
                "conformidade": 1.0,
                "qtd_violacoes": 0,
                "exemplos_violacao": [],
            })
            break
    return achados


# ── Derivação aritmética ────────────────────────────────────────────────────

_OPERACOES = (
    ("+", lambda a, b: a + b),
    ("-", lambda a, b: a - b),
    ("*", lambda a, b: a * b),
)


def detectar_derivacao_aritmetica(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Descobre que uma coluna é calculada a partir de outras duas.

    `vl_liquido = vl_bruto - vl_desconto` significa que a coluna é redundante
    — e que qualquer linha que não fecha é erro de cálculo na origem. Saber
    disso muda o que se recalcula e o que se confia.
    """
    _, numericas, _ = _colunas_por_tipo(colunas_meta, df)
    if len(numericas) < 3:
        return []

    amostra = _amostrar(df)[numericas].apply(pd.to_numeric, errors="coerce")
    amostra = amostra.dropna()
    if len(amostra) < MIN_LINHAS_REGRA:
        return []

    achados: list[dict[str, Any]] = []
    ja_explicadas: set[str] = set()
    # `a = b + c`, `b = a - c` e `c = a - b` são a mesma relação dita de três
    # formas. Reportar as três é ruído: uma por trio de colunas basta.
    trios_reportados: set[frozenset[str]] = set()
    for alvo in numericas:
        if alvo in ja_explicadas:
            continue
        candidatas = [c for c in numericas if c != alvo]
        for esquerda, direita in permutations(candidatas, 2):
            for simbolo, operacao in _OPERACOES:
                # `a + b` e `b + a` são a mesma regra: só testa uma ordem.
                if simbolo in "+*" and esquerda > direita:
                    continue
                previsto = operacao(amostra[esquerda], amostra[direita])
                bate = np.isclose(
                    amostra[alvo], previsto, rtol=_TOLERANCIA_RELATIVA, atol=1e-9
                )
                taxa = float(bate.mean())
                if taxa < CONFORMIDADE_MINIMA:
                    continue
                # Regra trivial: se a operação é sempre com zero, não informa nada.
                if simbolo in "+-" and float(amostra[direita].abs().sum()) == 0.0:
                    continue
                trio = frozenset((alvo, esquerda, direita))
                if trio in trios_reportados:
                    continue
                trios_reportados.add(trio)
                violacoes = amostra[~bate]
                achados.append({
                    "tipo": "Derivação aritmética",
                    "regra": f"`{alvo}` = `{esquerda}` {simbolo} `{direita}`",
                    "descricao": (
                        f"'{alvo}' é calculada a partir de '{esquerda}' e '{direita}' "
                        + ("em todas as linhas — é coluna redundante."
                           if violacoes.empty else
                           f"em {taxa:.1%} das linhas; {len(violacoes)} não fecham a conta.")
                    ),
                    "conformidade": round(taxa, 4),
                    "qtd_violacoes": int(len(violacoes)),
                    "exemplos_violacao": [
                        {
                            alvo: round(float(linha[alvo]), 4),
                            esquerda: round(float(linha[esquerda]), 4),
                            direita: round(float(linha[direita]), 4),
                        }
                        for _, linha in violacoes.head(_MAX_EXEMPLOS).iterrows()
                    ],
                })
                ja_explicadas.add(alvo)
                break
            if alvo in ja_explicadas:
                break
    return achados


# ── Orquestração ────────────────────────────────────────────────────────────

def inferir_regras(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Roda todas as famílias de regra e devolve as violações na frente.

    Regra com violação é achado acionável; regra perfeita é documentação do
    dado. As duas interessam, mas em ordens diferentes.
    """
    if len(df) < MIN_LINHAS_REGRA:
        return []
    regras: list[dict[str, Any]] = []
    regras += detectar_ordem_entre_datas(df, colunas_meta)
    regras += detectar_nulidade_condicional(df, colunas_meta)
    regras += detectar_derivacao_aritmetica(df, colunas_meta)
    regras.sort(key=lambda r: (r["qtd_violacoes"] == 0, -r["qtd_violacoes"]))
    return regras

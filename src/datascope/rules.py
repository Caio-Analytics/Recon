from itertools import combinations, permutations
from typing import Any

import numpy as np
import pandas as pd

from . import config


CONFORMIDADE_MINIMA = 0.95

MIN_LINHAS_REGRA = 20


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
        
        
        if tipo == config.TIPO_DATA_HORA or meta.get("Alertas", {}).get("data_como_texto"):
            datas.append(nome)
        elif "Número" in tipo and "🔑" not in meta.get("Caracteristica", ""):
            if meta.get("Dado_Sensivel_LGPD", "Nenhum") == "Nenhum":
                numericas.append(nome)
        elif 1 < meta.get("Qtd_Unicos", 0) <= 25:
            categoricas.append(nome)
    return (datas[:MAX_COLUNAS_DATA], numericas[:MAX_COLUNAS_NUMERICAS],
            categoricas[:MAX_COLUNAS_CONDICIONAIS])




def detectar_ordem_entre_datas(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    datas, _, _ = _colunas_por_tipo(colunas_meta, df)
    if len(datas) < 2:
        return []

    amostra = _amostrar(df)
    
    
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
            break  
    return achados




def detectar_nulidade_condicional(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
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




_OPERACOES = (
    ("+", lambda a, b: a + b),
    ("-", lambda a, b: a - b),
    ("*", lambda a, b: a * b),
)


def detectar_derivacao_aritmetica(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    _, numericas, _ = _colunas_por_tipo(colunas_meta, df)
    if len(numericas) < 3:
        return []

    amostra = _amostrar(df)[numericas].apply(pd.to_numeric, errors="coerce")
    amostra = amostra.dropna()
    if len(amostra) < MIN_LINHAS_REGRA:
        return []

    achados: list[dict[str, Any]] = []
    ja_explicadas: set[str] = set()
    
    
    trios_reportados: set[frozenset[str]] = set()
    for alvo in numericas:
        if alvo in ja_explicadas:
            continue
        candidatas = [c for c in numericas if c != alvo]
        for esquerda, direita in permutations(candidatas, 2):
            for simbolo, operacao in _OPERACOES:
                
                if simbolo in "+*" and esquerda > direita:
                    continue
                previsto = operacao(amostra[esquerda], amostra[direita])
                bate = np.isclose(
                    amostra[alvo], previsto, rtol=_TOLERANCIA_RELATIVA, atol=1e-9
                )
                taxa = float(bate.mean())
                if taxa < CONFORMIDADE_MINIMA:
                    continue
                
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




def inferir_regras(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(df) < MIN_LINHAS_REGRA:
        return []
    regras: list[dict[str, Any]] = []
    regras += detectar_ordem_entre_datas(df, colunas_meta)
    regras += detectar_nulidade_condicional(df, colunas_meta)
    regras += detectar_derivacao_aritmetica(df, colunas_meta)
    regras.sort(key=lambda r: (r["qtd_violacoes"] == 0, -r["qtd_violacoes"]))
    return regras

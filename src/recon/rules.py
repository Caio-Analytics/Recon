from datetime import UTC, datetime
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


def _tokens_nome(nome: str) -> set[str]:
    from .semantics import tokenizar

    return set(tokenizar(nome))


def _regra_de_faixa(
    serie: pd.Series, coluna: str, minimo: float, maximo: float,
    pacote: str, descricao: str,
) -> dict[str, Any] | None:
    valores = pd.to_numeric(serie, errors="coerce").dropna()
    if len(valores) < MIN_LINHAS_REGRA:
        return None
    conforme = valores.between(minimo, maximo)
    taxa = float(conforme.mean())
    if taxa < CONFORMIDADE_MINIMA:
        return None
    violacoes = valores[~conforme]
    return {
        "tipo": f"Regra de {pacote}", "pacote": pacote,
        "regra": f"`{coluna}` entre {minimo:g} e {maximo:g}",
        "descricao": descricao if violacoes.empty else f"{descricao} Há {len(violacoes)} valor(es) fora da faixa.",
        "conformidade": round(taxa, 4), "qtd_violacoes": int(len(violacoes)),
        "exemplos_violacao": [{coluna: float(valor)} for valor in violacoes.head(_MAX_EXEMPLOS)],
    }


def detectar_regras_por_pacote(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(df) < MIN_LINHAS_REGRA:
        return []
    achados: list[dict[str, Any]] = []
    nomes = {nome: _tokens_nome(nome) for nome in df.columns}

    
    descontos = [nome for nome, tokens in nomes.items() if {"desconto", "discount"} & tokens]
    brutos = [nome for nome, tokens in nomes.items() if {"bruto", "gross"} & tokens]
    if descontos and brutos:
        desconto, bruto = descontos[0], brutos[0]
        pares = df[[desconto, bruto]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pares) >= MIN_LINHAS_REGRA:
            conforme = (pares[desconto] >= 0) & (pares[desconto] <= pares[bruto])
            taxa = float(conforme.mean())
            if taxa >= CONFORMIDADE_MINIMA:
                erros = pares[~conforme]
                achados.append({
                    "tipo": "Regra de Financeiro", "pacote": "Financeiro",
                    "regra": f"`{desconto}` entre 0 e `{bruto}`",
                    "descricao": (
                        "O desconto é compatível com o valor bruto."
                        if erros.empty else f"{len(erros)} linha(s) têm desconto negativo ou acima do bruto."
                    ),
                    "conformidade": round(taxa, 4), "qtd_violacoes": int(len(erros)),
                    "exemplos_violacao": erros.head(_MAX_EXEMPLOS).to_dict("records"),
                })

    
    for nome, tokens in nomes.items():
        if {"estoque", "inventory", "stock"} & tokens:
            regra = _regra_de_faixa(
                df[nome], nome, 0, float("inf"), "Logística",
                "O estoque físico não deveria ficar negativo; confirme baixas, devoluções e ajustes.",
            )
            if regra:
                achados.append(regra)
            break

    
    for nome, tokens in nomes.items():
        if {"idade", "age"} & tokens:
            regra = _regra_de_faixa(
                df[nome], nome, 0, 130, "Saúde",
                "A idade está dentro de uma faixa humana plausível; confira valores extremos na origem.",
            )
            if regra:
                achados.append(regra)
            break

    
    limite_ano = datetime.now(UTC).year + 1
    for nome, tokens in nomes.items():
        if "ano" in tokens and ({"exercicio", "referencia", "competencia"} & tokens):
            regra = _regra_de_faixa(
                df[nome], nome, 1900, limite_ano, "Dados públicos",
                "O ano de referência está dentro do período esperado para publicação e prestação de contas.",
            )
            if regra:
                achados.append(regra)
            break

    
    prazos = [nome for nome, tokens in nomes.items() if {"sla", "prazo", "deadline"} & tokens]
    fins = [nome for nome, tokens in nomes.items() if {"resolucao", "conclusao", "fechamento", "encerramento"} & tokens]
    if prazos and fins:
        prazo, fim = prazos[0], fins[0]
        pares = pd.DataFrame({
            prazo: pd.to_datetime(df[prazo], errors="coerce", format="mixed"),
            fim: pd.to_datetime(df[fim], errors="coerce", format="mixed"),
        }).dropna()
        if len(pares) >= MIN_LINHAS_REGRA:
            conforme = pares[fim] <= pares[prazo]
            taxa = float(conforme.mean())
            if taxa >= CONFORMIDADE_MINIMA:
                erros = pares[~conforme]
                achados.append({
                    "tipo": "Regra de Suporte", "pacote": "Suporte / SLA",
                    "regra": f"`{fim}` <= `{prazo}`",
                    "descricao": "Os chamados foram concluídos até o prazo de SLA." if erros.empty else (
                        f"{len(erros)} chamado(s) foram concluídos após o prazo de SLA."
                    ),
                    "conformidade": round(taxa, 4), "qtd_violacoes": int(len(erros)),
                    "exemplos_violacao": erros.head(_MAX_EXEMPLOS).astype(str).to_dict("records"),
                })
    return achados


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




def _sem_zero(serie: pd.Series) -> pd.Series:
    return serie.where(serie != 0)





_OPERACOES = (
    ("+", lambda a, b: a + b, "`{a}` + `{b}`"),
    ("-", lambda a, b: a - b, "`{a}` - `{b}`"),
    ("*", lambda a, b: a * b, "`{a}` × `{b}`"),
    ("/", lambda a, b: a / _sem_zero(b), "`{a}` ÷ `{b}`"),
    ("%", lambda a, b: a * b / 100.0, "`{a}` × `{b}`% (percentual em escala 0-100)"),
    ("1-", lambda a, b: a * (1 - b), "`{a}` × (1 − `{b}`)"),
    ("1-%", lambda a, b: a * (1 - b / 100.0), "`{a}` × (1 − `{b}`%), percentual em escala 0-100"),
)
_COMUTATIVAS = frozenset({"+", "*", "%"})






_TOKENS_DERIVADO = frozenset({
    "liquido", "total", "final", "saldo", "resultado", "geral", "efetivo",
    "acumulado", "subtotal", "devido", "pagar", "receber",
})
_TOKENS_PARCELA = frozenset({
    "bruto", "base", "inicial", "taxa", "percentual", "pct", "aliquota",
    "desconto", "acrescimo",
})



_TOKENS_CONTAGEM = frozenset({"quantidade", "qtd", "qtde", "contagem", "num", "numero"})


def _pontuacao_derivado(nome: str) -> int:
    from .semantics import tokenizar

    tokens = set(tokenizar(nome))
    return (
        (2 if tokens & _TOKENS_DERIVADO else 0)
        - (1 if tokens & _TOKENS_PARCELA else 0)
        - (2 if tokens & _TOKENS_CONTAGEM else 0)
    )


def detectar_derivacao_aritmetica(
    df: pd.DataFrame, colunas_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    _, numericas, _ = _colunas_por_tipo(colunas_meta, df)
    if len(numericas) < 3:
        return []

    base = _amostrar(df)[numericas].apply(pd.to_numeric, errors="coerce")

    achados: list[dict[str, Any]] = []
    explicadas: set[str] = set()
    for trio in combinations(numericas, 3):
        
        
        
        
        if all(c in explicadas for c in trio):
            continue
        
        
        
        
        dados = base[list(trio)].dropna()
        if len(dados) < MIN_LINHAS_REGRA:
            continue

        candidatos: list[tuple[int, float, dict[str, Any]]] = []
        for alvo in trio:
            if alvo in explicadas:
                continue
            outros = [c for c in trio if c != alvo]
            for esquerda, direita in permutations(outros, 2):
                for simbolo, operacao, modelo in _OPERACOES:
                    
                    if simbolo in _COMUTATIVAS and esquerda > direita:
                        continue
                    previsto = operacao(dados[esquerda], dados[direita]).to_numpy()
                    aplicavel = np.isfinite(previsto)
                    if aplicavel.sum() < MIN_LINHAS_REGRA:
                        continue
                    bate = np.isclose(
                        dados[alvo].to_numpy(), previsto,
                        rtol=_TOLERANCIA_RELATIVA, atol=1e-9,
                    ) & aplicavel
                    taxa = float(bate.sum() / aplicavel.sum())
                    if taxa < CONFORMIDADE_MINIMA:
                        continue
                    
                    if simbolo in "+-" and float(dados[direita].abs().sum()) == 0.0:
                        continue
                    expressao = modelo.format(a=esquerda, b=direita)
                    violacoes = dados[aplicavel & ~bate]
                    candidatos.append((
                        _pontuacao_derivado(alvo), taxa,
                        {
                            "tipo": "Derivação aritmética",
                            "regra": f"`{alvo}` = {expressao}",
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
                            "_alvo": alvo,
                        },
                    ))
        if not candidatos:
            continue
        
        
        
        candidatos.sort(key=lambda c: (-c[0], -c[1]))
        melhor = candidatos[0][2]
        explicadas.add(melhor.pop("_alvo"))
        achados.append(melhor)
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
    regras += detectar_regras_por_pacote(df, colunas_meta)
    regras.sort(key=lambda r: (r["qtd_violacoes"] == 0, -r["qtd_violacoes"]))
    return regras

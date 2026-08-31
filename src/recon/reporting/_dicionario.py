"""Dicionário de dados em XLSX.

Formato para distribuição: anexado a chamados, filtrado pelo gestor por
conta própria, usado como documentação oficial da base. O conteúdo já está
inteiro no payload; falta o arquivo num formato que as pessoas já sabem
abrir.

Uma aba por tabela, uma linha por coluna, mais uma aba de resumo quando há
mais de uma tabela.
"""
from collections.abc import Sequence
from typing import Any

import pandas as pd
from loguru import logger

_COLUNAS = (
    ("Coluna", "Coluna"),
    ("Tipo", "Tipo_Inferred"),
    ("Semântica", "Semantica_IA"),
    ("Papel", "Papel"),
    ("Domínio", "Dominio"),
    ("Característica", "Caracteristica"),
    ("Valores distintos", "Qtd_Unicos"),
    ("% nulos", "Pct_Nulos"),
    ("Dado pessoal", "Dado_Sensivel_LGPD"),
    ("Exemplos", "Amostra_Valores"),
)
_LARGURAS = (28, 18, 24, 22, 22, 26, 16, 10, 16, 52)
_MAX_ABA = 31  # limite do Excel para nome de aba


def _linhas_da_tabela(payload: dict[str, Any]) -> pd.DataFrame:
    registros = []
    for coluna in payload["colunas"]:
        registro = {rotulo: coluna.get(chave, "") for rotulo, chave in _COLUNAS}
        registro["Exemplos"] = str(registro["Exemplos"])[:300]
        registros.append(registro)
    return pd.DataFrame(registros)


def _resumo(payloads: Sequence[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Tabela": p["metadados_execucao"]["tabela"],
            "Linhas": p["metadados_execucao"]["linhas_originais"],
            "Colunas": p["metadados_execucao"]["total_colunas"],
            "Score de qualidade": p["metadados_execucao"]["score_qualidade"]["score"],
            "Nota": p["metadados_execucao"]["score_qualidade"]["nota"],
            "Exposição LGPD": (p["metadados_execucao"].get("risco_lgpd") or {}).get("nivel", "—"),
            "Recomendações": len(p.get("recomendacoes_etl", [])),
        }
        for p in payloads
    ])


def _nome_de_aba(nome: str, usados: set[str]) -> str:
    limpo = "".join(c for c in str(nome) if c not in "[]:*?/\\")[:_MAX_ABA] or "tabela"
    base, sufixo = limpo, 2
    while limpo in usados:
        corte = _MAX_ABA - len(str(sufixo)) - 1
        limpo = f"{base[:corte]}_{sufixo}"
        sufixo += 1
    usados.add(limpo)
    return limpo


def exportar_dicionario_xlsx(payloads: Sequence[dict[str, Any]], caminho: str) -> None:
    """Grava o dicionário de dados de uma ou mais tabelas."""
    if not payloads:
        raise ValueError("Nenhuma tabela para documentar.")

    usados: set[str] = set()
    with pd.ExcelWriter(caminho, engine="openpyxl") as escritor:
        if len(payloads) > 1:
            _resumo(payloads).to_excel(escritor, sheet_name="Resumo", index=False)
        for payload in payloads:
            aba = _nome_de_aba(payload["metadados_execucao"]["tabela"], usados)
            quadro = _linhas_da_tabela(payload)
            quadro.to_excel(escritor, sheet_name=aba, index=False)
            planilha = escritor.sheets[aba]
            # Congelar o cabeçalho e ligar o filtro: sem isso, ninguém navega
            # uma tabela de 70 colunas no Excel.
            planilha.freeze_panes = "A2"
            planilha.auto_filter.ref = planilha.dimensions
            for indice, largura in enumerate(_LARGURAS, start=1):
                planilha.column_dimensions[
                    planilha.cell(row=1, column=indice).column_letter
                ].width = largura
    logger.info(f"✓ Dicionário de dados exportado: '{caminho}' ({len(payloads)} tabela(s))")

"""Qualidade de dados: dependências funcionais, gap analysis de KPI e recomendações ETL."""
from typing import Any, Dict, List, Set

import pandas as pd

from . import config

_REGRAS_KPI: List[Dict[str, Any]] = [
    {"id": "KPI_HR_001", "nome": "Volume de Esforço por Departamento",
     "semanticas": ["Estrutura Organizacional", "Quantidade / Métrica"]},
    {"id": "KPI_HR_002", "nome": "Distribuição de Liderança por Perfil",
     "semanticas": ["Perfil do Colaborador", "Cargo / Função"]},
    {"id": "KPI_HR_003", "nome": "Evolução de Custo de Pessoal",
     "semanticas": ["Valor Financeiro", "Data / Calendário"]},
    {"id": "KPI_HR_004", "nome": "Análise de Turnover",
     "semanticas": ["Perfil do Colaborador", "Data / Calendário"]},
    {"id": "KPI_TREIN_001", "nome": "Efetividade de Treinamentos",
     "semanticas": ["Curso / Treinamento", "Resultado de Avaliação"]},
    {"id": "KPI_GEO_001", "nome": "Distribuição Geográfica de Headcount",
     "semanticas": ["Localização Geográfica", "Estrutura Organizacional"]},
]


def detectar_dependencias_funcionais(
    df: pd.DataFrame, colunas_meta: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    candidatas = [
        m["Coluna"] for m in colunas_meta
        if m.get("Qtd_Unicos", 999_999) < 500
        and m.get("Caracteristica", "") not in ("⚠️ Coluna 100% Vazia", "⚠️ Sem Valores Válidos")
    ]
    determinantes_validos = {
        m["Coluna"] for m in colunas_meta
        if m.get("Ratio_Unicidade", 1.0) < config.THRESHOLD_DETERMINANTE_MAX_UNICIDADE
    }

    dependencias = []
    for i, col_a in enumerate(candidatas):
        for col_b in candidatas[i + 1:]:
            if col_a == col_b:
                continue
            try:
                if col_a in determinantes_validos:
                    max_b_por_a = df.groupby(col_a, dropna=False)[col_b].nunique(dropna=False).max()
                    if max_b_por_a == 1:
                        dependencias.append({
                            "determinante": col_a, "dependente": col_b,
                            "tipo": "Dependência Funcional Direta",
                            "descricao": f"'{col_a}' determina unicamente '{col_b}'. Candidata à desnormalização ou chave composta.",
                        })
                if col_b in determinantes_validos:
                    max_a_por_b = df.groupby(col_b, dropna=False)[col_a].nunique(dropna=False).max()
                    if max_a_por_b == 1:
                        dependencias.append({
                            "determinante": col_b, "dependente": col_a,
                            "tipo": "Dependência Funcional Direta",
                            "descricao": f"'{col_b}' determina unicamente '{col_a}'. Candidata à desnormalização ou chave composta.",
                        })
            except Exception:
                continue
    return dependencias


def gerar_gap_analysis(semanticas_presentes: Set[str]) -> List[Dict[str, Any]]:
    gaps = []
    for regra in _REGRAS_KPI:
        exigidas = set(regra["semanticas"])
        presentes = exigidas & semanticas_presentes
        ausentes = exigidas - semanticas_presentes
        cobertura = len(presentes) / len(exigidas)

        if cobertura == 1.0:
            status = "✅ Habilitado"
        elif cobertura > 0:
            status = "⚠️ Parcialmente Habilitado"
        else:
            status = "❌ Bloqueado"

        gaps.append({
            "kpi_id": regra["id"],
            "kpi_nome": regra["nome"],
            "status": status,
            "cobertura_pct": f"{cobertura:.0%}",
            "semanticas_presentes": sorted(presentes),
            "semanticas_ausentes": sorted(ausentes),
            "recomendacao": (
                f"Inclua colunas com semântica: {', '.join(sorted(ausentes))}"
                if ausentes else "Tabela possui todos os requisitos para este KPI."
            ),
        })
    return gaps


def gerar_recomendacoes_etl(
    nome_tabela: str,
    coluna: str,
    stats: Dict[str, Any],
    padrao_estruturado: str,
    linhas_analisadas: int,
) -> List[Dict[str, Any]]:
    recomendacoes: List[Dict[str, Any]] = []
    n_validos = linhas_analisadas - stats["nulos_qtd"]
    pct_validos = (n_validos / linhas_analisadas * 100) if linhas_analisadas > 0 else 0.0

    if "Vazia" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Bronze",
            "Acao": f"Remover '{coluna}': 100% nulos. Zero impacto em dados úteis.",
            "Linhas_Afetadas": 0,
        })

    if stats["flags"]["is_date_as_text"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Bronze",
            "Acao": f"Converter '{coluna}' para Date/Datetime. Viabiliza filtros e JOINs temporais.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if padrao_estruturado != "Nenhum":
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Silver",
            "Acao": f"LGPD: Mascarar/Hashear '{coluna}' ({padrao_estruturado}). Protege {n_validos:,} registros ({pct_validos:.1f}%).",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if "Chave Primária Potencial" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
            "Acao": f"Promover '{coluna}' como PK. {stats['valores_unicos']:,} valores únicos garantem integridade.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if "Quase-Chave" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Bronze",
            "Acao": f"'{coluna}' tem {stats['ratio_unicidade']:.1%} de unicidade — verificar duplicatas ou dados sujos antes de usar como chave.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if "Quasi-Constante" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
            "Acao": f"'{coluna}' é quasi-constante. Avaliar remoção ou tratamento como constante no pipeline.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if stats["flags"]["mistura_tipos"].get("tem_mistura"):
        tipos = stats["flags"]["mistura_tipos"].get("tipos_detectados", [])
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Bronze",
            "Acao": f"'{coluna}' contém mistura de tipos: {tipos}. Normalizar antes de qualquer transformação.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    outliers_info = stats["estatisticas_adicionais"].get("outliers_iqr", {})
    n_out = outliers_info.get("qtd_outliers_total", 0)
    if n_out > 0:
        pct_out = round(n_out / linhas_analisadas * 100, 1) if linhas_analisadas > 0 else 0.0
        if pct_out > 1.0:
            recomendacoes.append({
                "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
                "Acao": (
                    f"'{coluna}' tem {n_out:,} outliers IQR ({pct_out:.1f}%). "
                    f"Intervalo esperado: [{outliers_info['limite_inferior']}, {outliers_info['limite_superior']}]."
                ),
                "Linhas_Afetadas": n_out, "Pct_Impacto": f"{pct_out:.1f}%",
            })

    return recomendacoes

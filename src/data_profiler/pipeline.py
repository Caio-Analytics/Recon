"""Orquestração do profiling: liga ingestion, semantics, statistics, quality e reporting."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union

import pandas as pd
from loguru import logger
from tqdm import tqdm

from . import config, ingestion, quality, reporting, semantics, statistics


def analisar_temporal_series(
    df: pd.DataFrame, colunas_meta: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    candidatas_data = [
        m for m in colunas_meta
        if m.get("Semantica_IA") == "Data / Calendário" and m.get("Tipo_Inferred") == "Data / Hora"
    ]
    if not candidatas_data:
        return []

    col_referencia = min(candidatas_data, key=lambda m: m["Pct_Nulos"])["Coluna"]
    df_ordenado = df.sort_values(by=col_referencia).reset_index(drop=True)

    colunas_numericas = [
        m["Coluna"] for m in colunas_meta
        if "Número" in m.get("Tipo_Inferred", "") and m["Coluna"] != col_referencia
    ]

    resultados = []
    for coluna in colunas_numericas:
        serie = df_ordenado[coluna].dropna()
        if len(serie) > config.ANALISE_TEMPORAL_MAX_PONTOS:
            serie = serie.iloc[: config.ANALISE_TEMPORAL_MAX_PONTOS]
        adf = statistics.testar_estacionariedade_adf(serie)
        ljung_box = statistics.testar_autocorrelacao_ljungbox(serie)
        if not adf.get("aplicavel") and not ljung_box.get("aplicavel"):
            continue
        resultados.append({
            "coluna": coluna,
            "coluna_temporal_referencia": col_referencia,
            "adf": adf,
            "ljung_box": ljung_box,
        })
    return resultados


class DataProfiler:
    def __init__(self, limite_amostra: int = 500_000):
        self.limite_amostra = limite_amostra

    def processar_dataframe(self, df: pd.DataFrame, nome_tabela: str) -> Dict[str, Any]:
        if df is None or df.empty:
            raise ValueError(f"DataFrame '{nome_tabela}' está vazio ou inválido.")

        total_linhas = len(df)
        df_alvo = df.sample(n=self.limite_amostra, random_state=42) if total_linhas > self.limite_amostra else df
        linhas_analisadas = len(df_alvo)

        logger.info(f"Iniciando profiling: '{nome_tabela}' | {linhas_analisadas:,}/{total_linhas:,} linhas | {len(df_alvo.columns)} colunas")

        lista_colunas: List[Dict[str, Any]] = []
        recomendacoes: List[Dict[str, Any]] = []
        semanticas_presentes: Set[str] = set()

        for coluna in tqdm(df_alvo.columns, desc=f"Profilando '{nome_tabela}'", unit="col"):
            serie = df_alvo[coluna]
            stats = statistics.analisar_estatisticas(serie, linhas_analisadas)
            padrao_estruturado = stats["flags"]["detected_pattern"]
            sem = semantics.inferir_semantica(str(coluna), detectado_padrao=padrao_estruturado)

            if sem["semantica"] != "Genérico / Não mapeado":
                semanticas_presentes.add(sem["semantica"])

            registro = {
                "Tabela_Origem": str(nome_tabela),
                "Coluna": str(coluna),
                "Tipo_Inferred": stats["tipo_dados"],
                "Semantica_IA": sem["semantica"],
                "Semantica_Score": sem["confianca_score"],
                "Semantica_Origem": sem["origem"],
                "Qtd_Unicos": stats["valores_unicos"],
                "Ratio_Unicidade": stats["ratio_unicidade"],
                "Qtd_Nulos": stats["nulos_qtd"],
                "Pct_Nulos": stats["nulos_pct"],
                "Caracteristica": stats["caracteristica"],
                "Dado_Sensivel_LGPD": padrao_estruturado,
                "Amostra_Valores": ", ".join(stats["amostra_representativa"]),
                "Alertas": {
                    "data_como_texto": stats["flags"]["is_date_as_text"],
                    "mistura_tipos": stats["flags"]["mistura_tipos"],
                },
                "Stats_Extra": stats["estatisticas_adicionais"],
            }
            lista_colunas.append(registro)
            recomendacoes.extend(
                quality.gerar_recomendacoes_etl(nome_tabela, str(coluna), stats, padrao_estruturado, linhas_analisadas)
            )

        logger.info("Analisando dependências funcionais...")
        dependencias = quality.detectar_dependencias_funcionais(df_alvo, lista_colunas)

        logger.info("Gerando gap analysis de KPIs...")
        gaps = quality.gerar_gap_analysis(semanticas_presentes)

        logger.info("Rodando análise temporal cross-coluna (se aplicável)...")
        analise_temporal = analisar_temporal_series(df_alvo, lista_colunas)

        total_colunas = len(lista_colunas)
        colunas_com_nulos = sum(1 for c in lista_colunas if c["Pct_Nulos"] > 0)
        colunas_sensiveis = sum(1 for c in lista_colunas if c["Dado_Sensivel_LGPD"] != "Nenhum")
        colunas_vazias = sum(1 for c in lista_colunas if "Vazia" in c["Caracteristica"])
        kpis_habilitados = sum(1 for g in gaps if "✅" in g["status"])

        if not recomendacoes:
            recomendacoes.append({
                "Tabela": nome_tabela, "Coluna": "N/A", "Prioridade": "🟢 INFO", "Camada": "N/A",
                "Acao": "Nenhuma anomalia crítica estrutural encontrada.", "Linhas_Afetadas": 0, "Pct_Impacto": "0%",
            })

        return {
            "metadados_execucao": {
                "tabela": nome_tabela,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "versao_profiler": "2.0-Fase1",
                "linhas_originais": total_linhas,
                "linhas_analisadas": linhas_analisadas,
                "total_colunas": total_colunas,
                "resumo_qualidade": {
                    "colunas_com_nulos": colunas_com_nulos,
                    "colunas_100pct_nulas": colunas_vazias,
                    "colunas_sensiveis_lgpd": colunas_sensiveis,
                    "semanticas_mapeadas": len(semanticas_presentes),
                    "semanticas_encontradas": sorted(semanticas_presentes),
                    "kpis_habilitados": kpis_habilitados,
                    "total_recomendacoes": len(recomendacoes),
                },
            },
            "colunas": lista_colunas,
            "recomendacoes_etl": recomendacoes,
            "dependencias_funcionais": dependencias,
            "gap_analysis_kpis": gaps,
            "analise_temporal_series": analise_temporal,
        }

    def processar_arquivo(
        self,
        caminho: str,
        aba_excel: Optional[Union[str, int]] = 0,
        processar_todas_abas: bool = False,
        saida_base: str = "profiler_output",
        tambem_parquet: bool = False,
    ) -> List[Dict[str, Any]]:
        import os
        extensao = os.path.splitext(caminho)[1].lower()

        if processar_todas_abas and extensao in (".xlsx", ".xls", ".xlsb"):
            pares = ingestion.carregar_todas_abas_excel(caminho)
        else:
            pares = [ingestion.carregar_arquivo(caminho, aba_excel=aba_excel)]

        resultados = []
        for df, nome_tabela in pares:
            payload = self.processar_dataframe(df, nome_tabela)
            nome_safe = reporting.nome_seguro(nome_tabela)
            reporting.exportar_json(payload, f"{saida_base}_{nome_safe}.json")
            reporting.exportar_markdown(payload, f"{saida_base}_{nome_safe}.md")
            if tambem_parquet:
                reporting.exportar_parquet(payload, saida_base)
            resultados.append(payload)
        return resultados

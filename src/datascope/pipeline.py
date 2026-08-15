"""Orquestração do profiling: liga ingestion, semantics, statistics,
relationships, quality e reporting."""
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from loguru import logger
from tqdm import tqdm

from . import (
    __version__,
    codegen,
    config,
    datamodel,
    ingestion,
    quality,
    relationships,
    reporting,
    rules,
    semantics,
    statistics,
)

FORMATOS_PADRAO = ("json", "markdown")
FORMATOS_VALIDOS = ("json", "markdown", "html", "parquet")

_SEMANTICAS_BENFORD = frozenset({"Valor Financeiro"})


class DataProfiler:
    """Perfila um DataFrame ou arquivo e exporta o resultado.

    `limite_amostra` limita quantas linhas entram na análise. É a decisão mais
    importante de custo × precisão da ferramenta: acima dele o profiler
    trabalha sobre uma amostra aleatória determinística, e as métricas de
    unicidade e duplicata passam a valer para a amostra, não para a tabela —
    o payload sinaliza isso em `amostragem_aplicada`.
    """

    def __init__(
        self,
        limite_amostra: int = 500_000,
        regras_kpi: Sequence[dict[str, Any]] | None = None,
    ):
        self.limite_amostra = limite_amostra
        self.regras_kpi = list(regras_kpi) if regras_kpi is not None else config.REGRAS_KPI_PADRAO

    # ── Análise ─────────────────────────────────────────────────────────
    def _analisar_colunas(self, df_alvo: pd.DataFrame, nome_tabela: str, linhas: int):
        lista_colunas: list[dict[str, Any]] = []
        recomendacoes: list[dict[str, Any]] = []
        semanticas_presentes: set[str] = set()

        # Fase 1 — descrição de cada coluna, independente das demais.
        nomes: list[str] = []
        stats_por_coluna: list[dict[str, Any]] = []
        entradas_semanticas: list[dict[str, Any]] = []

        for coluna in tqdm(df_alvo.columns, desc=f"Profilando '{nome_tabela}'", unit="col"):
            # Inferência preliminar só pelo nome: decide se vale rodar Benford
            # (que só faz sentido em coluna de valor) antes de conhecer o
            # padrão detectado no conteúdo.
            preliminar = semantics.inferir_semantica(str(coluna))
            avaliar_benford = bool(
                _SEMANTICAS_BENFORD & set(semantics.semanticas_para_gap_analysis(preliminar))
            )

            stats = statistics.analisar_estatisticas(
                df_alvo[coluna], linhas, avaliar_benford=avaliar_benford
            )
            nomes.append(str(coluna))
            stats_por_coluna.append(stats)
            entradas_semanticas.append({
                "nome": str(coluna),
                "padrao": stats["flags"]["detected_pattern"],
                "perfil": semantics.perfil_de_registro(stats, stats["amostra_representativa"]),
            })

        # Fase 2 — semântica da tabela inteira: só aqui as colunas conversam
        # entre si e as abreviaturas ambíguas se resolvem pelo contexto.
        logger.info("Inferindo semântica das colunas (com contexto da tabela)...")
        semanticas = semantics.inferir_semanticas_da_tabela(entradas_semanticas)

        for coluna, stats, sem in zip(nomes, stats_por_coluna, semanticas, strict=True):
            padrao_estruturado = stats["flags"]["detected_pattern"]
            semanticas_presentes.update(semantics.semanticas_para_gap_analysis(sem))

            lista_colunas.append({
                "Tabela_Origem": str(nome_tabela),
                "Coluna": str(coluna),
                "Tipo_Inferred": stats["tipo_dados"],
                "Semantica_IA": sem["semantica"],
                "Papel": sem["papel"],
                "Dominio": sem["dominio"],
                "Semantica_Score": sem["confianca_score"],
                "Semantica_Origem": sem["origem"],
                "Semantica_Conclusiva": sem["conclusiva"],
                "Semantica_Hipoteses": sem["hipoteses"],
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
                    "stats_suprimidas_lgpd": stats["flags"]["stats_suprimidas_lgpd"],
                },
                "Qualidade": stats["qualidade"],
                "Otimizacao": stats["otimizacao"],
                "Stats_Extra": stats["estatisticas_adicionais"],
            })
            recomendacoes.extend(
                quality.gerar_recomendacoes_etl(
                    nome_tabela, str(coluna), stats, padrao_estruturado, linhas
                )
            )

        return lista_colunas, recomendacoes, semanticas_presentes

    def processar_dataframe(self, df: pd.DataFrame, nome_tabela: str) -> dict[str, Any]:
        if df is None or df.empty:
            raise ValueError(f"DataFrame '{nome_tabela}' está vazio ou inválido.")

        # `ingestion` anexa o diagnóstico de layout ao DataFrame; ele precisa
        # chegar ao relatório porque explica *por que* a tabela analisada não
        # é literalmente o que está no arquivo.
        lay = df.attrs.get("layout")
        layout_info = {
            "linha_cabecalho": getattr(lay, "linha_cabecalho", 0),
            "linhas_rodape_removidas": getattr(lay, "linhas_rodape", 0),
            "colunas_vazias_removidas": getattr(lay, "colunas_vazias_removidas", []),
            "avisos": getattr(lay, "avisos", []),
        }

        total_linhas = len(df)
        amostrado = total_linhas > self.limite_amostra
        df_alvo = df.sample(n=self.limite_amostra, random_state=42) if amostrado else df
        linhas_analisadas = len(df_alvo)

        logger.info(
            f"Iniciando profiling: '{nome_tabela}' | {linhas_analisadas:,}/{total_linhas:,} linhas"
            f" | {len(df_alvo.columns)} colunas"
        )

        lista_colunas, recomendacoes, semanticas_presentes = self._analisar_colunas(
            df_alvo, nome_tabela, linhas_analisadas
        )

        logger.info("Analisando dependências funcionais...")
        dependencias = relationships.detectar_dependencias_funcionais(df_alvo, lista_colunas)

        logger.info("Procurando duplicatas, colunas redundantes e chaves compostas...")
        duplicatas = relationships.analisar_duplicatas(df_alvo)
        redundantes = relationships.detectar_colunas_redundantes(df_alvo)
        chaves_compostas = relationships.detectar_chaves_compostas(df_alvo, lista_colunas)

        logger.info("Medindo correlações entre colunas...")
        correlacoes = relationships.analisar_correlacoes(df_alvo, lista_colunas)
        hierarquias = relationships.detectar_hierarquias(dependencias)
        explicacoes = relationships.explicar_medidas(df_alvo, lista_colunas)

        logger.info("Inferindo regras de negócio...")
        regras_negocio = rules.inferir_regras(df_alvo, lista_colunas)

        logger.info("Gerando gap analysis de KPIs...")
        gaps = quality.gerar_gap_analysis(semanticas_presentes, self.regras_kpi)

        logger.info("Rodando análise temporal cross-coluna (se aplicável)...")
        analise_temporal = relationships.analisar_series_temporais(df_alvo, lista_colunas)

        recomendacoes.extend(quality.gerar_recomendacoes_tabela(
            nome_tabela, duplicatas, redundantes, chaves_compostas, linhas_analisadas
        ))

        score = quality.calcular_score_qualidade(lista_colunas, duplicatas, redundantes)

        if not recomendacoes:
            recomendacoes.append({
                "Tabela": nome_tabela, "Coluna": "N/A", "Prioridade": quality.PRIORIDADE_INFO,
                "Camada": "N/A", "Acao": "Nenhuma anomalia crítica estrutural encontrada.",
                "Linhas_Afetadas": 0, "Pct_Impacto": "0%",
            })

        return {
            "metadados_execucao": {
                "tabela": nome_tabela,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "versao_profiler": __version__,
                "schema_version": config.SCHEMA_VERSION,
                "linhas_originais": total_linhas,
                "linhas_analisadas": linhas_analisadas,
                "amostragem_aplicada": amostrado,
                "total_colunas": len(lista_colunas),
                "layout": layout_info,
                "score_qualidade": score,
                "duplicatas": duplicatas,
                "resumo_qualidade": {
                    "colunas_com_nulos": sum(1 for c in lista_colunas if c["Pct_Nulos"] > 0),
                    "colunas_100pct_nulas": sum(
                        1 for c in lista_colunas if "Vazia" in c["Caracteristica"]
                    ),
                    "colunas_sensiveis_lgpd": sum(
                        1 for c in lista_colunas if c["Dado_Sensivel_LGPD"] != "Nenhum"
                    ),
                    "colunas_com_sentinela": sum(
                        1 for c in lista_colunas
                        if c["Qualidade"].get("sentinelas", {}).get("tem_sentinela")
                    ),
                    "semanticas_mapeadas": len(semanticas_presentes),
                    "semanticas_encontradas": sorted(semanticas_presentes),
                    "kpis_habilitados": sum(1 for g in gaps if "✅" in g["status"]),
                    "total_recomendacoes": len(recomendacoes),
                },
            },
            "colunas": lista_colunas,
            "recomendacoes_etl": recomendacoes,
            "dependencias_funcionais": dependencias,
            "colunas_redundantes": redundantes,
            "chaves_compostas": chaves_compostas,
            "correlacoes": correlacoes,
            "hierarquias": hierarquias,
            "explicacoes_de_medidas": explicacoes,
            "regras_negocio": regras_negocio,
            "gap_analysis_kpis": gaps,
            "analise_temporal_series": analise_temporal,
        }

    # ── Exportação ──────────────────────────────────────────────────────
    def processar_arquivo(
        self,
        caminho: str,
        aba_excel: str | int | None = 0,
        processar_todas_abas: bool = False,
        saida_base: str = "profiler_output",
        tambem_parquet: bool = False,
        formatos: Sequence[str] = FORMATOS_PADRAO,
        json_compacto: bool = False,
        detectar_layout: bool = True,
        linha_cabecalho: int | None = None,
        gerar_limpeza: bool = False,
    ) -> list[dict[str, Any]]:
        formatos = list(formatos)
        if tambem_parquet and "parquet" not in formatos:
            formatos.append("parquet")
        desconhecidos = set(formatos) - set(FORMATOS_VALIDOS)
        if desconhecidos:
            raise ValueError(
                f"Formato(s) de saída inválido(s): {', '.join(sorted(desconhecidos))}. "
                f"Use: {', '.join(FORMATOS_VALIDOS)}."
            )

        extensao = os.path.splitext(caminho)[1].lower()
        if processar_todas_abas and extensao in (".xlsx", ".xls", ".xlsb"):
            pares = ingestion.carregar_todas_abas_excel(caminho, detectar_layout)
        else:
            pares = [ingestion.carregar_arquivo(
                caminho, aba_excel=aba_excel, detectar_layout=detectar_layout,
                linha_cabecalho=linha_cabecalho,
            )]

        nomes_usados: set[str] = set()
        resultados = []
        for df, nome_tabela in pares:
            payload = self.processar_dataframe(df, nome_tabela)
            nome_safe = reporting.gerar_nome_unico(nome_tabela, nomes_usados)
            if "json" in formatos:
                reporting.exportar_json(payload, f"{saida_base}_{nome_safe}.json", json_compacto)
            if "markdown" in formatos:
                reporting.exportar_markdown(payload, f"{saida_base}_{nome_safe}.md")
            if "html" in formatos:
                reporting.exportar_html(payload, f"{saida_base}_{nome_safe}.html")
            if "parquet" in formatos:
                reporting.exportar_parquet(payload, saida_base, nome_safe)
            if gerar_limpeza:
                codegen.exportar_script_limpeza(
                    payload, caminho, f"{saida_base}_{nome_safe}_limpeza.py"
                )
            resultados.append(payload)
        return resultados


    # ── Conjunto de arquivos ────────────────────────────────────────────
    def modelar_conjunto(
        self,
        caminhos: Sequence[str],
        saida_base: str = "modelo",
        formatos: Sequence[str] = FORMATOS_PADRAO,
        json_compacto: bool = False,
        perfis_individuais: bool = True,
    ) -> dict[str, Any]:
        """Perfila várias tabelas e infere como elas se ligam.

        Cada aba de um Excel entra como uma tabela independente — é assim que
        um arquivo de cinco abas vira cinco tabelas que podem se relacionar
        entre si, que é o arranjo mais comum de quem trabalha com extração de
        sistema em planilha.
        """
        tabelas: list[datamodel.TabelaCarregada] = []
        nomes_usados: set[str] = set()

        for caminho in caminhos:
            extensao = os.path.splitext(caminho)[1].lower()
            if extensao in (".xlsx", ".xls", ".xlsb"):
                pares = [
                    (df, nome, f"{caminho}::{nome.split('__', 1)[-1]}")
                    for df, nome in ingestion.carregar_todas_abas_excel(caminho)
                ]
            else:
                df, nome = ingestion.carregar_arquivo(caminho)
                pares = [(df, nome, caminho)]

            for df, nome_tabela, origem in pares:
                if df is None or df.empty:
                    logger.warning(f"'{nome_tabela}' está vazia — fora da análise do conjunto.")
                    continue
                payload = self.processar_dataframe(df, nome_tabela)
                nome_safe = reporting.gerar_nome_unico(nome_tabela, nomes_usados)
                if perfis_individuais:
                    if "json" in formatos:
                        reporting.exportar_json(
                            payload, f"{saida_base}_{nome_safe}.json", json_compacto
                        )
                    if "markdown" in formatos:
                        reporting.exportar_markdown(payload, f"{saida_base}_{nome_safe}.md")
                    if "html" in formatos:
                        reporting.exportar_html(payload, f"{saida_base}_{nome_safe}.html")
                tabelas.append(datamodel.TabelaCarregada(
                    nome=nome_tabela, df=df, payload=payload, origem=origem
                ))

        if len(tabelas) < 2:
            raise ValueError(
                "Modelagem de conjunto precisa de ao menos 2 tabelas "
                f"(encontrei {len(tabelas)}). Para uma tabela só, use `datascope perfilar`."
            )

        nome_conjunto = os.path.basename(saida_base) or "conjunto"
        modelo = datamodel.analisar_conjunto(tabelas, nome_conjunto)

        if "json" in formatos:
            reporting.exportar_json(modelo, f"{saida_base}_modelo.json", json_compacto)
        if "markdown" in formatos:
            reporting.exportar_modelo_markdown(modelo, f"{saida_base}_modelo.md")
        if "html" in formatos:
            reporting.exportar_modelo_html(modelo, f"{saida_base}_modelo.html")
        return modelo

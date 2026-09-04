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
    insights,
    patterns,
    quality,
    relationships,
    reporting,
    rules,
    semantics,
    statistics,
)
from . import historico as historico_mod
from .tipos import IncertezaAmostra, LayoutPayload, MetadadosExecucao

# HTML como padrão: um `.html` clicado abre renderizado no navegador de
# qualquer máquina, enquanto um `.md` abre no bloco de notas mostrando a
# marcação crua para quem não tem visualizador.
FORMATOS_PADRAO = ("json", "html")
FORMATOS_VALIDOS = ("json", "markdown", "html", "pdf", "parquet")
EXTENSOES_EXCEL = (".xlsx", ".xls", ".xlsb")


def _exportar_html_e_pdf(
    payload: dict[str, Any], caminho_html: str, formatos: Sequence[str]
) -> None:
    """Gera HTML visível e/ou PDF, apagando a cópia temporária quando preciso."""
    if "html" not in formatos and "pdf" not in formatos:
        return
    reporting.exportar_html(payload, caminho_html)
    if "pdf" in formatos:
        reporting.exportar_pdf_de_html(caminho_html, os.path.splitext(caminho_html)[0] + ".pdf")
    if "html" not in formatos:
        os.unlink(caminho_html)


def abas_fora_da_analise(caminho: str, aba_excel: str | int | None) -> list[str]:
    """Abas de um Excel que ficarão de fora ao perfilar uma aba só.

    Vazio quando não é Excel, quando o arquivo tem uma aba só, ou quando o
    usuário escolheu explicitamente qual aba quer.
    """
    if os.path.splitext(caminho)[1].lower() not in EXTENSOES_EXCEL:
        return []
    if aba_excel not in (0, None):
        return []
    abas = ingestion.listar_abas(caminho)
    return [str(a) for a in abas[1:]] if len(abas) > 1 else []

_SEMANTICAS_BENFORD = frozenset({"Valor Financeiro"})

# Trabalho (linhas × colunas) a partir do qual vale distribuir a fase de
# colunas entre processos. Abaixo disso o custo de criar os processos come o
# ganho — medido: 40 colunas × 100 mil linhas rende 4×; uma tabela pequena
# fica mais lenta.
TRABALHO_MINIMO_PARALELO = 2_000_000


def _perfilar_coluna(argumentos: tuple[pd.Series, int, bool]) -> dict[str, Any]:
    """Descrição de uma coluna. No topo do módulo porque precisa ser
    serializável para rodar noutro processo."""
    serie, linhas, avaliar_benford = argumentos
    return statistics.analisar_estatisticas(serie, linhas, avaliar_benford=avaliar_benford)


def _processos_disponiveis(trabalho: int, colunas: int) -> int:
    """Quantos processos usar na fase de colunas — 0 significa sequencial.

    Só com `fork` e `forkserver` (Linux e a maioria dos contêineres; no 3.14 o
    padrão do Linux passou a ser `forkserver`). Em `spawn` — Windows e macOS —
    cada processo reimporta pandas, numpy e scipy do zero, o que custa segundos
    por worker e inverte o ganho justamente na máquina corporativa que a
    ferramenta mira. Lá continua sequencial, que é o comportamento que sempre
    funcionou.
    """
    import multiprocessing

    if trabalho < TRABALHO_MINIMO_PARALELO or colunas < 8:
        return 0
    # Sem `allow_none`: com ele o método só é reportado depois que alguém já o
    # fixou, e a resposta vinha `None` — a paralelização nunca ligava.
    if multiprocessing.get_start_method() not in ("fork", "forkserver"):
        return 0
    nucleos = os.cpu_count() or 1
    if nucleos < 4:
        return 0
    return min(8, nucleos, colunas)


def _mascarar_nomes(stats: dict[str, Any]) -> None:
    """Mascara, no registro já montado, tudo que expõe o nome em claro."""
    stats["amostra_representativa"] = [
        patterns.mascarar_nome_pessoa(v) for v in stats["amostra_representativa"]
    ]
    for item in stats["estatisticas_adicionais"].get("distribuicao_top5", []):
        item["valor"] = patterns.mascarar_nome_pessoa(item["valor"])


class DataProfiler:
    """Perfila um DataFrame ou arquivo e exporta o resultado.

    `limite_amostra` limita quantas linhas entram na análise. É a decisão mais
    importante de custo × precisão da ferramenta: acima dele o profiler
    trabalha sobre uma amostra aleatória determinística, e as métricas de
    unicidade e duplicata passam a valer para a amostra, não para a tabela —
    o payload sinaliza isso em `amostragem_aplicada`.

    O teto padrão é alto de propósito. Amostrar troca correção por tempo:
    numa amostra, duplicata e unicidade só podem ser subestimadas, nunca
    superestimadas, o que gera "chave primária potencial" que não existe. Com
    memória disponível, analisar tudo é a resposta certa; quem precisar de
    velocidade baixa o teto explicitamente.
    """

    def __init__(
        self,
        limite_amostra: int = 2_000_000,
        regras_kpi: Sequence[dict[str, Any]] | None = None,
        vocabularios: str | None = None,
    ):
        self.limite_amostra = limite_amostra
        self.regras_kpi = list(regras_kpi) if regras_kpi is not None else config.REGRAS_KPI_PADRAO
        self.vocabularios = vocabularios

    # ── Análise ─────────────────────────────────────────────────────────
    def _analisar_colunas(self, df_alvo: pd.DataFrame, nome_tabela: str, linhas: int):
        lista_colunas: list[dict[str, Any]] = []
        recomendacoes: list[dict[str, Any]] = []
        semanticas_presentes: set[str] = set()

        # Fase 1 — descrição de cada coluna, independente das demais.
        nomes: list[str] = []
        stats_por_coluna: list[dict[str, Any]] = []
        entradas_semanticas: list[dict[str, Any]] = []

        # Inferência preliminar só pelo nome: decide se vale rodar Benford (que
        # só faz sentido em coluna de valor) antes de conhecer o padrão
        # detectado no conteúdo.
        tarefas = []
        for coluna in df_alvo.columns:
            preliminar = semantics.inferir_semantica(str(coluna))
            avaliar_benford = bool(
                _SEMANTICAS_BENFORD & set(semantics.semanticas_para_gap_analysis(preliminar))
            )
            nomes.append(str(coluna))
            tarefas.append((df_alvo[coluna], linhas, avaliar_benford))

        processos = _processos_disponiveis(linhas * len(tarefas), len(tarefas))
        descricao = f"Profilando '{nome_tabela}'"
        stats_por_coluna = []
        if processos:
            # As funções de análise são puras e independentes por coluna — é o
            # que torna a distribuição segura. Cada processo devolve o registro
            # pronto; nada é compartilhado.
            from concurrent.futures import ProcessPoolExecutor

            logger.info(f"Distribuindo {len(tarefas)} colunas entre {processos} processos...")
            try:
                with ProcessPoolExecutor(max_workers=processos) as executor:
                    stats_por_coluna = list(tqdm(
                        executor.map(_perfilar_coluna, tarefas, chunksize=2),
                        total=len(tarefas), desc=descricao, unit="col",
                    ))
            except Exception as erro:  # noqa: BLE001
                # Ambiente que não deixa criar processo (sandbox, interpretador
                # embarcado, `python -` sem módulo principal) não pode derrubar
                # uma análise que roda perfeitamente numa thread só.
                logger.warning(
                    f"Não consegui usar processos ({type(erro).__name__}); "
                    "seguindo em sequencial."
                )
                stats_por_coluna = []

        if not stats_por_coluna:
            stats_por_coluna = [
                _perfilar_coluna(tarefa)
                for tarefa in tqdm(tarefas, desc=descricao, unit="col")
            ]

        for nome, stats in zip(nomes, stats_por_coluna, strict=True):
            entradas_semanticas.append({
                "nome": nome,
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

            # Nome de pessoa é dado pessoal e não casa com nenhum padrão
            # estruturado — quem sinaliza é a semântica, que só fica pronta
            # aqui na fase 2. Sem isto, `FULL_NAME` ia para o relatório com os
            # nomes em claro.
            if sem["papel"] == config.SEMANTICA_NOME_PESSOA and not patterns.eh_sensivel(
                padrao_estruturado
            ):
                padrao_estruturado = "Nome de pessoa"
                _mascarar_nomes(stats)

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
                "Caracteristica": statistics.ajustar_caracteristica_com_semantica(
                    stats["caracteristica"], sem["papel"]
                ),
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
        """Perfila uma tabela com vocabulário local isolado por execução."""
        with semantics.vocabulario_temporario(self.vocabularios):
            return self._processar_dataframe(df, nome_tabela)

    def _processar_dataframe(self, df: pd.DataFrame, nome_tabela: str) -> dict[str, Any]:
        if df is None or df.empty:
            raise ValueError(f"DataFrame '{nome_tabela}' está vazio ou inválido.")

        # `ingestion` anexa o diagnóstico de layout ao DataFrame; ele precisa
        # chegar ao relatório porque explica *por que* a tabela analisada não
        # é literalmente o que está no arquivo.
        lay = df.attrs.get("layout")
        layout_info: LayoutPayload = {
            "linha_cabecalho": getattr(lay, "linha_cabecalho", 0),
            "linhas_rodape_removidas": getattr(lay, "linhas_rodape", 0),
            "colunas_vazias_removidas": getattr(lay, "colunas_vazias_removidas", []),
            "separador": getattr(lay, "separador", None),
            "encoding": getattr(lay, "encoding", None),
            "avisos": getattr(lay, "avisos", []),
        }

        # Em arquivo grande a amostragem acontece durante a leitura (o arquivo
        # inteiro nunca cabe na memória), e o total real vem de lá.
        total_linhas = int(df.attrs.get("linhas_originais") or len(df))
        total_desconhecido = bool(df.attrs.get("linhas_originais_desconhecidas"))
        motivo_amostragem = df.attrs.get("motivo_amostragem")
        amostrado = (
            total_desconhecido or total_linhas > len(df) or total_linhas > self.limite_amostra
        )
        df_alvo = df.sample(n=self.limite_amostra, random_state=42) if amostrado else df
        linhas_analisadas = len(df_alvo)
        cobertura_amostra = (linhas_analisadas / total_linhas) if total_linhas else 1.0
        incerteza_amostra: IncertezaAmostra = {
            "cobertura_pct": round(cobertura_amostra * 100, 3),
            "limiar_evento_raro_pct": round((3 / linhas_analisadas) * 100, 4)
            if linhas_analisadas else None,
            "mensagem": (
                "Amostra uniforme: resultados descrevem as linhas sorteadas. Eventos muito raros "
                "podem não aparecer; confirme chaves, duplicatas e categorias críticas na base completa."
                if amostrado else "A base inteira foi analisada."
            ),
        }

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
        duplicatas_aproximadas = relationships.detectar_duplicatas_aproximadas(
            df_alvo, lista_colunas
        )
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
            nome_tabela, duplicatas, redundantes, chaves_compostas, linhas_analisadas,
            colunas=lista_colunas, duplicatas_aproximadas=duplicatas_aproximadas,
        ))

        score = quality.calcular_score_qualidade(lista_colunas, duplicatas, redundantes)
        risco_lgpd = quality.calcular_risco_lgpd(lista_colunas)

        if not recomendacoes:
            recomendacoes.append({
                "Tabela": nome_tabela, "Coluna": "N/A", "Prioridade": quality.PRIORIDADE_INFO,
                "Camada": "N/A", "Acao": "Nenhuma anomalia crítica estrutural encontrada.",
                "Linhas_Afetadas": 0, "Pct_Impacto": "0%",
            })

        metadados: MetadadosExecucao = {
                "tabela": nome_tabela,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "versao_profiler": __version__,
                "schema_version": config.SCHEMA_VERSION,
                "linhas_originais": total_linhas,
                "linhas_originais_desconhecidas": total_desconhecido,
                "linhas_analisadas": linhas_analisadas,
                "amostragem_aplicada": amostrado,
                "motivo_amostragem": motivo_amostragem,
                "incerteza_amostra": incerteza_amostra,
                "total_colunas": len(lista_colunas),
                "layout": layout_info,
                "score_qualidade": score,
                "risco_lgpd": risco_lgpd,
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
        }
        resultado = {
            "metadados_execucao": metadados,
            "colunas": lista_colunas,
            "recomendacoes_etl": recomendacoes,
            "dependencias_funcionais": dependencias,
            "colunas_redundantes": redundantes,
            "duplicatas_aproximadas": duplicatas_aproximadas,
            "chaves_compostas": chaves_compostas,
            "correlacoes": correlacoes,
            "hierarquias": hierarquias,
            "explicacoes_de_medidas": explicacoes,
            "regras_negocio": regras_negocio,
            "gap_analysis_kpis": gaps,
            "analise_temporal_series": analise_temporal,
        }
        resultado["insights_textuais"] = insights.gerar_insights_textuais(resultado)
        return resultado

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
        gerar_limpeza_powerquery: bool = False,
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
        abas_ignoradas: list[str] = []
        if processar_todas_abas and extensao in EXTENSOES_EXCEL:
            pares = ingestion.carregar_todas_abas_excel(
                caminho, detectar_layout, self.limite_amostra
            )
        else:
            # O aviso mora aqui, e não na CLI, porque a janela e o menu também
            # chamam este método: perfilar em silêncio uma aba de cinco é a
            # forma mais fácil de alguém concluir coisa errada sobre os dados, e
            # eram justamente os dois caminhos do usuário leigo que não recebiam
            # o alerta.
            abas_ignoradas = abas_fora_da_analise(caminho, aba_excel)
            if abas_ignoradas:
                logger.warning(
                    f"'{os.path.basename(caminho)}' tem {len(abas_ignoradas) + 1} abas e só a "
                    f"primeira será analisada. Ficaram de fora: "
                    f"{', '.join(abas_ignoradas[:4])}"
                    f"{'...' if len(abas_ignoradas) > 4 else ''}. "
                    "Para um relatório por aba, marque 'analisar todas as abas' na janela "
                    "ou use --todas-abas na linha de comando; `recon modelar` analisa as abas "
                    "juntas e descobre como se ligam."
                )
            pares = [ingestion.carregar_arquivo(
                caminho, aba_excel=aba_excel, detectar_layout=detectar_layout,
                linha_cabecalho=linha_cabecalho, limite_linhas=self.limite_amostra,
            )]

        nomes_usados: set[str] = set()
        resultados = []
        for df, nome_tabela in pares:
            payload = self.processar_dataframe(df, nome_tabela)
            payload["metadados_execucao"]["abas_ignoradas"] = abas_ignoradas
            nome_safe = reporting.gerar_nome_unico(nome_tabela, nomes_usados)
            if "json" in formatos:
                reporting.exportar_json(payload, f"{saida_base}_{nome_safe}.json", json_compacto)
            if "markdown" in formatos:
                reporting.exportar_markdown(payload, f"{saida_base}_{nome_safe}.md")
            _exportar_html_e_pdf(payload, f"{saida_base}_{nome_safe}.html", formatos)
            if "parquet" in formatos:
                reporting.exportar_parquet(payload, saida_base, nome_safe)
            if gerar_limpeza:
                codegen.exportar_script_limpeza(
                    payload, caminho, f"{saida_base}_{nome_safe}_limpeza.py"
                )
            if gerar_limpeza_powerquery:
                codegen.exportar_script_limpeza_m(
                    payload, caminho, f"{saida_base}_{nome_safe}_limpeza.pq"
                )
            resultados.append(payload)
        return resultados

    def processar_consulta(
        self,
        conexao: str,
        sql: str,
        saida_base: str = "profiler_output",
        formatos: Sequence[str] = FORMATOS_PADRAO,
        json_compacto: bool = False,
    ) -> dict[str, Any]:
        """Perfila uma consulta de leitura em banco local suportado."""
        quadro, nome_tabela = ingestion.carregar_consulta(conexao, sql)
        if quadro.empty:
            raise ValueError("A consulta não retornou linhas para analisar.")
        payload = self.processar_dataframe(quadro, nome_tabela)
        nome_safe = reporting.gerar_nome_unico(nome_tabela, set())
        if "json" in formatos:
            reporting.exportar_json(payload, f"{saida_base}_{nome_safe}.json", json_compacto)
        if "markdown" in formatos:
            reporting.exportar_markdown(payload, f"{saida_base}_{nome_safe}.md")
        _exportar_html_e_pdf(payload, f"{saida_base}_{nome_safe}.html", formatos)
        if "parquet" in formatos:
            reporting.exportar_parquet(payload, saida_base, nome_safe)
        return payload


    # ── Conferência entre versões ───────────────────────────────────────
    def conferir_versoes(
        self,
        caminho_anterior: str,
        caminho_novo: str,
        saida_base: str = "conferencia",
        formatos: Sequence[str] = FORMATOS_PADRAO,
        json_compacto: bool = False,
    ) -> dict[str, Any]:
        """Compara duas versões da mesma base e devolve o que mudou.

        Um relatório de tabela isolada mostra, por exemplo, 40% de nulos numa
        coluna, mas não diz se isso é novo ou sempre foi assim — falta a versão
        anterior para comparar.
        """
        carregadas = []
        for caminho in (caminho_anterior, caminho_novo):
            df, nome = ingestion.carregar_arquivo(caminho, limite_linhas=self.limite_amostra)
            if df is None or df.empty:
                raise ValueError(f"'{caminho}' está vazio — não há o que conferir.")
            logger.info(f"Perfilando '{nome}' para a conferência...")
            payload = self.processar_dataframe(df, nome)
            carregadas.append(
                datamodel.TabelaCarregada(nome=nome, df=df, payload=payload, origem=caminho)
            )

        logger.info("Comparando as duas versões...")
        resultado = datamodel.reconciliar(carregadas[0], carregadas[1])
        resultado["metadados_execucao"] = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "versao_profiler": __version__,
            "schema_version": config.SCHEMA_VERSION,
            "arquivo_anterior": caminho_anterior,
            "arquivo_novo": caminho_novo,
        }

        if "json" in formatos:
            reporting.exportar_json(resultado, f"{saida_base}_conferencia.json", json_compacto)
        if "markdown" in formatos:
            reporting.exportar_conferencia_markdown(
                resultado, f"{saida_base}_conferencia.md"
            )
        if "html" in formatos:
            reporting.exportar_conferencia_html(resultado, f"{saida_base}_conferencia.html")
        return resultado

    def analisar_historico(
        self,
        caminhos: Sequence[str],
        saida_base: str = "historico",
        formatos: Sequence[str] = FORMATOS_PADRAO,
        json_compacto: bool = False,
        limites: str | None = None,
    ) -> dict[str, Any]:
        """Compara a evolução de várias extrações da mesma base na ordem dada."""
        if len(caminhos) < 2:
            raise ValueError("O histórico precisa de ao menos duas extrações, em ordem cronológica.")
        extracoes: list[dict[str, Any]] = []
        alertas: list[str] = []
        limites_ativos = historico_mod.carregar_limiares(limites)
        anterior: dict[str, Any] | None = None
        for caminho in caminhos:
            df, nome = ingestion.carregar_arquivo(caminho, limite_linhas=self.limite_amostra)
            if df is None or df.empty:
                raise ValueError(f"'{caminho}' está vazio — não há histórico a calcular.")
            perfil = self.processar_dataframe(df, nome)
            meta = perfil["metadados_execucao"]
            atual = {
                "arquivo": os.path.basename(caminho),
                "linhas": meta["linhas_originais"],
                "linhas_analisadas": meta["linhas_analisadas"],
                "linhas_total_desconhecido": meta["linhas_originais_desconhecidas"],
                "amostragem_aplicada": meta["amostragem_aplicada"],
                "cobertura_amostra_pct": meta["incerteza_amostra"]["cobertura_pct"],
                "colunas": meta["total_colunas"],
                "score": meta["score_qualidade"]["score"],
                "colunas_com_nulos": meta["resumo_qualidade"]["colunas_com_nulos"],
                "recomendacoes": meta["resumo_qualidade"]["total_recomendacoes"],
            }
            alertas.extend(historico_mod.alertas_da_transicao(anterior, atual, limites_ativos))
            extracoes.append(atual)
            anterior = atual
        resultado = {
            "metadados_execucao": {"timestamp_utc": datetime.now(UTC).isoformat()},
            "extracoes": extracoes,
            "alertas": alertas,
            "limites": limites_ativos,
            "resumo": (
                f"{len(extracoes)} extrações analisadas na ordem informada. "
                f"{len(alertas)} alerta(s) de evolução encontrado(s)."
            ),
        }
        if "json" in formatos:
            reporting.exportar_json(resultado, f"{saida_base}_historico.json", json_compacto)
        if "markdown" in formatos:
            reporting.exportar_historico_markdown(resultado, f"{saida_base}_historico.md")
        if "html" in formatos:
            reporting.exportar_historico_html(resultado, f"{saida_base}_historico.html")
        return resultado

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
                    for df, nome in ingestion.carregar_todas_abas_excel(
                        caminho, limite_linhas=self.limite_amostra
                    )
                ]
            else:
                df, nome = ingestion.carregar_arquivo(
                    caminho, limite_linhas=self.limite_amostra
                )
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
                f"(encontrei {len(tabelas)}). Para uma tabela só, use `recon perfilar`."
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


    # ── Lote ────────────────────────────────────────────────────────────
    def processar_lote(
        self,
        caminhos: Sequence[str],
        saida_base: str = "lote",
        formatos: Sequence[str] = FORMATOS_PADRAO,
        json_compacto: bool = False,
        detectar_layout: bool = True,
        consolidado: bool = True,
    ) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
        """Perfila vários arquivos e consolida num relatório comparativo.

        A saída padrão é um HTML único com todos os arquivos ordenados do pior
        para o melhor, em vez de um relatório separado por arquivo.

        Devolve os payloads e a lista de falhas, para o chamador decidir o
        código de saída.
        """
        payloads: list[dict[str, Any]] = []
        falhas: list[tuple[str, str]] = []
        nomes_usados: set[str] = set()

        for caminho in caminhos:
            try:
                extensao = os.path.splitext(caminho)[1].lower()
                if extensao in (".xlsx", ".xls", ".xlsb"):
                    pares = ingestion.carregar_todas_abas_excel(
                        caminho, detectar_layout, self.limite_amostra
                    )
                else:
                    pares = [ingestion.carregar_arquivo(
                        caminho, detectar_layout=detectar_layout,
                        limite_linhas=self.limite_amostra,
                    )]
                for df, nome_tabela in pares:
                    if df is None or df.empty:
                        falhas.append((f"{caminho} ({nome_tabela})", "tabela vazia"))
                        continue
                    payload = self.processar_dataframe(df, nome_tabela)
                    payloads.append(payload)
                    nome_safe = reporting.gerar_nome_unico(nome_tabela, nomes_usados)
                    if "json" in formatos:
                        reporting.exportar_json(
                            payload, f"{saida_base}_{nome_safe}.json", json_compacto
                        )
                    if "markdown" in formatos:
                        reporting.exportar_markdown(payload, f"{saida_base}_{nome_safe}.md")
                    if "parquet" in formatos:
                        reporting.exportar_parquet(payload, saida_base, nome_safe)
            except (FileNotFoundError, ingestion.IngestionError, ValueError, OSError) as e:
                falhas.append((caminho, str(e)))
                logger.error(f"Falha em '{caminho}': {e}")

        if payloads and consolidado and "html" in formatos:
            reporting.exportar_lote_html(
                payloads, f"{saida_base}_consolidado.html", os.path.basename(saida_base) or "lote"
            )
        return payloads, falhas

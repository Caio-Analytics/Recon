"""Exportação: JSON, Markdown, HTML e nomes de arquivo."""
import json

from recon.reporting import (
    exportar_conferencia_html,
    exportar_dicionario_xlsx,
    exportar_html,
    exportar_json,
    exportar_markdown,
    gerar_nome_unico,
    sanear_floats,
)


def _payload():
    return {
        "metadados_execucao": {
            "tabela": "TB_TESTE",
            "timestamp_utc": "2026-08-14T21:00:00+00:00",
            "versao_profiler": "3.0.0",
            "schema_version": "3.0",
            "linhas_originais": 100,
            "linhas_analisadas": 100,
            "amostragem_aplicada": False,
            "total_colunas": 3,
            "score_qualidade": {
                "score": 72.5, "nota": "C",
                "penalidades": [{"dimensao": "Nulos (incl. sentinelas)",
                                 "intensidade": 0.3, "pontos_perdidos": 7.5}],
            },
            "duplicatas": {"qtd_linhas_duplicadas": 4, "pct_linhas_duplicadas": 0.04},
            "resumo_qualidade": {
                "colunas_com_nulos": 1, "colunas_100pct_nulas": 0,
                "colunas_sensiveis_lgpd": 1, "colunas_com_sentinela": 1,
                "semanticas_mapeadas": 2,
                "semanticas_encontradas": ["Chave Identificadora (ID)", "Contato / Rede"],
                "kpis_habilitados": 0, "total_recomendacoes": 2,
            },
        },
        "colunas": [
            {"Coluna": "id", "Tipo_Inferred": "Número Inteiro",
             "Semantica_IA": "Chave Identificadora (ID)", "Papel": "Chave Identificadora (ID)",
             "Dominio": None, "Pct_Nulos": 0.0, "Qtd_Nulos": 0, "Qtd_Unicos": 100,
             "Ratio_Unicidade": 1.0, "Caracteristica": "🔑 Chave Primária Potencial",
             "Dado_Sensivel_LGPD": "Nenhum", "Amostra_Valores": "1, 2, 3",
             "Alertas": {"mistura_tipos": {"tem_mistura": False}, "data_como_texto": False},
             "Qualidade": {"nulos_efetivos_qtd": 0, "nulos_efetivos_pct": 0.0},
             "Otimizacao": {"dtype_atual": "int64", "dtype_sugerido": "int8",
                            "economia_mb": 0.7, "economia_pct": 0.87},
             "Stats_Extra": {"min": 1, "max": 100, "media": 50.5, "mediana": 50.5,
                             "desvio_padrao": 29.0, "assimetria": 0.0}},
            {"Coluna": "cpf", "Tipo_Inferred": "Texto",
             "Semantica_IA": "Chave Identificadora (ID)", "Papel": "Chave Identificadora (ID)",
             "Dominio": None, "Pct_Nulos": 2.0, "Qtd_Nulos": 2, "Qtd_Unicos": 98,
             "Ratio_Unicidade": 0.98, "Caracteristica": "📋 Atributo Geral",
             "Dado_Sensivel_LGPD": "CPF", "Amostra_Valores": "111********",
             "Alertas": {"mistura_tipos": {"tem_mistura": False}, "data_como_texto": False,
                         "stats_suprimidas_lgpd": True},
             "Qualidade": {"nulos_efetivos_qtd": 2, "nulos_efetivos_pct": 2.0},
             "Otimizacao": {}, "Stats_Extra": {"str_len_min": 14, "str_len_max": 14,
                                               "str_len_media": 14.0, "comprimento_fixo": True}},
            {"Coluna": "score_desempenho", "Tipo_Inferred": "Número Decimal",
             "Semantica_IA": "Resultado de Avaliação", "Papel": "Resultado de Avaliação",
             "Dominio": None, "Pct_Nulos": 0.0, "Qtd_Nulos": 0, "Qtd_Unicos": 40,
             "Ratio_Unicidade": 0.4, "Caracteristica": "📊 Métrica Contínua",
             "Dado_Sensivel_LGPD": "Nenhum", "Amostra_Valores": "1.5, 2.5",
             "Alertas": {"mistura_tipos": {"tem_mistura": False}, "data_como_texto": False},
             "Qualidade": {"nulos_efetivos_qtd": 0, "nulos_efetivos_pct": 0.0,
                           "sentinelas": {"tem_sentinela": True, "qtd_total": 5, "pct_total": 0.05,
                                          "valores": [{"valor": -1.0, "qtd": 5, "pct": 0.05}]}},
             "Otimizacao": {},
             "Stats_Extra": {
                 "min": 1.5, "max": 9.5, "media": 5.5, "mediana": 5.5, "desvio_padrao": 2.1,
                 "assimetria": 0.1,
                 "outliers_iqr": {"metodo": "IQR", "qtd_outliers_total": 3,
                                  "limite_inferior": 0.0, "limite_superior": 10.0},
                 "testes_hipotese": {
                     "shapiro_wilk": {"aplicavel": True, "estatistica_w": 0.98, "p_valor": 0.1234,
                                      "normal_provavel": True, "desvio_relevante": False},
                     "intervalo_confianca_media_95": {"aplicavel": True, "media": 5.5,
                                                      "limite_inferior": 5.0, "limite_superior": 6.0},
                     "distribuicao_provavel": {"aplicavel": True, "distribuicao": "normal",
                                               "criterio": "AIC", "aic": 1234.5,
                                               "escolha_conclusiva": True},
                 }}},
        ],
        "recomendacoes_etl": [
            {"Tabela": "TB_TESTE", "Coluna": "cpf", "Prioridade": "🔴 ALTA", "Camada": "Silver",
             "Acao": "LGPD: Mascarar 'cpf' (CPF).", "Linhas_Afetadas": 98},
            {"Tabela": "TB_TESTE", "Coluna": "id", "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
             "Acao": "Promover 'id' como PK.", "Linhas_Afetadas": 100},
        ],
        "dependencias_funcionais": [
            {"determinante": "a", "dependente": "b", "tipo": "Equivalência (Bijeção)",
             "descricao": "'a' e 'b' são equivalentes."},
        ],
        "colunas_redundantes": [{"coluna": "a", "coluna_redundante": "a2",
                                 "descricao": "'a2' é idêntica a 'a'."}],
        "chaves_compostas": [{"colunas": ["ano", "mes"], "descricao": "ano + mes identificam."}],
        "correlacoes": [{"coluna_a": "x", "coluna_b": "y", "metrica": "Pearson / Spearman",
                         "valor": 0.95, "valor_secundario": 0.94, "forca": "forte"}],
        "gap_analysis_kpis": [
            {"kpi_id": "KPI_HR_001", "kpi_nome": "Volume de Esforço por Departamento",
             "status": "❌ Bloqueado", "cobertura_pct": "0%",
             "semanticas_presentes": [], "semanticas_ausentes": ["Estrutura Organizacional"]},
        ],
        "analise_temporal_series": [
            {"coluna": "valor", "coluna_temporal_referencia": "dt", "agregacao": "mensal",
             "n_pontos": 36,
             "adf": {"aplicavel": True, "estacionaria": True, "p_valor": 0.01},
             "ljung_box": {"aplicavel": True, "autocorrelacionada": False, "p_valor": 0.4}},
        ],
    }


# ── Saneamento ──────────────────────────────────────────────────────────────

def test_sanear_floats_converte_nan_para_none():
    resultado = sanear_floats({"skew": float("nan"), "std": 1.5, "valores": [float("inf"), 2.0]})
    assert resultado == {"skew": None, "std": 1.5, "valores": [None, 2.0]}


def test_exportar_json_nunca_gera_token_nan_cru(tmp_path):
    caminho = tmp_path / "saida.json"
    exportar_json({"colunas": [{"nome": "x", "assimetria": float("nan")}]}, str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "NaN" not in conteudo
    assert json.loads(conteudo)["colunas"][0]["assimetria"] is None


def test_json_compacto_e_menor_que_indentado(tmp_path):
    indentado, compacto = tmp_path / "a.json", tmp_path / "b.json"
    exportar_json(_payload(), str(indentado))
    exportar_json(_payload(), str(compacto), compacto=True)

    assert compacto.stat().st_size < indentado.stat().st_size
    assert json.loads(compacto.read_text(encoding="utf-8"))["colunas"]


# ── Nomes de arquivo ────────────────────────────────────────────────────────

def test_nomes_de_aba_diferentes_nao_colidem():
    """Regressão: `nome_seguro` colapsa caracteres distintos no mesmo `_`, e
    duas abas (`Vendas 2024` / `Vendas-2024`) sobrescreviam o relatório uma da
    outra sem aviso."""
    usados = set()
    primeiro = gerar_nome_unico("Vendas 2024", usados)
    segundo = gerar_nome_unico("Vendas-2024", usados)

    assert primeiro == "Vendas_2024"
    assert segundo != primeiro


# ── Markdown ────────────────────────────────────────────────────────────────

def test_markdown_tem_secoes_esperadas(tmp_path):
    caminho = tmp_path / "relatorio.md"
    exportar_markdown(_payload(), str(caminho))
    conteudo = caminho.read_text(encoding="utf-8")

    for esperado in ("TB_TESTE", "Qualidade geral", "Principais problemas",
                     "Visão geral das colunas", "Detalhe por coluna",
                     "Recomendações ETL", "Relações entre colunas",
                     "Gap Analysis de KPIs", "Análise Temporal"):
        assert esperado in conteudo


def test_markdown_traz_estatisticas_por_coluna(tmp_path):
    """Regressão: o relatório humano não continha nenhuma estatística de
    coluna — min/max/média existiam só no JSON."""
    caminho = tmp_path / "relatorio.md"
    exportar_markdown(_payload(), str(caminho))
    conteudo = caminho.read_text(encoding="utf-8")

    assert "Faixa: 1.50 → 9.50" in conteudo or "Faixa: 1.50" in conteudo
    assert "Outliers: 3" in conteudo
    assert "Shapiro-Wilk" in conteudo
    assert "Comprimento: 14" in conteudo


def test_markdown_ordena_recomendacoes_por_prioridade(tmp_path):
    caminho = tmp_path / "relatorio.md"
    exportar_markdown(_payload(), str(caminho))
    conteudo = caminho.read_text(encoding="utf-8")

    secao = conteudo.split("## Recomendações ETL")[1]
    assert secao.index("🔴 ALTA") < secao.index("🟡 MÉDIA")


def test_markdown_sinaliza_supressao_de_estatisticas_lgpd(tmp_path):
    caminho = tmp_path / "relatorio.md"
    exportar_markdown(_payload(), str(caminho))
    assert "estatísticas de posição suprimidas" in caminho.read_text(encoding="utf-8")


# ── HTML ────────────────────────────────────────────────────────────────────

def test_html_e_autocontido_e_sem_recurso_externo(tmp_path):
    """Nenhum recurso buscado na rede: o relatório precisa abrir numa máquina
    corporativa com CDN bloqueada.

    O `xmlns` do SVG (`http://www.w3.org/2000/svg`) é identificador de
    namespace, não endereço buscado — verificar `"http://" not in conteudo`
    acusaria falso positivo em todo gráfico inline.
    """
    import re

    caminho = tmp_path / "relatorio.html"
    exportar_html(_payload(), str(caminho))
    conteudo = caminho.read_text(encoding="utf-8")

    assert conteudo.startswith("<!doctype html>")
    assert "<style>" in conteudo
    assert "<script" in conteudo
    assert "Buscar coluna" in conteudo
    assert "Navegar no relatório" in conteudo
    assert "atualizarAtiva" in conteudo
    assert "Resumo executivo" in conteudo
    assert "Ver problemas prioritários" in conteudo

    buscados = (
        re.findall(r"""(?:src|href)\s*=\s*['"]\s*https?://""", conteudo)
        + re.findall(r"url\(\s*['\"]?https?://", conteudo)
        + re.findall(r"@import\s+url", conteudo)
    )
    assert buscados == []


def test_html_contem_secoes_e_dados(tmp_path):
    caminho = tmp_path / "relatorio.html"
    exportar_html(_payload(), str(caminho))
    conteudo = caminho.read_text(encoding="utf-8")

    assert "TB_TESTE" in conteudo
    assert "score_desempenho" in conteudo
    assert "Gap Analysis" in conteudo
    assert "72.5" in conteudo


def test_html_escapa_conteudo_do_dado(tmp_path):
    payload = _payload()
    payload["colunas"][0]["Amostra_Valores"] = "<script>alert(1)</script>"
    caminho = tmp_path / "relatorio.html"

    exportar_html(payload, str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in conteudo
    assert "&lt;script&gt;" in conteudo


def test_html_tem_as_mesmas_secoes_do_markdown(tmp_path):
    """O HTML é o formato padrão — não pode perder seção que o Markdown tem.

    Regressão: `Principais problemas`, `Regras de negócio`, `Hierarquias` e
    `O que explica cada medida` só existiam no Markdown, e trocar o padrão
    teria rebaixado a saída sem ninguém perceber.
    """
    import re

    payload = _payload()
    payload["regras_negocio"] = [{
        "tipo": "Ordem entre datas", "regra": "`a` <= `b`", "descricao": "a nunca é posterior a b",
        "conformidade": 1.0, "qtd_violacoes": 0, "exemplos_violacao": [],
    }]
    payload["hierarquias"] = [{"niveis": ["a", "b", "c"], "descricao": "Hierarquia: a → b → c"}]
    payload["explicacoes_de_medidas"] = [{
        "medida": "salario", "explicacoes": [{"atributo": "cargo", "eta_quadrado": 0.87}],
        "descricao": "`salario` é explicada por `cargo`",
    }]

    md_path, html_path = tmp_path / "r.md", tmp_path / "r.html"
    exportar_markdown(payload, str(md_path))
    exportar_html(payload, str(html_path))

    md = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")

    for secao in ("Principais problemas", "Regras de negócio inferidas",
                  "Hierarquias", "O que explica cada medida"):
        assert secao in md, f"{secao} sumiu do Markdown"
        assert secao in html, f"{secao} falta no HTML"

    assert len(re.findall(r"<h2>", html)) >= 8


def test_aviso_de_amostragem_aparece_nos_dois_formatos(tmp_path):
    """Regressão: o aviso existia só no Markdown, e o HTML virou o padrão.

    Numa amostra a unicidade só pode ser subestimada, o que gera "chave
    primária potencial" que não existe na base inteira — omitir isso do
    formato padrão é o pior lugar para omitir.
    """
    payload = _payload()
    payload["metadados_execucao"]["amostragem_aplicada"] = True

    md, html = tmp_path / "a.md", tmp_path / "a.html"
    exportar_markdown(payload, str(md))
    exportar_html(payload, str(html))

    assert "Amostragem aplicada" in md.read_text(encoding="utf-8")
    assert "Amostragem aplicada" in html.read_text(encoding="utf-8")


def test_dicionario_neutraliza_formulas_vindas_da_base(tmp_path):
    """Conteúdo externo nunca pode virar fórmula ao abrir o XLSX."""
    from openpyxl import load_workbook

    payload = _payload()
    payload["metadados_execucao"]["tabela"] = "=TabelaExterna"
    payload["colunas"][0]["Coluna"] = "=HIPERLINK(\"https://exemplo\")"
    payload["colunas"][0]["Amostra_Valores"] = "+1+1"
    caminho = tmp_path / "dicionario.xlsx"

    exportar_dicionario_xlsx([payload], str(caminho))

    planilha = load_workbook(caminho, data_only=False).active
    assert planilha["A2"].data_type == "s"
    assert planilha["J2"].data_type == "s"
    assert planilha["A2"].value.startswith("'")
    assert planilha["J2"].value == "'+1+1"


def test_conferencia_html_renderiza_variacao_sem_drift_e_drift_sem_variacao(tmp_path):
    base = {
        "tabela_a": "antes", "tabela_b": "depois", "linhas_a": 10, "linhas_b": 12,
        "variacao_linhas": 0.2, "colunas_comuns": 1, "colunas_so_em_a": [],
        "colunas_so_em_b": [], "avisos": [], "chave_comparada": None,
        "motivo_sem_chave": "Sem chave.",
    }
    variacao = {
        "coluna": "status", "severidade": "🟡 MÉDIA", "pct_nulos_a": 0.0,
        "pct_nulos_b": 10.0, "unicos_a": 2, "unicos_b": 3, "tipo_a": "Texto",
        "tipo_b": "Texto", "mudou_tipo": False, "descricao": "Mais nulos.",
    }
    drift = {"coluna": "status", "tipo": "categórico", "descricao": "Categorias mudaram."}

    somente_variacao = tmp_path / "variacao.html"
    exportar_conferencia_html({**base, "variacoes_de_coluna": [variacao], "drifts_de_distribuicao": []}, str(somente_variacao))
    assert "Mais nulos." in somente_variacao.read_text(encoding="utf-8")

    somente_drift = tmp_path / "drift.html"
    exportar_conferencia_html({**base, "variacoes_de_coluna": [], "drifts_de_distribuicao": [drift]}, str(somente_drift))
    assert "Categorias mudaram." in somente_drift.read_text(encoding="utf-8")


def test_perfil_pdf_e_gerado_a_partir_do_html(tmp_path):
    from recon.pipeline import DataProfiler

    origem = tmp_path / "vendas.csv"
    origem.write_text("id,valor\n1,10\n2,20\n", encoding="utf-8")

    DataProfiler().processar_arquivo(str(origem), saida_base=str(tmp_path / "perfil"), formatos=["pdf"])

    pdf = tmp_path / "perfil_vendas.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")

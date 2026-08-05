import json
import math

from datascope.reporting import exportar_json, exportar_markdown, sanear_floats


def test_sanear_floats_converte_nan_para_none():
    resultado = sanear_floats({"skew": float("nan"), "std": 1.5, "valores": [float("inf"), 2.0]})
    assert resultado == {"skew": None, "std": 1.5, "valores": [None, 2.0]}


def test_exportar_json_nunca_gera_token_nan_cru(tmp_path):
    payload = {"colunas": [{"nome": "x", "assimetria": float("nan")}]}
    caminho = tmp_path / "saida.json"

    exportar_json(payload, str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "NaN" not in conteudo
    dados = json.loads(conteudo)  # json.loads padrão rejeita NaN cru se não houvesse o saneamento
    assert dados["colunas"][0]["assimetria"] is None


def _payload_minimo():
    return {
        "metadados_execucao": {
            "tabela": "TB_TESTE",
            "linhas_originais": 100,
            "linhas_analisadas": 100,
            "total_colunas": 2,
            "resumo_qualidade": {
                "colunas_com_nulos": 1, "colunas_100pct_nulas": 0,
                "colunas_sensiveis_lgpd": 1, "semanticas_mapeadas": 2,
                "semanticas_encontradas": ["Chave Identificadora (ID)", "Contato / Rede"],
                "kpis_habilitados": 0, "total_recomendacoes": 1,
            },
        },
        "colunas": [
            {"Coluna": "id", "Tipo_Inferred": "Número Inteiro", "Semantica_IA": "Chave Identificadora (ID)",
             "Pct_Nulos": 0.0, "Caracteristica": "🔑 Chave Primária Potencial"},
            {"Coluna": "cpf", "Tipo_Inferred": "Texto", "Semantica_IA": "Chave Identificadora (ID)",
             "Pct_Nulos": 2.0, "Caracteristica": "📋 Atributo Geral"},
            {"Coluna": "score_desempenho", "Tipo_Inferred": "Número Decimal", "Semantica_IA": "Resultado de Avaliação",
             "Pct_Nulos": 0.0, "Caracteristica": "📊 Métrica Contínua",
             "Stats_Extra": {
                 "testes_hipotese": {
                     "shapiro_wilk": {"aplicavel": True, "p_valor": 0.1234, "normal_provavel": True},
                     "intervalo_confianca_media_95": {"aplicavel": True, "media": 11.5, "limite_inferior": 10.2, "limite_superior": 12.8},
                     "distribuicao_provavel": {"aplicavel": True, "distribuicao": "normal", "p_valor": 0.4},
                 },
             }},
        ],
        "recomendacoes_etl": [
            {"Tabela": "TB_TESTE", "Coluna": "cpf", "Prioridade": "🔴 ALTA", "Camada": "Silver",
             "Acao": "LGPD: Mascarar 'cpf' (CPF)."},
        ],
        "dependencias_funcionais": [],
        "gap_analysis_kpis": [
            {"kpi_id": "KPI_HR_001", "kpi_nome": "Volume de Esforço por Departamento",
             "status": "❌ Bloqueado", "cobertura_pct": "0%"},
        ],
        "analise_temporal_series": [],
    }


def test_exportar_markdown_gera_arquivo_com_secoes_esperadas(tmp_path):
    caminho = tmp_path / "relatorio.md"

    exportar_markdown(_payload_minimo(), str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "TB_TESTE" in conteudo
    assert "cpf" in conteudo
    assert "Recomendações ETL" in conteudo
    assert "KPI_HR_001" in conteudo


def test_exportar_markdown_inclui_secao_de_testes_estatisticos(tmp_path):
    """A spec exige um resumo dos testes de hipótese no relatório Markdown
    (só existia a seção de análise temporal antes desta correção)."""
    caminho = tmp_path / "relatorio.md"

    exportar_markdown(_payload_minimo(), str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "## Testes Estatísticos" in conteudo
    assert "score_desempenho" in conteudo
    assert "Shapiro-Wilk" in conteudo
    assert "0.1234" in conteudo
    # coluna 'id' e 'cpf' não têm testes_hipotese no payload -> não devem
    # gerar ruído de "N/A" na seção.
    assert "N/A" not in conteudo

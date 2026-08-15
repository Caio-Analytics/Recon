"""Recomendações de ETL, gap analysis, score e regras de KPI."""
import pytest

from datascope import config, quality


def _stats(**overrides):
    base = {
        "nulos_qtd": 0,
        "caracteristica": "🏷️ Categórica / Dimensão Curta",
        "valores_unicos": 5,
        "ratio_unicidade": 0.05,
        "flags": {"is_date_as_text": False, "mistura_tipos": {"tem_mistura": False},
                  "detected_pattern": "Nenhum", "stats_suprimidas_lgpd": False},
        "qualidade": {},
        "otimizacao": {},
        "estatisticas_adicionais": {},
    }
    base.update(overrides)
    return base


def _acoes(recomendacoes):
    return " ".join(r["Acao"] for r in recomendacoes)


# ── Prioridades ─────────────────────────────────────────────────────────────

def test_ordenacao_por_prioridade_usa_rank_explicito():
    """Regressão: a ordenação dependia do codepoint do emoji e funcionava por
    acidente do Unicode — renomear uma prioridade quebraria em silêncio."""
    recomendacoes = [
        {"Prioridade": quality.PRIORIDADE_BAIXA, "Coluna": "c"},
        {"Prioridade": quality.PRIORIDADE_ALTA, "Coluna": "a"},
        {"Prioridade": quality.PRIORIDADE_MEDIA, "Coluna": "b"},
    ]
    ordenadas = quality.ordenar_por_prioridade(recomendacoes)
    assert [r["Prioridade"] for r in ordenadas] == [
        quality.PRIORIDADE_ALTA, quality.PRIORIDADE_MEDIA, quality.PRIORIDADE_BAIXA,
    ]


# ── Recomendações por coluna ────────────────────────────────────────────────

def test_chave_primaria_sensivel_recomenda_surrogate_key():
    """Regressão: o mesmo relatório mandava mascarar o CPF e, duas linhas
    abaixo, promovê-lo a chave primária."""
    stats = _stats(caracteristica="🔑 Chave Primária Potencial", valores_unicos=100)

    recomendacoes = quality.gerar_recomendacoes_etl("T", "cpf", stats, "CPF", 100)
    texto = _acoes(recomendacoes)

    assert "surrogate key" in texto
    assert "Promover 'cpf' como PK" not in texto


def test_chave_primaria_nao_sensivel_e_promovida_normalmente():
    stats = _stats(caracteristica="🔑 Chave Primária Potencial", valores_unicos=100)
    texto = _acoes(quality.gerar_recomendacoes_etl("T", "id", stats, "Nenhum", 100))
    assert "Promover 'id' como PK" in texto


def test_sentinela_gera_recomendacao_de_converter_para_null():
    stats = _stats(qualidade={
        "sentinelas": {"tem_sentinela": True, "qtd_total": 150, "pct_total": 0.3,
                       "valores": [{"valor": "N/A", "qtd": 80, "pct": 0.16}]},
    })
    recomendacoes = quality.gerar_recomendacoes_etl("T", "uf", stats, "Nenhum", 500)

    assert any(r["Prioridade"] == quality.PRIORIDADE_ALTA for r in recomendacoes)
    assert "NULL" in _acoes(recomendacoes)


def test_inconsistencia_de_grafia_gera_recomendacao():
    stats = _stats(qualidade={
        "inconsistencia_normalizacao": {
            "tem_inconsistencia": True, "valores_unicos_atual": 5,
            "valores_unicos_normalizado": 2, "grupos_afetados": 1,
            "exemplos": [{"variantes": ["SP", "sp", " SP"], "qtd_total": 300}],
        },
    })
    texto = _acoes(quality.gerar_recomendacoes_etl("T", "uf", stats, "Nenhum", 400))
    assert "Padronizar" in texto and "cardinalidade" in texto


def test_pii_em_texto_livre_gera_recomendacao_lgpd():
    stats = _stats(qualidade={"pii_texto_livre": {"tem_pii": True, "tipos": {"CPF": {}}}})
    recomendacoes = quality.gerar_recomendacoes_etl("T", "obs", stats, "Nenhum", 100)
    assert any("LGPD" in r["Acao"] and r["Prioridade"] == quality.PRIORIDADE_ALTA
               for r in recomendacoes)


def test_mojibake_gera_recomendacao_de_reprocessar_carga():
    stats = _stats(qualidade={
        "mojibake": {"tem_mojibake": True, "pct_amostra": 0.5, "exemplos": ["ObservaÃ§Ã£o"]},
    })
    assert "Reprocessar a carga" in _acoes(
        quality.gerar_recomendacoes_etl("T", "obs", stats, "Nenhum", 100)
    )


def test_datas_futuras_geram_recomendacao():
    stats = _stats(estatisticas_adicionais={"qtd_datas_futuras": 5, "max_data": "2099-12-31"})
    assert "futuro" in _acoes(quality.gerar_recomendacoes_etl("T", "dt", stats, "Nenhum", 100))


def test_sugestao_de_dtype_so_aparece_com_ganho_relevante():
    pouco = _stats(otimizacao={"dtype_sugerido": "int32", "dtype_atual": "int64",
                               "economia_mb": 0.1, "economia_pct": 0.1})
    muito = _stats(otimizacao={"dtype_sugerido": "int8", "dtype_atual": "int64",
                               "economia_mb": 3.5, "economia_pct": 0.87})

    assert "Converter" not in _acoes(quality.gerar_recomendacoes_etl("T", "x", pouco, "Nenhum", 100))
    assert "Converter" in _acoes(quality.gerar_recomendacoes_etl("T", "x", muito, "Nenhum", 100))


# ── Recomendações de tabela ─────────────────────────────────────────────────

def test_duplicatas_geram_recomendacao_de_alta_prioridade():
    recomendacoes = quality.gerar_recomendacoes_tabela(
        "T", {"qtd_linhas_duplicadas": 30, "pct_linhas_duplicadas": 0.23}, [], [], 130
    )
    assert recomendacoes[0]["Prioridade"] == quality.PRIORIDADE_ALTA
    assert "Deduplicar" in recomendacoes[0]["Acao"]


def test_sem_duplicata_nem_redundancia_nao_gera_recomendacao_de_tabela():
    assert quality.gerar_recomendacoes_tabela("T", {"qtd_linhas_duplicadas": 0}, [], [], 100) == []


# ── Gap analysis ────────────────────────────────────────────────────────────

def test_gap_analysis_kpi_bloqueado_sem_semanticas():
    assert all(g["status"] == "❌ Bloqueado" for g in quality.gerar_gap_analysis(set()))


def test_gap_analysis_kpi_habilitado_com_semanticas_completas():
    gaps = quality.gerar_gap_analysis({"Estrutura Organizacional", "Quantidade / Métrica"})
    assert next(g for g in gaps if g["kpi_id"] == "KPI_HR_001")["status"] == "✅ Habilitado"


def test_regras_kpi_semanticas_existem_na_taxonomia():
    todas = set(config.CATEGORIAS_FORTES) | set(config.CATEGORIAS_FUZZY)
    for regra in config.REGRAS_KPI_PADRAO:
        for semantica in regra["semanticas"]:
            assert semantica in todas, f"{semantica} não existe em nenhuma taxonomia"


def test_carregar_regras_kpi_de_yaml(tmp_path):
    arquivo = tmp_path / "kpis.yaml"
    arquivo.write_text(
        "kpis:\n"
        "  - id: KPI_FIN_001\n"
        "    nome: Receita por Região\n"
        "    semanticas: [Valor Financeiro, Localização Geográfica]\n",
        encoding="utf-8",
    )

    regras = quality.carregar_regras_kpi(str(arquivo))

    assert len(regras) == 1
    assert regras[0]["id"] == "KPI_FIN_001"
    gaps = quality.gerar_gap_analysis({"Valor Financeiro", "Localização Geográfica"}, regras)
    assert gaps[0]["status"] == "✅ Habilitado"


def test_carregar_regras_kpi_sem_caminho_usa_padrao():
    assert quality.carregar_regras_kpi(None) == config.REGRAS_KPI_PADRAO


def test_carregar_regras_kpi_invalido_levanta_erro(tmp_path):
    arquivo = tmp_path / "ruim.yaml"
    arquivo.write_text("kpis:\n  - nome: sem semanticas\n", encoding="utf-8")
    with pytest.raises(ValueError):
        quality.carregar_regras_kpi(str(arquivo))


# ── Score de qualidade ──────────────────────────────────────────────────────

def _coluna(**overrides):
    base = {
        "Pct_Nulos": 0.0, "Caracteristica": "🏷️ Categórica / Dimensão Curta",
        "Alertas": {"mistura_tipos": {"tem_mistura": False}, "data_como_texto": False},
        "Qualidade": {"nulos_efetivos_pct": 0.0},
    }
    base.update(overrides)
    return base


def test_score_maximo_para_tabela_limpa():
    resultado = quality.calcular_score_qualidade([_coluna(), _coluna()], {}, [])
    assert resultado["score"] == 100.0
    assert resultado["nota"] == "A"


def test_score_penaliza_e_ordena_dimensoes():
    colunas = [
        _coluna(Pct_Nulos=80.0,
                Qualidade={"nulos_efetivos_pct": 90.0,
                           "sentinelas": {"tem_sentinela": True}}),
        _coluna(Pct_Nulos=100.0, Caracteristica="⚠️ Coluna 100% Vazia",
                Qualidade={"nulos_efetivos_pct": 100.0}),
    ]
    resultado = quality.calcular_score_qualidade(
        colunas, {"pct_linhas_duplicadas": 0.5}, []
    )

    assert resultado["score"] < 60
    assert resultado["nota"] in {"C", "D", "E"}
    pontos = [p["pontos_perdidos"] for p in resultado["penalidades"]]
    assert pontos == sorted(pontos, reverse=True)


def test_score_nao_conta_sentinela_duas_vezes():
    """Regressão: `nulos_efetivos_pct` inclui as sentinelas, e usá-lo na
    dimensão de nulos fazia a mesma sujeira penalizar duas dimensões — o score
    saía pessimista em toda tabela com 'N/A'."""
    so_sentinela = [_coluna(
        Pct_Nulos=0.0,
        Qualidade={"nulos_efetivos_pct": 30.0, "sentinelas": {"tem_sentinela": True}},
    )]
    resultado = quality.calcular_score_qualidade(so_sentinela, {}, [])

    perdido = {p["dimensao"]: p["pontos_perdidos"] for p in resultado["penalidades"]}
    assert "Nulos reais" not in perdido
    assert perdido["Sentinelas / nulos disfarçados"] > 0


def test_score_de_tabela_sem_colunas():
    assert quality.calcular_score_qualidade([], {}, [])["score"] == 0.0

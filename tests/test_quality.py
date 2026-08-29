"""Recomendações de ETL, gap analysis, score e regras de KPI."""
import pytest

from recon import config, quality


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


def test_sugestao_de_dtype_e_agregada_numa_linha_so():
    """Regressão: numa tabela de 70 colunas eram 68 recomendações de 'converter
    para category' afogando os 22 achados que importavam."""
    colunas = [
        {"Coluna": f"c{i}", "Otimizacao": {"dtype_sugerido": "category",
                                           "dtype_atual": "str",
                                           "economia_mb": 1.5, "economia_pct": 0.9}}
        for i in range(30)
    ]
    recomendacoes = quality.gerar_recomendacoes_tabela(
        "T", {"qtd_linhas_duplicadas": 0}, [], [], 1000, colunas=colunas
    )
    dtype = [r for r in recomendacoes if "dtype" in r["Acao"]]

    assert len(dtype) == 1
    assert "30 coluna(s)" in dtype[0]["Acao"]
    assert "45.0 MB" in dtype[0]["Acao"]


def test_dtype_com_ganho_pequeno_nao_entra():
    colunas = [{"Coluna": "c", "Otimizacao": {"dtype_sugerido": "int32",
                                              "dtype_atual": "int64",
                                              "economia_mb": 0.1, "economia_pct": 0.1}}]
    recomendacoes = quality.gerar_recomendacoes_tabela(
        "T", {"qtd_linhas_duplicadas": 0}, [], [], 100, colunas=colunas
    )
    assert not [r for r in recomendacoes if "dtype" in r["Acao"]]


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
        "Coluna": "c", "Pct_Nulos": 0.0, "Caracteristica": "🏷️ Categórica / Dimensão Curta",
        "Alertas": {"mistura_tipos": {"tem_mistura": False}, "data_como_texto": False},
        "Qualidade": {"nulos_efetivos_pct": 0.0},
    }
    base.update(overrides)
    return base


def test_score_maximo_para_tabela_limpa():
    resultado = quality.calcular_score_qualidade([_coluna(), _coluna()], {}, [])
    assert resultado["score"] == 100.0
    assert resultado["nota"] == "A"
    assert resultado["colunas_comprometidas"] == 0


def test_score_e_invariante_ao_tamanho_da_tabela():
    """Regressão: cada dimensão dividia pelo total de colunas, então o score
    encolhia conforme a tabela crescia — uma base de 70 colunas com 21
    comprometidas tirava a mesma nota de uma base limpa."""
    def tabela(n_total, n_ruins):
        ruim = _coluna(Pct_Nulos=0.0,
                       Qualidade={"nulos_efetivos_pct": 0.0,
                                  "mojibake": {"tem_mojibake": True},
                                  "sentinelas": {"tem_sentinela": True}})
        return [ruim] * n_ruins + [_coluna()] * (n_total - n_ruins)

    pequena = quality.calcular_score_qualidade(tabela(10, 3), {}, [])["score"]
    grande = quality.calcular_score_qualidade(tabela(200, 60), {}, [])["score"]

    assert abs(pequena - grande) < 1.0
    assert pequena < 80


def test_score_discrimina_tabela_muito_suja():
    limpa = [_coluna() for _ in range(10)]
    suja = [
        _coluna(Caracteristica="⚠️ Coluna 100% Vazia"),
        _coluna(Pct_Nulos=60.0, Qualidade={"nulos_efetivos_pct": 60.0}),
        _coluna(Qualidade={"nulos_efetivos_pct": 0.0,
                           "mojibake": {"tem_mojibake": True},
                           "documento_invalido": {"tem_documento_invalido": True}}),
    ] + [_coluna() for _ in range(3)]

    assert quality.calcular_score_qualidade(limpa, {}, [])["score"] == 100.0
    assert quality.calcular_score_qualidade(suja, {}, [])["score"] < 65


def test_score_lista_as_colunas_mais_comprometidas():
    colunas = [
        _coluna(Coluna="ok"),
        _coluna(Coluna="morta", Caracteristica="⚠️ Coluna 100% Vazia"),
    ]
    resultado = quality.calcular_score_qualidade(colunas, {}, [])

    assert resultado["colunas_criticas"][0]["coluna"] == "morta"
    assert resultado["colunas_criticas"][0]["dano"] == 1.0
    assert "vazia" in resultado["colunas_criticas"][0]["motivos"][0]


def test_dano_da_coluna_satura_em_um():
    """Uma coluna com vários defeitos está mais comprometida que uma com um só,
    mas nenhuma passa de inutilizável."""
    pior = _coluna(Pct_Nulos=90.0, Qualidade={
        "nulos_efetivos_pct": 90.0,
        "mojibake": {"tem_mojibake": True},
        "documento_invalido": {"tem_documento_invalido": True},
        "sentinelas": {"tem_sentinela": True},
    })
    dano, motivos = quality.dano_da_coluna(pior)
    assert dano == 1.0
    assert len(motivos) >= 3


def test_duplicatas_derrubam_o_score():
    colunas = [_coluna() for _ in range(5)]
    limpo = quality.calcular_score_qualidade(colunas, {}, [])["score"]
    com_dup = quality.calcular_score_qualidade(
        colunas, {"pct_linhas_duplicadas": 0.5}, []
    )["score"]
    assert com_dup < limpo


def test_score_de_tabela_sem_colunas():
    assert quality.calcular_score_qualidade([], {}, [])["score"] == 0.0


# ── Risco LGPD ──────────────────────────────────────────────────────────────

def test_cnpj_nao_conta_como_risco_lgpd():
    """CNPJ identifica pessoa jurídica, não natural — a LGPD (Art. 5º, I)
    define dado pessoal como o que se relaciona a pessoa natural. Uma coluna
    só de CNPJ não pode gerar "risco de exposição de dado pessoal"."""
    colunas = [{"Coluna": "CNPJ_FORNECEDOR", "Dado_Sensivel_LGPD": "CNPJ", "Qualidade": {}}]
    resultado = quality.calcular_risco_lgpd(colunas)
    assert resultado["nivel"] == "🟢 Sem dado pessoal identificado"
    assert resultado["colunas_sensiveis"] == []


def test_cpf_continua_contando_como_risco_lgpd_junto_com_cnpj():
    """CNPJ fora do escopo não pode esconder um CPF real na mesma tabela."""
    colunas = [
        {"Coluna": "CNPJ_FORNECEDOR", "Dado_Sensivel_LGPD": "CNPJ", "Qualidade": {}},
        {"Coluna": "CPF_CLIENTE", "Dado_Sensivel_LGPD": "CPF", "Qualidade": {}},
    ]
    resultado = quality.calcular_risco_lgpd(colunas)
    assert [c["coluna"] for c in resultado["colunas_sensiveis"]] == ["CPF_CLIENTE"]

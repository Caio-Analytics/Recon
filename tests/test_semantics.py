import pytest

from recon import config
from recon.semantics import (
    PerfilConteudo,
    expandir_abreviatura,
    inferir_semantica,
    inferir_semanticas_da_tabela,
    semanticas_para_gap_analysis,
    tokenizar,
)


def test_tokenizar_separa_camel_case_e_snake_case():
    assert tokenizar("dt_admissao") == ["dt", "admissao"]
    assert tokenizar("hireDate") == ["hire", "date"]


def test_match_forte_por_token_exato():
    resultado = inferir_semantica("cod_departamento")
    assert resultado["semantica"] == config.SEMANTICA_CHAVE_ID
    assert resultado["confianca_score"] >= 0.90


def test_match_fuzzy_nome_com_erro_de_digitacao():
    assert inferir_semantica("cidde")["semantica"] == "Localização Geográfica"


def test_fallback_por_conteudo_cpf_ignora_nome():
    resultado = inferir_semantica("campo_qualquer", detectado_padrao="CPF")
    assert resultado["semantica"] == config.SEMANTICA_CHAVE_ID
    
    
    
    assert resultado["confianca_score"] >= 0.95


def test_nome_sem_semantica_cai_em_generico():
    assert inferir_semantica("xyzabc123")["semantica"] == config.SEMANTICA_GENERICA


@pytest.mark.parametrize("nome,esperado", [
    ("id_funcionario", config.SEMANTICA_CHAVE_ID),
    ("matricula_colaborador", config.SEMANTICA_CHAVE_ID),
    ("num_matricula", config.SEMANTICA_CHAVE_ID),
    ("cpf_cliente", config.SEMANTICA_CHAVE_ID),
    ("dt_desligamento", config.SEMANTICA_DATA_CALENDARIO),
    ("data_nascimento_usuario", config.SEMANTICA_DATA_CALENDARIO),
])
def test_qualificador_posicional_define_o_papel(nome, esperado):
    assert inferir_semantica(nome)["semantica"] == esperado


@pytest.mark.parametrize("nome,dominio", [
    ("nome_departamento", "Estrutura Organizacional"),
    ("nome_filial", "Estrutura Organizacional"),
    ("nome_curso", "Curso / Treinamento"),
    ("desc_cargo", "Cargo / Função"),
])
def test_dominio_vence_quando_o_papel_e_apenas_formal(nome, dominio):
    resultado = inferir_semantica(nome)
    assert resultado["semantica"] == dominio
    assert resultado["dominio"] == dominio


def test_dominio_e_avaliado_mesmo_com_papel_forte():
    resultado = inferir_semantica("cod_departamento")
    assert resultado["papel"] == config.SEMANTICA_CHAVE_ID
    assert resultado["dominio"] == "Estrutura Organizacional"


def test_semanticas_para_gap_analysis_reune_papel_e_dominio():
    resultado = inferir_semantica("cod_departamento")
    semanticas = set(semanticas_para_gap_analysis(resultado))
    assert semanticas == {config.SEMANTICA_CHAVE_ID, "Estrutura Organizacional"}


def test_nome_pessoal_puro_continua_sendo_nome():
    resultado = inferir_semantica("nome_completo")
    assert resultado["semantica"] == "Nome / Identificação Pessoal"
    assert resultado["dominio"] is None


def test_coluna_de_uf_e_localizacao():
    assert inferir_semantica("uf")["semantica"] == "Localização Geográfica"




@pytest.mark.parametrize("abreviatura,esperado", [
    ("dpto", "departamento"),
    ("mvto", "movimento"),
    ("func", "funcionario"),
    ("lotac", "lotacao"),
    ("trein", "treinamento"),
    ("escol", "escolaridade"),
    ("nasc", "nascimento"),
])
def test_abreviatura_reconstruida_por_subsequencia(abreviatura, esperado):
    assert esperado in [palavra for palavra, _ in expandir_abreviatura(abreviatura)]


def test_abreviatura_ambigua_devolve_todas_as_leituras():
    expansoes = [p for p, _ in expandir_abreviatura("dep")]
    assert {"departamento", "dependente", "deposito"} <= set(expansoes)


def test_abreviatura_ambigua_tem_confianca_menor():
    ((_, conf_unica),) = expandir_abreviatura("dpto")
    confs_ambiguas = [c for _, c in expandir_abreviatura("dep")]
    assert conf_unica > max(confs_ambiguas)


@pytest.mark.parametrize("nome,esperado", [
    ("cd_dpto_lot", "Chave Identificadora (ID)"),
    ("vl_saque", "Valor Financeiro"),
    ("qt_itens", "Quantidade / Métrica"),
    ("nm_cliente", "Nome / Identificação Pessoal"),
    ("dt_mvto", "Data / Calendário"),
])
def test_nome_abreviado_e_classificado(nome, esperado):
    resultado = inferir_semantica(nome)
    assert resultado["semantica"] == esperado
    assert resultado["confianca_score"] > 0.5




def _perfil(valores, tipo="Texto"):
    distintos = sorted(set(valores))
    return PerfilConteudo(
        tipo_dados=tipo, valores_distintos=distintos, n_unicos=len(distintos),
        ratio_unicidade=len(distintos) / len(valores),
    )


@pytest.mark.parametrize("valores,esperado", [
    (["SP", "RJ", "MG", "BA", "RS", "PR"] * 10, "Localização Geográfica"),
    (["M", "F", "MASCULINO", "FEMININO"] * 10, "Perfil do Colaborador"),
    (["Medio", "Superior", "Mestrado", "Doutorado"] * 10, "Perfil do Colaborador"),
    (["S", "N"] * 30, "Status / Indicador / Flag"),
    (["janeiro", "fevereiro", "marco", "abril"] * 10, "Data / Calendário"),
])
def test_nome_opaco_resolvido_pelo_conteudo(valores, esperado):
    resultado = inferir_semantica("f27", perfil=_perfil(valores))
    assert resultado["semantica"] == esperado


def test_conteudo_generico_nao_dispara_gazetteer():
    valores = [f"produto_{i}" for i in range(40)]
    assert inferir_semantica("f27", perfil=_perfil(valores))["semantica"] == \
        config.SEMANTICA_GENERICA




def test_resultado_traz_hipoteses_ranqueadas():
    resultado = inferir_semantica("cod_departamento")
    assert len(resultado["hipoteses"]) >= 2
    confiancas = [h["confianca"] for h in resultado["hipoteses"]]
    assert confiancas == sorted(confiancas, reverse=True)
    assert all(h["evidencias"] for h in resultado["hipoteses"])


def test_evidencias_independentes_se_reforcam():
    valores = ["SP", "RJ", "MG", "BA"] * 10
    so_nome = inferir_semantica("uf")
    so_conteudo = inferir_semantica("f27", perfil=_perfil(valores))
    ambos = inferir_semantica("uf", perfil=_perfil(valores))

    assert ambos["confianca_score"] > so_nome["confianca_score"]
    assert ambos["confianca_score"] > so_conteudo["confianca_score"]


def test_dominio_incerto_nao_e_afirmado():
    resultado = inferir_semantica("cod_dep")
    assert resultado["dominio"] is None
    assert any(h["semantica"] == "Estrutura Organizacional" for h in resultado["hipoteses"])
    assert resultado["conclusiva"] is False




def _tabela(colunas):
    return inferir_semanticas_da_tabela(
        [{"nome": c, "padrao": "Nenhum", "perfil": None} for c in colunas]
    )


def test_contexto_da_tabela_desambigua_abreviatura():
    colunas = ["matricula", "nome_func", "cod_dep", "diretoria", "dt_admissao"]
    resultado = _tabela(colunas)[colunas.index("cod_dep")]

    assert resultado["dominio"] == "Estrutura Organizacional"
    assert any("contexto da tabela" in e
               for h in resultado["hipoteses"] for e in h["evidencias"])


def test_sem_contexto_a_abreviatura_ambigua_fica_em_aberto():
    colunas = ["cod_curso", "nome_curso", "cod_dep", "carga_horaria"]
    resultado = _tabela(colunas)[colunas.index("cod_dep")]
    assert resultado["dominio"] is None


def test_contexto_nao_altera_coluna_ja_conclusiva():
    colunas = ["cpf", "nome_completo", "diretoria", "salario_bruto"]
    isolado = inferir_semantica("salario_bruto")
    com_tabela = _tabela(colunas)[colunas.index("salario_bruto")]
    assert com_tabela["semantica"] == isolado["semantica"]


def test_coluna_com_apenas_dominio_entra_no_contexto():
    assert inferir_semantica("diretoria")["conclusiva"] is True


def test_token_conhecido_nao_e_expandido_como_abreviatura():
    assert expandir_abreviatura("name") == ()
    assert inferir_semantica("FULL_NAME")["semantica"] == "Nome / Identificação Pessoal"


def test_abreviatura_de_verdade_continua_expandindo():
    for abreviatura, esperado in (("dpto", "departamento"), ("mvto", "movimento"),
                                  ("nasc", "nascimento"), ("vl", "valor")):
        assert esperado in [p for p, _ in expandir_abreviatura(abreviatura)]


def test_qualificador_na_ponta_final_define_o_papel():
    for coluna in ("SUPPLIER_CONTACT_CODE", "WAREHOUSE_ACCESS_IDENTIFIER",
                   "PROJECT_BUDGET_CODE", "SHIPPING_MANAGER_IDEN"):
        assert inferir_semantica(coluna)["papel"] == config.SEMANTICA_CHAVE_ID, coluna
    assert inferir_semantica("id_funcionario")["papel"] == config.SEMANTICA_CHAVE_ID


def test_expansao_ambigua_na_borda_resolve_pelo_papel():
    assert inferir_semantica("REFUND_TYPE_DES")["papel"] != "Valor Financeiro"


def test_nome_de_coisa_nao_e_nome_de_pessoa():
    assert inferir_semantica("FULL_NAME")["papel"] == config.SEMANTICA_NOME_PESSOA
    for coluna in ("DEPARTMENT_NAME", "POSITION_NAME"):
        assert inferir_semantica(coluna)["papel"] == config.SEMANTICA_ROTULO_ENTIDADE, coluna


def test_descricao_com_poucos_valores_vira_categoria():
    poucos = PerfilConteudo(tipo_dados="Texto", n_unicos=4, ratio_unicidade=0.00005)
    muitos = PerfilConteudo(tipo_dados="Texto", n_unicos=9000, ratio_unicidade=0.7)
    assert inferir_semantica("SHIFT_TYPE_DESC", perfil=poucos)["papel"] == \
        config.SEMANTICA_CATEGORIA
    assert inferir_semantica("JOB_DESCRIPTION", perfil=muitos)["papel"] == \
        config.SEMANTICA_TEXTO_LIVRE


def test_homografo_com_papel_forte_nao_gera_dominio():
    resultado = inferir_semantica("RECORD_UPDATE_TIME")
    assert resultado["papel"] == config.SEMANTICA_DATA_CALENDARIO
    assert resultado["dominio"] != "Estrutura Organizacional"


def test_prefixo_curto_nao_casa_com_palavra_longa():
    assert inferir_semantica("WORK_EMAIL_ADDRESS")["dominio"] != "Curso / Treinamento"


def test_nome_de_produto_nao_e_nome_de_pessoa():
    assert inferir_semantica("NOME_PRODUTO")["papel"] == config.SEMANTICA_ROTULO_ENTIDADE
    assert inferir_semantica("NOME_CLIENTE")["papel"] == config.SEMANTICA_NOME_PESSOA


def test_marca_de_produto_nao_vira_matricula():
    resultado = inferir_semantica("MARCA_PRODUTO")
    assert resultado["papel"] != config.SEMANTICA_CHAVE_ID
    assert resultado["dominio"] == "Produto / Item"


def test_qualificador_generico_perde_para_palavra_de_dominio_no_fuzzy():
    assert inferir_semantica("CATEGORIA_PRODUTO")["dominio"] == "Produto / Item"


def test_sufixo_de_unidade_de_duracao_vence_palavra_ambigua():
    assert inferir_semantica("PRAZO_ENTREGA_DIAS")["papel"] == "Quantidade / Métrica"


def test_ano_nao_vira_dado_pessoal():
    assert expandir_abreviatura("ano") == ()
    resultado = inferir_semantica("ANO_BASE")
    assert resultado["papel"] == config.SEMANTICA_DATA_CALENDARIO
    assert resultado["papel"] != config.SEMANTICA_NOME_PESSOA


def test_abreviatura_especulativa_de_duas_letras_nao_e_tentada():
    assert expandir_abreviatura("ue") == ()
    assert inferir_semantica("nm")[  
        "papel"
    ] == config.SEMANTICA_NOME_PESSOA


def test_nome_de_conceito_eleitoral_nao_e_dado_pessoal():
    for coluna in ("NM_PARTIDO", "NM_TIPO_ELEICAO", "NM_PARTIDO_FORNECEDOR"):
        assert inferir_semantica(coluna)["papel"] != config.SEMANTICA_NOME_PESSOA, coluna
    for coluna in ("NM_DOADOR", "NM_FORNECEDOR"):
        assert inferir_semantica(coluna)["papel"] == config.SEMANTICA_NOME_PESSOA, coluna


def test_nome_de_orgao_publico_nao_e_dado_pessoal():
    for coluna in ("Nome do órgão superior", "Nome órgão solicitante"):
        assert inferir_semantica(coluna)["papel"] != config.SEMANTICA_NOME_PESSOA, coluna


def test_sequencial_de_candidato_e_chave_nao_nome():
    assert inferir_semantica("SQ_CANDIDATO_FORNECEDOR")["papel"] == config.SEMANTICA_CHAVE_ID

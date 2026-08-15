"""Inferência semântica: papel, domínio e semântica primária."""
import pytest

from datascope import config
from datascope.semantics import (
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
    # A confiança passou a ser calculada a partir do peso das evidências, em vez
    # de fixada — conteúdo validado é a pista mais forte que existe, mas nem ela
    # chega a 1,0.
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
    """Regressão: o desempate usava o comprimento da palavra-chave, então o
    qualificador (`id`, `dt`, `cod`) sempre perdia para a entidade — e
    `id_funcionario` era classificado como 'Nome / Identificação Pessoal'."""
    assert inferir_semantica(nome)["semantica"] == esperado


@pytest.mark.parametrize("nome,dominio", [
    ("nome_departamento", "Estrutura Organizacional"),
    ("nome_filial", "Estrutura Organizacional"),
    ("nome_curso", "Curso / Treinamento"),
    ("desc_cargo", "Cargo / Função"),
])
def test_dominio_vence_quando_o_papel_e_apenas_formal(nome, dominio):
    """`nome_departamento` é sobre estrutura organizacional; 'Nome' descreve a
    forma, não o assunto."""
    resultado = inferir_semantica(nome)
    assert resultado["semantica"] == dominio
    assert resultado["dominio"] == dominio


def test_dominio_e_avaliado_mesmo_com_papel_forte():
    """Regressão estrutural: o fuzzy só rodava quando nenhum token forte
    casava. Como `cod`/`nome`/`id` prefixam metade das colunas de um sistema
    corporativo, as categorias de domínio ficavam inalcançáveis e o gap
    analysis dava KPI bloqueado com a coluna presente na tabela."""
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


# ── Expansão de abreviaturas ────────────────────────────────────────────────

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
    """Abreviatura corporativa é a palavra com letras removidas *na ordem*
    (`dpto` ⊂ `departamento`). Distância de edição erra esse caso;
    subsequência acerta."""
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


# ── Detecção por conteúdo (gazetteer) ───────────────────────────────────────

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
    """Uma coluna chamada `f27` cujos valores são as siglas de UF é uma coluna
    de localização, e nenhuma análise do nome chegaria lá."""
    resultado = inferir_semantica("f27", perfil=_perfil(valores))
    assert resultado["semantica"] == esperado


def test_conteudo_generico_nao_dispara_gazetteer():
    valores = [f"produto_{i}" for i in range(40)]
    assert inferir_semantica("f27", perfil=_perfil(valores))["semantica"] == \
        config.SEMANTICA_GENERICA


# ── Hipóteses e confiança ───────────────────────────────────────────────────

def test_resultado_traz_hipoteses_ranqueadas():
    resultado = inferir_semantica("cod_departamento")
    assert len(resultado["hipoteses"]) >= 2
    confiancas = [h["confianca"] for h in resultado["hipoteses"]]
    assert confiancas == sorted(confiancas, reverse=True)
    assert all(h["evidencias"] for h in resultado["hipoteses"])


def test_evidencias_independentes_se_reforcam():
    """Noisy-OR: nome e conteúdo apontando para a mesma coisa devem dar mais
    confiança do que qualquer um sozinho."""
    valores = ["SP", "RJ", "MG", "BA"] * 10
    so_nome = inferir_semantica("uf")
    so_conteudo = inferir_semantica("f27", perfil=_perfil(valores))
    ambos = inferir_semantica("uf", perfil=_perfil(valores))

    assert ambos["confianca_score"] > so_nome["confianca_score"]
    assert ambos["confianca_score"] > so_conteudo["confianca_score"]


def test_dominio_incerto_nao_e_afirmado():
    """Domínio abaixo do piso continua listado como hipótese, mas não vira
    fato no relatório."""
    resultado = inferir_semantica("cod_dep")
    assert resultado["dominio"] is None
    assert any(h["semantica"] == "Estrutura Organizacional" for h in resultado["hipoteses"])
    assert resultado["conclusiva"] is False


# ── Contexto da tabela ──────────────────────────────────────────────────────

def _tabela(colunas):
    return inferir_semanticas_da_tabela(
        [{"nome": c, "padrao": "Nenhum", "perfil": None} for c in colunas]
    )


def test_contexto_da_tabela_desambigua_abreviatura():
    """`dep` é insolúvel na coluna e trivial na tabela: com uma coluna
    organizacional inequívoca por perto, a leitura 'departamento' passa a ser
    a provável."""
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
    """`diretoria` não tem papel nenhum — ausência de evidência não é
    ambiguidade, e ela precisa contar como contexto resolvido."""
    assert inferir_semantica("diretoria")["conclusiva"] is True

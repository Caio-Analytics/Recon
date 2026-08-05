from datascope.semantics import inferir_semantica, tokenizar


def test_tokenizar_separa_camel_case_e_snake_case():
    assert tokenizar("dt_admissao") == ["dt", "admissao"]
    assert tokenizar("hireDate") == ["hire", "date"]


def test_match_forte_por_token_exato():
    resultado = inferir_semantica("cod_departamento")
    assert resultado["semantica"] == "Chave Identificadora (ID)"
    assert resultado["confianca_score"] >= 0.90


def test_match_fuzzy_nome_com_erro_de_digitacao():
    resultado = inferir_semantica("cidde")  # "cidade" com erro de digitação
    assert resultado["semantica"] == "Localização Geográfica"


def test_fallback_por_conteudo_cpf_ignora_nome():
    resultado = inferir_semantica("campo_qualquer", detectado_padrao="CPF")
    assert resultado["semantica"] == "Chave Identificadora (ID)"
    assert resultado["confianca_score"] == 1.0


def test_nome_sem_semantica_cai_em_generico():
    resultado = inferir_semantica("xyzabc123")
    assert resultado["semantica"] == "Genérico / Não mapeado"

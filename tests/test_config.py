"""Invariantes da configuração — protege contra renomeação silenciosa."""
import re

from recon import config


def test_padrao_email_aceita_dominio_com_multiplos_pontos():
    regex = config.PADROES_ESTRUTURADOS["E-mail"]
    assert re.match(regex, "usuario@empresa.com.br")
    assert re.match(regex, "usuario@empresa.com")


def test_categorias_fortes_tem_id_e_data():
    assert "id" in config.CATEGORIAS_FORTES[config.SEMANTICA_CHAVE_ID]
    assert "cpf" in config.CATEGORIAS_FORTES[config.SEMANTICA_CHAVE_ID]
    assert "data" in config.CATEGORIAS_FORTES[config.SEMANTICA_DATA_CALENDARIO]


def test_categorias_fuzzy_tem_localizacao():
    assert "cidade" in config.CATEGORIAS_FUZZY["Localização Geográfica"]


def test_categorias_fortes_e_fuzzy_nao_se_sobrepoem():
    """Uma mesma categoria nos dois dicionários tornaria papel e domínio
    ambíguos."""
    assert not set(config.CATEGORIAS_FORTES) & set(config.CATEGORIAS_FUZZY)


def test_padroes_estruturados_tem_cpf_cnpj_email():
    assert set(config.PADROES_ESTRUTURADOS) >= {"CPF", "CNPJ", "CEP", "E-mail", "Telefone", "UUID"}


def test_padroes_com_validacao_existem_entre_os_estruturados():
    assert set(config.PADROES_ESTRUTURADOS) >= config.PADROES_COM_VALIDACAO


def test_tokens_qualificadores_existem_em_alguma_categoria_forte():
    """Um qualificador que não mapeia para categoria alguma nunca dispara a
    regra posicional — seria configuração morta."""
    todos = {p for palavras in config.CATEGORIAS_FORTES.values() for p in palavras}
    mapeados = config.TOKENS_QUALIFICADORES & todos
    assert len(mapeados) >= 15


def test_threshold_determinante_max_unicidade_existe():
    assert 0.0 < config.THRESHOLD_DETERMINANTE_MAX_UNICIDADE < 1.0


def test_thresholds_testes_hipotese_existem():
    assert config.SHAPIRO_MIN_N == 20
    assert config.SHAPIRO_MAX_N == 5000
    assert config.CHI2_MIN_FREQ_ESPERADA == 5
    assert config.CHI2_MAX_CATEGORIAS == 50
    assert config.ADF_MIN_N == 30
    assert config.ALPHA_SIGNIFICANCIA == 0.05


def test_dano_por_defeito_esta_entre_zero_e_um():
    """O dano é por coluna, não fração do total — cada valor precisa ser
    interpretável como 'quanto desta coluna está comprometido'."""
    assert all(0 < v <= 1.0 for v in config.DANO_POR_DEFEITO.values())
    assert config.DANO_POR_DEFEITO["coluna_vazia"] == 1.0


def test_divisao_do_score_entre_coluna_e_tabela_soma_um():
    assert config.PESO_DANO_COLUNAS + config.PESO_DANO_TABELA == 1.0


def test_tipos_elegiveis_a_chave_excluem_decimal():
    assert "Número Decimal" not in config.TIPOS_ELEGIVEIS_CHAVE
    assert "Número Inteiro" in config.TIPOS_ELEGIVEIS_CHAVE


def test_sentinelas_de_texto_estao_normalizadas():
    """A comparação é feita sobre o valor normalizado — um catálogo com
    maiúscula ou acento nunca casaria."""
    for valor in config.SENTINELAS_TEXTO:
        assert valor == valor.lower().strip()


def test_defeito_grave_pesa_mais_que_defeito_leve():
    dano = config.DANO_POR_DEFEITO
    assert dano["mojibake"] > dano["data_como_texto"]
    assert dano["documento_invalido"] > dano["lgpd_estruturado"]

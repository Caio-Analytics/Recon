"""Invariantes da configuração — protege contra renomeação silenciosa."""
import re

from datascope import config


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


def test_pesos_do_score_somam_cem():
    """Os pesos são o desconto máximo possível: se somarem mais que 100 o
    score satura em zero antes de a última dimensão contar."""
    assert sum(config.PESOS_SCORE_QUALIDADE.values()) == 100.0


def test_tipos_elegiveis_a_chave_excluem_decimal():
    assert "Número Decimal" not in config.TIPOS_ELEGIVEIS_CHAVE
    assert "Número Inteiro" in config.TIPOS_ELEGIVEIS_CHAVE


def test_sentinelas_de_texto_estao_normalizadas():
    """A comparação é feita sobre o valor normalizado — um catálogo com
    maiúscula ou acento nunca casaria."""
    for valor in config.SENTINELAS_TEXTO:
        assert valor == valor.lower().strip()


def test_score_penaliza_abrangencia_alem_de_cada_defeito():
    """Cada dimensão divide pelo total de colunas, então um defeito em 1 de 8
    colunas nunca passa de 12,5% daquela dimensão. Sem uma dimensão de
    abrangência, uma tabela com seis colunas problemáticas — cada uma com um
    problema diferente — somava pouco em tudo e saía com nota alta."""
    assert "colunas_com_defeito" in config.PESOS_SCORE_QUALIDADE
    assert config.PESOS_SCORE_QUALIDADE["colunas_com_defeito"] >= 20

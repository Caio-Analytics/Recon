from data_profiler import config


def test_categorias_fortes_tem_id_e_data():
    assert "id" in config.CATEGORIAS_FORTES["Chave Identificadora (ID)"]
    assert "cpf" in config.CATEGORIAS_FORTES["Chave Identificadora (ID)"]
    assert "data" in config.CATEGORIAS_FORTES["Data / Calendário"]


def test_categorias_fuzzy_tem_localizacao():
    assert "cidade" in config.CATEGORIAS_FUZZY["Localização Geográfica"]


def test_padroes_estruturados_tem_cpf_cnpj_email():
    assert set(config.PADROES_ESTRUTURADOS) >= {"CPF", "CNPJ", "CEP", "E-mail", "Telefone", "UUID"}


def test_threshold_determinante_max_unicidade_existe():
    assert 0.0 < config.THRESHOLD_DETERMINANTE_MAX_UNICIDADE < 1.0


def test_thresholds_testes_hipotese_existem():
    assert config.SHAPIRO_MIN_N == 20
    assert config.SHAPIRO_MAX_N == 5000
    assert config.CHI2_MIN_FREQ_ESPERADA == 5
    assert config.CHI2_MAX_CATEGORIAS == 50
    assert config.ADF_MIN_N == 30
    assert config.ALPHA_SIGNIFICANCIA == 0.05

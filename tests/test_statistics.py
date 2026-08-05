import math

import numpy as np
import pandas as pd

from data_profiler.statistics import (
    analisar_estatisticas,
    calcular_intervalo_confianca_media,
    detectar_distribuicao_provavel,
    testar_autocorrelacao_ljungbox,
    testar_estacionariedade_adf,
    testar_normalidade_shapiro,
    testar_uniformidade_chi2,
)


def test_coluna_numerica_com_menos_de_3_validos_nao_gera_nan():
    serie = pd.Series([5.0, 7.0], name="score")

    resultado = analisar_estatisticas(serie, total_linhas=2)

    assimetria = resultado["estatisticas_adicionais"]["assimetria"]
    curtose = resultado["estatisticas_adicionais"]["curtose"]
    assert assimetria is None or math.isfinite(assimetria)
    assert curtose is None or math.isfinite(curtose)


def test_coluna_100_pct_vazia():
    serie = pd.Series([None, None, None], name="campo_lixo")

    resultado = analisar_estatisticas(serie, total_linhas=3)

    assert resultado["caracteristica"] == "⚠️ Coluna 100% Vazia"
    assert resultado["nulos_pct"] == 100.0


def test_coluna_chave_primaria_potencial():
    serie = pd.Series(range(100), name="id")

    resultado = analisar_estatisticas(serie, total_linhas=100)

    assert "Chave Primária Potencial" in resultado["caracteristica"]


def test_cpf_detectado_mesmo_em_coluna_de_chave_sistema():
    serie = pd.Series(["123.456.789-00"] * 20, name="id_cpf")

    resultado = analisar_estatisticas(serie, total_linhas=20)

    assert resultado["flags"]["detected_pattern"] == "CPF"


def test_cep_nao_detectado_em_coluna_de_chave_sistema():
    # 5 dígitos numéricos batem no regex de CEP, mas o nome indica chave de
    # sistema (contém "id") — não deve ser marcado como CEP.
    serie = pd.Series([str(90000 + i) for i in range(20)], name="id_interno")

    resultado = analisar_estatisticas(serie, total_linhas=20)

    assert resultado["flags"]["detected_pattern"] != "CEP"


def test_cpf_detectado_quando_armazenado_como_inteiro():
    serie = pd.Series([12345678900 + i for i in range(20)], name="cpf_colaborador")

    resultado = analisar_estatisticas(serie, total_linhas=20)

    assert resultado["flags"]["detected_pattern"] == "CPF"
    for valor in resultado["amostra_representativa"]:
        assert valor.count("*") > 0


def test_cnpj_detectado_quando_armazenado_como_inteiro():
    serie = pd.Series([12345678000100 + i for i in range(20)], name="cnpj_empresa")

    resultado = analisar_estatisticas(serie, total_linhas=20)

    assert resultado["flags"]["detected_pattern"] == "CNPJ"


def test_id_numerico_generico_nao_vira_cpf_falso_positivo():
    # 6 dígitos — comprimento comum de ID sequencial, não deve bater no
    # heurístico de CPF (10-11 dígitos) nem CNPJ (13-14 dígitos).
    serie = pd.Series(range(100000, 100020), name="id_funcionario")

    resultado = analisar_estatisticas(serie, total_linhas=20)

    assert resultado["flags"]["detected_pattern"] == "Nenhum"


def test_mistura_de_tipos_detectada():
    serie = pd.Series(
        ["123"] * 10 + ["texto_livre"] * 10 + ["2024-01-01"] * 10, name="tipo_misto"
    )

    resultado = analisar_estatisticas(serie, total_linhas=30)

    assert resultado["flags"]["mistura_tipos"]["tem_mistura"] is True


def test_coef_variacao_overflow_guard():
    # Regression test: ensure coef_variacao doesn't return inf when std/mean ratio overflows
    # Using values where the ratio could overflow: 1e300 / 1e-300 = inf
    serie = pd.Series([1e300, 1e300, 1e300, -1e-300], name="overflow_test")

    resultado = analisar_estatisticas(serie, total_linhas=4)

    coef_var = resultado["estatisticas_adicionais"]["coef_variacao"]
    # coef_variacao must be either None or a finite float, never inf/nan
    assert coef_var is None or math.isfinite(coef_var)


def test_shapiro_amostra_insuficiente_retorna_nao_aplicavel():
    resultado = testar_normalidade_shapiro(pd.Series([1.0, 2.0, 3.0]))
    assert resultado["aplicavel"] is False


def test_shapiro_normal_provavel_para_amostra_normal():
    rng = np.random.default_rng(42)
    serie = pd.Series(rng.normal(loc=0, scale=1, size=500))

    resultado = testar_normalidade_shapiro(serie)

    assert resultado["aplicavel"] is True
    assert resultado["normal_provavel"] is True


def test_chi2_categorias_demais_retorna_nao_aplicavel():
    serie = pd.Series([f"cat_{i}" for i in range(60)])
    resultado = testar_uniformidade_chi2(serie)
    assert resultado["aplicavel"] is False


def test_chi2_distribuicao_uniforme():
    serie = pd.Series((["A"] * 50 + ["B"] * 50 + ["C"] * 50))
    resultado = testar_uniformidade_chi2(serie)
    assert resultado["aplicavel"] is True
    assert resultado["distribuicao_uniforme_provavel"] is True


def test_ic_media_amostra_minima():
    resultado = calcular_intervalo_confianca_media(pd.Series([10.0, 20.0]))
    assert resultado["aplicavel"] is True
    assert resultado["limite_inferior"] <= resultado["media"] <= resultado["limite_superior"]


def test_distribuicao_provavel_amostra_insuficiente():
    resultado = detectar_distribuicao_provavel(pd.Series([1.0, 2.0, 3.0]))
    assert resultado["aplicavel"] is False


def test_distribuicao_provavel_detecta_normal():
    rng = np.random.default_rng(42)
    serie = pd.Series(rng.normal(loc=100, scale=15, size=500))

    resultado = detectar_distribuicao_provavel(serie)

    assert resultado["distribuicao"] == "normal"


def test_adf_amostra_insuficiente():
    resultado = testar_estacionariedade_adf(pd.Series(range(10), dtype=float))
    assert resultado["aplicavel"] is False


def test_ljungbox_amostra_insuficiente():
    resultado = testar_autocorrelacao_ljungbox(pd.Series(range(10), dtype=float))
    assert resultado["aplicavel"] is False


def test_ljungbox_serie_constante_nao_aplicavel():
    """Mirrors the nunique()<=1 guard já existente em testar_estacionariedade_adf:
    uma série de variância zero não deve reportar aplicavel=True com NaN."""
    resultado = testar_autocorrelacao_ljungbox(pd.Series([5.0] * 40))
    assert resultado["aplicavel"] is False


def test_valores_lgpd_sensiveis_sao_mascarados_na_amostra_e_no_top5():
    """Coluna com CPFs reais e nome que dispara detecção CPF: nem a amostra
    representativa nem a distribuição top5 devem conter o valor original."""
    cpfs_originais = [f"{100 + i:03d}.456.789-{i:02d}" for i in range(30)]
    serie = pd.Series(cpfs_originais, name="cpf_colaborador")

    resultado = analisar_estatisticas(serie, total_linhas=30)

    assert resultado["flags"]["detected_pattern"] == "CPF"
    amostra = resultado["amostra_representativa"]
    top5 = [item["valor"] for item in resultado["estatisticas_adicionais"]["distribuicao_top5"]]

    for original in cpfs_originais:
        assert original not in amostra
        assert original not in top5
    # A máscara deve preservar reconhecibilidade do padrão (mantém pontuação)
    assert any("***" in v for v in amostra)


def test_dtype_nullable_int64_classificado_como_numero():
    """pandas Int64 (nullable) tem `str(dtype) == "Int64"` (capital I). A
    checagem original `"int" in tipo_bruto` é case-sensitive e falha nesse
    caso, jogando a coluna para o ramo "Texto" silenciosamente."""
    serie = pd.Series([1, 2, 3, None], dtype="Int64")

    resultado = analisar_estatisticas(serie, total_linhas=4)

    assert "Número" in resultado["tipo_dados"]
    assert "media" in resultado["estatisticas_adicionais"]


def test_analisar_estatisticas_inclui_testes_hipotese_para_numerica():
    serie = pd.Series(range(50), dtype=float)

    resultado = analisar_estatisticas(serie, total_linhas=50)

    assert "testes_hipotese" in resultado["estatisticas_adicionais"]
    assert "shapiro_wilk" in resultado["estatisticas_adicionais"]["testes_hipotese"]

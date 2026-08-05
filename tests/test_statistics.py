import math

import numpy as np
import pandas as pd

from data_profiler.statistics import analisar_estatisticas


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

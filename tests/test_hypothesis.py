"""Testes de hipótese, seleção de distribuição e outliers robustos."""
import numpy as np
import pandas as pd

from recon.hypothesis import (
    calcular_intervalo_confianca_media,
    calcular_outliers,
    detectar_distribuicao_provavel,
    testar_autocorrelacao_ljungbox,
    testar_estacionariedade_adf,
    testar_normalidade_shapiro,
    testar_uniformidade_chi2,
)

# ── Normalidade ─────────────────────────────────────────────────────────────

def test_shapiro_amostra_insuficiente_retorna_nao_aplicavel():
    assert testar_normalidade_shapiro(pd.Series([1.0, 2.0, 3.0]))["aplicavel"] is False


def test_shapiro_serie_constante_nao_aplicavel_sem_warning(recwarn):
    resultado = testar_normalidade_shapiro(pd.Series([7.0] * 30))
    assert resultado["aplicavel"] is False
    assert len(recwarn) == 0


def test_shapiro_normal_provavel_para_amostra_normal():
    rng = np.random.default_rng(42)
    resultado = testar_normalidade_shapiro(pd.Series(rng.normal(0, 1, 500)))
    assert resultado["aplicavel"] is True
    assert resultado["normal_provavel"] is True


def test_shapiro_reporta_tamanho_do_desvio_alem_do_p_valor():
    """Com n grande o p-valor vai a zero por desvios irrelevantes. Sem uma
    medida de magnitude (W, assimetria, curtose), `p=0.0` não informa nada."""
    rng = np.random.default_rng(3)
    resultado = testar_normalidade_shapiro(pd.Series(rng.normal(0, 1, 3000)))

    assert "estatistica_w" in resultado
    assert resultado["estatistica_w"] > 0.99
    assert resultado["desvio_relevante"] is False

    assimetrica = testar_normalidade_shapiro(pd.Series(rng.lognormal(0, 1, 3000)))
    assert assimetrica["desvio_relevante"] is True


# ── Distribuição ────────────────────────────────────────────────────────────

def test_distribuicao_provavel_amostra_insuficiente():
    assert detectar_distribuicao_provavel(pd.Series([1.0, 2.0, 3.0]))["aplicavel"] is False


def test_distribuicao_provavel_serie_constante_nao_aplicavel_sem_warning(recwarn):
    resultado = detectar_distribuicao_provavel(pd.Series([7.0] * 30))
    assert resultado["aplicavel"] is False
    assert len(recwarn) == 0


def test_distribuicao_provavel_detecta_normal():
    rng = np.random.default_rng(42)
    resultado = detectar_distribuicao_provavel(pd.Series(rng.normal(100, 15, 500)))
    assert resultado["distribuicao"] == "normal"
    assert resultado["criterio"] == "AIC"


def test_distribuicao_provavel_detecta_lognormal():
    rng = np.random.default_rng(11)
    resultado = detectar_distribuicao_provavel(pd.Series(rng.lognormal(3, 0.6, 2000)))
    assert resultado["distribuicao"] == "lognormal"


def test_distribuicao_cauda_pesada_nao_e_classificada_como_normal():
    """Regressão: `kstest` com parâmetros estimados da própria amostra viola a
    premissa do teste e infla o p-valor — uma t de Student com 3 graus de
    liberdade passava como normal. O AIC penaliza o ajuste ruim da cauda."""
    rng = np.random.default_rng(7)
    dados = pd.Series(rng.standard_t(3, 2000))

    resultado = detectar_distribuicao_provavel(dados)
    shapiro = testar_normalidade_shapiro(dados)

    assert shapiro["normal_provavel"] is False
    # A distância KS da melhor candidata denuncia o desajuste, mesmo quando a
    # normal é a menos ruim entre as candidatas disponíveis.
    assert resultado["ks_distancia"] > 0.05


def test_distribuicao_reporta_ranking_e_empate_tecnico():
    rng = np.random.default_rng(5)
    resultado = detectar_distribuicao_provavel(pd.Series(rng.normal(50, 5, 300)))
    assert len(resultado["ranking"]) >= 2
    assert resultado["ranking"][0]["aic"] <= resultado["ranking"][1]["aic"]
    assert isinstance(resultado["escolha_conclusiva"], bool)


# ── Uniformidade ────────────────────────────────────────────────────────────

def test_chi2_categorias_demais_retorna_nao_aplicavel():
    contagens = pd.Series([f"cat_{i}" for i in range(60)]).value_counts()
    assert testar_uniformidade_chi2(contagens)["aplicavel"] is False


def test_chi2_distribuicao_uniforme():
    contagens = pd.Series(["A"] * 50 + ["B"] * 50 + ["C"] * 50).value_counts()
    resultado = testar_uniformidade_chi2(contagens)
    assert resultado["aplicavel"] is True
    assert resultado["distribuicao_uniforme_provavel"] is True
    assert resultado["v_cramer"] < 0.05


def test_chi2_reporta_v_de_cramer_como_tamanho_de_efeito():
    contagens = pd.Series(["A"] * 990 + ["B"] * 10).value_counts()
    resultado = testar_uniformidade_chi2(contagens)
    assert resultado["distribuicao_uniforme_provavel"] is False
    assert resultado["v_cramer"] > 0.9


# ── Intervalo de confiança ──────────────────────────────────────────────────

def test_ic_media_amostra_minima():
    resultado = calcular_intervalo_confianca_media(pd.Series([10.0, 20.0]))
    assert resultado["aplicavel"] is True
    assert resultado["limite_inferior"] <= resultado["media"] <= resultado["limite_superior"]


# ── Outliers ────────────────────────────────────────────────────────────────

def test_outliers_iqr_classico_em_serie_simetrica():
    rng = np.random.default_rng(1)
    serie = pd.Series(rng.normal(100, 10, 5000))
    resultado = calcular_outliers(serie)
    assert resultado["metodo"] == "IQR"
    assert resultado["qtd_outliers_total"] / len(serie) < 0.02


def test_outliers_usa_boxplot_ajustado_em_serie_assimetrica():
    """Regressão: o IQR com fator fixo 1,5 pressupõe simetria e acusa a cauda
    direita legítima de uma lognormal (salário, receita) como anomalia."""
    rng = np.random.default_rng(2)
    serie = pd.Series(rng.lognormal(8.5, 0.6, 5000))

    ajustado = calcular_outliers(serie)
    assert ajustado["metodo"] == "IQR ajustado (medcouple)"

    q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
    limite_classico = q3 + 1.5 * (q3 - q1)
    outliers_classicos = int((serie > limite_classico).sum())

    assert ajustado["qtd_outliers_superiores"] < outliers_classicos


def test_outliers_detecta_anomalia_real_mesmo_com_ajuste():
    rng = np.random.default_rng(4)
    serie = pd.Series(np.concatenate([rng.lognormal(8, 0.4, 2000), [1e9, 1.2e9]]))
    resultado = calcular_outliers(serie)
    assert resultado["qtd_outliers_superiores"] >= 2


# ── Séries temporais ────────────────────────────────────────────────────────

def test_adf_amostra_insuficiente():
    assert testar_estacionariedade_adf(pd.Series(range(10), dtype=float))["aplicavel"] is False


def test_ljungbox_amostra_insuficiente():
    assert testar_autocorrelacao_ljungbox(pd.Series(range(10), dtype=float))["aplicavel"] is False


def test_ljungbox_serie_constante_nao_aplicavel():
    assert testar_autocorrelacao_ljungbox(pd.Series([5.0] * 40))["aplicavel"] is False


def test_adf_detecta_serie_com_tendencia_como_nao_estacionaria():
    serie = pd.Series(np.cumsum(np.random.default_rng(9).normal(0.5, 1, 200)))
    resultado = testar_estacionariedade_adf(serie)
    assert resultado["aplicavel"] is True
    assert resultado["estacionaria"] is False

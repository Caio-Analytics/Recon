"""Testes de hipótese e seleção de distribuição.

Separado de `statistics` (que faz descrição de coluna) porque aqui a
responsabilidade é inferencial: cada função declara explicitamente quando
não é aplicável, em vez de devolver um número sem significado.
"""
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.stattools import medcouple
from statsmodels.tsa.stattools import adfuller

from . import config

# medcouple na statsmodels é O(n²) em memória; acima disso o cálculo é feito
# sobre uma subamostra determinística, que é suficiente para estimar a
# assimetria do boxplot.
_MEDCOUPLE_MAX_N = 5_000


def _como_float(x: Any) -> float:
    """Agregações do pandas são tipadas com uma união ampla (podem devolver
    Timestamp, Timedelta etc.). Nos caminhos numéricos deste módulo o valor é
    sempre escalar numérico — esta função concentra a conversão."""
    return float(x)


def valor_ou_none(x: Any) -> float | None:
    valor = _como_float(x)
    return round(valor, 6) if math.isfinite(valor) else None


# ── Outliers ────────────────────────────────────────────────────────────────

def calcular_outliers(serie: pd.Series) -> dict[str, Any]:
    """Detecta outliers por IQR, trocando para o boxplot ajustado de
    Hubert-Vandervieren quando a distribuição é assimétrica.

    O IQR clássico com fator 1,5 pressupõe simetria. Numa lognormal (salário,
    receita, tempo de atendimento — praticamente toda coluna financeira) ele
    acusa a cauda direita legítima como anomalia. O ajuste por medcouple
    alarga o limite do lado da cauda e mantém o outro, o que reduz o falso
    positivo sem perder o outlier de verdade.
    """
    q1 = _como_float(serie.quantile(0.25))
    q3 = _como_float(serie.quantile(0.75))
    iqr = q3 - q1

    assimetria = _como_float(serie.skew()) if len(serie) > 2 else 0.0
    usar_ajustado = math.isfinite(assimetria) and abs(assimetria) >= config.THRESHOLD_ASSIMETRIA_ROBUSTA
    mc = 0.0

    if usar_ajustado and iqr > 0:
        amostra = (
            serie.sample(n=_MEDCOUPLE_MAX_N, random_state=42)
            if len(serie) > _MEDCOUPLE_MAX_N else serie
        )
        try:
            mc = float(np.asarray(medcouple(amostra.to_numpy())).item())
        except Exception:
            mc = 0.0
        if not math.isfinite(mc):
            mc = 0.0

    if usar_ajustado and mc != 0.0:
        if mc >= 0:
            fator_inf, fator_sup = math.exp(-4 * mc), math.exp(3 * mc)
        else:
            fator_inf, fator_sup = math.exp(-3 * mc), math.exp(4 * mc)
        metodo = "IQR ajustado (medcouple)"
    else:
        fator_inf = fator_sup = 1.0
        metodo = "IQR"

    limite_inf = q1 - config.THRESHOLD_OUTLIER_IQR * fator_inf * iqr
    limite_sup = q3 + config.THRESHOLD_OUTLIER_IQR * fator_sup * iqr
    n_outliers_inf = int((serie < limite_inf).sum())
    n_outliers_sup = int((serie > limite_sup).sum())
    return {
        "metodo": metodo,
        "assimetria": valor_ou_none(assimetria),
        "medcouple": round(mc, 4) if metodo != "IQR" else None,
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "iqr": round(iqr, 4),
        "limite_inferior": round(limite_inf, 4),
        "limite_superior": round(limite_sup, 4),
        "qtd_outliers_inferiores": n_outliers_inf,
        "qtd_outliers_superiores": n_outliers_sup,
        "qtd_outliers_total": n_outliers_inf + n_outliers_sup,
    }


# ── Normalidade ─────────────────────────────────────────────────────────────

def testar_normalidade_shapiro(numericos: pd.Series) -> dict[str, Any]:
    """Shapiro-Wilk acompanhado do tamanho do desvio.

    Com n grande o p-valor de qualquer teste de normalidade tende a zero por
    desvios irrelevantes — reportar só `p=0.0` não informa nada. A estatística
    W (1,0 = normal perfeita) e a assimetria/curtose dizem o quanto a série
    se afasta, o que decide se dá para usar um método paramétrico.
    """
    n = len(numericos)
    if n < config.SHAPIRO_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.SHAPIRO_MIN_N})"}
    if _como_float(numericos.std()) == 0.0:
        return {"aplicavel": False, "motivo": "Série constante (variância zero) — teste de normalidade não aplicável"}

    amostra = (
        numericos.sample(n=config.SHAPIRO_MAX_N, random_state=42)
        if n > config.SHAPIRO_MAX_N else numericos
    )
    estatistica, p_valor = scipy_stats.shapiro(amostra)
    assimetria = _como_float(numericos.skew())
    curtose = _como_float(numericos.kurt())
    desvio_relevante = (
        (math.isfinite(assimetria) and abs(assimetria) >= 0.5)
        or (math.isfinite(curtose) and abs(curtose) >= 1.0)
    )
    return {
        "aplicavel": True,
        "estatistica_w": round(float(estatistica), 6),
        "p_valor": round(float(p_valor), 6),
        "normal_provavel": bool(p_valor > config.ALPHA_SIGNIFICANCIA),
        "assimetria": valor_ou_none(assimetria),
        "curtose_excesso": valor_ou_none(curtose),
        "desvio_relevante": bool(desvio_relevante),
        "n_amostra": int(len(amostra)),
    }


# ── Uniformidade ────────────────────────────────────────────────────────────

def testar_uniformidade_chi2(contagens: pd.Series) -> dict[str, Any]:
    """Qui-quadrado de aderência à distribuição uniforme.

    Recebe o `value_counts` já calculado — a mesma contagem alimenta a
    distribuição top-5 e a detecção de sentinela, não faz sentido varrer a
    coluna três vezes.
    """
    n_categorias = len(contagens)
    n_total = int(contagens.sum())
    if n_categorias < 2:
        return {"aplicavel": False, "motivo": "Menos de 2 categorias distintas"}
    if n_categorias > config.CHI2_MAX_CATEGORIAS:
        return {"aplicavel": False, "motivo": f"Categorias demais (n={n_categorias} > {config.CHI2_MAX_CATEGORIAS})"}
    freq_esperada = n_total / n_categorias
    if freq_esperada < config.CHI2_MIN_FREQ_ESPERADA:
        return {
            "aplicavel": False,
            "motivo": f"Frequência esperada insuficiente ({freq_esperada:.1f} < {config.CHI2_MIN_FREQ_ESPERADA})",
        }
    estatistica, p_valor = scipy_stats.chisquare(contagens.to_numpy())
    # V de Cramér para uma tabela 1×k: mede o quanto a distribuição se afasta
    # da uniforme numa escala 0-1, independente de n.
    v_cramer = math.sqrt(float(estatistica) / (n_total * (n_categorias - 1))) if n_total > 0 else 0.0
    return {
        "aplicavel": True,
        "estatistica": round(float(estatistica), 6),
        "p_valor": round(float(p_valor), 6),
        "distribuicao_uniforme_provavel": bool(p_valor > config.ALPHA_SIGNIFICANCIA),
        "v_cramer": round(v_cramer, 4),
        "n_categorias": int(n_categorias),
    }


# ── Intervalo de confiança ──────────────────────────────────────────────────

def calcular_intervalo_confianca_media(numericos: pd.Series) -> dict[str, Any]:
    n = len(numericos)
    if n < 2:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < 2)"}
    media = _como_float(numericos.mean())
    erro_padrao = _como_float(numericos.std(ddof=1)) / (n ** 0.5)
    if erro_padrao == 0.0 or not math.isfinite(erro_padrao):
        return {
            "aplicavel": True, "media": round(media, 6),
            "limite_inferior": round(media, 6), "limite_superior": round(media, 6),
        }
    limite_inf, limite_sup = scipy_stats.t.interval(0.95, df=n - 1, loc=media, scale=erro_padrao)
    return {
        "aplicavel": True,
        "media": round(media, 6),
        "limite_inferior": round(float(limite_inf), 6),
        "limite_superior": round(float(limite_sup), 6),
    }


# ── Seleção de distribuição ─────────────────────────────────────────────────

# Cada candidata declara os argumentos de ajuste e quantos parâmetros ficam
# livres. `floc=0` nas distribuições definidas em x>0 não é detalhe: com a
# locação livre o ajuste de 3 parâmetros é degenerado (a locação corre para o
# mínimo amostral) e vence qualquer comparação por verossimilhança sem
# descrever melhor os dados. Fixando-a, todas as candidatas competem com o
# mesmo número de graus de liberdade.
# nome -> (distribuição, kwargs do fit, nº de parâmetros livres)
_Candidata = tuple[Any, dict[str, Any], int]

_CANDIDATAS_SEMPRE: dict[str, _Candidata] = {"normal": (scipy_stats.norm, {}, 2)}
_CANDIDATAS_NAO_NEGATIVAS: dict[str, _Candidata] = {
    "uniforme": (scipy_stats.uniform, {}, 2),
    "exponencial": (scipy_stats.expon, {"floc": 0}, 1),
}
_CANDIDATAS_POSITIVAS: dict[str, _Candidata] = {
    "lognormal": (scipy_stats.lognorm, {"floc": 0}, 2),
    "gama": (scipy_stats.gamma, {"floc": 0}, 2),
}

_DIST_MAX_N = 20_000


def detectar_distribuicao_provavel(numericos: pd.Series) -> dict[str, Any]:
    """Escolhe a distribuição que melhor descreve a série por AIC.

    A abordagem anterior ajustava os parâmetros com `fit()` e testava aderência
    com `kstest` usando esses mesmos parâmetros. Isso viola a premissa do KS
    (parâmetros têm que ser conhecidos a priori) e infla o p-valor: uma t de
    Student com 3 graus de liberdade passava como normal. Além disso, escolher
    o maior p-valor compara modelos com número diferente de parâmetros livres,
    o que não é seleção de modelo.

    AIC responde a pergunta certa — qual modelo explica melhor os dados
    penalizando complexidade — e é estável, não depende de um limiar de
    significância. A distância KS continua sendo reportada, mas como medida
    descritiva de aderência, não como decisão.
    """
    n = len(numericos)
    if n < config.DIST_DETECTION_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.DIST_DETECTION_MIN_N})"}
    if _como_float(numericos.std()) == 0.0:
        return {"aplicavel": False, "motivo": "Série constante (variância zero) — nenhuma distribuição é aplicável"}

    valores = numericos.to_numpy()
    if n > _DIST_MAX_N:
        valores = numericos.sample(n=_DIST_MAX_N, random_state=42).to_numpy()

    candidatas: dict[str, _Candidata] = dict(_CANDIDATAS_SEMPRE)
    if (valores >= 0).all():
        candidatas.update(_CANDIDATAS_NAO_NEGATIVAS)
    if (valores > 0).all():
        candidatas.update(_CANDIDATAS_POSITIVAS)

    ranking: list[dict[str, Any]] = []
    for nome, (dist, kwargs_fit, k_livres) in candidatas.items():
        try:
            params = dist.fit(valores, **kwargs_fit)
            ajustada = dist(*params)
            log_verossimilhanca = float(np.sum(ajustada.logpdf(valores)))
            if not math.isfinite(log_verossimilhanca):
                continue
            aic = 2 * k_livres - 2 * log_verossimilhanca
            # A distribuição congelada é passada como callable: em scipy 1.18
            # o atalho `kstest(x, "norm", args=...)` levanta TypeError.
            ks = float(scipy_stats.kstest(valores, ajustada.cdf).statistic)
        except Exception:
            continue
        if not math.isfinite(aic):
            continue
        ranking.append({"distribuicao": nome, "aic": round(aic, 2), "ks_distancia": round(ks, 4)})

    if not ranking:
        return {"aplicavel": True, "distribuicao": "Desconhecida", "criterio": "AIC", "ranking": []}

    ranking.sort(key=lambda r: r["aic"])
    melhor = ranking[0]
    # Diferença de AIC < 2 é o limiar clássico de "modelos equivalentes":
    # nesse caso a escolha do topo não é informativa e o relatório diz isso.
    delta = ranking[1]["aic"] - melhor["aic"] if len(ranking) > 1 else float("inf")
    return {
        "aplicavel": True,
        "distribuicao": melhor["distribuicao"],
        "criterio": "AIC",
        "aic": melhor["aic"],
        "ks_distancia": melhor["ks_distancia"],
        "delta_aic_segundo": round(delta, 2) if math.isfinite(delta) else None,
        "escolha_conclusiva": bool(delta >= 2.0),
        "ranking": ranking[:4],
        "n_amostra": int(len(valores)),
    }


# ── Séries temporais ────────────────────────────────────────────────────────

def testar_estacionariedade_adf(serie_numerica_ordenada: pd.Series) -> dict[str, Any]:
    n = len(serie_numerica_ordenada)
    if n < config.ADF_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.ADF_MIN_N})"}
    if serie_numerica_ordenada.nunique() <= 1:
        return {"aplicavel": False, "motivo": "Série constante (variância zero) — teste ADF não aplicável"}
    try:
        resultado = adfuller(serie_numerica_ordenada.to_numpy(), autolag="AIC")
    except Exception as e:
        return {"aplicavel": False, "motivo": f"Falha no cálculo do ADF: {e}"}
    estatistica, p_valor = float(resultado[0]), float(resultado[1])
    return {
        "aplicavel": True,
        "estatistica": round(estatistica, 6),
        "p_valor": round(p_valor, 6),
        "estacionaria": bool(p_valor < config.ALPHA_SIGNIFICANCIA),
    }


def testar_autocorrelacao_ljungbox(serie_numerica_ordenada: pd.Series) -> dict[str, Any]:
    n = len(serie_numerica_ordenada)
    if n < config.ADF_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.ADF_MIN_N})"}
    if serie_numerica_ordenada.nunique() <= 1:
        return {"aplicavel": False, "motivo": "Série constante (variância zero) — Ljung-Box não aplicável"}
    lags = max(1, min(10, n // 5))
    try:
        resultado = acorr_ljungbox(serie_numerica_ordenada, lags=[lags], return_df=True)
    except Exception as e:
        return {"aplicavel": False, "motivo": f"Falha no cálculo do Ljung-Box: {e}"}
    estatistica = float(resultado["lb_stat"].iloc[0])
    p_valor = float(resultado["lb_pvalue"].iloc[0])
    return {
        "aplicavel": True,
        "estatistica": round(estatistica, 6),
        "p_valor": round(p_valor, 6),
        "autocorrelacionada": bool(p_valor < config.ALPHA_SIGNIFICANCIA),
        "lags": int(lags),
    }

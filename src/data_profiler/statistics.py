"""Análise estatística descritiva por coluna: tipagem, outliers, mistura de
tipos, padrões estruturados e testes de hipótese (Task 6)."""
import math
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from . import config
from .semantics import tokenizar


def _valor_ou_none(x: float) -> Optional[float]:
    return round(float(x), 6) if math.isfinite(float(x)) else None


def calcular_outliers_iqr(serie: pd.Series) -> Dict[str, Any]:
    q1 = float(serie.quantile(0.25))
    q3 = float(serie.quantile(0.75))
    iqr = q3 - q1
    limite_inf = q1 - config.THRESHOLD_OUTLIER_IQR * iqr
    limite_sup = q3 + config.THRESHOLD_OUTLIER_IQR * iqr
    n_outliers_inf = int((serie < limite_inf).sum())
    n_outliers_sup = int((serie > limite_sup).sum())
    return {
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "iqr": round(iqr, 4),
        "limite_inferior": round(limite_inf, 4),
        "limite_superior": round(limite_sup, 4),
        "qtd_outliers_inferiores": n_outliers_inf,
        "qtd_outliers_superiores": n_outliers_sup,
        "qtd_outliers_total": n_outliers_inf + n_outliers_sup,
    }


def calcular_distribuicao_top(serie: pd.Series, top_n: int = 5) -> List[Dict[str, Any]]:
    try:
        vc = serie.value_counts(normalize=True).head(top_n)
        return [
            {"valor": str(k), "frequencia_relativa": round(float(v), 4), "frequencia_pct": f"{v:.1%}"}
            for k, v in vc.items()
        ]
    except Exception:
        return []


def detectar_mistura_tipos(serie_limpa: pd.Series, amostra_str: List[str]) -> Dict[str, Any]:
    n = len(amostra_str)
    if n == 0:
        return {"tem_mistura": False}

    re_numerico = re.compile(r"^-?\d+([.,]\d+)?$")
    re_data = re.compile("|".join(config.PADROES_DATA))

    qtd_num = sum(1 for v in amostra_str if re_numerico.match(v.replace(",", ".")))
    qtd_data = sum(1 for v in amostra_str if re_data.match(v))
    qtd_vazio = sum(1 for v in amostra_str if v.strip() == "")
    qtd_texto_puro = n - qtd_num - qtd_data - qtd_vazio

    proporcoes = {
        "numerico": round(qtd_num / n, 4),
        "data": round(qtd_data / n, 4),
        "texto_puro": round(qtd_texto_puro / n, 4),
        "vazio_ou_nulo": round(qtd_vazio / n, 4),
    }
    tipos_dominantes = [k for k, v in proporcoes.items() if v >= config.THRESHOLD_MISTO_TIPOS]
    tem_mistura = len(tipos_dominantes) > 1

    return {
        "tem_mistura": tem_mistura,
        "tipos_detectados": tipos_dominantes if tem_mistura else [],
        "proporcoes": proporcoes if tem_mistura else {},
    }


def analisar_estatisticas(serie: pd.Series, total_linhas: int) -> Dict[str, Any]:
    nulos_qtd = int(serie.isna().sum())
    nulos_pct = round((nulos_qtd / total_linhas) * 100, 4) if total_linhas > 0 else 0.0

    serie_limpa = serie.dropna()
    n_validos = len(serie_limpa)
    n_unicos = int(serie_limpa.nunique())
    tipo_bruto = str(serie_limpa.dtype)

    n_amostrar = min(config.AMOSTRA_ANALISE, n_validos)
    amostra_serie = serie_limpa.sample(n=n_amostrar, random_state=42) if n_validos > 0 else serie_limpa
    amostra_str = amostra_serie.astype(str).tolist()

    flag_data_como_texto = False
    flag_padrao_estruturado = "Nenhum"
    estatisticas_extra: Dict[str, Any] = {}
    alerta_mistura_tipos: Dict[str, Any] = {"tem_mistura": False}
    tipo_amigavel = "Desconhecido"

    if "float" in tipo_bruto or "int" in tipo_bruto:
        numericos = serie_limpa.replace([np.inf, -np.inf], np.nan).dropna()

        if numericos.empty:
            tipo_amigavel = "Número (Apenas Inf/NaN)"
        elif (numericos % 1 == 0).all():
            tipo_amigavel = "Número Inteiro"
        else:
            tipo_amigavel = "Número Decimal"

        qtd_inf = int(serie_limpa.isin([np.inf, -np.inf]).sum())

        if not numericos.empty:
            std_val = float(numericos.std())
            media_val = float(numericos.mean())
            estatisticas_extra = {
                "min": round(float(numericos.min()), 6),
                "max": round(float(numericos.max()), 6),
                "media": round(media_val, 6),
                "mediana": round(float(numericos.median()), 6),
                "desvio_padrao": _valor_ou_none(std_val),
                "coef_variacao": _valor_ou_none(std_val / media_val) if media_val != 0 else None,
                "assimetria": _valor_ou_none(numericos.skew()),
                "curtose": _valor_ou_none(numericos.kurt()),
                "qtd_negativos": int((numericos < 0).sum()),
                "qtd_zeros": int((numericos == 0).sum()),
                "qtd_inf": qtd_inf,
                "outliers_iqr": calcular_outliers_iqr(numericos),
                "distribuicao_top5": calcular_distribuicao_top(serie_limpa, 5),
            }

    elif "datetime" in tipo_bruto:
        tipo_amigavel = "Data / Hora"
        if n_validos > 0:
            estatisticas_extra = {
                "min_data": str(serie_limpa.min()),
                "max_data": str(serie_limpa.max()),
                "range_dias": (serie_limpa.max() - serie_limpa.min()).days,
                "distribuicao_top5": calcular_distribuicao_top(serie_limpa, 5),
            }

    elif "bool" in tipo_bruto:
        tipo_amigavel = "Booleano"
        if n_validos > 0:
            estatisticas_extra = {
                "qtd_true": int(serie_limpa.sum()),
                "qtd_false": n_validos - int(serie_limpa.sum()),
                "pct_true": round(float(serie_limpa.sum()) / n_validos, 4),
            }

    else:
        tipo_amigavel = "Texto"
        if amostra_str:
            matches_dt = sum(1 for v in amostra_str if any(re.match(p, v) for p in config.PADROES_DATA))
            if (matches_dt / len(amostra_str)) >= config.THRESHOLD_DATA_TEXTO:
                tipo_amigavel = "Texto (⚠️ Parece Data)"
                flag_data_como_texto = True
            else:
                tokens_col = set(tokenizar(str(serie.name)))
                eh_chave_sistema = bool(tokens_col & config.TOKENS_CHAVE_SISTEMA)
                for padrao_nome, regex in config.PADROES_ESTRUTURADOS.items():
                    if eh_chave_sistema and padrao_nome in ("CEP", "Telefone"):
                        continue
                    matches_pad = sum(1 for v in amostra_str if re.match(regex, v))
                    if (matches_pad / len(amostra_str)) >= config.THRESHOLD_PADRAO_ESTRUTURADO:
                        flag_padrao_estruturado = padrao_nome
                        break
                alerta_mistura_tipos = detectar_mistura_tipos(serie_limpa, amostra_str)

        if n_validos > 0:
            lens = serie_limpa.astype(str).str.len()
            estatisticas_extra = {
                "str_len_min": int(lens.min()),
                "str_len_max": int(lens.max()),
                "str_len_media": round(float(lens.mean()), 2),
                "str_len_std": round(float(lens.std()), 2) if n_validos > 1 else 0.0,
                "comprimento_fixo": int(lens.min()) == int(lens.max()),
                "distribuicao_top5": calcular_distribuicao_top(serie_limpa, 5),
            }

    ratio_unicidade = n_unicos / total_linhas if total_linhas > 0 else 0.0
    top_freq = 0.0
    if n_validos > 0 and n_unicos > 1:
        try:
            top_freq = float(serie_limpa.value_counts(normalize=True).iloc[0])
        except Exception:
            top_freq = 0.0

    if nulos_pct == 100.0:
        caracteristica = "⚠️ Coluna 100% Vazia"
    elif n_unicos == 0:
        caracteristica = "⚠️ Sem Valores Válidos"
    elif n_unicos == 1:
        caracteristica = "🔒 Valor Constante"
    elif top_freq >= config.THRESHOLD_QUASI_CONSTANTE:
        caracteristica = f"⚠️ Quasi-Constante ({top_freq:.1%} em um único valor)"
    elif ratio_unicidade == 1.0 and total_linhas > 1:
        caracteristica = "🔑 Chave Primária Potencial"
    elif ratio_unicidade >= config.THRESHOLD_QUASE_CHAVE and total_linhas > 1:
        caracteristica = f"🔑 Quase-Chave ({ratio_unicidade:.1%} únicos — possível dado sujo)"
    elif "Data" in tipo_amigavel:
        caracteristica = "📅 Série Temporal"
    elif 1 < n_unicos <= 25:
        caracteristica = "🏷️ Categórica / Dimensão Curta"
    elif 25 < n_unicos <= 100:
        caracteristica = "📂 Dimensão Média"
    elif "Texto" in tipo_amigavel:
        caracteristica = "📋 Dimensão Longa (Texto Livre)"
    elif "Número" in tipo_amigavel:
        caracteristica = "📊 Métrica Contínua"
    else:
        caracteristica = "📋 Atributo Geral"

    valores_amostra: List[str] = []
    if n_validos > 0:
        if n_unicos <= 25:
            valores_amostra = [str(v) for v in serie_limpa.unique().tolist()]
        else:
            valores_amostra = (
                serie_limpa.drop_duplicates().sample(min(10, n_unicos), random_state=42).astype(str).tolist()
            )

    return {
        "tipo_dados": tipo_amigavel,
        "valores_unicos": n_unicos,
        "nulos_qtd": nulos_qtd,
        "nulos_pct": nulos_pct,
        "caracteristica": caracteristica,
        "ratio_unicidade": round(ratio_unicidade, 4),
        "amostra_representativa": valores_amostra,
        "estatisticas_adicionais": estatisticas_extra,
        "flags": {
            "is_date_as_text": flag_data_como_texto,
            "detected_pattern": flag_padrao_estruturado,
            "mistura_tipos": alerta_mistura_tipos,
        },
    }

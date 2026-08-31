"""Análise estatística descritiva por coluna: tipagem, outliers, mistura de
tipos, padrões estruturados, sentinelas e sugestão de dtype.

Os testes de hipótese vivem em `hypothesis`; a lógica de conteúdo de valor
(validação de documento, mascaramento, sentinela, mojibake) vive em
`patterns`. Aqui fica a descrição da coluna e a montagem do registro.
"""
import math
import re
from collections.abc import Callable
from typing import Any, cast

import numpy as np
import pandas as pd

from . import config, hypothesis, patterns
from .semantics import tokenizar

# Máximo de valores distintos para os quais vale a pena rodar as análises que
# dependem de agrupar por valor (sentinela textual, inconsistência de grafia).
# Acima disso a coluna é texto livre e o agrupamento não diz nada.
_MAX_CARDINALIDADE_ANALISE_VALOR = 5_000

_RE_DATA_QUALQUER = re.compile("|".join(config.PADROES_DATA))


def calcular_distribuicao_top(
    contagens: pd.Series,
    n_validos: int,
    top_n: int = 5,
    mascarar_fn: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    """Top-N valores mais frequentes a partir do `value_counts` já calculado."""
    if contagens.empty or n_validos <= 0:
        return []
    resultado = []
    for valor, qtd in contagens.head(top_n).items():
        freq = float(qtd) / n_validos
        resultado.append({
            "valor": mascarar_fn(str(valor)) if mascarar_fn else str(valor),
            "frequencia_relativa": round(freq, 4),
            "frequencia_pct": f"{freq:.1%}",
        })
    return resultado


def _casas_decimais_fixas(numericos: pd.Series) -> int | None:
    """Quantas casas decimais a coluna usa, se usar sempre as mesmas.

    Um decimal sempre com 2 casas é uma assinatura de valor monetário — pista
    fraca sozinha, útil quando somada a um nome ambíguo.
    """
    amostra = (
        numericos.sample(n=1_000, random_state=42) if len(numericos) > 1_000 else numericos
    )
    valores = amostra.to_numpy()
    for casas in range(4):
        if np.allclose(valores, np.round(valores, casas), rtol=0, atol=1e-9):
            return casas
    return None


def detectar_mistura_tipos(amostra_str: list[str]) -> dict[str, Any]:
    """Estima a proporção de numéricos, datas, texto e vazios numa amostra de
    strings, sinalizando quando mais de um tipo é relevante na mesma coluna."""
    n = len(amostra_str)
    if n == 0:
        return {"tem_mistura": False}

    qtd_num = sum(1 for v in amostra_str if patterns.eh_numerico_br(v))
    qtd_data = sum(1 for v in amostra_str if _RE_DATA_QUALQUER.match(v))
    qtd_vazio = sum(1 for v in amostra_str if v.strip() == "")
    qtd_texto_puro = max(n - qtd_num - qtd_data - qtd_vazio, 0)

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


# ── Sugestão de dtype ───────────────────────────────────────────────────────

def sugerir_dtype(
    serie: pd.Series, tipo_amigavel: str, n_unicos: int, n_validos: int
) -> dict[str, Any]:
    """Sugere um dtype mais econômico e estima o ganho de memória.

    É a recomendação de ETL mais diretamente acionável que dá para extrair de
    um profiling: vem com número em MB, não com uma opinião.
    """
    dtype_atual = str(serie.dtype)
    memoria_atual = int(serie.memory_usage(deep=True))
    sugerido: str | None = None

    if tipo_amigavel == "Número Inteiro" and n_validos > 0:
        numericos = pd.to_numeric(serie.dropna(), errors="coerce").dropna()
        if not numericos.empty:
            minimo, maximo = float(numericos.min()), float(numericos.max())
            # Com um nulo que seja, o pandas guarda inteiros como float64 e o
            # `astype("int16")` estoura no NaN — a sugestão morria no `except` e
            # a coluna ficava sem recomendação nenhuma. O dtype nullable do
            # pandas (`Int16`) tem o mesmo intervalo e aceita ausência, e coluna
            # inteira com nulo é a regra, não a exceção.
            tem_nulo = bool(serie.isna().any())
            for nome_tipo in ("int8", "int16", "int32"):
                info = np.iinfo(nome_tipo)
                if minimo >= info.min and maximo <= info.max:
                    sugerido = nome_tipo.capitalize() if tem_nulo else nome_tipo
                    break
    elif tipo_amigavel == "Número Decimal":
        if dtype_atual == "float64":
            sugerido = "float32"
    elif tipo_amigavel.startswith("Texto"):
        # `category` só compensa quando há repetição real; com cardinalidade
        # alta o dicionário custa mais do que economiza.
        if n_validos > 0 and n_unicos > 0 and (n_unicos / n_validos) <= 0.5:
            sugerido = "category"

    if sugerido is None or sugerido == dtype_atual:
        return {
            "dtype_atual": dtype_atual,
            "dtype_sugerido": None,
            "memoria_atual_mb": round(memoria_atual / 1e6, 3),
        }

    try:
        memoria_nova = int(serie.astype(cast(Any, sugerido)).memory_usage(deep=True))
    except Exception:
        return {
            "dtype_atual": dtype_atual,
            "dtype_sugerido": None,
            "memoria_atual_mb": round(memoria_atual / 1e6, 3),
        }

    economia = memoria_atual - memoria_nova
    return {
        "dtype_atual": dtype_atual,
        "dtype_sugerido": sugerido,
        "memoria_atual_mb": round(memoria_atual / 1e6, 3),
        "memoria_sugerida_mb": round(memoria_nova / 1e6, 3),
        "economia_mb": round(economia / 1e6, 3),
        "economia_pct": round(economia / memoria_atual, 4) if memoria_atual > 0 else 0.0,
    }


def calcular_histograma(numericos: pd.Series, n_faixas: int = 18) -> dict[str, Any] | None:
    """Distribuição da coluna em faixas, para desenhar o histograma.

    Vai no payload em vez de ser calculado na hora de renderizar porque o
    relatório é gerado a partir do JSON — quem consome o payload por código
    consegue redesenhar o mesmo gráfico sem reabrir o arquivo original.
    """
    if len(numericos) < 10:
        return None
    valores = numericos.to_numpy()
    minimo, maximo = float(valores.min()), float(valores.max())
    if not (math.isfinite(minimo) and math.isfinite(maximo)) or minimo == maximo:
        return None
    contagens, bordas = np.histogram(valores, bins=n_faixas)
    return {
        "faixas": [
            {"de": round(float(bordas[i]), 4), "ate": round(float(bordas[i + 1]), 4),
             "qtd": int(contagens[i])}
            for i in range(len(contagens))
        ],
        "min": round(minimo, 4),
        "max": round(maximo, 4),
    }


# ── Perfil de datas ─────────────────────────────────────────────────────────

def perfilar_datas(serie: pd.Series) -> dict[str, Any]:
    """Estatísticas específicas de coluna temporal.

    Datas no futuro, concentração no dia 1º e meses sem nenhum registro são
    sinais clássicos de erro de digitação, valor default e falha de carga —
    coisas que min/max sozinhos não revelam.
    """
    if serie.empty:
        return {}

    agora = pd.Timestamp.now()
    futuras = int((serie > agora).sum())
    dias_semana = serie.dt.dayofweek
    fim_de_semana = int(dias_semana.isin([5, 6]).sum())
    primeiro_dia_mes = int((serie.dt.day == 1).sum())
    n = len(serie)

    # A cobertura de calendário é medida só sobre o passado: uma única data
    # sentinela em 2099 esticaria o intervalo por décadas e transformaria todo
    # mês real num "mês faltante".
    serie_passado = serie[serie <= agora]
    meses = serie_passado.dt.to_period("M")
    meses_presentes = int(meses.nunique())
    span_meses = 0
    meses_faltantes: list[str] = []
    if meses_presentes > 0:
        periodo_min, periodo_max = meses.min(), meses.max()
        span_meses = int((periodo_max - periodo_min).n) + 1
        if 0 < span_meses <= 1_200:
            presentes = set(meses.unique().astype(str))
            todos = pd.period_range(periodo_min, periodo_max, freq="M").astype(str)
            meses_faltantes = [m for m in todos if m not in presentes]

    # Série mensal para o gráfico temporal. Limitada a 120 pontos: acima
    # disso o desenho vira ruído e o payload incha sem ganho de leitura.
    contagem_mensal = serie_passado.dt.to_period("M").value_counts().sort_index()
    serie_mensal = [
        {"mes": str(periodo), "qtd": int(qtd)}
        for periodo, qtd in list(contagem_mensal.items())[-120:]
    ]

    return {
        "serie_mensal": serie_mensal,
        "min_data": str(serie.min()),
        "max_data": str(serie.max()),
        "range_dias": int((serie.max() - serie.min()).days),
        "qtd_datas_futuras": futuras,
        "pct_datas_futuras": round(futuras / n, 4),
        "pct_fim_de_semana": round(fim_de_semana / n, 4),
        "pct_primeiro_dia_do_mes": round(primeiro_dia_mes / n, 4),
        "meses_cobertos": meses_presentes,
        "meses_no_intervalo": span_meses,
        "meses_sem_registro": meses_faltantes[:12],
        "qtd_meses_sem_registro": len(meses_faltantes),
    }


# ── Característica da coluna ────────────────────────────────────────────────

_CARACTERISTICA_METRICA = "📊 Métrica Contínua"
_CARACTERISTICA_TEXTO_LONGO = "📋 Dimensão Longa (Texto Livre)"


def _classificar_caracteristica(
    n_validos: int,
    n_unicos: int,
    total_linhas: int,
    ratio_unicidade: float,
    top_freq: float,
    tipo_amigavel: str,
) -> str:
    if n_validos == 0:
        return "⚠️ Coluna 100% Vazia"
    if n_unicos == 1:
        return "🔒 Valor Constante"
    if top_freq >= config.THRESHOLD_QUASI_CONSTANTE:
        return f"⚠️ Quasi-Constante ({top_freq:.1%} em um único valor)"

    # Unicidade alta só é sinal de chave em coluna que pode ser chave. Um
    # `Número Decimal` (salário, medida) é quase-único por natureza e virava
    # "possível dado sujo" sem nenhum motivo.
    elegivel_chave = tipo_amigavel in config.TIPOS_ELEGIVEIS_CHAVE
    if elegivel_chave and total_linhas > 1:
        if ratio_unicidade == 1.0:
            return "🔑 Chave Primária Potencial"
        if ratio_unicidade >= config.THRESHOLD_QUASE_CHAVE:
            # Sem "possível dado sujo": nome de pessoa e matrícula são
            # naturalmente quase-únicos numa base de cadastro, e o rótulo
            # acusava sujeira em toda coluna legítima. A ressalva sobre
            # conferir duplicatas continua na recomendação de ETL, que é onde
            # ela tem contexto.
            return f"🔑 Quase-Chave ({ratio_unicidade:.1%} únicos)"

    if config.TIPO_DATA_HORA in tipo_amigavel or "Parece Data" in tipo_amigavel:
        return "📅 Série Temporal"
    if 1 < n_unicos <= 25:
        return "🏷️ Categórica / Dimensão Curta"
    if 25 < n_unicos <= 100:
        return "📂 Dimensão Média"
    if "Texto" in tipo_amigavel:
        return _CARACTERISTICA_TEXTO_LONGO
    if "Número" in tipo_amigavel:
        return _CARACTERISTICA_METRICA
    return "📋 Atributo Geral"


def ajustar_caracteristica_com_semantica(caracteristica: str, papel: str | None) -> str:
    """Corrige a característica com o papel, que só é conhecido depois.

    A característica sai da forma do dado, e um identificador tem a mesma forma
    de outras coisas: inteiro e sem repetição parece métrica (`MANAGER_IDEN`
    saía como "Métrica Contínua", convidando alguém a somar uma matrícula);
    texto com muitos valores parece texto livre (`WAREHOUSE_LOCATION_CODE` saía como
    "Dimensão Longa (Texto Livre)", que ninguém trata como chave). O papel
    resolve os dois, mas só existe na fase 2 — daí o ajuste aqui em vez de
    dentro do classificador.
    """
    if papel != config.SEMANTICA_CHAVE_ID:
        return caracteristica
    if caracteristica in (_CARACTERISTICA_METRICA, _CARACTERISTICA_TEXTO_LONGO):
        return "🔢 Código / Identificador"
    return caracteristica


# ── Análise principal ───────────────────────────────────────────────────────

def analisar_estatisticas(
    serie: pd.Series, total_linhas: int, avaliar_benford: bool = False
) -> dict[str, Any]:
    """Perfil descritivo completo de uma coluna."""
    nulos_qtd = int(serie.isna().sum())
    nulos_pct = round((nulos_qtd / total_linhas) * 100, 4) if total_linhas > 0 else 0.0

    serie_limpa = serie.dropna()
    n_validos = len(serie_limpa)
    n_unicos = int(serie_limpa.nunique())
    tipo_bruto_lower = str(serie_limpa.dtype).lower()

    # Uma única passada de contagem alimenta top-5, frequência máxima,
    # qui-quadrado, sentinela textual e inconsistência de grafia. Antes cada
    # um desses recalculava por conta própria.
    contagens: pd.Series = (
        serie_limpa.value_counts() if n_validos > 0 else pd.Series(dtype="int64")
    )

    n_amostrar = min(config.AMOSTRA_ANALISE, n_validos)
    amostra_serie = (
        serie_limpa.sample(n=n_amostrar, random_state=42) if n_validos > 0 else serie_limpa
    )
    amostra_str = amostra_serie.astype(str).tolist()

    flag_data_como_texto = False
    flag_padrao_estruturado = "Nenhum"
    estatisticas_extra: dict[str, Any] = {}
    alerta_mistura_tipos: dict[str, Any] = {"tem_mistura": False}
    qualidade: dict[str, Any] = {}
    tipo_amigavel = "Desconhecido"
    stats_suprimidas = False
    monotonica_crescente = False
    casas_decimais: int | None = None

    # ── Numérico ────────────────────────────────────────────────────────
    if "float" in tipo_bruto_lower or "int" in tipo_bruto_lower:
        numericos = serie_limpa.replace([np.inf, -np.inf], np.nan).dropna()
        if pd.api.types.is_extension_array_dtype(numericos):
            # Dtypes nullable do pandas (Int64, Float64, ...) retornam
            # pd.NA em várias agregações (kurt, skew) em vez de NaN — usar
            # o dtype numpy padrão evita vazar NAType para o cálculo.
            numericos = numericos.astype("float64")

        if n_validos == 0:
            tipo_amigavel = config.TIPO_VAZIO
        elif numericos.empty:
            tipo_amigavel = "Número (Apenas Inf/NaN)"
        elif (numericos % 1 == 0).all():
            tipo_amigavel = "Número Inteiro"
        else:
            tipo_amigavel = "Número Decimal"

        qtd_inf = int(serie_limpa.isin([np.inf, -np.inf]).sum())

        if tipo_amigavel == "Número Inteiro" and not numericos.empty:
            amostra_num = numericos.sample(
                n=min(config.AMOSTRA_ANALISE, len(numericos)), random_state=42
            )
            flag_padrao_estruturado = patterns.detectar_padrao_numerico(
                [str(int(v)) for v in amostra_num]
            )

        if not numericos.empty:
            monotonica_crescente = bool(numericos.is_monotonic_increasing)
            casas_decimais = (
                _casas_decimais_fixas(numericos) if tipo_amigavel == "Número Decimal" else 0
            )
            sensivel = patterns.eh_sensivel(flag_padrao_estruturado)
            mascarar_fn_num = (
                (lambda v: patterns.mascarar_valor_sensivel(v, flag_padrao_estruturado))
                if sensivel else None
            )
            estatisticas_extra = {
                "qtd_negativos": int((numericos < 0).sum()),
                "qtd_zeros": int((numericos == 0).sum()),
                "qtd_inf": qtd_inf,
                "distribuicao_top5": calcular_distribuicao_top(
                    contagens, n_validos, 5, mascarar_fn=mascarar_fn_num
                ),
            }

            if sensivel:
                # Min, max, média, mediana e limites de outlier de uma coluna
                # de CPF/CNPJ são documentos reais de pessoas reais. Mascarar
                # só a amostra e publicar o mínimo em claro anula a proteção —
                # e para um identificador nenhum desses números tem
                # significado analítico. Suprimidos por completo.
                stats_suprimidas = True
                estatisticas_extra["estatisticas_suprimidas"] = {
                    "motivo": (
                        f"Coluna identificada como {flag_padrao_estruturado} (dado sensível LGPD). "
                        "Estatísticas de posição e dispersão omitidas para não expor o valor real."
                    ),
                }
            else:
                std_val = float(numericos.std())
                media_val = float(numericos.mean())
                estatisticas_extra.update({
                    "min": round(float(numericos.min()), 6),
                    "max": round(float(numericos.max()), 6),
                    "media": round(media_val, 6),
                    "mediana": round(float(numericos.median()), 6),
                    "desvio_padrao": hypothesis.valor_ou_none(std_val),
                    "coef_variacao": hypothesis.valor_ou_none(std_val / media_val) if media_val != 0 else None,
                    "assimetria": hypothesis.valor_ou_none(numericos.skew()),
                    "curtose": hypothesis.valor_ou_none(numericos.kurt()),
                    "outliers_iqr": hypothesis.calcular_outliers(numericos),
                })
                histograma = calcular_histograma(numericos)
                if histograma:
                    estatisticas_extra["histograma"] = histograma
                estatisticas_extra["testes_hipotese"] = {
                    "shapiro_wilk": hypothesis.testar_normalidade_shapiro(numericos),
                    "intervalo_confianca_media_95": hypothesis.calcular_intervalo_confianca_media(numericos),
                    "distribuicao_provavel": hypothesis.detectar_distribuicao_provavel(numericos),
                }
                if avaliar_benford:
                    benford = patterns.distribuicao_benford(numericos)
                    if benford:
                        estatisticas_extra["benford"] = benford

                qualidade["sentinelas"] = patterns.detectar_sentinelas_numericas(numericos, n_validos)

    # ── Data / hora ─────────────────────────────────────────────────────
    elif "datetime" in tipo_bruto_lower:
        tipo_amigavel = config.TIPO_DATA_HORA
        if n_validos > 0:
            estatisticas_extra = perfilar_datas(serie_limpa)
            estatisticas_extra["distribuicao_top5"] = calcular_distribuicao_top(contagens, n_validos, 5)
            qualidade["sentinelas"] = patterns.detectar_sentinelas_data(serie_limpa, n_validos)

    # ── Booleano ────────────────────────────────────────────────────────
    elif "bool" in tipo_bruto_lower:
        tipo_amigavel = "Booleano"
        if n_validos > 0:
            qtd_true = int(serie_limpa.sum())
            estatisticas_extra = {
                "qtd_true": qtd_true,
                "qtd_false": n_validos - qtd_true,
                "pct_true": round(qtd_true / n_validos, 4),
            }

    # ── Texto ───────────────────────────────────────────────────────────
    else:
        tipo_amigavel = config.TIPO_VAZIO if n_validos == 0 else "Texto"
        if amostra_str:
            matches_dt = sum(1 for v in amostra_str if _RE_DATA_QUALQUER.match(v))
            if (matches_dt / len(amostra_str)) >= config.THRESHOLD_DATA_TEXTO:
                tipo_amigavel = "Texto (⚠️ Parece Data)"
                flag_data_como_texto = True
            else:
                tokens_col = set(tokenizar(str(serie.name)))
                flag_padrao_estruturado = patterns.detectar_padrao_texto(
                    amostra_str, eh_chave_sistema=bool(tokens_col & config.TOKENS_CHAVE_SISTEMA)
                )
                alerta_mistura_tipos = detectar_mistura_tipos(amostra_str)

        if n_validos > 0:
            sensivel = patterns.eh_sensivel(flag_padrao_estruturado)
            mascarar_fn = (
                (lambda v: patterns.mascarar_valor_sensivel(v, flag_padrao_estruturado))
                if sensivel else None
            )
            lens = serie_limpa.astype(str).str.len()
            estatisticas_extra = {
                "str_len_min": int(lens.min()),
                "str_len_max": int(lens.max()),
                "str_len_media": round(float(lens.mean()), 2),
                "str_len_std": round(float(lens.std()), 2) if n_validos > 1 else 0.0,
                "comprimento_fixo": int(lens.min()) == int(lens.max()),
                "distribuicao_top5": calcular_distribuicao_top(
                    contagens, n_validos, 5, mascarar_fn=mascarar_fn
                ),
            }
            if n_unicos <= config.CHI2_MAX_CATEGORIAS:
                estatisticas_extra["testes_hipotese"] = {
                    "qui_quadrado_uniformidade": hypothesis.testar_uniformidade_chi2(contagens),
                }

            qualidade["mojibake"] = patterns.detectar_mojibake(amostra_str)
            if not sensivel:
                qualidade["pii_texto_livre"] = patterns.detectar_pii_em_texto_livre(amostra_str)
                qualidade["documento_invalido"] = patterns.detectar_documento_invalido(amostra_str)
            if n_unicos <= _MAX_CARDINALIDADE_ANALISE_VALOR:
                qualidade["sentinelas"] = patterns.detectar_sentinelas_texto(contagens, n_validos)
                qualidade["inconsistencia_normalizacao"] = (
                    patterns.detectar_inconsistencia_normalizacao(contagens)
                )
            # Formato dominante: cobre a família de códigos que não é CPF nem
            # CNPJ — matrícula, código de produto, número de contrato. O
            # achado é a lista de quem foge do formato, não o formato em si.
            if not sensivel and not flag_data_como_texto:
                qualidade["formato"] = patterns.inferir_formato(amostra_str)

    # ── Consolidação ────────────────────────────────────────────────────
    ratio_unicidade = n_unicos / total_linhas if total_linhas > 0 else 0.0
    top_freq = float(contagens.iloc[0]) / n_validos if (n_validos > 0 and n_unicos > 1) else 0.0

    caracteristica = _classificar_caracteristica(
        n_validos, n_unicos, total_linhas, ratio_unicidade, top_freq, tipo_amigavel
    )

    # Nulos efetivos = nulos reais + sentinelas. É o número que importa para
    # decidir se a coluna é utilizável, e o que antes saía como 0% numa coluna
    # 30% preenchida com "N/A".
    sentinela_qtd = int(qualidade.get("sentinelas", {}).get("qtd_total", 0))
    nulos_efetivos = nulos_qtd + sentinela_qtd
    qualidade["nulos_efetivos_qtd"] = nulos_efetivos
    qualidade["nulos_efetivos_pct"] = (
        round(nulos_efetivos / total_linhas * 100, 4) if total_linhas > 0 else 0.0
    )

    valores_amostra: list[str] = []
    if n_validos > 0:
        if n_unicos <= config.MAX_VALORES_AMOSTRA_COMPLETA:
            valores_amostra = [str(v) for v in serie_limpa.unique().tolist()]
        else:
            valores_amostra = (
                serie_limpa.drop_duplicates()
                .sample(min(10, n_unicos), random_state=42)
                .astype(str).tolist()
            )
        if patterns.eh_sensivel(flag_padrao_estruturado):
            valores_amostra = [
                patterns.mascarar_valor_sensivel(v, flag_padrao_estruturado) for v in valores_amostra
            ]
        elif qualidade.get("pii_texto_livre", {}).get("tem_pii"):
            valores_amostra = [patterns.redigir_pii_em_texto(v) for v in valores_amostra]

    return {
        "tipo_dados": tipo_amigavel,
        "valores_unicos": n_unicos,
        "monotonica_crescente": monotonica_crescente,
        "casas_decimais_fixas": casas_decimais,
        "nulos_qtd": nulos_qtd,
        "nulos_pct": nulos_pct,
        "caracteristica": caracteristica,
        "ratio_unicidade": round(ratio_unicidade, 4),
        "amostra_representativa": valores_amostra,
        "estatisticas_adicionais": estatisticas_extra,
        "qualidade": qualidade,
        "otimizacao": sugerir_dtype(serie, tipo_amigavel, n_unicos, n_validos),
        "flags": {
            "is_date_as_text": flag_data_como_texto,
            "detected_pattern": flag_padrao_estruturado,
            "mistura_tipos": alerta_mistura_tipos,
            "stats_suprimidas_lgpd": stats_suprimidas,
        },
    }

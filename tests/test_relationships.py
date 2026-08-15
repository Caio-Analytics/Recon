"""Relações entre colunas: FD, duplicatas, redundância, chaves compostas,
correlação e séries temporais."""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from recon import config, relationships


def _meta(coluna, qtd_unicos, ratio_unicidade,
          caracteristica="🏷️ Categórica / Dimensão Curta", tipo="Texto"):
    return {
        "Coluna": coluna, "Qtd_Unicos": qtd_unicos, "Ratio_Unicidade": ratio_unicidade,
        "Caracteristica": caracteristica, "Tipo_Inferred": tipo, "Pct_Nulos": 0.0,
        "Dado_Sensivel_LGPD": "Nenhum",
    }


# ── Dependências funcionais ─────────────────────────────────────────────────

def test_fd_real_e_detectada():
    df = pd.DataFrame({
        "cod_depto": ["D1"] * 5 + ["D2"] * 5,
        "nome_depto": ["Operações"] * 5 + ["TI"] * 5,
        "cidade": ["SP", "RJ"] * 5,
    })
    meta = [_meta("cod_depto", 2, 0.2), _meta("nome_depto", 2, 0.2), _meta("cidade", 2, 0.2)]

    fds = relationships.detectar_dependencias_funcionais(df, meta)

    assert any(f["determinante"] == "cod_depto" and f["dependente"] == "nome_depto" for f in fds)


def test_bijecao_e_reportada_uma_unica_vez_como_equivalencia():
    """Regressão: `cod → nome` e `nome → cod` saíam como duas linhas separadas
    para um único fato. Uma bijeção é uma equivalência, não duas FDs."""
    df = pd.DataFrame({
        "cod_depto": ["D1"] * 40 + ["D2"] * 40,
        "nome_depto": ["TI"] * 40 + ["RH"] * 40,
    })
    meta = [_meta("cod_depto", 2, 0.025), _meta("nome_depto", 2, 0.025)]

    fds = relationships.detectar_dependencias_funcionais(df, meta)

    assert len(fds) == 1
    assert fds[0]["tipo"] == "Equivalência (Bijeção)"


def test_coluna_quase_chave_nao_vira_determinante_trivial():
    df = pd.DataFrame({
        "id_quase_unico": [f"ID{i}" for i in range(100)],
        "outra_coluna": ["X"] * 50 + ["Y"] * 50,
    })
    meta = [_meta("id_quase_unico", 100, 1.0), _meta("outra_coluna", 2, 0.02)]

    fds = relationships.detectar_dependencias_funcionais(df, meta)

    assert "id_quase_unico" not in {f["determinante"] for f in fds}


def test_coluna_constante_nao_vira_dependente_trivial():
    df = pd.DataFrame({
        "cod_depto": ["D1"] * 5 + ["D2"] * 5,
        "flag_sempre_true": [True] * 10,
    })
    meta = [_meta("cod_depto", 2, 0.2), _meta("flag_sempre_true", 1, 0.1)]

    fds = relationships.detectar_dependencias_funcionais(df, meta)

    assert "flag_sempre_true" not in {f["dependente"] for f in fds}


def test_fd_considera_nulos_no_agrupador():
    df = pd.DataFrame({
        "cod_depto": ["D1", "D1", None, None],
        "nome_depto": ["Operações", "Operações", "TI", "RH"],
    })
    meta = [_meta("cod_depto", 2, 0.5), _meta("nome_depto", 3, 0.75)]

    fds = relationships.detectar_dependencias_funcionais(df, meta)

    de_nome = [f for f in fds if f["dependente"] == "nome_depto"]
    assert all(f["determinante"] != "cod_depto" for f in de_nome)


def test_poda_por_cardinalidade_nao_perde_fd_valida():
    """A poda `nunique(determinante) >= nunique(dependente)` é condição
    necessária de uma FD — precisa descartar pares sem eliminar achado real."""
    df = pd.DataFrame({
        "cidade": (["SP"] * 20 + ["RJ"] * 20 + ["BH"] * 20 + ["POA"] * 20),
        "uf": (["SP"] * 20 + ["RJ"] * 20 + ["MG"] * 20 + ["RS"] * 20),
        "regiao": (["Sudeste"] * 60 + ["Sul"] * 20),
    })
    meta = [_meta("cidade", 4, 0.05), _meta("uf", 4, 0.05), _meta("regiao", 2, 0.025)]

    fds = relationships.detectar_dependencias_funcionais(df, meta)
    pares = {(f["determinante"], f["dependente"]) for f in fds}

    assert ("uf", "regiao") in pares or ("cidade", "regiao") in pares


# ── Duplicatas e redundância ────────────────────────────────────────────────

def test_linhas_duplicadas_sao_contadas():
    base = pd.DataFrame({"a": range(100), "b": list("xy") * 50})
    df = pd.concat([base, base.head(30)], ignore_index=True)

    resultado = relationships.analisar_duplicatas(df)

    assert resultado["qtd_linhas_duplicadas"] == 30
    assert 0.23 < resultado["pct_linhas_duplicadas"] < 0.24


def test_tabela_sem_duplicata_reporta_zero():
    df = pd.DataFrame({"a": range(50)})
    assert relationships.analisar_duplicatas(df)["qtd_linhas_duplicadas"] == 0


def test_colunas_identicas_sao_detectadas():
    df = pd.DataFrame({"a": range(100), "a_copia": range(100), "b": list("xy") * 50})

    redundantes = relationships.detectar_colunas_redundantes(df)

    assert len(redundantes) == 1
    assert {redundantes[0]["coluna"], redundantes[0]["coluna_redundante"]} == {"a", "a_copia"}


def test_colunas_diferentes_nao_sao_reportadas_como_redundantes():
    df = pd.DataFrame({"a": range(100), "b": range(1, 101)})
    assert relationships.detectar_colunas_redundantes(df) == []


# ── Chave composta ──────────────────────────────────────────────────────────

def test_chave_composta_detectada_quando_nenhuma_coluna_e_unica():
    df = pd.DataFrame({
        "ano": [2023] * 12 + [2024] * 12,
        "mes": list(range(1, 13)) * 2,
        "valor": range(24),
    })
    meta = [
        _meta("ano", 2, 2 / 24), _meta("mes", 12, 12 / 24),
        _meta("valor", 24, 1.0, tipo="Número Inteiro"),
    ]
    # `valor` é único sozinho — removido para simular o caso sem PK natural.
    meta = [m for m in meta if m["Coluna"] != "valor"]

    chaves = relationships.detectar_chaves_compostas(df[["ano", "mes"]], meta)

    assert chaves and set(chaves[0]["colunas"]) == {"ano", "mes"}


def test_chave_composta_nao_e_sugerida_quando_ja_existe_pk():
    df = pd.DataFrame({"id": range(50), "grupo": ["A", "B"] * 25})
    meta = [_meta("id", 50, 1.0, tipo="Número Inteiro"), _meta("grupo", 2, 0.04)]

    assert relationships.detectar_chaves_compostas(df, meta) == []


# ── Correlação ──────────────────────────────────────────────────────────────

def test_correlacao_numerica_forte_detectada():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, 500)
    df = pd.DataFrame({"a": x, "b": x * 2 + rng.normal(0, 0.05, 500), "c": rng.normal(0, 1, 500)})
    meta = [_meta(c, 500, 1.0, tipo="Número Decimal") for c in df.columns]

    correlacoes = relationships.analisar_correlacoes(df, meta)
    pares = {frozenset((c["coluna_a"], c["coluna_b"])) for c in correlacoes}

    assert frozenset(("a", "b")) in pares
    assert frozenset(("a", "c")) not in pares


def test_correlacao_categorica_usa_v_de_cramer():
    df = pd.DataFrame({
        "uf": ["SP"] * 100 + ["RJ"] * 100,
        "regional": ["Sudeste-1"] * 100 + ["Sudeste-2"] * 100,
    })
    meta = [_meta("uf", 2, 0.01), _meta("regional", 2, 0.01)]

    correlacoes = relationships.analisar_correlacoes(df, meta)

    assert any(c["metrica"] == "V de Cramér" for c in correlacoes)


def test_correlacao_categorica_numerica_usa_razao_de_correlacao():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({
        "cargo": ["Junior"] * 100 + ["Senior"] * 100,
        "salario": np.concatenate([rng.normal(3000, 50, 100), rng.normal(12000, 50, 100)]),
    })
    meta = [_meta("cargo", 2, 0.01), _meta("salario", 200, 1.0, tipo="Número Decimal")]

    correlacoes = relationships.analisar_correlacoes(df, meta)

    assert any(c["metrica"].startswith("Razão de correlação") for c in correlacoes)


# ── Séries temporais ────────────────────────────────────────────────────────

def _meta_temporal(coluna, tipo, semantica, caracteristica="📊 Métrica Contínua", unicos=100):
    return {
        "Coluna": coluna, "Tipo_Inferred": tipo, "Semantica_IA": semantica,
        "Papel": semantica, "Pct_Nulos": 0.0, "Caracteristica": caracteristica,
        "Qtd_Unicos": unicos, "Ratio_Unicidade": 0.5, "Dado_Sensivel_LGPD": "Nenhum",
        "Alertas": {},
    }


def test_analise_temporal_ausente_sem_coluna_de_data():
    df = pd.DataFrame({"valor": range(50)})
    meta = [_meta_temporal("valor", "Número Inteiro", config.SEMANTICA_GENERICA)]
    assert relationships.analisar_series_temporais(df, meta) == []


def test_analise_temporal_agrega_por_periodo():
    """Regressão: o ADF rodava sobre linhas transacionais ordenadas por data —
    várias linhas na mesma data, espaçamento irregular. O que era testado era a
    ordem arbitrária dentro do dia, não a dinâmica temporal."""
    inicio = date(2022, 1, 1)
    datas, valores = [], []
    for i in range(120):
        for _ in range(5):  # 5 lançamentos por dia
            datas.append(inicio + timedelta(days=i))
            valores.append(100 + i * 0.5)
    df = pd.DataFrame({"dt_evento": pd.to_datetime(datas), "valor": valores})
    meta = [
        _meta_temporal("dt_evento", config.TIPO_DATA_HORA, config.SEMANTICA_DATA_CALENDARIO,
                       "📅 Série Temporal"),
        _meta_temporal("valor", "Número Decimal", "Valor Financeiro"),
    ]

    resultado = relationships.analisar_series_temporais(df, meta)

    assert len(resultado) == 1
    assert resultado[0]["agregacao"] == "diária"
    # 600 linhas viram 120 pontos diários — a agregação é o que torna o teste
    # interpretável.
    assert resultado[0]["n_pontos"] == 120


def test_analise_temporal_ignora_colunas_de_chave():
    """A estacionariedade de um ID sequencial não significa nada."""
    inicio = date(2022, 1, 1)
    n = 200
    df = pd.DataFrame({
        "dt_evento": pd.to_datetime([inicio + timedelta(days=i) for i in range(n)]),
        "id_registro": range(n),
        "valor": np.random.default_rng(3).normal(100, 5, n),
    })
    meta = [
        _meta_temporal("dt_evento", config.TIPO_DATA_HORA, config.SEMANTICA_DATA_CALENDARIO,
                       "📅 Série Temporal"),
        _meta_temporal("id_registro", "Número Inteiro", config.SEMANTICA_CHAVE_ID,
                       "🔑 Chave Primária Potencial", unicos=n),
        _meta_temporal("valor", "Número Decimal", "Valor Financeiro"),
    ]

    colunas = {r["coluna"] for r in relationships.analisar_series_temporais(df, meta)}

    assert "id_registro" not in colunas
    assert "valor" in colunas


def test_analise_temporal_data_iso_como_texto_nao_emite_warning(recwarn):
    """Regressão: `dayfirst=True` fixo emitia UserWarning em data ISO e podia
    inverter dia/mês em arquivo de formato americano."""
    n = 200
    datas = [(date(2022, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    df = pd.DataFrame({"dt_evento": datas, "valor": np.arange(n, dtype=float)})
    meta = [
        _meta_temporal("dt_evento", "Texto (⚠️ Parece Data)", config.SEMANTICA_DATA_CALENDARIO,
                       "📅 Série Temporal"),
        _meta_temporal("valor", "Número Decimal", "Quantidade / Métrica"),
    ]
    meta[0]["Alertas"] = {"data_como_texto": True}

    resultado = relationships.analisar_series_temporais(df, meta)

    assert len(resultado) == 1
    assert not [w for w in recwarn if "dayfirst" in str(w.message)]


def test_analise_temporal_data_brasileira_dd_mm_aaaa():
    n = 200
    datas = [(date(2022, 1, 1) + timedelta(days=i)).strftime("%d/%m/%Y") for i in range(n)]
    df = pd.DataFrame({"dt_evento": datas, "valor": np.arange(n, dtype=float)})
    meta = [
        _meta_temporal("dt_evento", "Texto (⚠️ Parece Data)", config.SEMANTICA_DATA_CALENDARIO,
                       "📅 Série Temporal"),
        _meta_temporal("valor", "Número Decimal", "Quantidade / Métrica"),
    ]
    meta[0]["Alertas"] = {"data_como_texto": True}

    resultado = relationships.analisar_series_temporais(df, meta)

    assert len(resultado) == 1
    assert resultado[0]["n_pontos"] >= config.ADF_MIN_N


def test_redundancia_parcial_encontra_mesmo_dado_de_duas_origens():
    """Numa base consolidada, o par 93% igual vale mais que o 100% igual: o
    idêntico é coluna sobrando, o quase-idêntico é o mesmo campo vindo de dois
    sistemas — e as linhas divergentes são a lista de reconciliação."""
    base = [f"USR{i:05d}" for i in range(200)]
    divergente = list(base)
    for i in range(0, 200, 25):          # 8 linhas divergentes = 96% de acordo
        divergente[i] = f"OUTRO{i}"
    df = pd.DataFrame({"sistema_a": base, "sistema_b": divergente})

    achados = relationships.detectar_colunas_redundantes(df)
    parciais = [a for a in achados if a["tipo"] == "quase idêntica"]
    assert len(parciais) == 1
    assert parciais[0]["linhas_divergentes"] == 8
    assert 0.9 <= parciais[0]["concordancia"] < 1.0


def test_colunas_sem_relacao_nao_viram_redundancia_parcial():
    df = pd.DataFrame({"a": [f"x{i}" for i in range(100)],
                       "b": [f"y{i}" for i in range(100)]})
    assert relationships.detectar_colunas_redundantes(df) == []


def test_redundancia_exata_continua_reportada_sozinha():
    """Par idêntico não pode aparecer duas vezes (exato + parcial)."""
    valores = [f"v{i}" for i in range(50)]
    df = pd.DataFrame({"a": valores, "b": list(valores)})
    achados = relationships.detectar_colunas_redundantes(df)
    assert len(achados) == 1
    assert achados[0]["tipo"] == "idêntica"

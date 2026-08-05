from data_profiler.pipeline import DataProfiler, analisar_temporal_series


def test_processar_dataframe_retorna_payload_completo(df_rh_exemplo):
    profiler = DataProfiler()

    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    assert resultado["metadados_execucao"]["tabela"] == "TB_TESTE"
    assert len(resultado["colunas"]) == len(df_rh_exemplo.columns)
    assert "recomendacoes_etl" in resultado
    assert "dependencias_funcionais" in resultado
    assert "gap_analysis_kpis" in resultado
    assert "analise_temporal_series" in resultado


def test_processar_dataframe_detecta_lgpd_no_cpf(df_rh_exemplo):
    profiler = DataProfiler()
    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    col_cpf = next(c for c in resultado["colunas"] if c["Coluna"] == "cpf_colaborador")
    assert col_cpf["Dado_Sensivel_LGPD"] == "CPF"


def test_processar_dataframe_detecta_fd_cod_para_nome_departamento(df_rh_exemplo):
    profiler = DataProfiler()
    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    determinantes = {d["determinante"] for d in resultado["dependencias_funcionais"]}
    assert "cod_departamento" in determinantes


def test_analise_temporal_ausente_sem_coluna_de_data():
    import pandas as pd
    df = pd.DataFrame({"valor": range(50)})
    colunas_meta = [{"Coluna": "valor", "Semantica_IA": "Genérico / Não mapeado", "Tipo_Inferred": "Número Inteiro", "Pct_Nulos": 0.0}]

    resultado = analisar_temporal_series(df, colunas_meta)

    assert resultado == []


def test_analise_temporal_roda_com_coluna_de_data(df_rh_exemplo):
    profiler = DataProfiler()
    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    # dt_admissao é datetime e o nome bate em "Data / Calendário" -> deve ativar
    assert len(resultado["analise_temporal_series"]) > 0
    entrada = resultado["analise_temporal_series"][0]
    assert entrada["coluna_temporal_referencia"] == "dt_admissao"


def test_analise_temporal_roda_com_coluna_de_data_como_texto_csv():
    """CSVs nunca passam por parse_dates em ingestion.py — uma coluna de data
    chega como string pura ('2020-01-15', não pd.Timestamp) e statistics.py a
    classifica como 'Texto (⚠️ Parece Data)', não 'Data / Hora'. Antes da
    correção, analisar_temporal_series só aceitava Tipo_Inferred == 'Data /
    Hora', então a análise temporal nunca ativava para CSV. Este teste usa uma
    coluna de datas como strings Python simples (não pd.to_datetime-wrapped),
    ao contrário da fixture df_rh_exemplo que já vem pré-parseada."""
    import pandas as pd

    df = pd.DataFrame({
        "dt_pedido": ["2020-01-15", "2021-03-10", "2022-06-20", "2023-09-01"] * 12 + ["2024-01-01"] * 2,
        "valor_pedido": [float(i % 10) + 1 for i in range(50)],
    })
    profiler = DataProfiler()

    resultado = profiler.processar_dataframe(df, "TB_CSV")

    col_data = next(c for c in resultado["colunas"] if c["Coluna"] == "dt_pedido")
    assert col_data["Alertas"]["data_como_texto"] is True
    assert col_data["Tipo_Inferred"] != "Data / Hora"
    assert len(resultado["analise_temporal_series"]) > 0
    assert resultado["analise_temporal_series"][0]["coluna_temporal_referencia"] == "dt_pedido"


def test_analise_temporal_datas_br_dd_mm_aaaa_nao_sao_misparseadas():
    """Regressão: 31 dias consecutivos (janeiro/2024) em formato brasileiro
    dd/mm/aaaa (config.PADROES_DATA reconhece ^\\d{2}/\\d{2}/\\d{4}$), com uma
    coluna numérica associada. Sem dayfirst=True, pd.to_datetime assume mês
    primeiro (convenção US): qualquer linha com dia > 12 (19 das 31, dias
    13-31) vira NaT (mês inválido) e é descartada por
    analisar_temporal_series antes do ADF/Ljung-Box. Sobram só 12 linhas
    (dias 1-12, com dia/mês trocados silenciosamente) — abaixo de
    config.ADF_MIN_N (30) — então nem ADF nem Ljung-Box ficam aplicáveis e
    'analise_temporal_series' sai vazia, apesar de haver 31 linhas de dado
    válido. Com dayfirst=True (a correção), as 31 linhas são parseadas
    corretamente, n=31 >= ADF_MIN_N, e a análise temporal roda normalmente."""
    import pandas as pd
    from datetime import date, timedelta

    inicio = date(2024, 1, 1)
    datas = [inicio + timedelta(days=i) for i in range(31)]  # janeiro/2024 completo
    datas_str = [d.strftime("%d/%m/%Y") for d in datas]
    valores = [100.0 + i * 2.5 + (i % 5) * 0.3 for i in range(31)]  # tendência de alta real + leve ruído

    df = pd.DataFrame({
        "dt_pedido": datas_str,
        "valor_pedido": valores,
    })
    profiler = DataProfiler()

    resultado = profiler.processar_dataframe(df, "TB_BR_DATAS")

    col_data = next(c for c in resultado["colunas"] if c["Coluna"] == "dt_pedido")
    assert col_data["Alertas"]["data_como_texto"] is True

    # Sem dayfirst=True, apenas 12/31 linhas sobreviveriam ao parse (dias
    # 1-12), abaixo do ADF_MIN_N=30 — a seção inteira sairia vazia.
    assert len(resultado["analise_temporal_series"]) > 0
    entrada = resultado["analise_temporal_series"][0]
    assert entrada["coluna_temporal_referencia"] == "dt_pedido"
    assert entrada["adf"]["aplicavel"] is True


def test_dataframe_vazio_levanta_value_error():
    import pandas as pd
    import pytest

    profiler = DataProfiler()
    with pytest.raises(ValueError):
        profiler.processar_dataframe(pd.DataFrame(), "TB_VAZIA")

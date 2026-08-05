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


def test_dataframe_vazio_levanta_value_error():
    import pandas as pd
    import pytest

    profiler = DataProfiler()
    with pytest.raises(ValueError):
        profiler.processar_dataframe(pd.DataFrame(), "TB_VAZIA")

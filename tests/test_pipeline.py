"""Orquestração ponta a ponta."""
import pandas as pd
import pytest

from recon import __version__, codegen, config, ingestion
from recon.pipeline import DataProfiler

from .conftest import gerar_cpfs


def test_processar_dataframe_retorna_payload_completo(df_rh_exemplo):
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "TB_TESTE")

    meta = resultado["metadados_execucao"]
    assert meta["tabela"] == "TB_TESTE"
    assert meta["versao_profiler"] == __version__
    assert meta["schema_version"] == config.SCHEMA_VERSION
    assert len(resultado["colunas"]) == len(df_rh_exemplo.columns)
    for chave in ("recomendacoes_etl", "dependencias_funcionais", "colunas_redundantes",
                  "chaves_compostas", "correlacoes", "gap_analysis_kpis",
                  "analise_temporal_series"):
        assert chave in resultado


def test_payload_traz_leitura_textual_com_evidencias(df_rh_exemplo):
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "TB_TESTE")

    assert resultado["insights_textuais"]
    assert any("`" in insight for insight in resultado["insights_textuais"])


def test_vocabulario_customizado_nao_vaza_para_a_execucao_seguinte(tmp_path, df_rh_exemplo):
    """A GUI pode analisar domínios diferentes na mesma sessão."""
    from recon import config

    caminho = tmp_path / "dominio.yaml"
    caminho.write_text("categorias_fortes:\n  Categoria Temporaria: [aurora_local]\n", encoding="utf-8")
    DataProfiler(vocabularios=str(caminho)).processar_dataframe(df_rh_exemplo, "COM_VOCAB")

    assert "Categoria Temporaria" not in config.CATEGORIAS_FORTES


def test_vocabularios_concorrentes_ficam_isolados_por_execucao(tmp_path):
    """Duas análises da GUI não podem trocar dicionários no meio da execução."""
    from concurrent.futures import ThreadPoolExecutor

    primeiro = tmp_path / "primeiro.yaml"
    segundo = tmp_path / "segundo.yaml"
    primeiro.write_text("categorias_fortes:\n  Domínio Aurora: [aurora_interna]\n", encoding="utf-8")
    segundo.write_text("categorias_fortes:\n  Domínio Brisa: [brisa_interna]\n", encoding="utf-8")

    def analisar(caminho, coluna):
        payload = DataProfiler(vocabularios=str(caminho)).processar_dataframe(
            pd.DataFrame({coluna: ["A", "B"] * 40}), "teste"
        )
        return payload["colunas"][0]["Semantica_IA"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(
            lambda args: analisar(*args),
            [(primeiro, "aurora_interna"), (segundo, "brisa_interna")],
        ))

    assert resultados == ["Domínio Aurora", "Domínio Brisa"]


def test_correcao_semantica_por_coluna_prevalece_somente_na_execucao(tmp_path):
    caminho = tmp_path / "correcoes.yaml"
    caminho.write_text("correcoes_colunas:\n  codigo_interno: Categoria Revisada\n", encoding="utf-8")

    corrigido = DataProfiler(vocabularios=str(caminho)).processar_dataframe(
        pd.DataFrame({"codigo_interno": ["A", "B"] * 30}), "teste"
    )
    normal = DataProfiler().processar_dataframe(
        pd.DataFrame({"codigo_interno": ["A", "B"] * 30}), "teste"
    )

    assert corrigido["colunas"][0]["Semantica_IA"] == "Categoria Revisada"
    assert normal["colunas"][0]["Semantica_IA"] != "Categoria Revisada"


def test_versao_do_payload_vem_do_pacote(df_rh_exemplo):
    """Regressão: a versão saía hardcoded como '2.0-Fase1' e divergia do
    pyproject."""
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "T")
    assert resultado["metadados_execucao"]["versao_profiler"] == __version__
    assert "Fase1" not in resultado["metadados_execucao"]["versao_profiler"]


def test_score_de_qualidade_presente_no_payload(df_rh_exemplo):
    score = DataProfiler().processar_dataframe(df_rh_exemplo, "T")["metadados_execucao"]["score_qualidade"]
    assert 0 <= score["score"] <= 100
    assert score["nota"] in {"A", "B", "C", "D", "E"}


def test_processar_dataframe_detecta_lgpd_no_cpf(df_rh_exemplo):
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "TB_TESTE")
    col = next(c for c in resultado["colunas"] if c["Coluna"] == "cpf_colaborador")
    assert col["Dado_Sensivel_LGPD"] == "CPF"


def test_id_funcionario_e_classificado_como_chave(df_rh_exemplo):
    """Regressão de ponta a ponta: `id_funcionario` era classificado como
    'Nome / Identificação Pessoal'."""
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "T")
    col = next(c for c in resultado["colunas"] if c["Coluna"] == "id_funcionario")
    assert col["Semantica_IA"] == config.SEMANTICA_CHAVE_ID


def test_gap_analysis_enxerga_estrutura_organizacional(df_rh_exemplo):
    """Regressão: com `cod_departamento` e `nome_departamento` na tabela, o
    KPI de departamento saía '❌ Bloqueado | 0%' porque as categorias de
    domínio nunca eram avaliadas."""
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "T")

    semanticas = resultado["metadados_execucao"]["resumo_qualidade"]["semanticas_encontradas"]
    assert "Estrutura Organizacional" in semanticas

    kpi = next(g for g in resultado["gap_analysis_kpis"] if g["kpi_id"] == "KPI_HR_001")
    assert kpi["status"] != "❌ Bloqueado"


def test_cpf_nao_e_recomendado_como_chave_primaria():
    """Regressão: o mesmo relatório mandava mascarar o CPF e promovê-lo a PK."""
    df = pd.DataFrame({"cpf": gerar_cpfs(60), "valor": range(60)})
    resultado = DataProfiler().processar_dataframe(df, "T")

    acoes = [r["Acao"] for r in resultado["recomendacoes_etl"] if r["Coluna"] == "cpf"]
    assert any("surrogate key" in a for a in acoes)
    assert not any("Promover 'cpf' como PK" in a for a in acoes)


def test_processar_dataframe_detecta_fd_cod_para_nome_departamento(df_rh_exemplo):
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "TB_TESTE")
    envolvidos = {
        (d["determinante"], d["dependente"]) for d in resultado["dependencias_funcionais"]
    }
    assert any("cod_departamento" in par for par in envolvidos)


def test_duplicatas_e_redundancia_aparecem_no_payload():
    base = pd.DataFrame({"a": range(60), "b": list("xy") * 30})
    df = pd.concat([base, base.head(10)], ignore_index=True)
    df["a_copia"] = df["a"]

    resultado = DataProfiler().processar_dataframe(df, "T")

    assert resultado["metadados_execucao"]["duplicatas"]["qtd_linhas_duplicadas"] == 10
    assert len(resultado["colunas_redundantes"]) == 1


def test_sentinelas_viram_recomendacao_de_alta_prioridade():
    df = pd.DataFrame({
        "uf": ["SP"] * 300 + ["N/A"] * 100 + ["RJ"] * 100,
        "valor": range(500),
    })
    resultado = DataProfiler().processar_dataframe(df, "T")

    recomendacoes_uf = [r for r in resultado["recomendacoes_etl"] if r["Coluna"] == "uf"]
    assert any("NULL" in r["Acao"] and "ALTA" in r["Prioridade"] for r in recomendacoes_uf)


def test_analise_temporal_roda_com_coluna_de_data(df_rh_exemplo):
    resultado = DataProfiler().processar_dataframe(df_rh_exemplo, "TB_TESTE")
    assert all(t["coluna_temporal_referencia"] == "dt_admissao"
               for t in resultado["analise_temporal_series"])


def test_amostragem_e_sinalizada_no_payload():
    df = pd.DataFrame({"a": range(1000), "b": ["x"] * 1000})
    resultado = DataProfiler(limite_amostra=100).processar_dataframe(df, "T")

    meta = resultado["metadados_execucao"]
    assert meta["amostragem_aplicada"] is True
    assert meta["linhas_analisadas"] == 100
    assert meta["linhas_originais"] == 1000


def test_dataframe_vazio_levanta_value_error():
    with pytest.raises(ValueError):
        DataProfiler().processar_dataframe(pd.DataFrame(), "TB_VAZIA")


def test_regras_kpi_customizadas_sao_usadas(df_rh_exemplo):
    regras = [{"id": "X1", "nome": "Custom", "semanticas": ["Valor Financeiro"]}]
    resultado = DataProfiler(regras_kpi=regras).processar_dataframe(df_rh_exemplo, "T")

    assert len(resultado["gap_analysis_kpis"]) == 1
    assert resultado["gap_analysis_kpis"][0]["kpi_id"] == "X1"


def test_processar_arquivo_gera_todos_os_formatos(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho = tmp_path / "dados.csv"
    pd.DataFrame({"id": range(60), "uf": ["SP", "RJ"] * 30}).to_csv(caminho, index=False)

    DataProfiler().processar_arquivo(
        str(caminho), saida_base="saida", formatos=["json", "markdown", "html", "parquet"]
    )

    assert (tmp_path / "saida_dados.json").exists()
    assert (tmp_path / "saida_dados.md").exists()
    assert (tmp_path / "saida_dados.html").exists()
    assert (tmp_path / "saida_dados_columns.parquet").exists()


def test_formato_invalido_levanta_value_error(tmp_path):
    caminho = tmp_path / "dados.csv"
    pd.DataFrame({"a": range(10)}).to_csv(caminho, index=False)

    with pytest.raises(ValueError, match="inválido"):
        DataProfiler().processar_arquivo(str(caminho), formatos=["xml"])


def test_coluna_de_nome_sai_do_relatorio_mascarada():
    """Regressão real (base MDM): 79 mil nomes de funcionários saíam em claro
    na amostra, com `Dado_Sensivel_LGPD: Nenhum`."""
    df = pd.DataFrame({
        "FULL_NAME": [f"MARIA SOUZA {i}" for i in range(60)],
        "VALOR": range(60),
    })
    resultado = DataProfiler().processar_dataframe(df, "cadastro")
    nome = next(c for c in resultado["colunas"] if c["Coluna"] == "FULL_NAME")

    assert nome["Dado_Sensivel_LGPD"] == "Nome de pessoa"
    assert "MARIA" not in nome["Amostra_Valores"]
    assert "M****" in nome["Amostra_Valores"]


def test_fluxos_de_arquivo_propagam_limite_para_a_ingestao(tmp_path, monkeypatch):
    """Lote, modelo e conferência precisam limitar a leitura, não só o profiling."""
    caminhos = []
    for nome in ("a", "b"):
        caminho = tmp_path / f"{nome}.csv"
        pd.DataFrame({"id": range(12), "valor": range(12)}).to_csv(caminho, index=False)
        caminhos.append(str(caminho))

    original = ingestion.carregar_arquivo
    chamadas: list[int | None] = []

    def registrar(*args, **kwargs):
        chamadas.append(kwargs.get("limite_linhas"))
        return original(*args, **kwargs)

    monkeypatch.setattr(ingestion, "carregar_arquivo", registrar)
    profiler = DataProfiler(limite_amostra=5)
    profiler.processar_lote(caminhos[:1], formatos=[])
    profiler.modelar_conjunto(caminhos, formatos=[], perfis_individuais=False)
    profiler.conferir_versoes(*caminhos, formatos=[])

    assert chamadas == [5, 5, 5, 5, 5]


def test_script_limpeza_nao_executa_codigo_vindo_do_cabecalho(tmp_path):
    coluna_maliciosa = 'campo\nraise AssertionError("injetado") #'
    origem = tmp_path / "entrada.csv"
    pd.DataFrame({"id": [1, 2], coluna_maliciosa: [None, None]}).to_csv(origem, index=False)
    payload = {
        "metadados_execucao": {
            "tabela": 'tabela\nraise AssertionError("injetado") #',
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
            "versao_profiler": "3.0.0",
            "layout": {},
            "duplicatas": {},
        },
        "colunas": [{
            "Coluna": coluna_maliciosa,
            "Caracteristica": "⚠️ Coluna 100% Vazia",
            "Alertas": {},
            "Qualidade": {},
            "Otimizacao": {},
            "Dado_Sensivel_LGPD": "Nenhum",
        }],
        "colunas_redundantes": [],
        "regras_negocio": [],
    }

    script = codegen.gerar_script_limpeza(payload, str(origem))
    escopo: dict = {}
    exec(compile(script, "limpeza.py", "exec"), escopo)  # noqa: S102

    assert coluna_maliciosa not in escopo["df"].columns


def test_amostragem_por_memoria_fica_explicita_no_payload():
    df = pd.DataFrame({"id": range(20)})
    df.attrs["motivo_amostragem"] = "Leitura integral acima do orçamento seguro."
    df.attrs["linhas_originais_desconhecidas"] = True

    meta = DataProfiler(limite_amostra=5).processar_dataframe(df, "amostra")["metadados_execucao"]

    assert meta["amostragem_aplicada"] is True
    assert meta["linhas_originais_desconhecidas"] is True
    assert meta["motivo_amostragem"] == "Leitura integral acima do orçamento seguro."


def test_script_de_limpeza_pseudonimiza_pii_com_hmac_e_chave_externa(tmp_path, monkeypatch):
    origem = tmp_path / "pessoas.csv"
    cpfs = gerar_cpfs(6)
    pd.DataFrame({"cpf": cpfs}).to_csv(origem, index=False)
    payload = DataProfiler().processar_dataframe(pd.DataFrame({"cpf": cpfs}), "pessoas")

    script = codegen.gerar_script_limpeza(payload, str(origem))

    assert "RECON_PSEUDONYMIZATION_KEY" in script
    assert "hmac.new" in script
    assert "hexdigest()[:16]" not in script
    monkeypatch.setenv("RECON_PSEUDONYMIZATION_KEY", "segredo-de-teste")
    escopo: dict = {}
    exec(compile(script, "limpeza.py", "exec"), escopo)  # noqa: S102
    assert escopo["df"]["cpf"].iloc[0] != cpfs[0]
    assert len(escopo["df"]["cpf"].iloc[0]) == 64

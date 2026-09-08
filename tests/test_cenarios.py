import numpy as np
import pandas as pd
import pytest

from recon import datamodel
from recon.pipeline import DataProfiler

from .conftest import gerar_cpfs

N_LINHAS = 500
FRACAO_SUJA = 0.6


@pytest.fixture(scope="module")
def df_60pct_poluido() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n_sujo = int(N_LINHAS * FRACAO_SUJA)
    limpo = N_LINHAS - n_sujo

    uf = ["SP"] * (limpo // 2) + ["RJ"] * (limpo - limpo // 2)
    uf += ["sp"] * 80 + [" SP"] * 60 + ["N/A"] * 90 + ["-"] * 70

    datas = [f"{2023}-0{(i % 9) + 1}-15" for i in range(limpo)]
    datas += ["1900-01-01"] * 90 + ["2099-12-31"] * 40 + ["15/03/2023"] * 170

    valores = [float(v) for v in np.round(rng.lognormal(8, 0.4, limpo), 2)]
    valores += [-1.0] * 120 + [999999.0] * 60
    valores += [float(v) for v in np.round(rng.lognormal(8, 0.4, 120), 2)]
    valores = valores[:N_LINHAS]

    cpf = gerar_cpfs(1)[0]
    obs = ["sem observacao"] * (limpo)
    obs += ["ObservaÃ§Ã£o corrompida"] * 120 + [f"cliente CPF {cpf}"] * 80 + [""] * 100

    documentos = [f"{i:03d}.456.789-00" for i in range(N_LINHAS)]

    return pd.DataFrame(
        {
            "id_registro": range(1, N_LINHAS + 1),
            "uf": (uf + ["SP"] * N_LINHAS)[:N_LINHAS],
            "dt_evento": (datas + ["2023-01-01"] * N_LINHAS)[:N_LINHAS],
            "vl_total": valores[:N_LINHAS],
            "obs": (obs + ["ok"] * N_LINHAS)[:N_LINHAS],
            "cpf_cliente": documentos,
            "campo_vazio": [None] * N_LINHAS,
            "constante": ["X"] * N_LINHAS,
        }
    )


def test_perfil_de_base_60pct_poluida_acha_todos_os_defeitos(df_60pct_poluido):
    payload = DataProfiler().processar_dataframe(df_60pct_poluido, "sujo")

    por_coluna = {c["Coluna"]: c for c in payload["colunas"]}

    uf = por_coluna["uf"]["Qualidade"]
    assert uf["sentinelas"]["tem_sentinela"] is True
    assert uf["inconsistencia_normalizacao"]["tem_inconsistencia"] is True
    assert uf["nulos_efetivos_pct"] > 0

    assert por_coluna["dt_evento"]["Alertas"]["data_como_texto"] is True

    assert por_coluna["vl_total"]["Qualidade"]["sentinelas"]["tem_sentinela"] is True

    obs = por_coluna["obs"]["Qualidade"]
    assert obs["mojibake"]["tem_mojibake"] is True
    assert obs["pii_texto_livre"]["tem_pii"] is True

    documento = por_coluna["cpf_cliente"]["Qualidade"]["documento_invalido"]
    assert documento["tem_documento_invalido"] is True
    assert documento["tipo"] == "CPF"

    assert "Vazia" in por_coluna["campo_vazio"]["Caracteristica"]
    assert "Constante" in por_coluna["constante"]["Caracteristica"]


def test_score_de_base_muito_suja_e_baixo(df_60pct_poluido):
    score = DataProfiler().processar_dataframe(df_60pct_poluido, "sujo")["metadados_execucao"][
        "score_qualidade"
    ]
    assert score["score"] < 85
    assert score["penalidades"]


def test_base_suja_gera_recomendacoes_de_alta_prioridade(df_60pct_poluido):
    payload = DataProfiler().processar_dataframe(df_60pct_poluido, "sujo")
    altas = [r for r in payload["recomendacoes_etl"] if "ALTA" in r["Prioridade"]]
    colunas_com_alerta = {r["Coluna"] for r in altas}

    assert len(altas) >= 5
    assert {"uf", "dt_evento", "obs", "campo_vazio"} <= colunas_com_alerta


def test_script_de_limpeza_da_base_suja_e_executavel(df_60pct_poluido, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho = tmp_path / "sujo.csv"
    df_60pct_poluido.to_csv(caminho, index=False)

    DataProfiler().processar_arquivo(
        str(caminho), saida_base="s", formatos=["json"], gerar_limpeza=True
    )

    script = (tmp_path / "s_sujo_limpeza.py").read_text(encoding="utf-8")
    escopo: dict = {}
    exec(compile(script, "limpeza.py", "exec"), escopo)  # noqa: S102

    limpo = escopo["df"]
    assert isinstance(limpo, pd.DataFrame)
    assert len(limpo) > 0
    assert "campo_vazio" not in limpo.columns
    assert pd.api.types.is_datetime64_any_dtype(limpo["dt_evento"])
    assert not limpo["uf"].isin(["N/A", "-"]).any()


@pytest.fixture(scope="module")
def empregados() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 300
    return pd.DataFrame(
        {
            "matricula": range(50000, 50000 + n),
            "nome_colaborador": [f"Colaborador {i}" for i in range(n)],
            "diretoria": rng.choice(["Operacoes", "TI", "RH"], n),
            "cargo": rng.choice(["Analista", "Gerente"], n),
            "salario": np.round(rng.lognormal(8.5, 0.3, n), 2),
        }
    )


def _tabela(nome, df):
    payload = DataProfiler().processar_dataframe(df, nome)
    return datamodel.TabelaCarregada(nome=nome, df=df, payload=payload, origem=f"{nome}.csv")


def test_treinamentos_sem_chave_compativel_nao_inventa_relacao(empregados):
    rng = np.random.default_rng(11)
    treinamentos = pd.DataFrame(
        {
            "id_inscricao": range(1, 801),
            "cpf_participante": [f"{9000000 + i}" for i in range(800)],
            "nome_treinamento": rng.choice(["Excel", "Power BI", "LGPD"], 800),
            "carga_horaria": rng.integers(2, 40, 800),
        }
    )
    tabelas = [_tabela("empregados", empregados), _tabela("treinamentos", treinamentos)]

    modelo = datamodel.analisar_conjunto(tabelas, "sem_chave")

    assert modelo["relacionamentos"] == []
    papeis = {t["nome"]: t["papel"] for t in modelo["tabelas"]}
    assert all(p in ("Dimensão isolada", "Indefinida") for p in papeis.values())

    mensagens = " ".join(a["mensagem"] for a in modelo["avisos"])
    assert "não se liga" in mensagens
    assert "empregados" in mensagens and "treinamentos" in mensagens


def test_relatorio_sem_chave_explica_a_ausencia(empregados, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    treinamentos = pd.DataFrame(
        {
            "id_inscricao": range(1, 401),
            "cpf_participante": [f"{9000000 + i}" for i in range(400)],
            "nome_treinamento": ["Excel"] * 400,
        }
    )
    empregados.to_csv(tmp_path / "emp.csv", index=False)
    treinamentos.to_csv(tmp_path / "tre.csv", index=False)

    DataProfiler().modelar_conjunto(
        [str(tmp_path / "emp.csv"), str(tmp_path / "tre.csv")],
        saida_base="m",
        formatos=["markdown"],
        perfis_individuais=False,
    )

    conteudo = (tmp_path / "m_modelo.md").read_text(encoding="utf-8")
    assert "Nenhuma chave estrangeira detectada" in conteudo
    assert "Nenhuma análise cruzada sugerida" in conteudo


def test_chave_compativel_sem_dado_util_nao_promete_analise(empregados):
    rng = np.random.default_rng(13)
    log_acesso = pd.DataFrame(
        {
            "id_log": range(1, 901),
            "matricula": rng.choice(empregados["matricula"], 900),
            "hash_sessao": [f"{i:032x}" for i in range(900)],
        }
    )
    tabelas = [_tabela("empregados", empregados), _tabela("log_acesso", log_acesso)]

    modelo = datamodel.analisar_conjunto(tabelas, "sem_medida")

    pares = {
        (r["tabela_origem"], r["coluna_origem"], r["tabela_destino"])
        for r in modelo["relacionamentos"]
    }
    assert ("log_acesso", "matricula", "empregados") in pares

    log = next(t for t in modelo["tabelas"] if t["nome"] == "log_acesso")
    assert log["medidas"] == []

    for analise in modelo["analises_sugeridas"]:
        assert "hash_sessao" not in analise["pandas"]
        assert "id_log" not in analise["titulo"]


def test_tabela_so_com_chave_e_ruido_nao_vira_fato(empregados):
    rng = np.random.default_rng(17)
    ponte = pd.DataFrame(
        {
            "matricula": rng.choice(empregados["matricula"], 600),
            "carimbo": [f"{i:032x}" for i in range(600)],
        }
    )
    tabelas = [_tabela("empregados", empregados), _tabela("ponte", ponte)]

    modelo = datamodel.analisar_conjunto(tabelas, "ponte")

    papel = next(t["papel"] for t in modelo["tabelas"] if t["nome"] == "ponte")
    assert not papel.startswith("Fato") or papel == "Fato sem medida (eventos)"

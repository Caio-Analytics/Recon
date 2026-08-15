"""Regras de negócio inferidas."""
import numpy as np
import pandas as pd

from datascope import rules
from datascope.pipeline import DataProfiler


def _meta(df: pd.DataFrame, nome_tabela: str = "T"):
    payload = DataProfiler().processar_dataframe(df, nome_tabela)
    return payload["colunas"]


def _base_rh(n=400, violacoes=0, como_texto=False):
    rng = np.random.default_rng(5)
    admissao = pd.to_datetime("2018-01-01") + pd.to_timedelta(
        rng.integers(0, 2000, n), unit="D"
    )
    status = rng.choice(["Ativo", "Inativo"], n, p=[0.7, 0.3])
    desligamento = pd.Series([pd.NaT] * n)
    inativos = status == "Inativo"
    desligamento[inativos] = admissao[inativos] + pd.to_timedelta(
        rng.integers(30, 800, inativos.sum()), unit="D"
    )
    df = pd.DataFrame({
        "matricula": range(n),
        "status": status,
        "dt_admissao": admissao,
        "dt_desligamento": desligamento,
        "vl_bruto": np.round(rng.lognormal(8.4, 0.3, n), 2),
    })
    df["vl_desconto"] = np.round(df["vl_bruto"] * 0.11, 2)
    df["vl_liquido"] = np.round(df["vl_bruto"] - df["vl_desconto"], 2)

    if violacoes:
        alvo = df[inativos].index[:violacoes]
        df.loc[alvo, "dt_desligamento"] = df.loc[alvo, "dt_admissao"] - pd.Timedelta(days=100)
    if como_texto:
        for coluna in ("dt_admissao", "dt_desligamento"):
            df[coluna] = df[coluna].dt.strftime("%Y-%m-%d")
    return df


# ── Ordem entre datas ───────────────────────────────────────────────────────

def test_ordem_entre_datas_sem_violacao():
    df = _base_rh()
    regras = rules.detectar_ordem_entre_datas(df, _meta(df))
    ordem = next(r for r in regras if r["tipo"] == "Ordem entre datas")
    assert ordem["regra"] == "`dt_admissao` <= `dt_desligamento`"
    assert ordem["qtd_violacoes"] == 0


def test_ordem_entre_datas_lista_as_violacoes():
    df = _base_rh(violacoes=5)
    ordem = next(
        r for r in rules.detectar_ordem_entre_datas(df, _meta(df))
        if r["tipo"] == "Ordem entre datas"
    )
    assert ordem["qtd_violacoes"] == 5
    assert len(ordem["exemplos_violacao"]) == 3


def test_ordem_entre_datas_funciona_com_data_como_texto():
    """Regressão: em CSV a data chega como texto, e exigir `Data / Hora`
    deixava a regra cega justamente no formato de entrada mais comum."""
    df = _base_rh(violacoes=4, como_texto=True)
    regras = rules.detectar_ordem_entre_datas(df, _meta(df))
    assert any(r["qtd_violacoes"] == 4 for r in regras)


def test_datas_sem_relacao_de_ordem_nao_viram_regra():
    rng = np.random.default_rng(2)
    n = 300
    df = pd.DataFrame({
        "dt_a": pd.to_datetime("2020-01-01") + pd.to_timedelta(rng.integers(0, 900, n), unit="D"),
        "dt_b": pd.to_datetime("2020-01-01") + pd.to_timedelta(rng.integers(0, 900, n), unit="D"),
    })
    assert rules.detectar_ordem_entre_datas(df, _meta(df)) == []


# ── Nulidade condicional ────────────────────────────────────────────────────

def test_nulidade_condicional_detectada():
    """Coluna 70% nula pode não ser dado faltante — pode ser a regra do
    cadastro."""
    df = _base_rh()
    regras = rules.detectar_nulidade_condicional(df, _meta(df))
    regra = next(r for r in regras if "dt_desligamento" in r["regra"])
    assert "Inativo" in regra["regra"]
    assert "regra de negócio, não dado faltante" in regra["descricao"]


def test_nulo_espalhado_ao_acaso_nao_vira_regra():
    rng = np.random.default_rng(4)
    n = 300
    df = pd.DataFrame({
        "grupo": rng.choice(["A", "B", "C"], n),
        "valor": [None if rng.random() < 0.4 else float(i) for i in range(n)],
    })
    assert rules.detectar_nulidade_condicional(df, _meta(df)) == []


# ── Derivação aritmética ────────────────────────────────────────────────────

def test_derivacao_aritmetica_detectada():
    df = _base_rh()
    regras = rules.detectar_derivacao_aritmetica(df, _meta(df))
    assert regras
    envolvidas = set()
    for regra in regras:
        envolvidas |= {p.strip("`") for p in regra["regra"].replace("=", " ").split()
                       if p.startswith("`")}
    assert {"vl_bruto", "vl_desconto", "vl_liquido"} <= envolvidas


def test_derivacao_reporta_o_trio_uma_vez_so():
    """`a = b + c`, `b = a - c` e `c = a - b` são a mesma relação dita de três
    formas — reportar as três é ruído."""
    df = _base_rh()
    regras = rules.detectar_derivacao_aritmetica(df, _meta(df))
    trios = [
        frozenset(p.strip("`") for p in r["regra"].replace("=", " ").split()
                  if p.startswith("`"))
        for r in regras
    ]
    assert len(trios) == len(set(trios))


def test_numericas_independentes_nao_geram_derivacao():
    rng = np.random.default_rng(6)
    n = 300
    df = pd.DataFrame({
        "a": rng.normal(100, 10, n),
        "b": rng.normal(50, 5, n),
        "c": rng.normal(20, 2, n),
    })
    assert rules.detectar_derivacao_aritmetica(df, _meta(df)) == []


# ── Orquestração ────────────────────────────────────────────────────────────

def test_regras_com_violacao_vem_antes_das_perfeitas():
    # 3 de ~108 inativos = 97% de conformidade, acima do limiar de 95%. Com 6
    # a taxa cairia para 94% e a regra deixaria de ser reportada — que é o
    # comportamento correto, mas não é o que este teste verifica.
    df = _base_rh(violacoes=3)
    regras = rules.inferir_regras(df, _meta(df))
    assert regras[0]["qtd_violacoes"] > 0
    assert regras[-1]["qtd_violacoes"] == 0


def test_tabela_pequena_demais_nao_gera_regra():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [2, 4, 6]})
    assert rules.inferir_regras(df, _meta(df)) == []


def test_regras_chegam_ao_payload_e_ao_relatorio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho = tmp_path / "rh.csv"
    _base_rh(violacoes=3).to_csv(caminho, index=False)

    payloads = DataProfiler().processar_arquivo(
        str(caminho), saida_base="s", formatos=["markdown"]
    )

    assert payloads[0]["regras_negocio"]
    conteudo = (tmp_path / "s_rh.md").read_text(encoding="utf-8")
    assert "Regras de negócio inferidas" in conteudo


def test_regra_abaixo_do_limiar_nao_e_reportada():
    """Uma "regra" que falha em mais de 5% dos casos não é regra, é
    coincidência — e reportá-la como regra seria pior que silenciar."""
    df = _base_rh(violacoes=20)
    ordens = [r for r in rules.inferir_regras(df, _meta(df))
              if r["tipo"] == "Ordem entre datas"]
    assert ordens == []

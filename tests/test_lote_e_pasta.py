"""Lote consolidado, gráficos SVG e o comando de pasta."""
import numpy as np
import pandas as pd
from typer.testing import CliRunner

from recon.cli import app
from recon.pipeline import DataProfiler
from recon.reporting import _graficos

runner = CliRunner()


def _tres_arquivos(pasta):
    rng = np.random.default_rng(3)
    n = 200
    empregados = pd.DataFrame({
        "matricula": range(50000, 50000 + n),
        "nome": [f"C{i}" for i in range(n)],
        "diretoria": rng.choice(["Ops", "TI", "RH"], n),
        "salario": np.round(rng.lognormal(8.5, 0.3, n), 2),
    })
    cursos = pd.DataFrame({
        "cod_curso": [f"C{i:03d}" for i in range(20)],
        "nome_curso": [f"Curso {i}" for i in range(20)],
        "carga_horaria": rng.integers(2, 40, 20),
    })
    treinamentos = pd.DataFrame({
        "id_realizacao": range(1, 601),
        "matricula": rng.choice(empregados["matricula"], 600),
        "cod_curso": rng.choice(cursos["cod_curso"], 600),
        "nota": np.round(rng.uniform(5, 10, 600), 1),
    })
    for nome, df in (("empregados", empregados), ("cursos", cursos),
                     ("treinamentos", treinamentos)):
        df.to_csv(pasta / f"{nome}.csv", index=False)
    return [str(pasta / f"{n}.csv") for n in ("empregados", "cursos", "treinamentos")]


# ── Gráficos ────────────────────────────────────────────────────────────────

def test_histograma_gera_svg_sem_dependencia_externa():
    dados = {"faixas": [{"de": i, "ate": i + 1, "qtd": i * 3} for i in range(10)],
             "min": 0, "max": 10}
    svg = _graficos.histograma(dados)

    assert svg.startswith("<svg")
    assert "<rect" in svg
    assert "http://" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "<script" not in svg


def test_grafico_vazio_quando_nao_ha_dado():
    assert _graficos.histograma(None) == ""
    assert _graficos.histograma({"faixas": []}) == ""
    assert _graficos.linha_temporal([{"mes": "2023-01", "qtd": 1}]) == ""
    assert _graficos.barras_categoricas([]) == ""


def test_barra_de_completude_separa_nulo_de_sentinela():
    """Uma coluna com 0% de nulos e 30% de 'N/A' parece completa em qualquer
    contagem — a barra é o que torna isso visível."""
    svg = _graficos.barra_completude(pct_nulos=10.0, pct_sentinelas=0.3)
    assert svg.count("<rect") == 3
    assert "nulo disfarçado" in svg


def test_coluna_sensivel_nao_ganha_grafico():
    """A distribuição de uma coluna de CPF não tem significado analítico e
    ainda revela a faixa dos documentos."""
    coluna = {
        "Dado_Sensivel_LGPD": "CPF",
        "Stats_Extra": {"histograma": {"faixas": [{"de": 0, "ate": 1, "qtd": 5}],
                                       "min": 0, "max": 1}},
    }
    assert _graficos.graficos_da_coluna(coluna) == ""


def test_html_de_coluna_numerica_traz_histograma(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rng = np.random.default_rng(1)
    caminho = tmp_path / "n.csv"
    pd.DataFrame({"vl_total": np.round(rng.lognormal(8, 0.4, 500), 2)}).to_csv(
        caminho, index=False
    )

    DataProfiler().processar_arquivo(str(caminho), saida_base="s", formatos=["html"])

    html = (tmp_path / "s_n.html").read_text(encoding="utf-8")
    assert "Distribuição dos valores" in html
    assert "<svg" in html


# ── Lote consolidado ────────────────────────────────────────────────────────

def test_lote_gera_um_html_com_todos_os_arquivos(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    arquivos = _tres_arquivos(tmp_path)

    payloads, falhas = DataProfiler().processar_lote(
        arquivos, saida_base="l", formatos=["html"]
    )

    assert len(payloads) == 3
    assert falhas == []
    html = (tmp_path / "l_consolidado.html").read_text(encoding="utf-8")
    assert html.count("<details") == 3
    assert "Leitura executiva" in html
    for nome in ("empregados", "cursos", "treinamentos"):
        assert nome in html


def test_lote_ordena_do_pior_para_o_melhor(tmp_path, monkeypatch):
    """A pergunta do lote é por onde começar — o pior arquivo tem que estar no
    topo e já aberto."""
    monkeypatch.chdir(tmp_path)
    limpa = pd.DataFrame({"id": range(200), "uf": ["SP", "RJ"] * 100})
    suja = pd.DataFrame({
        "id": range(200),
        "morta": [None] * 200,
        "obs": ["ObservaÃ§Ã£o"] * 100 + ["-"] * 100,
    })
    limpa.to_csv(tmp_path / "limpa.csv", index=False)
    suja.to_csv(tmp_path / "suja.csv", index=False)

    DataProfiler().processar_lote(
        [str(tmp_path / "limpa.csv"), str(tmp_path / "suja.csv")],
        saida_base="l", formatos=["html"],
    )

    html = (tmp_path / "l_consolidado.html").read_text(encoding="utf-8")
    assert html.index("suja") < html.index("limpa")
    assert '<details class="tabela" open>' in html


def test_lote_continua_apos_falha_e_reporta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pd.DataFrame({"a": range(50)}).to_csv(tmp_path / "bom.csv", index=False)
    (tmp_path / "ruim.csv").write_text("", encoding="utf-8")

    payloads, falhas = DataProfiler().processar_lote(
        [str(tmp_path / "ruim.csv"), str(tmp_path / "bom.csv")],
        saida_base="l", formatos=["html"],
    )

    assert len(payloads) == 1
    assert len(falhas) == 1
    assert "ruim.csv" in falhas[0][0]


# ── Comando de pasta ────────────────────────────────────────────────────────

def test_pasta_com_um_arquivo_vira_individual(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = tmp_path / "in"
    entrada.mkdir()
    pd.DataFrame({"id": range(60), "uf": ["SP", "RJ"] * 30}).to_csv(
        entrada / "unico.csv", index=False
    )

    resultado = runner.invoke(app, ["pasta", str(entrada), "--saida", str(tmp_path / "out")])

    assert resultado.exit_code == 0
    assert "individual" in resultado.output
    assert (tmp_path / "out" / "in_unico.html").exists()


def test_pasta_encontra_csv_gzip_suportado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = tmp_path / "in"
    entrada.mkdir()
    pd.DataFrame({"id": range(60), "uf": ["SP", "RJ"] * 30}).to_csv(
        entrada / "compactado.csv.gz", index=False, compression="gzip"
    )

    resultado = runner.invoke(app, ["pasta", str(entrada), "--saida", str(tmp_path / "out")])

    assert resultado.exit_code == 0
    assert (tmp_path / "out" / "in_compactado.html").exists()


def test_pasta_com_varios_arquivos_vira_lote(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = tmp_path / "in"
    entrada.mkdir()
    _tres_arquivos(entrada)

    resultado = runner.invoke(
        app, ["pasta", str(entrada), "--saida", str(tmp_path / "out"), "--sim"]
    )

    assert resultado.exit_code == 0
    assert (tmp_path / "out" / "in_consolidado.html").exists()


def test_pasta_modo_modelo_cruza_as_tabelas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = tmp_path / "in"
    entrada.mkdir()
    _tres_arquivos(entrada)

    resultado = runner.invoke(
        app, ["pasta", str(entrada), "--saida", str(tmp_path / "out"), "--modo", "modelo"]
    )

    assert resultado.exit_code == 0
    assert (tmp_path / "out" / "in_modelo.html").exists()


def test_pasta_pergunta_quando_ha_varios_e_nao_ha_sim(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = tmp_path / "in"
    entrada.mkdir()
    _tres_arquivos(entrada)

    resultado = runner.invoke(
        app, ["pasta", str(entrada), "--saida", str(tmp_path / "out")], input="2\n"
    )

    assert resultado.exit_code == 0
    assert "Como quer analisar?" in resultado.output
    assert (tmp_path / "out" / "in_modelo.html").exists()


def test_pasta_inexistente_falha_com_mensagem(tmp_path):
    resultado = runner.invoke(app, ["pasta", str(tmp_path / "nao_existe")])
    assert resultado.exit_code != 0
    assert "não é uma pasta" in resultado.output


def test_pasta_sem_arquivo_suportado_falha(tmp_path):
    entrada = tmp_path / "in"
    entrada.mkdir()
    (entrada / "leia.txt").write_text("nada", encoding="utf-8")

    resultado = runner.invoke(app, ["pasta", str(entrada)])

    assert resultado.exit_code != 0
    assert "nenhum arquivo suportado" in resultado.output


def test_modo_invalido_e_rejeitado(tmp_path):
    entrada = tmp_path / "in"
    entrada.mkdir()
    pd.DataFrame({"a": range(30)}).to_csv(entrada / "a.csv", index=False)

    resultado = runner.invoke(app, ["pasta", str(entrada), "--modo", "turbo"])
    assert resultado.exit_code != 0

"""Modo interativo — o caminho de quem não decora comando."""
import pandas as pd
from typer.testing import CliRunner

from recon import interativo
from recon.cli import app

runner = CliRunner()


def _pasta_com_arquivos(tmp_path, quantos=3):
    entrada = tmp_path / "in"
    entrada.mkdir()
    for i in range(quantos):
        pd.DataFrame({"id": range(80), "uf": ["SP", "RJ"] * 40}).to_csv(
            entrada / f"base{i}.csv", index=False
        )
    return entrada


def test_recon_sem_argumento_abre_o_menu(tmp_path, monkeypatch):
    """Digitar `recon` e nada mais precisa dar em alguma coisa útil — é o
    caminho de quem usa a ferramenta uma vez por mês."""
    monkeypatch.chdir(tmp_path)
    entrada = _pasta_com_arquivos(tmp_path)
    saida = tmp_path / "out"

    resultado = runner.invoke(app, [], input=f"{entrada}\n1\n{saida}\n")

    assert resultado.exit_code == 0
    assert "Recon" in resultado.output
    assert "O que você quer fazer?" in resultado.output
    assert (saida / "in_consolidado.html").exists()


def test_menu_com_um_arquivo_nao_pergunta_o_modo(tmp_path, monkeypatch):
    """Com um arquivo só não há o que comparar nem cruzar — perguntar seria
    fazer o usuário decidir algo que não tem alternativa."""
    monkeypatch.chdir(tmp_path)
    entrada = _pasta_com_arquivos(tmp_path, quantos=1)
    saida = tmp_path / "out"

    resultado = runner.invoke(app, [], input=f"{entrada}\n{saida}\nn\n")

    assert resultado.exit_code == 0
    assert "O que você quer fazer?" not in resultado.output
    assert list(saida.glob("*.html"))


def test_menu_aceita_arquivo_unico_em_vez_de_pasta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = _pasta_com_arquivos(tmp_path, quantos=1)
    arquivo = entrada / "base0.csv"
    saida = tmp_path / "out"

    resultado = runner.invoke(app, [], input=f"{arquivo}\n{saida}\nn\n")

    assert resultado.exit_code == 0
    assert list(saida.glob("*.html"))


def test_menu_insiste_quando_o_caminho_nao_existe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = _pasta_com_arquivos(tmp_path)
    saida = tmp_path / "out"

    resultado = runner.invoke(
        app, [], input=f"/caminho/que/nao/existe\n{entrada}\n1\n{saida}\n"
    )

    assert resultado.exit_code == 0
    assert "não existe" in resultado.output


def test_menu_avisa_quando_a_pasta_nao_tem_arquivo_suportado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    (vazia / "leia.txt").write_text("nada", encoding="utf-8")
    entrada = _pasta_com_arquivos(tmp_path)
    saida = tmp_path / "out"

    resultado = runner.invoke(app, [], input=f"{vazia}\n{entrada}\n1\n{saida}\n")

    assert "Não achei CSV nem Excel" in resultado.output
    assert resultado.exit_code == 0


def test_menu_modo_modelo_cruza_as_tabelas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entrada = tmp_path / "in"
    entrada.mkdir()
    dim = pd.DataFrame({"cod_dep": [f"D{i:02d}" for i in range(20)],
                        "nome_dep": [f"Depto {i}" for i in range(20)]})
    fato = pd.DataFrame({"id_reg": range(200),
                         "cod_dep": [f"D{i % 20:02d}" for i in range(200)],
                         "vl_gasto": range(200)})
    dim.to_csv(entrada / "dim.csv", index=False)
    fato.to_csv(entrada / "fato.csv", index=False)
    saida = tmp_path / "out"

    resultado = runner.invoke(app, [], input=f"{entrada}\n2\n{saida}\n")

    assert resultado.exit_code == 0
    assert (saida / "in_modelo.html").exists()


def test_comandos_diretos_continuam_funcionando(tmp_path, monkeypatch):
    """O menu não pode ter engolido a CLI: quem sabe o comando digita o comando."""
    monkeypatch.chdir(tmp_path)
    entrada = _pasta_com_arquivos(tmp_path, quantos=1)

    resultado = runner.invoke(
        app, ["perfilar", str(entrada / "base0.csv"), "--saida-base", "d"]
    )

    assert resultado.exit_code == 0
    assert (tmp_path / "d_base0.html").exists()


def test_escolha_invalida_cai_no_padrao(tmp_path):
    assert interativo._perguntar_acao(1) == "individual"

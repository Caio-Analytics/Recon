import random

import pandas as pd
from typer.testing import CliRunner

from data_profiler.cli import app

runner = CliRunner()


def test_perfilar_gera_json_e_markdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho_csv = tmp_path / "dados.csv"
    pd.DataFrame({"id": range(30), "valor": range(30)}).to_csv(caminho_csv, index=False)

    resultado = runner.invoke(app, ["perfilar", str(caminho_csv), "--saida-base", "saida"])

    assert resultado.exit_code == 0
    assert (tmp_path / "saida_dados.json").exists()
    assert (tmp_path / "saida_dados.md").exists()


def test_perfilar_arquivo_inexistente_retorna_codigo_erro(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    resultado = runner.invoke(app, ["perfilar", "nao_existe.csv"])

    assert resultado.exit_code != 0


def test_lote_processa_varios_arquivos_mesmo_com_um_falhando(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pd.DataFrame({"a": range(10)}).to_csv(tmp_path / "bom.csv", index=False)
    (tmp_path / "vazio.csv").write_text("", encoding="utf-8")

    resultado = runner.invoke(app, ["lote", str(tmp_path / "bom.csv"), str(tmp_path / "vazio.csv"), "--saida-base", "lote_saida"])

    assert (tmp_path / "lote_saida_bom.json").exists()


def test_lote_continua_apos_falha_mesmo_com_arquivo_ruim_primeiro(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "vazio.csv").write_text("", encoding="utf-8")
    pd.DataFrame({"a": range(10)}).to_csv(tmp_path / "bom.csv", index=False)

    resultado = runner.invoke(app, ["lote", str(tmp_path / "vazio.csv"), str(tmp_path / "bom.csv"), "--saida-base", "lote_saida2"])

    assert (tmp_path / "lote_saida2_bom.json").exists()
    assert not (tmp_path / "lote_saida2_vazio.json").exists()


def test_lote_continua_apos_falha_de_encoding_mesmo_com_arquivo_ruim_primeiro(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho_ruim = tmp_path / "binario.csv"
    rng = random.Random(1)
    caminho_ruim.write_bytes(bytes(rng.randint(0, 255) for _ in range(2000)))
    pd.DataFrame({"a": range(10)}).to_csv(tmp_path / "bom.csv", index=False)

    resultado = runner.invoke(
        app, ["lote", str(caminho_ruim), str(tmp_path / "bom.csv"), "--saida-base", "lote_saida3"]
    )

    assert (tmp_path / "lote_saida3_bom.json").exists()
    assert not (tmp_path / "lote_saida3_binario.json").exists()

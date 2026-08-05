import pandas as pd
import pytest

from data_profiler.ingestion import carregar_arquivo, carregar_todas_abas_excel, FileFormatError


def test_carregar_csv_separador_ponto_virgula(tmp_path):
    caminho = tmp_path / "dados.csv"
    caminho.write_text("id;nome\n1;Ana\n2;Bruno\n", encoding="utf-8")

    df, nome = carregar_arquivo(str(caminho))

    assert list(df.columns) == ["id", "nome"]
    assert len(df) == 2
    assert nome == "dados"


def test_carregar_arquivo_inexistente_levanta_file_not_found():
    with pytest.raises(FileNotFoundError):
        carregar_arquivo("/caminho/que/nao/existe.csv")


def test_extensao_nao_suportada_levanta_file_format_error(tmp_path):
    caminho = tmp_path / "dados.txt"
    caminho.write_text("qualquer coisa", encoding="utf-8")

    with pytest.raises(FileFormatError):
        carregar_arquivo(str(caminho))


def test_csv_vazio_levanta_file_format_error_nao_csv_error(tmp_path):
    """Um CSV de 0 bytes faz o csv.Sniffer falhar com _csv.Error, que não é
    subclasse de ValueError. carregar_arquivo deve converter isso em
    FileFormatError em vez de deixar a exceção interna do pandas/csv vazar."""
    caminho = tmp_path / "vazio.csv"
    caminho.write_bytes(b"")

    with pytest.raises(FileFormatError):
        carregar_arquivo(str(caminho))


def test_carregar_xlsx(tmp_path):
    caminho = tmp_path / "planilha.xlsx"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(caminho, index=False)

    df, nome = carregar_arquivo(str(caminho))

    assert list(df.columns) == ["a", "b"]
    assert nome == "planilha__Sheet1"


def test_carregar_todas_abas_excel_arquivo_inexistente_levanta_file_not_found():
    with pytest.raises(FileNotFoundError):
        carregar_todas_abas_excel("/caminho/que/nao/existe.xlsx")


def test_carregar_todas_abas_excel_corrompido_levanta_file_format_error(tmp_path):
    """Um .xlsx corrompido (aqui, texto puro com a extensão errada) faz
    pd.ExcelFile levantar uma exceção crua da lib (ex.: zipfile.BadZipFile).
    carregar_todas_abas_excel deve converter isso em FileFormatError, igual
    sua irmã carregar_arquivo já faz, em vez de deixar vazar."""
    caminho = tmp_path / "planilha_corrompida.xlsx"
    caminho.write_text("isto nao e um arquivo excel valido", encoding="utf-8")

    with pytest.raises(FileFormatError):
        carregar_todas_abas_excel(str(caminho))

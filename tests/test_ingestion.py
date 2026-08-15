"""Ingestão: detecção de encoding, separador e leitura de Excel."""
import pandas as pd
import pytest

from recon.ingestion import (
    FileFormatError,
    carregar_arquivo,
    carregar_todas_abas_excel,
    detectar_separador,
)


def _escrever(tmp_path, nome, conteudo):
    caminho = tmp_path / nome
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


# ── Separador ───────────────────────────────────────────────────────────────

def test_carregar_csv_separador_ponto_virgula(tmp_path):
    caminho = _escrever(tmp_path, "dados.csv", "id;nome\n1;Ana\n2;Bruno\n")

    df, nome = carregar_arquivo(str(caminho))

    assert list(df.columns) == ["id", "nome"]
    assert len(df) == 2
    assert nome == "dados"


def test_csv_de_coluna_unica_nao_e_corrompido(tmp_path):
    """Regressão: nenhum separador candidato produzia >1 coluna, então a
    leitura caía no sniffer genérico, que elegia a letra 'o' como separador —
    `nome\\nAna\\nBruno` virava duas colunas `['n', 'me']`."""
    caminho = _escrever(tmp_path, "unica.csv", "nome\nAna\nBruno\nCarla\n")

    df, _ = carregar_arquivo(str(caminho))

    assert list(df.columns) == ["nome"]
    assert df["nome"].tolist() == ["Ana", "Bruno", "Carla"]


def test_separador_escolhido_pela_consistencia_de_campos(tmp_path):
    caminho = _escrever(tmp_path, "virgulas.csv", "nome;valor\nSilva, Ana;10\nSouza, Bo;20\n")
    assert detectar_separador(str(caminho), "utf-8") == ";"


def test_csv_com_pipe(tmp_path):
    caminho = _escrever(tmp_path, "pipe.csv", "a|b|c\n1|2|3\n4|5|6\n")
    df, _ = carregar_arquivo(str(caminho))
    assert list(df.columns) == ["a", "b", "c"]


def test_csv_com_tabulacao(tmp_path):
    caminho = _escrever(tmp_path, "tab.csv", "a\tb\n1\t2\n3\t4\n")
    df, _ = carregar_arquivo(str(caminho))
    assert list(df.columns) == ["a", "b"]


def test_csv_com_texto_entre_aspas_contendo_o_separador(tmp_path):
    caminho = _escrever(tmp_path, "aspas.csv", 'nome,cidade\n"Silva, Ana",SP\n"Souza, Bo",RJ\n')
    df, _ = carregar_arquivo(str(caminho))
    assert list(df.columns) == ["nome", "cidade"]
    assert df["nome"].tolist() == ["Silva, Ana", "Souza, Bo"]


# ── Erros ───────────────────────────────────────────────────────────────────

def test_carregar_arquivo_inexistente_levanta_file_not_found():
    with pytest.raises(FileNotFoundError):
        carregar_arquivo("/caminho/que/nao/existe.csv")


def test_extensao_nao_suportada_levanta_file_format_error(tmp_path):
    caminho = _escrever(tmp_path, "dados.txt", "qualquer coisa")
    with pytest.raises(FileFormatError):
        carregar_arquivo(str(caminho))


def test_csv_vazio_levanta_file_format_error(tmp_path):
    caminho = tmp_path / "vazio.csv"
    caminho.write_bytes(b"")
    with pytest.raises(FileFormatError):
        carregar_arquivo(str(caminho))


# ── Excel ───────────────────────────────────────────────────────────────────

def test_carregar_xlsx(tmp_path):
    caminho = tmp_path / "planilha.xlsx"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(caminho, index=False)

    df, nome = carregar_arquivo(str(caminho))

    assert list(df.columns) == ["a", "b"]
    assert nome == "planilha__Sheet1"


def test_aba_inexistente_por_indice_levanta_erro_claro(tmp_path):
    caminho = tmp_path / "planilha.xlsx"
    pd.DataFrame({"a": [1]}).to_excel(caminho, index=False)

    with pytest.raises(FileFormatError, match="índice 7"):
        carregar_arquivo(str(caminho), aba_excel=7)


def test_carregar_todas_abas_excel_arquivo_inexistente_levanta_file_not_found():
    with pytest.raises(FileNotFoundError):
        carregar_todas_abas_excel("/caminho/que/nao/existe.xlsx")


def test_carregar_todas_abas_excel_corrompido_levanta_file_format_error(tmp_path):
    caminho = _escrever(tmp_path, "corrompida.xlsx", "isto nao e um arquivo excel valido")
    with pytest.raises(FileFormatError):
        carregar_todas_abas_excel(str(caminho))

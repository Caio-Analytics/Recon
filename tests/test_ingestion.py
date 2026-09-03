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
    caminho = _escrever(tmp_path, "relatorio.docx", "qualquer coisa")
    with pytest.raises(FileFormatError):
        carregar_arquivo(str(caminho))


def test_txt_apontado_na_mao_e_lido_como_texto_delimitado(tmp_path):
    """Extração de sistema legado costuma sair com `.txt`. Apontado
    explicitamente, é lido; na varredura de pasta continua de fora, porque
    `leiame.txt` não é tabela."""
    caminho = _escrever(tmp_path, "extracao.txt", "id;uf\n1;SP\n2;RJ\n")
    df, nome = carregar_arquivo(str(caminho))

    assert nome == "extracao"
    assert list(df.columns) == ["id", "uf"]


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


# ── Byte que não decodifica no encoding detectado ───────────────────────────

def test_byte_corrompido_nao_derruba_a_analise(tmp_path, monkeypatch):
    """Regressão real: um export de sistema legado (136 MB, cp1252 detectado
    a partir da amostra do início) tinha uma dúzia de bytes corrompidos lá
    pelo meio — o mesmo byte 0x9D virando "Á" numa palavra e "ç"/"ã" noutra,
    sinal de que a fonte já estava quebrada antes de chegar aqui. Isso
    derrubava a análise inteira com `UnicodeDecodeError`. Byte corrompido no
    meio do arquivo não pode custar o relatório inteiro: substitui por "�" e
    avisa, em vez de travar."""
    from recon import ingestion

    monkeypatch.setattr(ingestion, "detectar_encoding", lambda *a, **k: "cp1252")
    conteudo = (
        b"ORGAO;VALOR\r\n"
        b'"BANCO CENTRAL DO BRASIL";"DI\x9dRIAS"\r\n'
        b'"OUTRO";"NORMAL"\r\n'
    ) * 50
    caminho = tmp_path / "legado.csv"
    caminho.write_bytes(conteudo)

    df, _ = carregar_arquivo(str(caminho))

    assert len(df) > 0
    assert "�" in df["VALOR"].iloc[0]
    avisos = df.attrs["layout"].avisos
    assert any(a["tipo"] == "encoding_substituido" for a in avisos)


def test_leitura_em_blocos_amostra_o_arquivo_inteiro(tmp_path, monkeypatch):
    """Não pode reter apenas os primeiros blocos de uma exportação ordenada."""
    from recon import ingestion

    caminho = _escrever(tmp_path, "grande.csv", "id\n" + "\n".join(map(str, range(9))) + "\n")
    monkeypatch.setattr(ingestion, "_LINHAS_POR_BLOCO", 3)

    df, total = ingestion._ler_csv_amostrado(str(caminho), "utf-8", ",", 0, 3)

    assert total == 9
    assert len(df) == 3
    assert set(df["id"]) != {0, 1, 2}
    assert any(valor >= 3 for valor in df["id"])


def test_limite_de_memoria_dispara_amostragem(tmp_path, monkeypatch):
    from recon import ingestion

    caminho = _escrever(tmp_path, "dados.csv", "id\n1\n")
    monkeypatch.setattr(ingestion, "_memoria_sistema_bytes", lambda: (1000, 1000))
    monkeypatch.setattr(ingestion.os.path, "getsize", lambda _: 200)

    aviso = ingestion._amostragem_por_memoria(str(caminho), "texto")

    assert aviso is not None
    assert "70%" in aviso

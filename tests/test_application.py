"""Casos de uso que a interface Qt chama, sem abrir janela gráfica."""
import pandas as pd

from recon.application import (
    ACOES_INTERFACE,
    executar_analise,
    resolver_pasta_saida,
    validar_selecao,
)


def _acao(chave: str):
    return next(acao for acao in ACOES_INTERFACE if acao.chave == chave)


def test_validacao_da_interface_respeita_ordem_e_quantidade(tmp_path):
    primeiro, segundo, terceiro = (tmp_path / nome for nome in ("a.csv", "b.csv", "c.csv"))
    for caminho in (primeiro, segundo, terceiro):
        caminho.write_text("id\n1\n", encoding="utf-8")

    assert validar_selecao(_acao("conferencia"), [str(primeiro)])
    assert validar_selecao(_acao("conferencia"), [str(primeiro), str(segundo), str(terceiro)])
    assert validar_selecao(_acao("conferencia"), [str(primeiro), str(segundo)]) is None
    assert resolver_pasta_saida("", [str(primeiro)]) == tmp_path


def test_interface_executa_conferencia_e_historico(tmp_path):
    primeiro, segundo = tmp_path / "jan.csv", tmp_path / "fev.csv"
    pd.DataFrame({"id": range(20), "valor": range(20)}).to_csv(primeiro, index=False)
    pd.DataFrame({"id": range(30), "valor": range(30)}).to_csv(segundo, index=False)

    gerados_conferencia, falhas_conferencia = executar_analise(
        _acao("conferencia"), [str(primeiro), str(segundo)], tmp_path / "conferencia", ["html"]
    )
    gerados_historico, falhas_historico = executar_analise(
        _acao("historico"), [str(primeiro), str(segundo)], tmp_path / "historico", ["html"]
    )

    assert not falhas_conferencia and not falhas_historico
    assert any(caminho.name.endswith("_conferencia.html") for caminho in gerados_conferencia)
    assert any(caminho.name.endswith("_historico.html") for caminho in gerados_historico)


def test_interface_localiza_pdf_quando_e_o_unico_formato(tmp_path):
    dados = tmp_path / "dados.csv"
    pd.DataFrame({"id": range(20)}).to_csv(dados, index=False)

    gerados, falhas = executar_analise(_acao("individual"), [str(dados)], tmp_path, ["pdf"])

    assert not falhas
    assert any(caminho.suffix == ".pdf" for caminho in gerados)


def test_interface_expoe_contrato_validacao_e_dicionario(tmp_path):
    dados = tmp_path / "clientes.csv"
    pd.DataFrame({"id_cliente": range(20), "status": ["ativo"] * 20}).to_csv(dados, index=False)

    contrato, falhas = executar_analise(_acao("contrato"), [str(dados)], tmp_path, ["html"])
    assert not falhas
    assert contrato[0].name == "recon_contrato.yaml"

    validacao, falhas = executar_analise(
        _acao("validar"), [str(dados)], tmp_path, ["html"], arquivo_auxiliar=str(contrato[0])
    )
    dicionario, falhas_dicionario = executar_analise(_acao("dicionario"), [str(dados)], tmp_path, ["html"])

    assert not falhas and not falhas_dicionario
    assert "Validação de contrato" in validacao[0].read_text(encoding="utf-8")
    assert dicionario[0].name == "recon_dicionario.xlsx"

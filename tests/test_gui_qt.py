
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from recon import application
from recon.gui_qt import JanelaReconQt, Trabalho


def _acao(chave: str) -> application.AcaoAnalise:
    return next(acao for acao in application.ACOES_INTERFACE if acao.chave == chave)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    return app


@pytest.fixture
def janela(qapp: QApplication) -> JanelaReconQt:
    janela = JanelaReconQt()
    yield janela
    janela.close()
    janela.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize(
    ("chave", "entrada", "executar", "formato_visivel"),
    [
        ("individual", "Dados de entrada", "Analisar agora", True),
        ("lote", "Bases para comparar qualidade", "Analisar agora", True),
        ("modelo", "Tabelas para relacionar", "Analisar agora", True),
        ("dicionario", "Dados de entrada", "Analisar agora", True),
        ("conferencia", "Versões da mesma base", "Analisar agora", True),
        ("historico", "Extrações em ordem cronológica", "Analisar agora", True),
        ("contrato", "Base que define o contrato", "Criar contrato YAML", False),
        ("validar", "Base para validar", "Validar contrato", False),
        ("url", "Arquivo hospedado", "Analisar agora", True),
        ("consulta", "Consulta de banco local", "Analisar agora", True),
        ("semantica", "Base para revisão de semântica", "Gerar YAML de revisão", False),
    ],
)
def test_modos_exibem_controles_proprios(
    janela: JanelaReconQt, chave: str, entrada: str, executar: str, formato_visivel: bool
) -> None:
    janela.abrir_fluxo(_acao(chave))

    assert janela.paginas.currentIndex() == 1
    assert janela.rotulo_entrada.text() == entrada
    assert janela.executar.text() == executar
    assert janela.widget_formatos.isHidden() is not formato_visivel
    assert janela.widget_versoes.isHidden() is (chave != "conferencia")
    assert janela.widget_ordem_historico.isHidden() is (chave != "historico")
    assert janela.widget_nome_contrato.isHidden() is (chave != "contrato")
    assert janela.widget_url.isHidden() is (chave != "url")
    assert janela.widget_consulta.isHidden() is (chave != "consulta")
    assert janela.widget_auxiliar.isHidden() is (chave != "validar")


def test_modos_especiais_usam_entradas_corretas(janela: JanelaReconQt, tmp_path: Path) -> None:
    anterior = tmp_path / "anterior.csv"
    novo = tmp_path / "novo.csv"

    janela.abrir_fluxo(_acao("conferencia"))
    janela.arquivo_anterior.setText(str(anterior))
    janela.arquivo_novo.setText(str(novo))
    assert janela._arquivos_para_analise() == [str(anterior), str(novo)]

    janela.abrir_fluxo(_acao("url"))
    janela.url_fonte.setText("https://exemplo.test/clientes.csv")
    assert janela._arquivos_para_analise() == ["https://exemplo.test/clientes.csv"]
    assert janela.rotulo_saida.text() == "Pasta obrigatória para a fonte remota"

    janela.abrir_fluxo(_acao("consulta"))
    assert janela._arquivos_para_analise() == []
    assert janela.rotulo_saida.text() == "Pasta obrigatória para a consulta"


def test_lista_de_arquivos_atualiza_e_preserva_ordem(janela: JanelaReconQt) -> None:
    janela.arquivos = ["/dados/primeiro.csv", "/dados/segundo.csv"]
    janela._atualizar_lista()
    janela.lista.setCurrentRow(0)
    janela.mover_arquivo(1)

    assert janela.arquivos == ["/dados/segundo.csv", "/dados/primeiro.csv"]
    assert janela.lista.currentRow() == 1
    assert janela.contador.text() == "2 arquivos selecionados"

    janela.limpar_arquivos()
    assert janela.arquivos == []
    assert janela.contador.text() == "0 arquivos selecionados"


def test_trabalho_repassa_resultado_e_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    saida = tmp_path / "recon.html"
    progresso: list[str] = []
    resultados: list[tuple[list[str], list]] = []
    trabalho = Trabalho(
        _acao("individual"), ["entrada.csv"], tmp_path, ["html"], "Detalhado", None,
        None, None, None, None,
    )
    monkeypatch.setattr(application, "executar_analise", lambda *args, **kwargs: ([saida], []))
    trabalho.progresso.connect(progresso.append)
    trabalho.terminou.connect(lambda gerados, falhas: resultados.append((gerados, falhas)))

    trabalho.executar()

    assert any("Iniciando analisar arquivos" in mensagem for mensagem in progresso)
    assert resultados == [([str(saida)], [])]


def test_trabalho_repassa_excecao(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    falhas: list[str] = []
    trabalho = Trabalho(
        _acao("individual"), ["entrada.csv"], tmp_path, ["html"], "Normal", None,
        None, None, None, None,
    )

    def interromper(*args: object, **kwargs: object) -> tuple[list[Path], list[tuple[str, str]]]:
        raise RuntimeError("fonte indisponível")

    monkeypatch.setattr(application, "executar_analise", interromper)
    trabalho.falhou.connect(falhas.append)

    trabalho.executar()

    assert len(falhas) == 1
    assert "RuntimeError: fonte indisponível" in falhas[0]


def test_conclusao_e_erro_restauram_a_janela(
    janela: JanelaReconQt, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    janela.saida.setText(str(tmp_path))
    janela.arquivos_em_execucao = [str(tmp_path / "entrada.csv")]
    janela.executar.setEnabled(False)
    janela.concluido([str(tmp_path / "recon.html")], [("ruim.csv", "não foi lido")])

    assert janela.executar.isEnabled()
    assert janela.abrir_saida.isEnabled()
    assert "Concluído." in janela.log.toPlainText()
    assert "ruim.csv: não foi lido" in janela.log.toPlainText()

    mensagens: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, titulo, mensagem: mensagens.append((titulo, mensagem)),
    )
    janela.nivel.setCurrentText("Normal")
    janela.falhou("detalhe técnico")

    assert mensagens == [("Erro na análise", "A análise falhou. Mude Diagnóstico para Técnico para ver detalhes.")]

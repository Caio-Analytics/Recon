"""Interface gráfica Qt do Recon para pessoas que não usam o terminal."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import application

_ESTILO = """
QMainWindow { background: #0b1120; color: #e5e7eb; font-family: Segoe UI, Inter, Ubuntu, sans-serif; font-size: 14px; }
QWidget#raiz { background: #0b1120; color: #e5e7eb; }
QLabel { background: transparent; }
QFrame#topo { background: #111a2e; border: 1px solid #25324c; border-radius: 14px; }
QFrame#cartao { background: #131d31; border: 1px solid #293852; border-radius: 14px; }
QFrame#cartao:hover { background: #17233a; border-color: #6685bb; }
QFrame#painel { background: #131d31; border: 1px solid #293852; border-radius: 14px; }
QLabel#marca { color: #c4b5fd; font-size: 26px; font-weight: 800; letter-spacing: 1px; }
QLabel#titulo { color: #f8fafc; font-size: 30px; font-weight: 750; }
QLabel#subtitulo, QLabel#descricao, QLabel#contador { color: #aab7cf; }
QLabel#cartao_titulo { color: #f8fafc; font-size: 19px; font-weight: 700; }
QLabel#cartao_descricao { color: #b8c5db; font-size: 14px; }
QListWidget, QLineEdit, QPlainTextEdit, QComboBox { background: #0b1325; border: 1px solid #33435f; border-radius: 8px; padding: 8px; selection-background-color: #7655d9; }
QListWidget::item { padding: 7px; border-bottom: 1px solid #202e47; }
QPushButton { background: #22304a; border: 1px solid #3a4b6b; border-radius: 8px; padding: 10px 15px; font-weight: 650; }
QPushButton:hover { background: #2c3d5d; border-color: #7d96c4; }
QPushButton#primario { background: #8056df; border-color: #8056df; color: white; }
QPushButton#primario:hover { background: #956dff; border-color: #956dff; }
QPushButton#voltar { border: none; color: #93c5fd; text-align: left; padding-left: 0; }
QPushButton:disabled { color: #8b98ae; background: #202b40; border-color: #202b40; }
QCheckBox { spacing: 7px; color: #e5e7eb; }
QProgressBar { background: #0b1325; border: 1px solid #33435f; border-radius: 6px; text-align: center; height: 12px; }
QProgressBar::chunk { background: #8056df; border-radius: 5px; }
"""

_DESCRICOES_MENU = {
    "individual": "Crie um perfil completo de cada arquivo, mesmo selecionando vários de uma vez.",
    "lote": "Veja diferenças de qualidade e priorize onde investigar primeiro.",
    "modelo": "Mapeie chaves candidatas, fatos, dimensões e possíveis cruzamentos.",
    "conferencia": "Compare uma extração anterior com a nova e veja mudanças que exigem atenção.",
    "historico": "Acompanhe volume, qualidade e estrutura de várias extrações ao longo do tempo.",
    "contrato": "Congele uma referência revisável para saber o que uma carga futura deve manter.",
    "validar": "Use um contrato existente para verificar se a nova extração continua dentro do combinado.",
    "dicionario": "Documente uma ou várias bases em uma planilha pronta para filtrar e compartilhar.",
}

_DETALHES_MENU = {
    "individual": (
        "Exemplo prático",
        "Recebi vendas.xlsx, clientes.csv e produtos.csv; quero um relatório separado de cada um.",
    ),
    "lote": (
        "Exemplo prático",
        "Tenho 20 bases mensais e preciso descobrir quais têm mais campos vazios ou inconsistências.",
    ),
    "modelo": (
        "Exemplo prático",
        "Tenho vendas, clientes e produtos; quero identificar a tabela fato, dimensões e chaves para cruzá-las.",
    ),
    "conferencia": (
        "Exemplo prático",
        "Recebi a carga de fevereiro e preciso saber o que mudou em relação à carga de janeiro.",
    ),
    "historico": (
        "Exemplo prático",
        "Quero acompanhar as cargas mensais e identificar quando a qualidade começou a cair.",
    ),
    "contrato": (
        "Exemplo prático",
        "A base de clientes está correta hoje; quero registrar colunas, tipos e limites antes da próxima carga.",
    ),
    "validar": (
        "Exemplo prático",
        "Recebi a carga de hoje e quero saber se ela respeita o contrato de clientes revisado pela equipe.",
    ),
    "dicionario": (
        "Exemplo prático",
        "Preciso entregar uma descrição clara dos campos de vendas, clientes e produtos para outra área.",
    ),
}


class Trabalho(QObject):
    """Executa a análise fora da thread que desenha a janela."""

    progresso = Signal(str)
    terminou = Signal(list, list)
    falhou = Signal(str)

    def __init__(
        self,
        acao: application.AcaoAnalise,
        arquivos: list[str],
        saida: Path,
        formatos: list[str],
        nivel_diagnostico: str,
        vocabularios: str | None,
        arquivo_auxiliar: str | None,
    ) -> None:
        super().__init__()
        self.acao = acao
        self.arquivos = arquivos
        self.saida = saida
        self.formatos = formatos
        self.nivel_diagnostico = nivel_diagnostico
        self.vocabularios = vocabularios
        self.arquivo_auxiliar = arquivo_auxiliar

    def executar(self) -> None:
        niveis = {"Normal": "WARNING", "Detalhado": "INFO", "Técnico": "DEBUG"}
        sink = logger.add(
            lambda mensagem: self.progresso.emit(mensagem.rstrip()),
            level=niveis.get(self.nivel_diagnostico, "INFO"),
            format="[{time:HH:mm:ss}] {level}: {message}",
        )
        try:
            self.progresso.emit(f"Iniciando {self.acao.titulo.lower()}…")
            gerados, falhas = application.executar_analise(
                self.acao, self.arquivos, self.saida, formatos=self.formatos,
                vocabularios=self.vocabularios,
                arquivo_auxiliar=self.arquivo_auxiliar,
            )
            self.terminou.emit([str(caminho) for caminho in gerados], falhas)
        except Exception:
            self.falhou.emit(traceback.format_exc())
        finally:
            logger.remove(sink)


class CartaoModo(QFrame):
    """Cartão da tela inicial que explica uma ação sem jargão técnico."""

    def __init__(
        self, acao: application.AcaoAnalise, ao_escolher: Callable[[application.AcaoAnalise], None]
    ) -> None:
        super().__init__()
        self.setObjectName("cartao")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        numero = application.ACOES_INTERFACE.index(acao) + 1
        marcador = QLabel(f"{numero:02d}  ·  {acao.aba.upper()}")
        marcador.setStyleSheet(f"color: {acao.cor}; font-weight: 700; font-size: 11px;")
        layout.addWidget(marcador)
        titulo = QLabel(acao.titulo)
        titulo.setObjectName("cartao_titulo")
        titulo.setWordWrap(True)
        layout.addWidget(titulo)
        descricao = QLabel(_DESCRICOES_MENU[acao.chave])
        descricao.setObjectName("cartao_descricao")
        descricao.setWordWrap(True)
        layout.addWidget(descricao, 1)
        detalhe_titulo, detalhe = _DETALHES_MENU[acao.chave]
        contexto = QLabel(f"<b>{detalhe_titulo}</b><br>{detalhe}")
        contexto.setObjectName("descricao")
        contexto.setWordWrap(True)
        contexto.setStyleSheet(
            "background: #0e1729; border: 1px solid #263753; border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(contexto)
        botao = QPushButton("Escolher este modo")
        botao.setObjectName("primario")
        botao.clicked.connect(lambda: ao_escolher(acao))
        layout.addWidget(botao)


class JanelaReconQt(QMainWindow):
    """Aplicação em duas telas: escolher intenção e depois configurar análise."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Recon — reconhecimento de dados")
        self.resize(1120, 740)
        self.arquivos: list[str] = []
        self.acao_atual: application.AcaoAnalise | None = None
        self.ultima_saida: Path | None = None
        self.worker_thread: QThread | None = None
        self.trabalho: Trabalho | None = None
        self._montar()

    def _montar(self) -> None:
        raiz = QWidget()
        raiz.setObjectName("raiz")
        layout = QVBoxLayout(raiz)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(18)
        layout.addWidget(self._criar_topo())
        self.paginas = QStackedWidget()
        self.paginas.addWidget(self._criar_menu())
        self.paginas.addWidget(self._criar_fluxo_analise())
        layout.addWidget(self.paginas, 1)
        self.setCentralWidget(raiz)

    def _criar_topo(self) -> QFrame:
        topo = QFrame()
        topo.setObjectName("topo")
        layout = QHBoxLayout(topo)
        layout.setContentsMargins(22, 16, 22, 16)
        marca = QLabel("RECON")
        marca.setObjectName("marca")
        layout.addWidget(marca)
        texto = QLabel("Conheça seus dados antes de analisá-los")
        texto.setObjectName("subtitulo")
        layout.addWidget(texto)
        layout.addStretch()
        privacidade = QLabel("● Processamento local")
        privacidade.setStyleSheet("background: transparent; color: #5eead4; font-weight: 650;")
        layout.addWidget(privacidade)
        return topo

    def _criar_menu(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setSpacing(16)
        titulo = QLabel("Por onde você quer começar?")
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)
        subtitulo = QLabel(
            "Escolha o objetivo da análise. Em seguida, selecione seus arquivos e revise tudo antes de iniciar."
        )
        subtitulo.setObjectName("subtitulo")
        layout.addWidget(subtitulo)

        cartoes = QGridLayout()
        cartoes.setSpacing(14)
        for indice, acao in enumerate(application.ACOES_INTERFACE):
            cartoes.addWidget(CartaoModo(acao, self.abrir_fluxo), indice // 2, indice % 2)
        cartoes.setColumnStretch(0, 1)
        cartoes.setColumnStretch(1, 1)
        layout.addLayout(cartoes, 1)
        ajuda = QLabel("Dica: na dúvida, comece por “Analisar arquivos”.")
        ajuda.setObjectName("subtitulo")
        ajuda.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ajuda)
        return pagina

    def _criar_fluxo_analise(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        voltar = QPushButton("← Voltar aos modos de análise")
        voltar.setObjectName("voltar")
        voltar.clicked.connect(lambda: self.paginas.setCurrentIndex(0))
        layout.addWidget(voltar, alignment=Qt.AlignmentFlag.AlignLeft)
        self.titulo_acao = QLabel()
        self.titulo_acao.setObjectName("titulo")
        layout.addWidget(self.titulo_acao)
        self.descricao_acao = QLabel()
        self.descricao_acao.setObjectName("subtitulo")
        self.descricao_acao.setWordWrap(True)
        layout.addWidget(self.descricao_acao)

        corpo = QSplitter()
        corpo.addWidget(self._criar_painel_selecao())
        corpo.addWidget(self._criar_painel_diagnostico())
        corpo.setSizes([545, 520])
        layout.addWidget(corpo, 1)
        return pagina

    def _criar_painel_selecao(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("painel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        rotulo = QLabel("1. Selecione os dados")
        rotulo.setObjectName("cartao_titulo")
        layout.addWidget(rotulo)
        self.contador = QLabel("Nenhum arquivo selecionado")
        self.contador.setObjectName("contador")
        layout.addWidget(self.contador)
        self.lista = QListWidget()
        self.lista.setMinimumHeight(180)
        layout.addWidget(self.lista, 1)
        botoes = QHBoxLayout()
        procurar = QPushButton("Adicionar arquivos…")
        procurar.setObjectName("primario")
        limpar = QPushButton("Limpar lista")
        procurar.clicked.connect(self.escolher_arquivos)
        limpar.clicked.connect(self.limpar_arquivos)
        botoes.addWidget(procurar)
        botoes.addWidget(limpar)
        layout.addLayout(botoes)

        destino = QLabel("2. Defina onde salvar")
        destino.setObjectName("cartao_titulo")
        layout.addWidget(destino)
        self.saida = QLineEdit()
        self.saida.setPlaceholderText("Na mesma pasta do arquivo, se deixar vazio")
        pasta = QPushButton("Escolher pasta…")
        pasta.clicked.connect(self.escolher_saida)
        linha_saida = QHBoxLayout()
        linha_saida.addWidget(self.saida, 1)
        linha_saida.addWidget(pasta)
        layout.addLayout(linha_saida)

        vocabulario = QLabel("Vocabulário do seu negócio (opcional)")
        vocabulario.setObjectName("cartao_titulo")
        layout.addWidget(vocabulario)
        self.vocabularios = QLineEdit()
        self.vocabularios.setPlaceholderText("YAML com termos próprios, se existir")
        escolher_vocabulario = QPushButton("Escolher YAML…")
        escolher_vocabulario.clicked.connect(self.escolher_vocabulario)
        linha_vocabulario = QHBoxLayout()
        linha_vocabulario.addWidget(self.vocabularios, 1)
        linha_vocabulario.addWidget(escolher_vocabulario)
        layout.addLayout(linha_vocabulario)

        self.rotulo_auxiliar = QLabel()
        self.rotulo_auxiliar.setObjectName("cartao_titulo")
        self.rotulo_auxiliar.setVisible(False)
        layout.addWidget(self.rotulo_auxiliar)
        self.arquivo_auxiliar = QLineEdit()
        self.arquivo_auxiliar.setVisible(False)
        self.botao_auxiliar = QPushButton("Escolher YAML…")
        self.botao_auxiliar.clicked.connect(self.escolher_arquivo_auxiliar)
        self.botao_auxiliar.setVisible(False)
        linha_auxiliar = QHBoxLayout()
        linha_auxiliar.addWidget(self.arquivo_auxiliar, 1)
        linha_auxiliar.addWidget(self.botao_auxiliar)
        self.widget_auxiliar = QWidget()
        self.widget_auxiliar.setLayout(linha_auxiliar)
        self.widget_auxiliar.setVisible(False)
        layout.addWidget(self.widget_auxiliar)

        formato = QLabel("3. Escolha o relatório")
        formato.setObjectName("cartao_titulo")
        layout.addWidget(formato)
        self.formatos = {nome: QCheckBox(rotulo) for nome, rotulo, _ in application.FORMATOS_INTERFACE}
        self.formatos["html"].setChecked(True)
        linha_formatos = QHBoxLayout()
        for caixa in self.formatos.values():
            linha_formatos.addWidget(caixa)
        linha_formatos.addStretch()
        layout.addLayout(linha_formatos)
        self.executar = QPushButton("Analisar agora")
        self.executar.setObjectName("primario")
        self.executar.clicked.connect(self.iniciar)
        layout.addWidget(self.executar)
        self.abrir_saida = QPushButton("Abrir pasta de relatórios")
        self.abrir_saida.setEnabled(False)
        self.abrir_saida.clicked.connect(self.abrir_pasta_saida)
        layout.addWidget(self.abrir_saida)
        return painel

    def _criar_painel_diagnostico(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("painel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 20, 20, 20)
        titulo = QLabel("Acompanhamento")
        titulo.setObjectName("cartao_titulo")
        layout.addWidget(titulo)
        texto = QLabel("Aqui você vê o que aconteceu. Use o nível técnico só ao investigar um erro.")
        texto.setObjectName("descricao")
        texto.setWordWrap(True)
        layout.addWidget(texto)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("A análise ainda não foi iniciada.")
        layout.addWidget(self.log, 1)
        nivel_linha = QHBoxLayout()
        nivel_linha.addWidget(QLabel("Detalhe do diagnóstico:"))
        self.nivel = QComboBox()
        self.nivel.addItems(["Normal", "Detalhado", "Técnico"])
        nivel_linha.addWidget(self.nivel)
        layout.addLayout(nivel_linha)
        self.progresso = QProgressBar()
        self.progresso.setRange(0, 1)
        layout.addWidget(self.progresso)
        return painel

    def abrir_fluxo(self, acao: application.AcaoAnalise) -> None:
        self.acao_atual = acao
        self.titulo_acao.setText(acao.titulo)
        self.descricao_acao.setText(acao.explicacao)
        usa_auxiliar = bool(acao.arquivo_auxiliar)
        self.rotulo_auxiliar.setVisible(usa_auxiliar)
        self.widget_auxiliar.setVisible(usa_auxiliar)
        if usa_auxiliar:
            self.rotulo_auxiliar.setText(f"2. {acao.arquivo_auxiliar}")
            self.arquivo_auxiliar.setPlaceholderText("Escolha o arquivo YAML já revisado")
        self.paginas.setCurrentIndex(1)

    def escolher_arquivos(self) -> None:
        arquivos, _ = QFileDialog.getOpenFileNames(
            self,
            "Escolha os arquivos",
            "",
            "Dados (*.csv *.tsv *.txt *.xlsx *.xls *.xlsb *.parquet *.gz *.zip)",
        )
        self.arquivos.extend(arquivo for arquivo in arquivos if arquivo not in self.arquivos)
        self._atualizar_lista()

    def escolher_saida(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Onde salvar os relatórios")
        if pasta:
            self.saida.setText(pasta)

    def escolher_vocabulario(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolha o vocabulário do negócio", "", "YAML (*.yaml *.yml)"
        )
        if caminho:
            self.vocabularios.setText(caminho)

    def escolher_arquivo_auxiliar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolha o contrato de referência", "", "YAML (*.yaml *.yml)"
        )
        if caminho:
            self.arquivo_auxiliar.setText(caminho)

    def abrir_pasta_saida(self) -> None:
        if self.ultima_saida is not None:
            application.abrir_no_explorador(self.ultima_saida)

    def limpar_arquivos(self) -> None:
        self.arquivos.clear()
        self._atualizar_lista()

    def _atualizar_lista(self) -> None:
        self.lista.clear()
        self.lista.addItems([Path(arquivo).name for arquivo in self.arquivos])
        quantidade = len(self.arquivos)
        if quantidade == 1:
            self.contador.setText("1 arquivo selecionado")
        else:
            self.contador.setText(f"{quantidade} arquivos selecionados")

    def _registrar(self, texto: str) -> None:
        self.log.appendPlainText(texto)

    def iniciar(self) -> None:
        if self.acao_atual is None:
            return
        erro = application.validar_selecao(self.acao_atual, self.arquivos)
        if erro:
            QMessageBox.warning(self, "Revise a seleção", erro)
            return
        try:
            pasta_saida = application.resolver_pasta_saida(self.saida.text(), self.arquivos)
        except ValueError as erro_saida:
            QMessageBox.warning(self, "Saída", str(erro_saida))
            return

        formatos = [nome for nome, caixa in self.formatos.items() if caixa.isChecked()]
        if not formatos:
            QMessageBox.warning(self, "Formatos", "Escolha ao menos um formato.")
            return

        self.executar.setEnabled(False)
        self.abrir_saida.setEnabled(False)
        self.progresso.setRange(0, 0)
        self.log.clear()
        self._registrar(f"Modo: {self.acao_atual.titulo}")
        self._registrar(f"Arquivos: {len(self.arquivos)} | Saída: {pasta_saida}")
        self.worker_thread = QThread(self)
        self.trabalho = Trabalho(
            self.acao_atual, self.arquivos, pasta_saida, formatos, self.nivel.currentText(),
            self.vocabularios.text().strip() or None,
            self.arquivo_auxiliar.text().strip() or None,
        )
        self.trabalho.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.trabalho.executar)
        self.trabalho.progresso.connect(self._registrar)
        self.trabalho.terminou.connect(self.concluido)
        self.trabalho.falhou.connect(self.falhou)
        self.trabalho.terminou.connect(self.worker_thread.quit)
        self.trabalho.falhou.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def concluido(self, gerados: list[str], falhas: list) -> None:
        self.progresso.setRange(0, 1)
        self.executar.setEnabled(True)
        self.ultima_saida = application.resolver_pasta_saida(self.saida.text(), self.arquivos)
        self.abrir_saida.setEnabled(True)
        self._registrar("Concluído.")
        self._registrar("Arquivos gerados:\n" + "\n".join(gerados))
        if falhas:
            texto_falhas = "\n".join(f"{arquivo}: {erro}" for arquivo, erro in falhas)
            self._registrar("Falhas:\n" + texto_falhas)

    def falhou(self, detalhe: str) -> None:
        self.progresso.setRange(0, 1)
        self.executar.setEnabled(True)
        mensagem = detalhe if self.nivel.currentText() == "Técnico" else (
            "A análise falhou. Mude Diagnóstico para Técnico para ver detalhes."
        )
        self._registrar(mensagem)
        QMessageBox.critical(self, "Erro na análise", mensagem)


def main() -> None:
    """Inicia a aplicação Qt."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    app.setStyleSheet(_ESTILO)
    janela = JanelaReconQt()
    janela.show()
    app.exec()

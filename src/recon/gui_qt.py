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
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import application

_ESTILO = """
QMainWindow { background: #111827; color: #e5edf7; font-family: Segoe UI, Inter, Ubuntu, sans-serif; font-size: 14px; }
QWidget#raiz, QWidget#conteudo_menu { background: #111827; color: #e5edf7; }
QLabel { background: transparent; color: #e5edf7; }
QFrame#topo { background: #172033; border: 1px solid #334155; border-radius: 16px; }
QFrame#cartao, QFrame#painel { background: #172033; border: 1px solid #334155; border-radius: 14px; }
QFrame#painel { border-radius: 16px; }
QFrame#cartao:hover { background: #1e293b; border-color: #60a5fa; }
QLabel#marca { color: #93c5fd; font-size: 26px; font-weight: 800; letter-spacing: 1px; }
QLabel#titulo, QLabel#cartao_titulo { color: #f8fafc; font-weight: 750; }
QLabel#titulo { font-size: 30px; }
QLabel#cartao_titulo { font-size: 19px; }
QLabel#subtitulo, QLabel#descricao, QLabel#contador { color: #b8c6d9; }
QLabel#cartao_descricao { color: #d1dbea; font-size: 14px; }
QListWidget, QLineEdit, QPlainTextEdit, QComboBox { background: #0f172a; border: 1px solid #475569; border-radius: 9px; padding: 9px; color: #e5edf7; selection-background-color: #1e40af; }
QLineEdit::placeholder, QPlainTextEdit::placeholder { color: #94a3b8; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #263449; }
QListWidget::item:selected { background: #1e3a8a; color: #ffffff; }
QPushButton { background: #263449; border: 1px solid #52657d; border-radius: 9px; min-height: 24px; padding: 9px 15px; color: #e5edf7; font-weight: 650; }
QPushButton:hover { background: #334155; border-color: #93c5fd; }
QPushButton#primario { background: #1e40af; border-color: #3b82f6; color: white; }
QPushButton#primario:hover { background: #2563eb; border-color: #bfdbfe; }
QPushButton#voltar { background: transparent; border: none; color: #93c5fd; font-size: 14px; font-weight: 650; min-height: 20px; padding: 4px 0; text-align: left; }
QPushButton#voltar:hover { background: transparent; color: #dbeafe; }
QPushButton:disabled { color: #7f8ea3; background: #1b2738; border-color: #2b3b50; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QListWidget:focus, QCheckBox:focus { border: 2px solid #fbbf24; }
QCheckBox { spacing: 7px; color: #e5edf7; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #64748b; border-radius: 4px; background: #0f172a; }
QCheckBox::indicator:checked { background: #2563eb; border-color: #93c5fd; }
QProgressBar { background: #0f172a; border: 1px solid #475569; border-radius: 6px; text-align: center; height: 12px; }
QProgressBar::chunk { background: #3b82f6; border-radius: 5px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #172033; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #52657d; min-height: 28px; border-radius: 5px; }
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
    "url": "Analise um arquivo hospedado sem precisar baixá-lo manualmente.",
    "consulta": "Leia o resultado de uma consulta segura em um banco local.",
    "semantica": "Gere um arquivo revisável para confirmar o significado de cada campo.",
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
    "url": (
        "Exemplo prático",
        "Recebi um link assinado para clientes.csv e quero analisá-lo diretamente.",
    ),
    "consulta": (
        "Exemplo prático",
        "Tenho vendas.db e quero perfilar somente o resultado de um SELECT revisado.",
    ),
    "semantica": (
        "Exemplo prático",
        "Quero revisar se campos como código, nome e status foram classificados corretamente.",
    ),
}


class Trabalho(QObject):
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
        nome_contrato: str | None,
        conexao: str | None,
        sql: str | None,
    ) -> None:
        super().__init__()
        self.acao = acao
        self.arquivos = arquivos
        self.saida = saida
        self.formatos = formatos
        self.nivel_diagnostico = nivel_diagnostico
        self.vocabularios = vocabularios
        self.arquivo_auxiliar = arquivo_auxiliar
        self.nome_contrato = nome_contrato
        self.conexao = conexao
        self.sql = sql

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
                self.acao,
                self.arquivos,
                self.saida,
                formatos=self.formatos,
                vocabularios=self.vocabularios,
                arquivo_auxiliar=self.arquivo_auxiliar,
                nome_contrato=self.nome_contrato,
                conexao=self.conexao,
                sql=self.sql,
            )
            self.terminou.emit([str(caminho) for caminho in gerados], falhas)
        except Exception:
            self.falhou.emit(traceback.format_exc())
        finally:
            logger.remove(sink)


class CartaoModo(QFrame):
    def __init__(
        self, acao: application.AcaoAnalise, ao_escolher: Callable[[application.AcaoAnalise], None]
    ) -> None:
        super().__init__()
        self.setObjectName("cartao")
        self.setMinimumHeight(188)
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
            "background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(contexto)
        botao = QPushButton("Escolher este modo")
        botao.setObjectName("primario")
        botao.clicked.connect(lambda: ao_escolher(acao))
        layout.addWidget(botao)


class JanelaReconQt(QMainWindow):
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

    def _criar_menu(self) -> QScrollArea:
        pagina = QScrollArea()
        pagina.setWidgetResizable(True)
        conteudo = QWidget()
        conteudo.setObjectName("conteudo_menu")
        pagina.setWidget(conteudo)
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(16)
        titulo = QLabel("O que você quer descobrir?")
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)
        subtitulo = QLabel(
            "Escolha um objetivo. Depois, selecione os arquivos e revise a execução antes de começar."
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
        ajuda = QLabel("Dica: se este é seu primeiro arquivo, comece por “Analisar arquivos”.")
        ajuda.setObjectName("subtitulo")
        ajuda.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ajuda)
        return pagina

    def _criar_fluxo_analise(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        voltar = QPushButton("‹  Modos de análise")
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
        corpo.setChildrenCollapsible(False)
        corpo.setHandleWidth(10)
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
        self.rotulo_entrada = QLabel("Dados de entrada")
        self.rotulo_entrada.setObjectName("cartao_titulo")
        layout.addWidget(self.rotulo_entrada)
        self.ajuda_entrada = QLabel()
        self.ajuda_entrada.setObjectName("descricao")
        self.ajuda_entrada.setWordWrap(True)
        layout.addWidget(self.ajuda_entrada)

        self.widget_arquivos = QWidget()
        arquivos_layout = QVBoxLayout(self.widget_arquivos)
        arquivos_layout.setContentsMargins(0, 0, 0, 0)
        arquivos_layout.setSpacing(8)
        self.contador = QLabel("Nenhum arquivo selecionado")
        self.contador.setObjectName("contador")
        arquivos_layout.addWidget(self.contador)
        self.lista = QListWidget()
        self.lista.setMinimumHeight(180)
        arquivos_layout.addWidget(self.lista, 1)
        botoes = QHBoxLayout()
        procurar = QPushButton("Adicionar arquivos…")
        procurar.setObjectName("primario")
        limpar = QPushButton("Limpar lista")
        procurar.clicked.connect(self.escolher_arquivos)
        limpar.clicked.connect(self.limpar_arquivos)
        botoes.addWidget(procurar)
        botoes.addWidget(limpar)
        arquivos_layout.addLayout(botoes)
        self.widget_ordem_historico = QWidget()
        ordem_layout = QHBoxLayout(self.widget_ordem_historico)
        ordem_layout.setContentsMargins(0, 0, 0, 0)
        ordem_layout.addWidget(QLabel("A lista acima é a linha do tempo."))
        subir = QPushButton("Mover para cima")
        descer = QPushButton("Mover para baixo")
        subir.clicked.connect(lambda: self.mover_arquivo(-1))
        descer.clicked.connect(lambda: self.mover_arquivo(1))
        ordem_layout.addStretch()
        ordem_layout.addWidget(subir)
        ordem_layout.addWidget(descer)
        self.widget_ordem_historico.setVisible(False)
        arquivos_layout.addWidget(self.widget_ordem_historico)
        layout.addWidget(self.widget_arquivos, 1)

        self.widget_url = QWidget()
        url_layout = QVBoxLayout(self.widget_url)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)
        url_layout.addWidget(QLabel("URL do arquivo"))
        self.url_fonte = QLineEdit()
        self.url_fonte.setPlaceholderText("https://servidor.exemplo/base.csv")
        self.url_fonte.setAccessibleName("URL do arquivo a analisar")
        url_layout.addWidget(self.url_fonte)
        ajuda_url = QLabel(
            "Aceita CSV, JSON e Parquet por HTTP(S). Links assinados funcionam enquanto estiverem válidos."
        )
        ajuda_url.setObjectName("descricao")
        ajuda_url.setWordWrap(True)
        url_layout.addWidget(ajuda_url)
        self.widget_url.setVisible(False)
        layout.addWidget(self.widget_url)

        self.widget_consulta = QWidget()
        consulta_layout = QVBoxLayout(self.widget_consulta)
        consulta_layout.setContentsMargins(0, 0, 0, 0)
        consulta_layout.setSpacing(6)
        consulta_layout.addWidget(QLabel("Conexão do banco local"))
        self.conexao_banco = QLineEdit()
        self.conexao_banco.setPlaceholderText(
            "sqlite:///caminho/base.db ou duckdb:///caminho/base.duckdb"
        )
        self.conexao_banco.setAccessibleName("Conexão SQLite ou DuckDB local")
        consulta_layout.addWidget(self.conexao_banco)
        consulta_layout.addWidget(QLabel("Consulta de leitura"))
        self.sql_consulta = QPlainTextEdit()
        self.sql_consulta.setPlaceholderText("SELECT * FROM clientes")
        self.sql_consulta.setAccessibleName("Consulta SQL somente de leitura")
        self.sql_consulta.setMinimumHeight(110)
        consulta_layout.addWidget(self.sql_consulta)
        ajuda_consulta = QLabel(
            "Por segurança, o Recon aceita somente consultas SELECT ou WITH e abre o banco em modo leitura."
        )
        ajuda_consulta.setObjectName("descricao")
        ajuda_consulta.setWordWrap(True)
        consulta_layout.addWidget(ajuda_consulta)
        self.widget_consulta.setVisible(False)
        layout.addWidget(self.widget_consulta, 1)

        self.widget_versoes = QWidget()
        versoes_layout = QVBoxLayout(self.widget_versoes)
        versoes_layout.setContentsMargins(0, 0, 0, 0)
        versoes_layout.setSpacing(10)
        self.arquivo_anterior = QLineEdit()
        self.arquivo_novo = QLineEdit()
        for rotulo_versao, campo, texto_botao in (
            ("Arquivo anterior", self.arquivo_anterior, "Escolher anterior…"),
            ("Arquivo novo", self.arquivo_novo, "Escolher novo…"),
        ):
            versoes_layout.addWidget(QLabel(rotulo_versao))
            campo.setPlaceholderText("Selecione o arquivo")
            botao = QPushButton(texto_botao)
            botao.clicked.connect(
                lambda _=False, destino=campo, titulo=rotulo_versao: self.escolher_versao(
                    destino, titulo
                )
            )
            linha = QHBoxLayout()
            linha.addWidget(campo, 1)
            linha.addWidget(botao)
            versoes_layout.addLayout(linha)
        self.widget_versoes.setVisible(False)
        layout.addWidget(self.widget_versoes, 1)

        self.rotulo_saida = QLabel("Onde salvar")
        self.rotulo_saida.setObjectName("cartao_titulo")
        layout.addWidget(self.rotulo_saida)
        self.saida = QLineEdit()
        self.saida.setPlaceholderText("Na mesma pasta do arquivo, se deixar vazio")
        pasta = QPushButton("Escolher pasta…")
        pasta.clicked.connect(self.escolher_saida)
        linha_saida = QHBoxLayout()
        linha_saida.addWidget(self.saida, 1)
        linha_saida.addWidget(pasta)
        layout.addLayout(linha_saida)

        self.widget_nome_contrato = QWidget()
        nome_contrato_layout = QVBoxLayout(self.widget_nome_contrato)
        nome_contrato_layout.setContentsMargins(0, 0, 0, 0)
        nome_contrato_layout.setSpacing(6)
        nome_contrato_layout.addWidget(QLabel("Nome do contrato"))
        self.nome_contrato = QLineEdit()
        self.nome_contrato.setPlaceholderText("contrato_clientes.yaml")
        nome_contrato_layout.addWidget(self.nome_contrato)
        self.widget_nome_contrato.setVisible(False)
        layout.addWidget(self.widget_nome_contrato)

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

        self.widget_formatos = QWidget()
        formatos_layout = QVBoxLayout(self.widget_formatos)
        formatos_layout.setContentsMargins(0, 0, 0, 0)
        formato = QLabel("Formato do relatório")
        formato.setObjectName("cartao_titulo")
        formatos_layout.addWidget(formato)
        self.formatos = {
            nome: QCheckBox(rotulo) for nome, rotulo, _ in application.FORMATOS_INTERFACE
        }
        self.formatos["html"].setChecked(True)
        linha_formatos = QHBoxLayout()
        for caixa in self.formatos.values():
            linha_formatos.addWidget(caixa)
        linha_formatos.addStretch()
        formatos_layout.addLayout(linha_formatos)
        layout.addWidget(self.widget_formatos)
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
        texto = QLabel(
            "Aqui você vê o que aconteceu. Use o nível técnico só ao investigar um erro."
        )
        texto.setObjectName("descricao")
        texto.setWordWrap(True)
        layout.addWidget(texto)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("A análise ainda não foi iniciada. O andamento aparecerá aqui.")
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
        conferencia = acao.chave == "conferencia"
        historico = acao.chave == "historico"
        contrato = acao.chave == "contrato"
        validar = acao.chave == "validar"
        url = acao.chave == "url"
        consulta = acao.chave == "consulta"
        semantica = acao.chave == "semantica"
        self.widget_arquivos.setVisible(not (conferencia or url or consulta))
        self.widget_url.setVisible(url)
        self.widget_consulta.setVisible(consulta)
        self.widget_versoes.setVisible(conferencia)
        self.widget_ordem_historico.setVisible(historico)
        self.widget_nome_contrato.setVisible(contrato)
        self.widget_formatos.setVisible(not (contrato or validar or semantica))
        self.executar.setText(
            "Criar contrato YAML"
            if contrato
            else "Validar contrato"
            if validar
            else "Gerar YAML de revisão"
            if semantica
            else "Analisar agora"
        )
        self.rotulo_entrada.setText(
            {
                "lote": "Bases para comparar qualidade",
                "modelo": "Tabelas para relacionar",
                "conferencia": "Versões da mesma base",
                "historico": "Extrações em ordem cronológica",
                "contrato": "Base que define o contrato",
                "validar": "Base para validar",
                "url": "Arquivo hospedado",
                "consulta": "Consulta de banco local",
                "semantica": "Base para revisão de semântica",
            }.get(acao.chave, "Dados de entrada")
        )
        self.ajuda_entrada.setText(
            {
                "lote": "Adicione bases comparáveis. Este modo as prioriza por qualidade; para usar uma base como referência, escolha “Conferir duas versões”.",
                "modelo": "Selecione as tabelas que fazem parte do mesmo assunto.",
                "conferencia": "A ordem é importante: o Recon compara a versão anterior com a nova.",
                "historico": "Adicione as extrações da mais antiga para a mais recente. Use os botões para corrigir a ordem.",
                "contrato": "Escolha uma base revisada e estável. O YAML salvo poderá ser reutilizado para validar cargas futuras.",
                "validar": "Escolha a base nova que será conferida contra o contrato YAML.",
                "url": "Cole uma URL HTTP(S). A fonte é lida diretamente e as credenciais não são armazenadas pelo Recon.",
                "consulta": "Informe uma conexão SQLite ou DuckDB local e uma consulta SELECT ou WITH.",
                "semantica": "Escolha uma base. O YAML resultante pode ser editado e reutilizado como vocabulário do negócio.",
            }.get(acao.chave, "Selecione os arquivos que o Recon deve analisar.")
        )
        self.rotulo_saida.setText(
            "Pasta onde o contrato será guardado"
            if contrato
            else "Pasta obrigatória para a fonte remota"
            if url
            else "Pasta obrigatória para a consulta"
            if consulta
            else "Onde salvar"
        )
        usa_auxiliar = bool(acao.arquivo_auxiliar)
        self.rotulo_auxiliar.setVisible(usa_auxiliar)
        self.widget_auxiliar.setVisible(usa_auxiliar)
        if usa_auxiliar:
            self.rotulo_auxiliar.setText(acao.arquivo_auxiliar or "")
            self.arquivo_auxiliar.setPlaceholderText("Escolha o arquivo YAML já revisado")
        if contrato and not self.nome_contrato.text() and self.arquivos:
            self.nome_contrato.setText(f"contrato_{Path(self.arquivos[0]).stem}.yaml")
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
        if self.acao_atual and self.acao_atual.chave == "contrato" and len(self.arquivos) == 1:
            self.nome_contrato.setText(f"contrato_{Path(self.arquivos[0]).stem}.yaml")

    def escolher_versao(self, destino: QLineEdit, titulo: str) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, titulo, "", "Dados (*.csv *.tsv *.txt *.xlsx *.xls *.xlsb *.parquet *.gz *.zip)"
        )
        if caminho:
            destino.setText(caminho)

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

    def mover_arquivo(self, deslocamento: int) -> None:
        atual = self.lista.currentRow()
        destino = atual + deslocamento
        if atual < 0 or destino < 0 or destino >= len(self.arquivos):
            return
        self.arquivos[atual], self.arquivos[destino] = self.arquivos[destino], self.arquivos[atual]
        self._atualizar_lista()
        self.lista.setCurrentRow(destino)

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

    def _arquivos_para_analise(self) -> list[str]:
        if self.acao_atual and self.acao_atual.chave == "conferencia":
            return [
                campo.text().strip()
                for campo in (self.arquivo_anterior, self.arquivo_novo)
                if campo.text().strip()
            ]
        if self.acao_atual and self.acao_atual.chave == "url":
            return [self.url_fonte.text().strip()] if self.url_fonte.text().strip() else []
        return self.arquivos.copy()

    def iniciar(self) -> None:
        if self.acao_atual is None:
            return
        arquivos = self._arquivos_para_analise()
        erro = application.validar_selecao(self.acao_atual, arquivos)
        if erro:
            QMessageBox.warning(self, "Revise a seleção", erro)
            return
        consulta = self.acao_atual.chave == "consulta"
        if consulta and (
            not self.conexao_banco.text().strip() or not self.sql_consulta.toPlainText().strip()
        ):
            QMessageBox.warning(
                self, "Consulta", "Informe a conexão local e uma consulta SELECT ou WITH."
            )
            return
        if self.acao_atual.chave in {"url", "consulta"} and not self.saida.text().strip():
            QMessageBox.warning(
                self, "Pasta de saída", "Escolha uma pasta para salvar os relatórios dessa fonte."
            )
            return
        try:
            fontes_para_saida = arquivos or [self.saida.text()]
            pasta_saida = application.resolver_pasta_saida(self.saida.text(), fontes_para_saida)
        except ValueError as erro_saida:
            QMessageBox.warning(self, "Saída", str(erro_saida))
            return

        formatos = [nome for nome, caixa in self.formatos.items() if caixa.isChecked()]
        if not formatos:
            QMessageBox.warning(self, "Formatos", "Escolha ao menos um formato.")
            return

        nome_contrato = self.nome_contrato.text().strip() or None
        if self.acao_atual.chave == "contrato" and nome_contrato:
            caminho_nome = Path(nome_contrato)
            if caminho_nome.name != nome_contrato or caminho_nome.suffix.lower() not in {
                ".yaml",
                ".yml",
            }:
                QMessageBox.warning(
                    self, "Nome do contrato", "Use somente um nome terminado em .yaml ou .yml."
                )
                return

        self.executar.setEnabled(False)
        self.abrir_saida.setEnabled(False)
        self.progresso.setRange(0, 0)
        self.log.clear()
        self._registrar(f"Modo: {self.acao_atual.titulo}")
        origem = "Consulta local" if consulta else f"Arquivos: {len(arquivos)}"
        self._registrar(f"{origem} | Saída: {pasta_saida}")
        self.arquivos_em_execucao = arquivos
        self.worker_thread = QThread(self)
        self.trabalho = Trabalho(
            self.acao_atual,
            arquivos,
            pasta_saida,
            formatos,
            self.nivel.currentText(),
            self.vocabularios.text().strip() or None,
            self.arquivo_auxiliar.text().strip() or None,
            nome_contrato,
            self.conexao_banco.text().strip() or None,
            self.sql_consulta.toPlainText().strip() or None,
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
        fontes_para_saida = self.arquivos_em_execucao or [self.saida.text()]
        self.ultima_saida = application.resolver_pasta_saida(self.saida.text(), fontes_para_saida)
        self.abrir_saida.setEnabled(True)
        self._registrar("Concluído.")
        self._registrar("Arquivos gerados:\n" + "\n".join(gerados))
        if falhas:
            texto_falhas = "\n".join(f"{arquivo}: {erro}" for arquivo, erro in falhas)
            self._registrar("Falhas:\n" + texto_falhas)

    def falhou(self, detalhe: str) -> None:
        self.progresso.setRange(0, 1)
        self.executar.setEnabled(True)
        mensagem = (
            detalhe
            if self.nivel.currentText() == "Técnico"
            else ("A análise falhou. Mude Diagnóstico para Técnico para ver detalhes.")
        )
        self._registrar(mensagem)
        QMessageBox.critical(self, "Erro na análise", mensagem)


def main() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    app.setStyleSheet(_ESTILO)
    janela = JanelaReconQt()
    janela.show()
    app.exec()

"""Janela do Recon: a mesma análise, sem terminal nenhum.

O modo interativo (`interativo.py`) resolveu metade da barreira de adoção —
não precisar decorar comando. A outra metade é o terminal em si: quem nunca
abriu um `cmd` trava antes de começar, e caminho digitado à mão (`C:\\Users\\...`)
erra na primeira tentativa. Esta janela é para essa pessoa: abas para escolher
o que fazer, botão "Procurar" que abre o Explorer, e uma barra que mostra que
algo está acontecendo.

Duas decisões estruturam o módulo:

1. A janela é lançador, não visualizador. Quem analisa é o `DataProfiler`,
   o mesmo da CLI; quem mostra o resultado é o HTML que ele já gera. Regra de
   negócio que aparecer aqui está no lugar errado.
2. A análise roda em outra thread. `processar_arquivo` leva minutos em
   arquivo grande e o Tk é single-thread: chamar direto no clique do botão faz
   o Windows escurecer a janela e escrever "Não Responde" — e o usuário leigo
   conclui que quebrou e mata o processo no meio. O trabalho vai para uma
   thread, que só conversa com a interface por uma fila drenada no `after`.
   Widget nunca é tocado fora da thread da interface.

Roda sem terminal: dois cliques no `Recon.pyw`, na raiz do repositório.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import cast

from . import __version__
from .ingestion import EXTENSOES_DESCOBERTAS as EXTENSOES
from .ingestion import EXTENSOES_SUPORTADAS

# O que a thread de trabalho devolve pela fila quando termina bem:
# pasta de saída, relatórios gerados e os arquivos que falharam.
_Conclusao = tuple[Path, list[Path], list[tuple[str, str]]]

# Paleta única da janela. Fica em um lugar só pelo mesmo motivo que o
# `config.py` existe: cor espalhada pelo código vira, na terceira mudança, uma
# janela com quatro cinzas levemente diferentes.
#
# Os valores são os do GitHub no tema escuro (Primer). Adotar uma escala pronta
# e testada resolve de graça o que é trabalhoso acertar no olho: a distância
# entre os quatro tons de fundo, o cinza de texto secundário que ainda passa em
# contraste (#8b949e sobre #0d1117 dá 6.8:1) e o par borda/superfície que
# separa sem chamar atenção.
#
# Cada ação tem seu acento — roxo, azul e ciano, análogos entre si: trocar de
# seção muda a cor sem brigar com a anterior.
CORES = {
    "fundo": "#0d1117",        # a janela  (canvas.default)
    "superficie": "#161b22",   # item ativo da navegação, caixas  (canvas.subtle)
    "campo": "#010409",        # lista e mensagens, recuados  (canvas.inset)
    "borda": "#30363d",
    "borda_suave": "#21262d",
    "texto": "#e6edf3",
    "texto_suave": "#8b949e",
    "texto_fraco": "#6e7681",
    "roxo": "#bc8cff",         # acento principal
    "roxo_forte": "#8957e5",   # botão de ação
    "roxo_hover": "#a371f7",
    "azul": "#58a6ff",
    "ciano": "#39c5cf",
    "verde": "#3fb950",
    "vermelho": "#f85149",
    "botao": "#21262d",
    "botao_hover": "#30363d",
    "desabilitado": "#484f58",
}

# Preferidas por plataforma, com queda para o que existir. Sem isso, "Segoe UI"
# fora do Windows não cai numa fonte parecida — cai no Helvetica bitmap do X11,
# e a janela inteira parece um programa de 1998.
_FAMILIAS_TEXTO = (
    "Segoe UI", "Inter", "Ubuntu", "Cantarell", "Noto Sans",
    "DejaVu Sans", "Helvetica Neue", "TkDefaultFont",
)
_FAMILIAS_MONO = (
    "Cascadia Mono", "Consolas", "JetBrains Mono", "Ubuntu Mono",
    "DejaVu Sans Mono", "Menlo", "TkFixedFont",
)
_ESCOLHIDAS = {"texto": "TkDefaultFont", "mono": "TkFixedFont"}


def _fonte(tamanho: int = 10, *, negrito: bool = False, mono: bool = False) -> tuple:
    familia = _ESCOLHIDAS["mono" if mono else "texto"]
    return (familia, tamanho, "bold") if negrito else (familia, tamanho)

_TIPOS_DIALOGO = [
    ("Planilhas e dados", " ".join(f"*{e}" for e in EXTENSOES_SUPORTADAS)),
    ("Todos os arquivos", "*.*"),
]

# Prefixo dos arquivos gerados. O nome da tabela vem depois (`recon_vendas.html`),
# então o relatório se identifica sozinho na pasta.
PREFIXO_SAIDA = "recon"

# Formatos oferecidos, cada um com uma explicação de para que serve — quem não
# programa precisa saber a finalidade, não só o nome do formato. Parquet fica
# de fora: quem precisa dele está na linha de comando, e é a única saída que
# não se abre com dois cliques.
FORMATOS: tuple[tuple[str, str, str], ...] = (
    ("html", "HTML", "abre no navegador — é o relatório para ler e mandar"),
    ("json", "JSON", "os dados do perfil, para colar num prompt de IA ou ler por código"),
    ("markdown", "Markdown", "texto puro, para colar em documento ou wiki"),
)
FORMATO_PADRAO = "html"

_AVISO_DEMORA = (
    "Analisando… em arquivo grande isso leva alguns minutos.\n"
    "Se a janela parecer parada, ela está trabalhando — não feche."
)


@dataclass(frozen=True)
class Acao:
    """Uma aba da janela. Os textos são os mesmos do menu do terminal, de
    propósito: quem aprendeu num modo reconhece o outro."""

    chave: str
    aba: str
    resumo: str
    titulo: str
    explicacao: str
    minimo: int
    cor: str
    limpeza: bool = False


ACOES: tuple[Acao, ...] = (
    Acao(
        chave="individual",
        aba="Analisar arquivos",
        resumo="um ou vários, com relatório por arquivo",
        titulo="Analisar arquivos",
        explicacao=(
            "Gera um relatório completo para cada arquivo selecionado: tipos de "
            "coluna, qualidade, dados ausentes, duplicidades e pontos de atenção. "
            "Use para entender uma ou várias planilhas sem misturar os resultados."
        ),
        minimo=1,
        cor=CORES["roxo"],
        limpeza=True,
    ),
    Acao(
        chave="lote",
        aba="Comparar arquivos",
        resumo="priorize diferenças entre várias bases",
        titulo="Comparar arquivos em lote",
        explicacao=(
            "Compara a qualidade dos arquivos em um resumo único e destaca onde há "
            "mais problemas. É útil para priorizar uma pasta inteira de bases, sem "
            "substituir os relatórios individuais de cada arquivo."
        ),
        minimo=2,
        cor=CORES["azul"],
    ),
    Acao(
        chave="modelo",
        aba="Modelar relações",
        resumo="chaves, fatos e dimensões",
        titulo="Entender relações entre tabelas",
        explicacao=(
            "Procura chaves candidatas entre tabelas, identifica possíveis fatos e "
            "dimensões e sugere cruzamentos com código pronto. Use quando arquivos "
            "como vendas, clientes e produtos fazem parte do mesmo assunto."
        ),
        minimo=2,
        cor=CORES["ciano"],
    ),
)

_AJUDA = """COMO USAR, EM TRÊS PASSOS

  1. Escolha na lista à esquerda o que você quer fazer.
  2. Clique em "Procurar…" e escolha o arquivo, ou a pasta inteira.
  3. Clique em "Analisar agora" e espere.

No fim, clique em "Abrir a pasta dos relatórios". O arquivo que termina
em .html é o relatório: dois cliques nele e abre no navegador, em qualquer
computador, sem instalar nada.


A JANELA TRAVOU?

Provavelmente não. Enquanto analisa, o botão fica cinza e a barra fica
correndo — é assim mesmo. Um arquivo de 500 mil linhas pode levar alguns
minutos, e durante esse tempo o Windows às vezes escreve "Não Responde"
na barra de título mesmo com tudo funcionando.

Espere. Não feche a janela, não clique várias vezes no botão. Se o
computador levar mais de dez minutos num arquivo pequeno, aí sim algo
está errado: feche e abra de novo.


ONDE OS RELATÓRIOS SÃO SALVOS

Se você não escolher nada em "Onde salvar", eles vão para a MESMA PASTA
do arquivo que você selecionou. Se preferir outro lugar, clique no
"Procurar…" de baixo e escolha a pasta.

Os nomes começam com "recon_". Rodar de novo em cima do mesmo arquivo
substitui o relatório anterior.


QUAL FORMATO EU ESCOLHO?

HTML, e mais nada, na maioria das vezes. É o relatório de verdade: abre
no navegador com dois cliques, em qualquer computador, sem instalar nada,
e é o que dá para mandar por e-mail para alguém que não é técnico.

JSON é o mesmo conteúdo em dados, sem formatação. Serve para colar num
prompt de IA ou para outro programa ler.

Markdown é texto puro com marcações simples, para colar em documento,
wiki ou chamado.

Pode marcar mais de um: cada formato vira um arquivo separado.


QUAL MODO EU USO?

  Um arquivo só, quero saber tudo sobre ele  →  Um arquivo
  Vários arquivos, quero saber por onde começar  →  Comparar vários
  Vários arquivos que são do mesmo assunto  →  Como se ligam

Na dúvida entre os dois últimos, comece por "Comparar vários".


DEU ERRO. E AGORA?

"Permissão negada" quase sempre quer dizer que a planilha está aberta no
Excel. Feche o Excel e tente de novo.

"Não achei o arquivo" quer dizer que ele foi movido, renomeado ou está
numa pasta de rede que caiu. Selecione de novo pelo "Procurar…".

Qualquer outra mensagem: o texto que aparece na área de mensagens é o
que o suporte precisa ver. Tire um print dela.


O QUE ELE ACEITA

Arquivos .csv, .xlsx, .xls e .xlsb.

Planilha com título em cima, linha em branco antes do cabeçalho ou linha
de TOTAL no rodapé não é problema: o Recon acha o cabeçalho de verdade
sozinho e avisa no relatório o que ele ajustou.

Nada é enviado para a internet. Tudo roda no seu computador.
"""


# ── Regras puras (sem widget: dá para testar sem abrir janela) ──────────────
def arquivos_suportados(pasta: Path) -> list[str]:
    """Os arquivos de uma pasta que o Recon sabe ler, em ordem."""
    return sorted(
        str(p) for p in pasta.iterdir()
        if p.is_file() and str(p).lower().endswith(tuple(EXTENSOES))
    )


def resolver_pasta_saida(escolha: str, arquivos: Sequence[str]) -> Path:
    """Onde gravar os relatórios.

    Sem escolha explícita, grava ao lado do arquivo de entrada. É o padrão que
    menos surpreende: a pessoa vai procurar o resultado onde estava o dado, não
    numa pasta de trabalho que ela nunca escolheu.
    """
    limpa = escolha.strip().strip('"').strip("'")
    if limpa:
        return Path(limpa).expanduser()
    if not arquivos:
        raise ValueError("Nenhum arquivo selecionado.")
    return Path(arquivos[0]).expanduser().resolve().parent


def validar_selecao(acao: Acao, arquivos: Sequence[str]) -> str | None:
    """Mensagem de impedimento, ou None se dá para rodar."""
    if not arquivos:
        return "Escolha primeiro o arquivo, no botão 'Procurar…'."
    if len(arquivos) < acao.minimo:
        return (
            f"'{acao.titulo}' precisa de pelo menos {acao.minimo} arquivos — "
            f"você escolheu {len(arquivos)}.\n\n"
            "Para analisar um arquivo só, escolha 'Um arquivo' na lista à esquerda."
        )
    faltando = [a for a in arquivos if not Path(a).is_file()]
    if faltando:
        return (
            "Este arquivo não está mais lá:\n\n"
            f"{Path(faltando[0]).name}\n\n"
            "Ele foi movido, renomeado, ou a pasta de rede caiu. "
            "Selecione de novo."
        )
    return None


def mensagem_amigavel(erro: BaseException) -> str:
    """Traduz a exceção para algo acionável.

    Traceback numa janela não serve para quem não programa: o que a pessoa
    precisa saber é o que ela pode fazer a respeito.
    """
    if isinstance(erro, PermissionError):
        return (
            "Não consegui abrir o arquivo — ele provavelmente está aberto no Excel.\n\n"
            "Feche a planilha e tente de novo."
        )
    if isinstance(erro, FileNotFoundError):
        return (
            "Não achei o arquivo. Ele foi movido, renomeado, ou está numa pasta "
            "de rede que caiu.\n\nSelecione de novo pelo botão 'Procurar…'."
        )
    if isinstance(erro, MemoryError):
        return (
            "O arquivo é grande demais para a memória deste computador.\n\n"
            "Dá para contornar pela linha de comando, com "
            "`recon perfilar arquivo.csv --limite-amostra 200000`."
        )
    detalhe = str(erro).strip() or erro.__class__.__name__
    return f"Não consegui concluir a análise.\n\n{detalhe}"


def resumir_selecao(arquivos: Sequence[str]) -> str:
    if not arquivos:
        return "Nenhum arquivo escolhido ainda."
    if len(arquivos) == 1:
        return f"1 arquivo: {Path(arquivos[0]).name}"
    return f"{len(arquivos)} arquivos escolhidos"


def executar_analise(
    acao: Acao,
    arquivos: Sequence[str],
    pasta_saida: Path,
    gerar_limpeza: bool = False,
    formatos: Sequence[str] = (FORMATO_PADRAO,),
) -> tuple[list[Path], list[tuple[str, str]]]:
    """Roda a análise e devolve (relatórios gerados, falhas por arquivo).

    Importa o pipeline aqui dentro, e não no topo do módulo, para a janela
    abrir instantânea: `pandas`, `scipy` e `statsmodels` juntos levam alguns
    segundos para carregar, e uma janela que demora a aparecer parece quebrada.
    """
    from .pipeline import DataProfiler

    pasta_saida.mkdir(parents=True, exist_ok=True)
    saida_base = str(pasta_saida / PREFIXO_SAIDA)
    caminhos = [str(a) for a in arquivos]
    escolhidos = list(formatos) or [FORMATO_PADRAO]
    profiler = DataProfiler()
    falhas: list[tuple[str, str]] = []

    if acao.chave == "modelo":
        profiler.modelar_conjunto(caminhos, saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "individual":
        for caminho in caminhos:
            profiler.processar_arquivo(
                caminho, saida_base=saida_base, formatos=escolhidos,
                gerar_limpeza=gerar_limpeza,
            )
    else:
        _, falhas = profiler.processar_lote(
            caminhos, saida_base=saida_base, formatos=escolhidos
        )

    # O que interessa listar é o que a pessoa vai abrir. Sem HTML, o relatório
    # principal é o primeiro arquivo do primeiro formato pedido.
    padroes = [f"{PREFIXO_SAIDA}*.html", f"{PREFIXO_SAIDA}*.md", f"{PREFIXO_SAIDA}*.json"]
    for padrao in padroes:
        gerados = sorted(pasta_saida.glob(padrao))
        if gerados:
            return gerados, falhas
    return [], falhas


def abrir_no_explorador(caminho: Path) -> None:
    """Abre a pasta no gerenciador de arquivos do sistema."""
    abrir_nativo = getattr(os, "startfile", None)  # só existe no Windows
    if abrir_nativo is not None:
        abrir_nativo(str(caminho))
        return
    comando = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([comando, str(caminho)], check=False)


# ── Interface ───────────────────────────────────────────────────────────────
def _ajustar_dpi() -> None:
    """Sem isso, a janela sai borrada em notebook com tela de alta densidade —
    o que basta para a ferramenta parecer amadora antes de rodar qualquer coisa."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — não é Windows, ou é Windows antigo
        pass


def _escolher_fontes(raiz: tk.Tk) -> None:
    """Primeira família instalada de cada lista, e as fontes nomeadas do Tk
    apontadas para ela — assim até widget sem estilo explícito acompanha."""
    from tkinter import font as tkfont

    instaladas = set(tkfont.families(raiz))
    for papel, preferidas in (("texto", _FAMILIAS_TEXTO), ("mono", _FAMILIAS_MONO)):
        _ESCOLHIDAS[papel] = next(
            (f for f in preferidas if f in instaladas), _ESCOLHIDAS[papel]
        )
    for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(nome, raiz).configure(family=_ESCOLHIDAS["texto"], size=10)
    tkfont.nametofont("TkFixedFont", raiz).configure(family=_ESCOLHIDAS["mono"], size=9)


def _aplicar_estilo(raiz: tk.Tk) -> None:
    """Tema escuro.

    Forçar o tema `clam` é decisão consciente: os temas nativos (`vista`,
    `aqua`) ignoram cor de fundo em botão, aba e barra — o resultado seria uma
    janela escura com widgets claros no meio. O `clam` desenha tudo por conta
    própria e aceita a paleta inteira, ao custo de não parecer nativo. Numa
    janela que roda no Windows, no Linux e no macOS, coerência interna vale
    mais do que imitar um dos três.
    """
    _escolher_fontes(raiz)
    raiz.configure(background=CORES["fundo"])
    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")

    estilo.configure(
        ".",
        background=CORES["fundo"], foreground=CORES["texto"],
        fieldbackground=CORES["campo"], bordercolor=CORES["borda"],
        darkcolor=CORES["fundo"], lightcolor=CORES["fundo"],
        troughcolor=CORES["campo"], focuscolor=CORES["fundo"],
        insertcolor=CORES["texto"], font=_fonte(10),
    )
    estilo.configure("TFrame", background=CORES["fundo"])
    estilo.configure("Painel.TFrame", background=CORES["fundo"])
    estilo.configure("TLabel", background=CORES["fundo"], foreground=CORES["texto"])
    estilo.configure("Separador.TFrame", background=CORES["borda_suave"])

    # Cabeçalho e textos de apoio
    estilo.configure("Titulo.TLabel", font=_fonte(16, negrito=True), foreground=CORES["texto"])
    estilo.configure("Sub.TLabel", font=_fonte(9), foreground=CORES["texto_suave"])
    estilo.configure("Secao.TLabel", font=_fonte(9, negrito=True), foreground=CORES["texto_suave"])
    estilo.configure("Dica.TLabel", font=_fonte(9), foreground=CORES["texto_fraco"])
    estilo.configure("Status.TLabel", font=_fonte(9), foreground=CORES["texto_suave"])
    estilo.configure("StatusOk.TLabel", font=_fonte(9, negrito=True), foreground=CORES["verde"])
    estilo.configure(
        "StatusErro.TLabel", font=_fonte(9, negrito=True), foreground=CORES["vermelho"]
    )
    estilo.configure(
        "Explicacao.TLabel", font=_fonte(9), foreground=CORES["texto_suave"],
    )
    estilo.configure("Resumo.TLabel", font=_fonte(9), foreground=CORES["texto_suave"])

    # Cada ação pinta seu próprio título e sua própria régua lateral.
    for acao in ACOES:
        estilo.configure(
            f"{acao.chave}.Titulo.TLabel", font=_fonte(13, negrito=True), foreground=acao.cor
        )
        estilo.configure(f"{acao.chave}.Regua.TFrame", background=acao.cor)

    # Botões. O de ação é sólido e único na janela; os de escolher arquivo são
    # discretos e com contorno, como os secundários do GitHub — três botões com
    # o mesmo peso visual não dizem por onde começar.
    estilo.configure(
        "TButton",
        background=CORES["botao"], foreground=CORES["texto"],
        bordercolor=CORES["borda"], lightcolor=CORES["botao"], darkcolor=CORES["botao"],
        borderwidth=1, focusthickness=0, padding=(12, 7), font=_fonte(9),
    )
    estilo.map(
        "TButton",
        background=[("disabled", CORES["fundo"]), ("pressed", CORES["borda_suave"]),
                    ("active", CORES["botao_hover"])],
        foreground=[("disabled", CORES["desabilitado"])],
        bordercolor=[("disabled", CORES["borda_suave"]), ("active", CORES["texto_fraco"])],
        lightcolor=[("active", CORES["botao_hover"]), ("disabled", CORES["fundo"])],
        darkcolor=[("active", CORES["botao_hover"]), ("disabled", CORES["fundo"])],
    )
    estilo.configure(
        "Analisar.TButton",
        background=CORES["roxo_forte"], foreground="#ffffff",
        bordercolor=CORES["roxo_forte"],
        lightcolor=CORES["roxo_forte"], darkcolor=CORES["roxo_forte"],
        font=_fonte(10, negrito=True), padding=(22, 11),
    )
    estilo.map(
        "Analisar.TButton",
        background=[("disabled", CORES["botao"]), ("active", CORES["roxo_hover"])],
        foreground=[("disabled", CORES["desabilitado"])],
        bordercolor=[("disabled", CORES["borda_suave"]), ("active", CORES["roxo_hover"])],
        lightcolor=[("active", CORES["roxo_hover"]), ("disabled", CORES["botao"])],
        darkcolor=[("active", CORES["roxo_hover"]), ("disabled", CORES["botao"])],
    )

    # Caixas de seção
    estilo.configure(
        "TLabelframe",
        background=CORES["fundo"], bordercolor=CORES["borda"],
        lightcolor=CORES["fundo"], darkcolor=CORES["fundo"], borderwidth=1,
    )
    estilo.configure(
        "TLabelframe.Label",
        background=CORES["fundo"], foreground=CORES["texto_suave"],
        font=_fonte(9, negrito=True),
    )
    estilo.configure(
        "TEntry",
        fieldbackground=CORES["campo"], foreground=CORES["texto"],
        bordercolor=CORES["borda"], lightcolor=CORES["borda"], darkcolor=CORES["borda"],
        insertcolor=CORES["texto"], padding=(8, 7), borderwidth=1,
    )
    estilo.map("TEntry", bordercolor=[("focus", CORES["azul"])])

    estilo.configure(
        "TCheckbutton",
        background=CORES["fundo"], foreground=CORES["texto"],
        indicatorbackground=CORES["campo"], indicatorforeground=CORES["fundo"],
        # O clam desenha a caixinha com uma borda clara própria; nos ~12px do
        # indicador ela domina e a caixa desmarcada aparece branca no tema escuro.
        upperbordercolor=CORES["borda"], lowerbordercolor=CORES["borda"],
        bordercolor=CORES["borda"], focusthickness=0, font=_fonte(9), padding=(0, 3),
    )
    estilo.map(
        "TCheckbutton",
        background=[("active", CORES["fundo"])],
        foreground=[("disabled", CORES["desabilitado"])],
        indicatorbackground=[("selected", CORES["roxo_forte"]),
                             ("active", CORES["borda_suave"])],
        indicatorforeground=[("selected", "#ffffff")],
        upperbordercolor=[("selected", CORES["roxo_forte"]), ("active", CORES["texto_fraco"])],
        lowerbordercolor=[("selected", CORES["roxo_forte"]), ("active", CORES["texto_fraco"])],
    )

    estilo.configure(
        "TProgressbar",
        background=CORES["roxo"], troughcolor=CORES["campo"],
        bordercolor=CORES["borda_suave"], lightcolor=CORES["roxo"], darkcolor=CORES["roxo"],
        thickness=6, borderwidth=0,
    )
    estilo.configure(
        "TScrollbar",
        background=CORES["borda"], troughcolor=CORES["fundo"],
        bordercolor=CORES["fundo"], arrowcolor=CORES["texto_suave"],
        lightcolor=CORES["borda"], darkcolor=CORES["borda"], borderwidth=0, arrowsize=12,
    )
    estilo.map("TScrollbar", background=[("active", CORES["texto_fraco"])])


class PainelAcao(ttk.Frame):
    """Uma aba: explicação, seleção de arquivos e as opções daquele modo."""

    def __init__(self, mestre: tk.Misc, acao: Acao, ao_mudar: Callable[[], None]):
        super().__init__(mestre, padding=(20, 18), style="Painel.TFrame")
        self.acao = acao
        self.ao_mudar = ao_mudar
        self.arquivos: list[str] = []
        self.gerar_limpeza = tk.BooleanVar(value=False)

        cabecalho = ttk.Frame(self, style="Painel.TFrame")
        cabecalho.pack(fill="x")
        ttk.Frame(
            cabecalho, style=f"{acao.chave}.Regua.TFrame", width=4, height=20
        ).pack(side="left", padx=(0, 11))
        ttk.Label(
            cabecalho, text=acao.titulo, style=f"{acao.chave}.Titulo.TLabel"
        ).pack(side="left")

        ttk.Label(
            self, text=acao.explicacao, style="Explicacao.TLabel",
            wraplength=640, justify="left",
        ).pack(anchor="w", pady=(8, 16))

        botoes = ttk.Frame(self, style="Painel.TFrame")
        botoes.pack(anchor="w", fill="x")
        rotulo = "Procurar arquivo…" if acao.minimo == 1 else "Procurar arquivos…"
        ttk.Button(botoes, text=rotulo, command=self._escolher_arquivos).pack(side="left")
        ttk.Button(
            botoes, text="Escolher uma pasta inteira…", command=self._escolher_pasta
        ).pack(side="left", padx=6)
        ttk.Button(botoes, text="Limpar", command=self._limpar).pack(side="left")

        self.resumo = ttk.Label(self, text=resumir_selecao([]), style="Resumo.TLabel")
        self.resumo.pack(anchor="w", pady=(12, 5))

        # `side="bottom"` antes da lista: em janela baixa quem encolhe é a
        # lista de arquivos, não a opção — widget empacotado depois é o que o
        # Tk deixa de fora quando falta espaço.
        if acao.limpeza:
            ttk.Checkbutton(
                self,
                text="Gerar também um script de limpeza em Python (para quem programa)",
                variable=self.gerar_limpeza,
            ).pack(side="bottom", anchor="w", pady=(10, 0))

        # `fill="x"` e não `expand`: esticada, a lista virava um retângulo vazio
        # ocupando metade da janela — espaço morto que empurrava o resto para
        # fora da tela sem mostrar mais nenhum arquivo.
        moldura = ttk.Frame(self, style="Painel.TFrame")
        moldura.pack(fill="x")
        self.lista = tk.Listbox(
            moldura, height=5, activestyle="none", borderwidth=0, relief="flat",
            background=CORES["campo"], foreground=CORES["texto"],
            selectbackground=acao.cor, selectforeground=CORES["fundo"],
            highlightthickness=1, highlightbackground=CORES["borda"],
            highlightcolor=CORES["borda"], font=_fonte(9),
        )
        barra = ttk.Scrollbar(moldura, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

    def _escolher_arquivos(self) -> None:
        if self.acao.minimo == 1:
            escolhido = filedialog.askopenfilename(
                title="Escolha o arquivo", filetypes=_TIPOS_DIALOGO
            )
            escolhidos = [escolhido] if escolhido else []
        else:
            escolhidos = list(filedialog.askopenfilenames(
                title="Escolha os arquivos (segure Ctrl para marcar vários)",
                filetypes=_TIPOS_DIALOGO,
            ))
        if escolhidos:
            self._definir(escolhidos)

    def _escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Escolha a pasta com os arquivos")
        if not pasta:
            return
        encontrados = arquivos_suportados(Path(pasta))
        if not encontrados:
            messagebox.showwarning(
                "Recon",
                "Não achei nenhum CSV nem Excel nesta pasta.\n\n"
                f"O Recon lê: {', '.join(EXTENSOES)}",
            )
            return
        if self.acao.minimo == 1 and len(encontrados) > 1:
            messagebox.showinfo(
                "Recon",
                f"Esta pasta tem {len(encontrados)} arquivos, e esta aba analisa "
                "um por vez.\n\nVou analisar todos, um relatório para cada. Para "
                "compará-los num relatório só, use a aba '2 · Comparar vários'.",
            )
        self._definir(encontrados)

    def _limpar(self) -> None:
        self._definir([])

    def _definir(self, arquivos: list[str]) -> None:
        self.arquivos = arquivos
        self.lista.delete(0, tk.END)
        for caminho in arquivos:
            self.lista.insert(tk.END, f"  {Path(caminho).name}")
        self.resumo.configure(text=resumir_selecao(arquivos))
        self.ao_mudar()


class PainelAjuda(ttk.Frame):
    def __init__(self, mestre: tk.Misc):
        super().__init__(mestre, padding=(20, 18), style="Painel.TFrame")
        # A altura importa além da estética: o Notebook adota a altura do maior
        # painel, e um `tk.Text` sem `height` pede as 24 linhas do padrão. Era a
        # ajuda, sozinha, que esticava a janela inteira em 200px e abria um vão
        # vazio nas outras abas.
        texto = tk.Text(
            self, height=15, wrap="word", borderwidth=0, highlightthickness=0,
            background=CORES["fundo"], foreground=CORES["texto_suave"],
            selectbackground=CORES["borda"], selectforeground=CORES["texto"],
            font=_fonte(9), padx=6, pady=2, spacing1=1, spacing3=2, cursor="arrow",
        )
        barra = ttk.Scrollbar(self, orient="vertical", command=texto.yview)
        texto.configure(yscrollcommand=barra.set)
        texto.insert("1.0", _AJUDA)

        # As seções em caixa alta viram títulos roxos: quem abre a ajuda está
        # procurando uma resposta específica, não lendo do começo.
        texto.tag_configure(
            "secao", foreground=CORES["roxo"], font=_fonte(9, negrito=True), spacing1=8
        )
        for numero, linha in enumerate(_AJUDA.splitlines(), start=1):
            if linha.strip() and linha == linha.upper() and any(c.isalpha() for c in linha):
                texto.tag_add("secao", f"{numero}.0", f"{numero}.end")

        texto.configure(state="disabled")
        texto.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")


class ItemNavegacao(tk.Frame):
    """Uma linha da navegação lateral: rótulo, uma linha de apoio e a régua
    colorida da ação quando está selecionado.

    É `tk.Frame` e não `ttk`: estado de hover em ttk exige criar um estilo por
    item e mapear estados, enquanto aqui é atribuir `background`. O clique é
    ligado no quadro e em cada filho porque o rótulo por cima do quadro
    engole o evento — clicar no texto não faria nada.
    """

    def __init__(self, mestre: tk.Misc, rotulo: str, apoio: str, cor: str,
                 ao_clicar: Callable[[], None]):
        super().__init__(mestre, background=CORES["fundo"], cursor="hand2")
        self.cor = cor
        self.selecionado = False

        self.regua = tk.Frame(self, background=CORES["fundo"], width=3)
        self.regua.pack(side="left", fill="y")
        interno = tk.Frame(self, background=CORES["fundo"], padx=13, pady=9)
        interno.pack(side="left", fill="both", expand=True)
        self.rotulo = tk.Label(
            interno, text=rotulo, background=CORES["fundo"], foreground=CORES["texto"],
            font=_fonte(10, negrito=True), anchor="w",
        )
        self.rotulo.pack(fill="x")
        self.apoio = tk.Label(
            interno, text=apoio, background=CORES["fundo"], foreground=CORES["texto_fraco"],
            font=_fonte(8), anchor="w", wraplength=150, justify="left",
        )
        self.apoio.pack(fill="x")

        self._pintaveis = (self, interno, self.rotulo, self.apoio)
        for widget in (self, self.regua, interno, self.rotulo, self.apoio):
            widget.bind("<Button-1>", lambda _e: ao_clicar())
            widget.bind("<Enter>", lambda _e: self._sobre(True))
            widget.bind("<Leave>", lambda _e: self._sobre(False))

    def _pintar(self, fundo: str) -> None:
        for widget in self._pintaveis:
            widget.configure(background=fundo)

    def _sobre(self, dentro: bool) -> None:
        if not self.selecionado:
            self._pintar(CORES["superficie"] if dentro else CORES["fundo"])

    def marcar(self, selecionado: bool) -> None:
        self.selecionado = selecionado
        self._pintar(CORES["superficie"] if selecionado else CORES["fundo"])
        self.regua.configure(background=self.cor if selecionado else CORES["fundo"])
        self.rotulo.configure(foreground=self.cor if selecionado else CORES["texto"])


class JanelaRecon:
    def __init__(self) -> None:
        _ajustar_dpi()
        self.raiz = tk.Tk()
        self.raiz.title(f"Recon {__version__}")
        self.raiz.minsize(700, 620)
        _aplicar_estilo(self.raiz)

        self.fila: queue.Queue[tuple[str, object]] = queue.Queue()
        self.rodando = False
        self.ultima_saida: Path | None = None
        self._pasta_atual: str = ""   # some dos caminhos no log; ver `_escrever`
        self.saida_escolhida = tk.StringVar()
        self.paineis: list[PainelAcao] = []
        self.itens: list[ItemNavegacao] = []
        self.indice_ativo = 0
        self.formatos = {
            chave: tk.BooleanVar(value=chave == FORMATO_PADRAO) for chave, _, _ in FORMATOS
        }

        self._montar()
        self._dimensionar()
        self.raiz.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self._atualizar_botao()

    def _dimensionar(self) -> None:
        """Cabe na tela e nasce no meio dela.

        O tamanho natural da janela passa de 900px de altura; num notebook de
        768px o botão "Analisar agora" ficaria embaixo da barra de tarefas, sem
        jeito de chegar nele. Aqui ela é limitada à tela — e, com a ordem de
        empacotamento do `_montar`, quem cede espaço é a lista de arquivos.
        """
        self.raiz.update_idletasks()
        tela_largura = self.raiz.winfo_screenwidth()
        tela_altura = self.raiz.winfo_screenheight()
        largura = min(max(self.raiz.winfo_reqwidth(), 780), tela_largura - 60)
        altura = min(self.raiz.winfo_reqheight(), tela_altura - 90)
        x = max((tela_largura - largura) // 2, 0)
        y = max((tela_altura - altura) // 3, 0)
        self.raiz.geometry(f"{largura}x{altura}+{x}+{y}")

    # ── montagem ────────────────────────────────────────────────────────
    def _montar(self) -> None:
        topo = ttk.Frame(self.raiz, padding=(20, 16, 20, 12))
        topo.pack(fill="x")
        titulo = ttk.Frame(topo)
        titulo.pack(anchor="w")
        ttk.Label(titulo, text="Recon", style="Titulo.TLabel").pack(side="left")
        ttk.Label(
            titulo, text=__version__, style="Sub.TLabel"
        ).pack(side="left", anchor="s", pady=(0, 4), padx=(8, 0))
        ttk.Label(
            topo,
            text="Descubra o que tem nos seus arquivos antes de começar a analisar.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Frame(self.raiz, style="Separador.TFrame", height=1).pack(fill="x", padx=20)

        # Daqui para baixo, tudo é empacotado com `side="bottom"`, de baixo para
        # cima, e só o Notebook fica com `expand`. A ordem importa: o Tk atende
        # os widgets na ordem em que foram empacotados e corta o que sobra, e
        # numa tela de 768px o Notebook sozinho pede altura demais — empacotado
        # antes, ele empurrava o botão "Analisar agora" para fora da janela,
        # deixando a ferramenta sem como ser acionada.
        moldura = ttk.LabelFrame(self.raiz, text=" Mensagens ", padding=8)
        moldura.pack(side="bottom", fill="x", padx=20, pady=(12, 18))
        self.log = tk.Text(
            moldura, height=5, wrap="word", state="disabled", borderwidth=0,
            highlightthickness=0, font=_fonte(9, mono=True),
            background=CORES["campo"], foreground=CORES["texto_suave"],
            selectbackground=CORES["borda"], selectforeground=CORES["texto"],
            padx=6, pady=4,
        )
        self.log.tag_configure("ok", foreground=CORES["verde"])
        self.log.tag_configure("erro", foreground=CORES["vermelho"])
        self.log.tag_configure("destaque", foreground=CORES["roxo"])
        self.log.tag_configure("dica", foreground=CORES["desabilitado"])
        barra_log = ttk.Scrollbar(moldura, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=barra_log.set)
        self.log.pack(side="left", fill="both", expand=True)
        barra_log.pack(side="right", fill="y")
        # Caixa vazia não diz para que serve; a dica some no primeiro log.
        self._escrever("O andamento da análise aparece aqui.", "dica")

        self.status = ttk.Label(
            self.raiz, text="Escolha um arquivo para começar.",
            style="Status.TLabel", justify="left",
        )
        self.status.pack(side="bottom", anchor="w", padx=20, pady=(0, 2))

        # Em modo indeterminado a barra desenha o bloco na origem mesmo parada,
        # e um toco roxo imóvel lê como defeito. Parada, ela é um trilho vazio.
        self.barra = ttk.Progressbar(self.raiz, mode="determinate", value=0)
        self.barra.pack(side="bottom", fill="x", padx=20, pady=(14, 6))

        acoes = ttk.Frame(self.raiz, padding=(20, 16, 20, 0))
        acoes.pack(side="bottom", fill="x")
        self.botao = ttk.Button(
            acoes, text="Analisar agora", style="Analisar.TButton", command=self._analisar
        )
        self.botao.pack(side="left")
        self.botao_pasta = ttk.Button(
            acoes, text="Abrir a pasta dos relatórios",
            command=self._abrir_saida, state="disabled",
        )
        self.botao_pasta.pack(side="left", padx=10)

        saida = ttk.LabelFrame(self.raiz, text=" Saída ", padding=12)
        saida.pack(side="bottom", fill="x", padx=20, pady=(16, 0))

        ttk.Label(saida, text="Onde salvar", style="Secao.TLabel").pack(anchor="w")
        linha = ttk.Frame(saida)
        linha.pack(fill="x", pady=(5, 0))
        ttk.Entry(linha, textvariable=self.saida_escolhida).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(linha, text="Procurar…", command=self._escolher_saida).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(
            saida,
            text="Deixe em branco para salvar na mesma pasta do arquivo escolhido.",
            style="Dica.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        ttk.Frame(saida, style="Separador.TFrame", height=1).pack(fill="x", pady=12)
        ttk.Label(saida, text="Formato do relatório", style="Secao.TLabel").pack(anchor="w")
        for chave, rotulo, explicacao in FORMATOS:
            linha_formato = ttk.Frame(saida)
            linha_formato.pack(fill="x", pady=(5, 0))
            ttk.Checkbutton(
                linha_formato, text=rotulo, variable=self.formatos[chave],
                command=self._atualizar_botao,
            ).pack(side="left")
            ttk.Label(linha_formato, text=f"— {explicacao}", style="Dica.TLabel").pack(
                side="left", padx=(8, 0)
            )

        # Navegação à esquerda, conteúdo à direita. Abas no topo cabiam três
        # rótulos curtos e nada mais; na lateral, cada modo carrega uma linha
        # dizendo para que serve — que é exatamente a dúvida de quem abre a
        # ferramenta pela primeira vez e não sabe qual escolher.
        corpo = ttk.Frame(self.raiz)
        corpo.pack(fill="both", expand=True, padx=20, pady=(14, 0))

        navegacao = tk.Frame(corpo, background=CORES["fundo"], width=186)
        navegacao.pack(side="left", fill="y")
        navegacao.pack_propagate(False)
        ttk.Frame(corpo, style="Separador.TFrame", width=1).pack(side="left", fill="y", padx=(0, 0))

        conteudo = ttk.Frame(corpo, padding=(4, 0, 0, 0))
        conteudo.pack(side="left", fill="both", expand=True)

        for indice, acao in enumerate(ACOES):
            item = ItemNavegacao(
                navegacao, acao.aba, acao.resumo, acao.cor,
                partial(self.selecionar, indice),
            )
            item.pack(fill="x")
            self.itens.append(item)
            self.paineis.append(PainelAcao(conteudo, acao, self._atualizar_botao))

        tk.Frame(navegacao, background=CORES["borda_suave"], height=1).pack(
            fill="x", pady=10, padx=(3, 0)
        )
        ajuda = ItemNavegacao(
            navegacao, "Ajuda", "dúvidas frequentes", CORES["texto_suave"],
            lambda: self.selecionar(len(ACOES)),
        )
        ajuda.pack(fill="x")
        self.itens.append(ajuda)
        self.painel_ajuda = PainelAjuda(conteudo)

        self.selecionar(0)

    # ── estado ──────────────────────────────────────────────────────────
    def selecionar(self, indice: int) -> None:
        """Troca a seção visível. Os painéis são todos criados no início e
        empacotados sob demanda: recriar a cada troca perderia a seleção de
        arquivos que a pessoa já tinha feito na outra seção."""
        self.indice_ativo = indice
        for i, item in enumerate(self.itens):
            item.marcar(i == indice)
        for painel in (*self.paineis, self.painel_ajuda):
            painel.pack_forget()
        alvo = self.paineis[indice] if indice < len(self.paineis) else self.painel_ajuda
        alvo.pack(fill="both", expand=True)
        self._atualizar_botao()

    def _painel_ativo(self) -> PainelAcao | None:
        indice = self.indice_ativo
        return self.paineis[indice] if indice < len(self.paineis) else None

    def _atualizar_botao(self) -> None:
        if self.rodando:
            return
        painel = self._painel_ativo()
        if painel is None:  # aba de ajuda
            self.botao.configure(state="disabled")
            self._dizer("Escolha um dos três modos, à esquerda, para analisar.")
            return
        self.botao.configure(state="normal" if painel.arquivos else "disabled")
        self._dizer(
            f"Pronto para analisar: {resumir_selecao(painel.arquivos)}"
            if painel.arquivos
            else "Escolha um arquivo no botão 'Procurar…' para liberar o botão."
        )

    def formatos_escolhidos(self) -> list[str]:
        """Na ordem de `FORMATOS`, para o HTML ser sempre o relatório principal
        quando estiver marcado."""
        return [chave for chave, _, _ in FORMATOS if self.formatos[chave].get()]

    def _escolher_saida(self) -> None:
        pasta = filedialog.askdirectory(title="Escolha onde salvar os relatórios")
        if pasta:
            self.saida_escolhida.set(pasta)

    def _abrir_saida(self) -> None:
        if self.ultima_saida is not None:
            abrir_no_explorador(self.ultima_saida)

    def _escrever(self, texto: str, marca: str = "") -> None:
        """Uma linha na área de mensagens. Sem marca explícita, a linha se
        classifica sozinha: o pipeline já prefixa com ✓ o que deu certo, e a
        cor poupa quem não vai ler doze linhas de log para achar a falha."""
        if self._pasta_atual:
            texto = texto.replace(f"{self._pasta_atual}{os.sep}", "")
        if not marca:
            baixo = texto.lower()
            if "✓" in texto:
                marca = "ok"
            elif "falhou" in baixo or "erro" in baixo or "não consegui" in baixo:
                marca = "erro"
        self.log.configure(state="normal")
        self.log.insert(tk.END, texto + "\n", marca or ())
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def _dizer(self, texto: str, tom: str = "") -> None:
        """Mensagem da linha de status, com a cor do desfecho."""
        self.status.configure(text=texto, style=f"{tom}Status.TLabel" if tom else "Status.TLabel")

    # ── execução ────────────────────────────────────────────────────────
    def _analisar(self) -> None:
        painel = self._painel_ativo()
        if painel is None or self.rodando:
            return
        impedimento = validar_selecao(painel.acao, painel.arquivos)
        if impedimento:
            messagebox.showwarning("Recon", impedimento)
            return
        formatos = self.formatos_escolhidos()
        if not formatos:
            messagebox.showwarning(
                "Recon",
                "Marque pelo menos um formato de relatório, em 'Formato do "
                "relatório'.\n\nO HTML é o que abre no navegador com dois cliques — "
                "na dúvida, deixe só ele.",
            )
            return
        try:
            pasta_saida = resolver_pasta_saida(self.saida_escolhida.get(), painel.arquivos)
        except (ValueError, OSError) as erro:
            messagebox.showerror("Recon", mensagem_amigavel(erro))
            return

        self.rodando = True
        self.botao.configure(state="disabled")
        self.botao_pasta.configure(state="disabled")
        self.barra.configure(mode="indeterminate")
        self.barra.start(12)
        self._dizer(_AVISO_DEMORA)
        self.log.configure(state="normal")
        self.log.delete("1.0", tk.END)
        self.log.configure(state="disabled")
        self._escrever(f"Salvando os relatórios em: {pasta_saida}", "destaque")
        self._pasta_atual = str(pasta_saida)

        _log_para_fila(self.fila)
        threading.Thread(
            target=self._trabalhar,
            args=(painel.acao, list(painel.arquivos), pasta_saida,
                  painel.gerar_limpeza.get(), formatos),
            daemon=True,
        ).start()
        self.raiz.after(120, self._drenar)

    def _trabalhar(
        self, acao: Acao, arquivos: list[str], pasta_saida: Path, limpeza: bool,
        formatos: list[str],
    ) -> None:
        """Roda na thread de trabalho. Nada aqui pode tocar num widget: o
        resultado sai pela fila e a interface o desenha no `_drenar`."""
        try:
            gerados, falhas = executar_analise(
                acao, arquivos, pasta_saida, limpeza, formatos
            )
            self.fila.put(("fim", (pasta_saida, gerados, falhas)))
        except BaseException as erro:  # noqa: BLE001 — vira caixa de diálogo, não traceback
            self.fila.put(("erro", mensagem_amigavel(erro)))

    def _drenar(self) -> None:
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "log":
                    self._escrever(str(dado))
                elif tipo == "fim":
                    self._concluir(*cast("_Conclusao", dado))
                elif tipo == "erro":
                    self._falhar(str(dado))
        except queue.Empty:
            pass
        if self.rodando:
            self.raiz.after(120, self._drenar)

    def _destravar(self) -> None:
        self.rodando = False
        self.barra.stop()
        self.barra.configure(mode="determinate", value=0)
        self.botao.configure(state="normal")

    def _concluir(
        self, pasta: Path, gerados: Sequence[Path], falhas: Sequence[tuple[str, str]]
    ) -> None:
        self._destravar()
        self.ultima_saida = pasta
        self.botao_pasta.configure(state="normal")

        for caminho, erro in falhas:
            self._escrever(f"Falhou: {Path(caminho).name} — {erro}")
        self._escrever("")
        self._escrever(f"Pronto. {len(gerados)} relatório(s) gerado(s).", "ok")

        principal = next((g for g in gerados if g.name.endswith("_consolidado.html")), None)
        principal = principal or next(
            (g for g in gerados if g.name.endswith("_modelo.html")), None
        )
        principal = principal or (gerados[0] if gerados else None)

        if principal:
            self._dizer(
                "Pronto! Clique em 'Abrir a pasta dos relatórios' e dê dois cliques "
                f"no arquivo {principal.name}.", tom="Ok",
            )
        else:
            self._dizer(
                "Terminou, mas nenhum relatório foi gerado. Veja as mensagens abaixo.",
                tom="Erro",
            )
        if falhas:
            messagebox.showwarning(
                "Recon",
                f"Terminei, mas {len(falhas)} arquivo(s) não puderam ser lidos.\n\n"
                "A área de mensagens, embaixo, diz qual e por quê.",
            )
        self._atualizar_botao_pos_execucao()

    def _falhar(self, mensagem: str) -> None:
        self._destravar()
        self._escrever(mensagem.replace("\n\n", " "), "erro")
        self._dizer("Não deu certo. Veja a mensagem e tente de novo.", tom="Erro")
        messagebox.showerror("Recon", mensagem)
        self._atualizar_botao_pos_execucao()

    def _atualizar_botao_pos_execucao(self) -> None:
        painel = self._painel_ativo()
        self.botao.configure(
            state="normal" if painel is not None and painel.arquivos else "disabled"
        )

    def _ao_fechar(self) -> None:
        if self.rodando and not messagebox.askokcancel(
            "Recon",
            "A análise ainda está rodando.\n\n"
            "Se fechar agora, ela para no meio e o relatório não fica pronto. "
            "Fechar mesmo assim?",
        ):
            return
        self.raiz.destroy()

    def rodar(self) -> None:
        self.raiz.mainloop()


def _log_para_fila(fila: queue.Queue[tuple[str, object]]) -> None:
    """Manda o log do pipeline para a área de mensagens da janela.

    Precisa acontecer de qualquer jeito: sob `pythonw.exe` (o `Recon.pyw`) não
    existe console, `sys.stderr` é None, e o sink padrão do loguru escreveria
    num lugar que não existe.
    """
    from loguru import logger

    logger.remove()
    logger.add(
        lambda msg: fila.put(("log", str(msg).rstrip())),
        format="{time:HH:mm:ss} · {message}",
        level="INFO",
        colorize=False,
    )


def _silenciar_saida_ausente() -> None:
    """Sem console, `print()` e o `tqdm` estouram em AttributeError porque
    `sys.stdout`/`sys.stderr` são None. Um destino nulo resolve."""
    for nome in ("stdout", "stderr"):
        if getattr(sys, nome, None) is None:
            setattr(sys, nome, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def main() -> None:
    """Abre a interface Qt moderna; Tkinter continua como fallback interno."""
    try:
        from .gui_qt import main as main_qt
        main_qt()
        return
    except ImportError:
        pass
    """Abre a janela. É o que o `Recon.pyw` e o comando `recon app` chamam."""
    _silenciar_saida_ausente()
    try:
        janela = JanelaRecon()
    except tk.TclError as erro:
        print(
            "Não consegui abrir a janela do Recon: "
            f"{erro}\n\nUse o modo terminal: digite `recon` e siga as perguntas.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    janela.rodar()


if __name__ == "__main__":
    main()

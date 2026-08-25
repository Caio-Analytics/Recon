"""Modo interativo: menu no terminal, sem decorar comando nenhum.

Existe por um motivo prático: a maior barreira de adoção não é a ferramenta
ser difícil, é a pessoa não lembrar a sintaxe. Quem usa uma vez por mês não
vai guardar `--formatos`, `--limite-amostra` e `--saida-base`.

Digitar `recon` sozinho abre este menu. Todas as perguntas têm resposta
padrão entre colchetes: dar Enter em tudo faz a coisa certa no caso comum.
"""
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .ingestion import EXTENSOES_DESCOBERTAS

console = Console()

_EXTENSOES = frozenset(EXTENSOES_DESCOBERTAS)
_MAX_LISTADOS = 12


def _achar_arquivos(pasta: Path) -> list[Path]:
    return sorted(
        p for p in pasta.iterdir()
        if p.is_file() and str(p).lower().endswith(tuple(_EXTENSOES))
    )


def _tabela_de_arquivos(arquivos: list[Path]) -> Table:
    tabela = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    tabela.add_column("#", justify="right", style="dim", width=3)
    tabela.add_column("Arquivo")
    tabela.add_column("Tamanho", justify="right")
    for i, arquivo in enumerate(arquivos[:_MAX_LISTADOS], start=1):
        tabela.add_row(str(i), arquivo.name, f"{arquivo.stat().st_size / 1e6:.1f} MB")
    if len(arquivos) > _MAX_LISTADOS:
        tabela.add_row("", f"... e mais {len(arquivos) - _MAX_LISTADOS}", "")
    return tabela


def _perguntar_pasta() -> Path:
    while True:
        resposta = typer.prompt(
            "\nOnde estão os arquivos? (Enter = pasta atual)",
            default=".", show_default=False,
        ).strip().strip('"').strip("'")
        pasta = Path(resposta).expanduser()
        if pasta.is_file():
            return pasta
        if pasta.is_dir():
            if _achar_arquivos(pasta):
                return pasta
            console.print(
                f"[yellow]Não achei CSV nem Excel em '{pasta}'. "
                "Tente outro caminho.[/yellow]"
            )
        else:
            console.print(f"[red]'{resposta}' não existe.[/red]")


def _perguntar_acao(quantidade: int) -> str:
    if quantidade == 1:
        return "individual"

    console.print("\n[bold]O que você quer fazer?[/bold]")
    console.print(
        "  [cyan]1[/cyan]  Comparar os arquivos  "
        "[dim]— um relatório só, do pior para o melhor (recomendado)[/dim]\n"
        "  [cyan]2[/cyan]  Descobrir como se ligam  "
        "[dim]— chaves entre as tabelas, fato × dimensão, análises prontas[/dim]\n"
        "  [cyan]3[/cyan]  Analisar um por um  "
        "[dim]— relatório completo e separado de cada arquivo[/dim]"
    )
    escolha = typer.prompt("Escolha", default="1").strip()
    return {"1": "lote", "2": "modelo", "3": "individual"}.get(escolha, "lote")


def executar() -> None:
    """Roda o fluxo interativo do começo ao fim."""
    console.print(Panel.fit(
        f"[bold]Recon[/bold] [dim]{__version__}[/dim]\n"
        "Descubra o que tem nos seus arquivos antes de começar a analisar.",
        border_style="cyan",
    ))

    alvo = _perguntar_pasta()
    if alvo.is_file():
        arquivos = [alvo]
        pasta_base = alvo.parent
    else:
        arquivos = _achar_arquivos(alvo)
        pasta_base = alvo

    console.print(f"\n[green]Encontrei {len(arquivos)} arquivo(s):[/green]")
    console.print(_tabela_de_arquivos(arquivos))

    acao = _perguntar_acao(len(arquivos))

    padrao_saida = str(pasta_base / "relatorios")
    saida = typer.prompt(
        f"\nOnde salvar os relatórios? (Enter = {padrao_saida})",
        default=padrao_saida, show_default=False,
    ).strip().strip('"').strip("'")
    pasta_saida = Path(saida).expanduser()
    pasta_saida.mkdir(parents=True, exist_ok=True)

    limpeza = False
    if acao == "individual":
        limpeza = typer.confirm(
            "Gerar também um script de limpeza em Python?", default=False
        )

    # Importado aqui para o menu abrir instantâneo: o pipeline puxa pandas,
    # scipy e statsmodels, o que leva alguns segundos.
    from .cli import setup_logging
    from .pipeline import DataProfiler

    setup_logging()
    console.print("\n[dim]Analisando... isso pode levar alguns minutos em arquivo grande.[/dim]\n")

    profiler = DataProfiler()
    saida_base = str(pasta_saida / (pasta_base.resolve().name or "recon"))
    caminhos = [str(a) for a in arquivos]

    try:
        if acao == "modelo":
            profiler.modelar_conjunto(caminhos, saida_base=saida_base)
        elif acao == "individual":
            for caminho in caminhos:
                profiler.processar_arquivo(
                    caminho, saida_base=saida_base, gerar_limpeza=limpeza
                )
        else:
            _, falhas = profiler.processar_lote(caminhos, saida_base=saida_base)
            for caminho, erro in falhas:
                console.print(f"[red]Falhou:[/red] {caminho} — {erro}")
    except Exception as e:
        console.print(f"\n[red]Não consegui concluir:[/red] {e}")
        raise typer.Exit(code=1) from None

    gerados = sorted(pasta_saida.glob("*.html"))
    console.print(Panel.fit(
        "[bold green]Pronto.[/bold green]\n\n"
        f"Relatórios em: [cyan]{pasta_saida.resolve()}[/cyan]\n"
        + (f"Abra este: [bold]{gerados[0].name}[/bold]" if gerados else "")
        + "\n\n[dim]Clique duas vezes no arquivo .html — abre no navegador.[/dim]",
        border_style="green",
    ))

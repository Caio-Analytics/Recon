"""CLI do data-profiler: `perfilar` (um arquivo) e `lote` (vários arquivos)."""
import sys
from typing import List, Optional

import typer
from loguru import logger

from .ingestion import FileFormatError
from .pipeline import DataProfiler

app = typer.Typer(help="Profiler exploratório de dados CSV/XLSX/XLS/XLSB.")


def setup_logging(log_file: Optional[str] = None) -> None:
    logger.remove()
    logger.add(lambda msg: print(msg, end="", flush=True), format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}", level="INFO", colorize=True)
    if log_file:
        logger.add(log_file, format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}", level="DEBUG", rotation="10 MB", encoding="utf-8")


@app.command()
def perfilar(
    caminho: str,
    todas_abas: bool = typer.Option(False, "--todas-abas"),
    aba: str = typer.Option("0", "--aba"),
    saida_base: str = typer.Option("profiler_output", "--saida-base"),
    tambem_parquet: bool = typer.Option(False, "--tambem-parquet"),
) -> None:
    setup_logging()
    aba_valor = int(aba) if aba.isdigit() else aba
    profiler = DataProfiler()
    try:
        profiler.processar_arquivo(
            caminho, aba_excel=aba_valor, processar_todas_abas=todas_abas,
            saida_base=saida_base, tambem_parquet=tambem_parquet,
        )
    except (FileNotFoundError, FileFormatError, ValueError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def lote(
    caminhos: List[str],
    saida_base: str = typer.Option("profiler_output", "--saida-base"),
    tambem_parquet: bool = typer.Option(False, "--tambem-parquet"),
) -> None:
    setup_logging()
    profiler = DataProfiler()
    falhas = 0
    for caminho in caminhos:
        try:
            profiler.processar_arquivo(caminho, saida_base=saida_base, tambem_parquet=tambem_parquet)
        except (FileNotFoundError, FileFormatError, ValueError) as e:
            falhas += 1
            typer.secho(f"Erro ao processar '{caminho}': {e}", fg=typer.colors.RED, err=True)
    if falhas == len(caminhos) and caminhos:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

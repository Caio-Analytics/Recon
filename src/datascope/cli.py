"""CLI do DataScope: `perfilar` (um arquivo) e `lote` (vários arquivos)."""
import os

import typer
from loguru import logger

from . import __version__
from .ingestion import IngestionError, listar_abas
from .pipeline import FORMATOS_VALIDOS, DataProfiler
from .quality import carregar_regras_kpi

app = typer.Typer(help="DataScope — profiler exploratório de dados CSV/XLSX/XLS/XLSB.")

_EXTENSOES_EXCEL = (".xlsx", ".xls", ".xlsb")

_OPCAO_SAIDA = typer.Option("profiler_output", "--saida-base", help="Prefixo dos arquivos gerados.")
_OPCAO_FORMATOS = typer.Option(
    "json,markdown", "--formatos",
    help=f"Formatos de saída separados por vírgula ({', '.join(FORMATOS_VALIDOS)}).",
)
_OPCAO_PARQUET = typer.Option(False, "--tambem-parquet", help="Atalho para incluir 'parquet'.")
_OPCAO_JSON_COMPACTO = typer.Option(
    False, "--json-compacto", help="JSON sem indentação (menor, melhor para colar em prompt de IA)."
)
_OPCAO_LIMITE = typer.Option(
    500_000, "--limite-amostra", min=1,
    help="Máximo de linhas analisadas. Acima disso o profiler usa amostra aleatória.",
)
_OPCAO_GERAR_LIMPEZA = typer.Option(
    False, "--gerar-limpeza",
    help="Gera um script pandas que aplica as recomendações do perfil.",
)
_OPCAO_SEM_LAYOUT = typer.Option(
    False, "--sem-deteccao-layout",
    help="Lê o arquivo cru: cabeçalho na primeira linha, sem remover total nem coluna vazia.",
)
_OPCAO_LINHA_CABECALHO = typer.Option(
    None, "--linha-cabecalho", min=0,
    help="Força a linha do cabeçalho (0 = primeira), em vez de detectar.",
)
_OPCAO_KPIS = typer.Option(
    None, "--kpis", help="YAML com regras de gap analysis próprias (padrão: regras de RH)."
)


def setup_logging(log_file: str | None = None) -> None:
    logger.remove()
    logger.add(
        lambda msg: print(msg, end="", flush=True),
        format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}", level="INFO", colorize=True,
    )
    if log_file:
        logger.add(
            log_file, format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}",
            level="DEBUG", rotation="10 MB", encoding="utf-8",
        )


def _parsear_formatos(formatos: str) -> list[str]:
    escolhidos = [f.strip().lower() for f in formatos.split(",") if f.strip()]
    invalidos = set(escolhidos) - set(FORMATOS_VALIDOS)
    if invalidos:
        raise typer.BadParameter(
            f"Formato(s) inválido(s): {', '.join(sorted(invalidos))}. "
            f"Use: {', '.join(FORMATOS_VALIDOS)}."
        )
    if not escolhidos:
        raise typer.BadParameter("Informe ao menos um formato de saída.")
    return escolhidos


def _construir_profiler(limite_amostra: int, kpis: str | None) -> DataProfiler:
    return DataProfiler(limite_amostra=limite_amostra, regras_kpi=carregar_regras_kpi(kpis))


@app.command()
def perfilar(
    caminho: str,
    todas_abas: bool = typer.Option(False, "--todas-abas"),
    aba: str = typer.Option("0", "--aba"),
    saida_base: str = _OPCAO_SAIDA,
    formatos: str = _OPCAO_FORMATOS,
    tambem_parquet: bool = _OPCAO_PARQUET,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    sem_deteccao_layout: bool = _OPCAO_SEM_LAYOUT,
    linha_cabecalho: int | None = _OPCAO_LINHA_CABECALHO,
    gerar_limpeza: bool = _OPCAO_GERAR_LIMPEZA,
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)

    # `--aba` só tem efeito em Excel; avisar é melhor do que ignorar calado.
    extensao = os.path.splitext(caminho)[1].lower()
    if extensao not in _EXTENSOES_EXCEL and (todas_abas or aba != "0"):
        logger.warning(f"'{extensao or 'sem extensão'}' não tem abas — --aba/--todas-abas ignorados.")

    # Perfilar em silêncio só a primeira aba de um arquivo com cinco é a forma
    # mais fácil de alguém concluir coisa errada sobre os dados.
    if extensao in _EXTENSOES_EXCEL and not todas_abas:
        abas = listar_abas(caminho)
        if len(abas) > 1 and aba == "0":
            logger.warning(
                f"'{os.path.basename(caminho)}' tem {len(abas)} abas e só "
                f"'{abas[0]}' será analisada. Use --todas-abas para perfilar todas, "
                "ou `datascope modelar` para analisá-las juntas e descobrir como se ligam."
            )

    aba_valor: str | int = int(aba) if aba.lstrip("-").isdigit() else aba
    try:
        profiler = _construir_profiler(limite_amostra, kpis)
        profiler.processar_arquivo(
            caminho, aba_excel=aba_valor, processar_todas_abas=todas_abas,
            saida_base=saida_base, tambem_parquet=tambem_parquet,
            formatos=escolhidos, json_compacto=json_compacto,
            detectar_layout=not sem_deteccao_layout, linha_cabecalho=linha_cabecalho,
            gerar_limpeza=gerar_limpeza,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command()
def lote(
    caminhos: list[str],
    saida_base: str = _OPCAO_SAIDA,
    formatos: str = _OPCAO_FORMATOS,
    tambem_parquet: bool = _OPCAO_PARQUET,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis)
    except (OSError, ValueError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    falhas = 0
    for caminho in caminhos:
        try:
            profiler.processar_arquivo(
                caminho, saida_base=saida_base, tambem_parquet=tambem_parquet,
                formatos=escolhidos, json_compacto=json_compacto,
            )
        except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
            falhas += 1
            typer.secho(f"Erro ao processar '{caminho}': {e}", fg=typer.colors.RED, err=True)
    if falhas == len(caminhos) and caminhos:
        raise typer.Exit(code=1) from None


@app.command()
def modelar(
    caminhos: list[str],
    saida_base: str = typer.Option("modelo", "--saida-base",
                                   help="Prefixo dos arquivos gerados."),
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    sem_perfis: bool = typer.Option(
        False, "--sem-perfis",
        help="Gera só o relatório do modelo, sem o perfil individual de cada tabela.",
    ),
) -> None:
    """Analisa várias tabelas juntas e infere como elas se relacionam.

    Descobre chaves estrangeiras, classifica cada tabela como fato ou
    dimensão e sugere análises cruzadas com o código pronto. Cada aba de um
    Excel entra como uma tabela independente.
    """
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis)
        profiler.modelar_conjunto(
            caminhos, saida_base=saida_base, formatos=escolhidos,
            json_compacto=json_compacto, perfis_individuais=not sem_perfis,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command()
def versao() -> None:
    """Mostra a versão instalada do DataScope."""
    typer.echo(f"DataScope {__version__}")


if __name__ == "__main__":
    app()

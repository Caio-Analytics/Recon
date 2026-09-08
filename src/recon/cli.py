import os
from pathlib import Path

import typer
from loguru import logger

from . import __version__, reporting
from . import contrato as contrato_mod
from .ingestion import EXTENSOES_DESCOBERTAS as _EXT
from .ingestion import IngestionError
from .ingestion import carregar_arquivo as _carregar
from .pipeline import FORMATOS_VALIDOS, DataProfiler
from .quality import carregar_regras_kpi

app = typer.Typer(
    help="Recon — descubra o que tem nos seus arquivos antes de começar a analisar.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback()
def principal(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        from .interativo import executar

        executar()


_EXTENSOES_EXCEL = (".xlsx", ".xls", ".xlsb")
_EXTENSOES_SUPORTADAS = frozenset(_EXT)
_MODOS_VALIDOS = ("auto", "individual", "lote", "modelo")


def _decidir_modo(modo: str, arquivos: list[str], sim: bool) -> str:
    if modo not in _MODOS_VALIDOS:
        raise typer.BadParameter(f"Modo inválido: {modo!r}. Use: {', '.join(_MODOS_VALIDOS)}.")
    if modo != "auto":
        return modo
    if len(arquivos) == 1:
        return "individual"
    if sim:
        return "lote"
    typer.echo(f"\nEncontrei {len(arquivos)} arquivos:")
    for arquivo in arquivos[:8]:
        typer.echo(f"  - {os.path.basename(arquivo)}")
    if len(arquivos) > 8:
        typer.echo(f"  ... e mais {len(arquivos) - 8}")
    typer.echo(
        "\n  [1] Lote — perfila todos e compara num relatório único (padrão)\n"
        "  [2] Modelo — além disso, descobre como as tabelas se ligam entre si\n"
        "  [3] Individual — um relatório completo por arquivo"
    )
    escolha = typer.prompt("Como quer analisar?", default="1")
    return {"1": "lote", "2": "modelo", "3": "individual"}.get(escolha.strip(), "lote")


_OPCAO_SAIDA = typer.Option("profiler_output", "--saida-base", help="Prefixo dos arquivos gerados.")
_OPCAO_FORMATOS = typer.Option(
    "json,html",
    "--formatos",
    help=(
        f"Formatos de saída separados por vírgula ({', '.join(FORMATOS_VALIDOS)}). "
        "Use 'json,markdown' para voltar ao Markdown."
    ),
)
_OPCAO_PARQUET = typer.Option(False, "--tambem-parquet", help="Atalho para incluir 'parquet'.")
_OPCAO_JSON_COMPACTO = typer.Option(
    False,
    "--json-compacto",
    help="JSON sem indentação, menor e mais fácil de integrar a outras ferramentas.",
)
_OPCAO_LIMITE = typer.Option(
    2_000_000,
    "--limite-amostra",
    min=1,
    help=(
        "Máximo de linhas analisadas. Acima disso o profiler usa amostra aleatória e "
        "as métricas de unicidade passam a valer para a amostra. Baixe para ganhar "
        "velocidade em arquivo muito grande."
    ),
)
_OPCAO_GERAR_LIMPEZA = typer.Option(
    False,
    "--gerar-limpeza",
    help="Gera um script pandas que aplica as recomendações do perfil.",
)
_OPCAO_LIMPEZA_M = typer.Option(
    False,
    "--gerar-limpeza-powerquery",
    help="Gera os mesmos passos em Power Query (M), para colar no Power BI.",
)
_OPCAO_SEM_LAYOUT = typer.Option(
    False,
    "--sem-deteccao-layout",
    help="Lê o arquivo cru: cabeçalho na primeira linha, sem remover total nem coluna vazia.",
)
_OPCAO_LINHA_CABECALHO = typer.Option(
    None,
    "--linha-cabecalho",
    min=0,
    help="Força a linha do cabeçalho (0 = primeira), em vez de detectar.",
)
_OPCAO_KPIS = typer.Option(
    None, "--kpis", help="YAML com regras de gap analysis próprias (padrão: regras de RH)."
)
_OPCAO_VOCABULARIOS = typer.Option(
    None,
    "--vocabularios",
    help="YAML(s) com termos e gazetteers do seu domínio, separados por vírgula.",
)


def setup_logging(log_file: str | None = None) -> None:
    logger.remove()
    logger.add(
        lambda msg: print(msg, end="", flush=True),
        format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}",
        level="INFO",
        colorize=True,
    )
    if log_file:
        logger.add(
            log_file,
            format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}",
            level="DEBUG",
            rotation="10 MB",
            encoding="utf-8",
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


def _construir_profiler(
    limite_amostra: int,
    kpis: str | None,
    vocabularios: str | None = None,
) -> DataProfiler:
    return DataProfiler(
        limite_amostra=limite_amostra,
        regras_kpi=carregar_regras_kpi(kpis),
        vocabularios=vocabularios,
    )


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
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
    sem_deteccao_layout: bool = _OPCAO_SEM_LAYOUT,
    linha_cabecalho: int | None = _OPCAO_LINHA_CABECALHO,
    gerar_limpeza: bool = _OPCAO_GERAR_LIMPEZA,
    gerar_limpeza_powerquery: bool = _OPCAO_LIMPEZA_M,
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)

    extensao = os.path.splitext(caminho)[1].lower()
    if extensao not in _EXTENSOES_EXCEL and (todas_abas or aba != "0"):
        logger.warning(
            f"'{extensao or 'sem extensão'}' não tem abas — --aba/--todas-abas ignorados."
        )

    aba_valor: str | int = int(aba) if aba.lstrip("-").isdigit() else aba
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.processar_arquivo(
            caminho,
            aba_excel=aba_valor,
            processar_todas_abas=todas_abas,
            saida_base=saida_base,
            tambem_parquet=tambem_parquet,
            formatos=escolhidos,
            json_compacto=json_compacto,
            detectar_layout=not sem_deteccao_layout,
            linha_cabecalho=linha_cabecalho,
            gerar_limpeza=gerar_limpeza,
            gerar_limpeza_powerquery=gerar_limpeza_powerquery,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command()
def lote(
    caminhos: list[str],
    saida_base: str = _OPCAO_SAIDA,
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
    sem_deteccao_layout: bool = _OPCAO_SEM_LAYOUT,
    sem_consolidado: bool = typer.Option(
        False,
        "--sem-consolidado",
        help="Não gera o HTML comparativo; só os relatórios individuais.",
    ),
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
    except (OSError, ValueError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    payloads, falhas = profiler.processar_lote(
        caminhos,
        saida_base=saida_base,
        formatos=escolhidos,
        json_compacto=json_compacto,
        detectar_layout=not sem_deteccao_layout,
        consolidado=not sem_consolidado,
    )
    for caminho, erro in falhas:
        typer.secho(f"Erro ao processar '{caminho}': {erro}", fg=typer.colors.RED, err=True)
    if not payloads:
        raise typer.Exit(code=1)


@app.command()
def modelar(
    caminhos: list[str],
    saida_base: str = typer.Option("modelo", "--saida-base", help="Prefixo dos arquivos gerados."),
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
    sem_perfis: bool = typer.Option(
        False,
        "--sem-perfis",
        help="Gera só o relatório do modelo, sem o perfil individual de cada tabela.",
    ),
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.modelar_conjunto(
            caminhos,
            saida_base=saida_base,
            formatos=escolhidos,
            json_compacto=json_compacto,
            perfis_individuais=not sem_perfis,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command()
def pasta(
    entrada: str = typer.Argument(..., help="Pasta com os arquivos a analisar."),
    saida: str = typer.Option(".", "--saida", help="Pasta onde gravar os relatórios."),
    modo: str = typer.Option(
        "auto",
        "--modo",
        help="auto (decide sozinho), individual, lote ou modelo (cruza as tabelas).",
    ),
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
    sem_deteccao_layout: bool = _OPCAO_SEM_LAYOUT,
    gerar_limpeza: bool = _OPCAO_GERAR_LIMPEZA,
    sim: bool = typer.Option(False, "--sim", "-s", help="Aceita a sugestão sem perguntar."),
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)

    pasta_entrada = Path(entrada)
    if not pasta_entrada.is_dir():
        typer.secho(f"Erro: '{entrada}' não é uma pasta.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    arquivos = sorted(
        str(p)
        for p in pasta_entrada.iterdir()
        if p.is_file() and p.name.lower().endswith(tuple(_EXTENSOES_SUPORTADAS))
    )
    if not arquivos:
        typer.secho(
            f"Erro: nenhum arquivo suportado em '{entrada}' "
            f"({', '.join(sorted(_EXTENSOES_SUPORTADAS))}).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    pasta_saida = Path(saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    saida_base = str(pasta_saida / (pasta_entrada.resolve().name or "saida"))

    escolhido = _decidir_modo(modo, arquivos, sim)
    logger.info(f"{len(arquivos)} arquivo(s) encontrado(s) — modo '{escolhido}'")

    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        if escolhido == "modelo":
            profiler.modelar_conjunto(
                arquivos,
                saida_base=saida_base,
                formatos=escolhidos,
                json_compacto=json_compacto,
            )
        elif escolhido == "individual":
            for arquivo in arquivos:
                profiler.processar_arquivo(
                    arquivo,
                    saida_base=saida_base,
                    formatos=escolhidos,
                    json_compacto=json_compacto,
                    detectar_layout=not sem_deteccao_layout,
                    gerar_limpeza=gerar_limpeza,
                )
        else:
            _, falhas = profiler.processar_lote(
                arquivos,
                saida_base=saida_base,
                formatos=escolhidos,
                json_compacto=json_compacto,
                detectar_layout=not sem_deteccao_layout,
            )
            for caminho, erro in falhas:
                typer.secho(f"Erro em '{caminho}': {erro}", fg=typer.colors.RED, err=True)
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    typer.secho(f"\nRelatórios em: {pasta_saida.resolve()}", fg=typer.colors.GREEN)


@app.command()
def conferir(
    anterior: str = typer.Argument(..., help="A versão que você já conhece."),
    nova: str = typer.Argument(..., help="A extração que acabou de chegar."),
    saida_base: str = typer.Option(
        "conferencia", "--saida-base", help="Prefixo dos arquivos gerados."
    ),
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.conferir_versoes(
            anterior,
            nova,
            saida_base=saida_base,
            formatos=escolhidos,
            json_compacto=json_compacto,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command()
def historico(
    caminhos: list[str],
    saida_base: str = typer.Option("historico", "--saida-base"),
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
    limites: str | None = typer.Option(
        None, "--limites", help="YAML com limites de score e variação para alertas históricos."
    ),
) -> None:
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.analisar_historico(
            caminhos,
            saida_base=saida_base,
            formatos=escolhidos,
            json_compacto=json_compacto,
            limites=limites,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command()
def contrato(
    caminho: str = typer.Argument(..., help="Base que serve de referência."),
    saida: str = typer.Option("contrato.yaml", "--saida", help="Arquivo YAML a gravar."),
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    setup_logging()
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        df, nome = _carregar(caminho)
        payload = profiler.processar_dataframe(df, nome)
        acordo = contrato_mod.gerar_contrato(payload)
        contrato_mod.salvar_contrato(acordo, saida)
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    typer.secho(
        f"Contrato de '{nome}' salvo em {saida}. "
        "Revise antes de usar: apagar uma entrada é dizer que aquilo pode variar.",
        fg=typer.colors.GREEN,
    )


@app.command()
def validar(
    caminho: str = typer.Argument(..., help="Extração nova a conferir."),
    contrato_arquivo: str = typer.Option(
        ..., "--contrato", help="YAML gerado por `recon contrato`."
    ),
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    setup_logging()
    try:
        acordo = contrato_mod.carregar_contrato(contrato_arquivo)
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        df, nome = _carregar(caminho)
        payload = profiler.processar_dataframe(df, nome)
        resultado = contrato_mod.conferir_contrato(payload, acordo)
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    for violacao in resultado["violacoes"]:
        cor = typer.colors.RED if "ALTA" in violacao["severidade"] else typer.colors.YELLOW
        typer.secho(f"{violacao['severidade']} [{violacao['tipo']}] {violacao['mensagem']}", fg=cor)
    for aviso in resultado.get("avisos", []):
        typer.secho(f"Aviso: {aviso}", fg=typer.colors.YELLOW)
    typer.secho(
        resultado["resumo"],
        fg=typer.colors.GREEN if resultado["aprovado"] else typer.colors.RED,
    )
    if not resultado["aprovado"]:
        raise typer.Exit(code=1)


@app.command()
def dicionario(
    caminhos: list[str] = typer.Argument(..., help="Arquivos a documentar."),
    saida: str = typer.Option("dicionario.xlsx", "--saida", help="Arquivo XLSX a gravar."),
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    setup_logging()
    payloads = []
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        for caminho in caminhos:
            df, nome = _carregar(caminho)
            payloads.append(profiler.processar_dataframe(df, nome))
        reporting.exportar_dicionario_xlsx(payloads, saida)
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    typer.secho(f"Dicionário de {len(payloads)} tabela(s) salvo em {saida}.", fg=typer.colors.GREEN)


@app.command("revisar-semantica")
def revisar_semantica(
    caminho: str = typer.Argument(..., help="Base usada para montar o modelo de revisão."),
    saida: str = typer.Option("correcoes_semanticas.yaml", "--saida"),
    limite_amostra: int = _OPCAO_LIMITE,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    from . import semantics

    setup_logging()
    try:
        profiler = _construir_profiler(limite_amostra, None, vocabularios)
        quadro, nome = _carregar(caminho)
        semantics.exportar_modelo_de_correcoes(profiler.processar_dataframe(quadro, nome), saida)
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    typer.secho(f"Modelo de revisão semântica salvo em {saida}.", fg=typer.colors.GREEN)


@app.command()
def fonte(
    conexao: str = typer.Argument(
        ..., help="sqlite:///arquivo.db ou duckdb:///arquivo.duckdb (banco local)."
    ),
    sql: str = typer.Option(..., "--sql", help="Consulta SELECT ou WITH a analisar."),
    saida_base: str = _OPCAO_SAIDA,
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    setup_logging()
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.processar_consulta(
            conexao,
            sql,
            saida_base=saida_base,
            formatos=_parsear_formatos(formatos),
            json_compacto=json_compacto,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command(help="Abre o Recon em janela, sem terminal.")
def janela() -> None:
    try:
        from .gui_qt import main
    except ImportError as e:
        typer.secho(
            "A interface gráfica não está instalada. Reinstale o Recon com o extra de GUI: "
            'pip install "recon[gui]".',
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from e
    main()


@app.command()
def versao() -> None:
    typer.echo(f"Recon {__version__}")


if __name__ == "__main__":
    app()

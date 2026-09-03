"""CLI do Recon: `perfilar` (um arquivo) e `lote` (vários arquivos)."""
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
    """Sem argumento nenhum, abre o menu interativo.

    Quem usa o Recon uma vez por mês não guarda `--formatos` nem
    `--limite-amostra` de cabeça; digitar `recon` e responder três perguntas
    não exige lembrar sintaxe nenhuma.
    """
    if ctx.invoked_subcommand is None:
        from .interativo import executar
        executar()

_EXTENSOES_EXCEL = (".xlsx", ".xls", ".xlsb")
_EXTENSOES_SUPORTADAS = frozenset(_EXT)
_MODOS_VALIDOS = ("auto", "individual", "lote", "modelo")


def _decidir_modo(modo: str, arquivos: list[str], sim: bool) -> str:
    """Escolhe entre perfil individual, lote e modelo do conjunto.

    Com um arquivo só não há o que comparar nem cruzar. Com vários, o lote é o
    padrão e o modelo é oferecido, não imposto: cruzar tabelas sem relação
    nenhuma só produz um relatório dizendo que não há relação.
    """
    if modo not in _MODOS_VALIDOS:
        raise typer.BadParameter(
            f"Modo inválido: {modo!r}. Use: {', '.join(_MODOS_VALIDOS)}."
        )
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
    "json,html", "--formatos",
    help=(
        f"Formatos de saída separados por vírgula ({', '.join(FORMATOS_VALIDOS)}). "
        "Use 'json,markdown' para voltar ao Markdown."
    ),
)
_OPCAO_PARQUET = typer.Option(False, "--tambem-parquet", help="Atalho para incluir 'parquet'.")
_OPCAO_JSON_COMPACTO = typer.Option(
    False, "--json-compacto", help="JSON sem indentação (menor, melhor para colar em prompt de IA)."
)
_OPCAO_LIMITE = typer.Option(
    2_000_000, "--limite-amostra", min=1,
    help=(
        "Máximo de linhas analisadas. Acima disso o profiler usa amostra aleatória e "
        "as métricas de unicidade passam a valer para a amostra. Baixe para ganhar "
        "velocidade em arquivo muito grande."
    ),
)
_OPCAO_GERAR_LIMPEZA = typer.Option(
    False, "--gerar-limpeza",
    help="Gera um script pandas que aplica as recomendações do perfil.",
)
_OPCAO_LIMPEZA_M = typer.Option(
    False, "--gerar-limpeza-powerquery",
    help="Gera os mesmos passos em Power Query (M), para colar no Power BI.",
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
_OPCAO_VOCABULARIOS = typer.Option(
    None, "--vocabularios", help="YAML(s) com termos e gazetteers do seu domínio, separados por vírgula."
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


def _construir_profiler(
    limite_amostra: int, kpis: str | None, vocabularios: str | None = None,
) -> DataProfiler:
    return DataProfiler(
        limite_amostra=limite_amostra, regras_kpi=carregar_regras_kpi(kpis),
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

    # `--aba` só tem efeito em Excel; avisar é melhor do que ignorar calado.
    extensao = os.path.splitext(caminho)[1].lower()
    if extensao not in _EXTENSOES_EXCEL and (todas_abas or aba != "0"):
        logger.warning(f"'{extensao or 'sem extensão'}' não tem abas — --aba/--todas-abas ignorados.")

    # O aviso de "este arquivo tem outras abas" vive no pipeline, para que a
    # janela e o menu interativo também o recebam.
    aba_valor: str | int = int(aba) if aba.lstrip("-").isdigit() else aba
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.processar_arquivo(
            caminho, aba_excel=aba_valor, processar_todas_abas=todas_abas,
            saida_base=saida_base, tambem_parquet=tambem_parquet,
            formatos=escolhidos, json_compacto=json_compacto,
            detectar_layout=not sem_deteccao_layout, linha_cabecalho=linha_cabecalho,
            gerar_limpeza=gerar_limpeza, gerar_limpeza_powerquery=gerar_limpeza_powerquery,
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
        False, "--sem-consolidado",
        help="Não gera o HTML comparativo; só os relatórios individuais.",
    ),
) -> None:
    """Perfila vários arquivos e compara todos num relatório único.

    A saída principal é um HTML só, com todos os arquivos ordenados do pior
    para o melhor e o pior já aberto.
    """
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
    except (OSError, ValueError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    payloads, falhas = profiler.processar_lote(
        caminhos, saida_base=saida_base, formatos=escolhidos,
        json_compacto=json_compacto, detectar_layout=not sem_deteccao_layout,
        consolidado=not sem_consolidado,
    )
    for caminho, erro in falhas:
        typer.secho(f"Erro ao processar '{caminho}': {erro}", fg=typer.colors.RED, err=True)
    if not payloads:
        raise typer.Exit(code=1)


@app.command()
def modelar(
    caminhos: list[str],
    saida_base: str = typer.Option("modelo", "--saida-base",
                                   help="Prefixo dos arquivos gerados."),
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
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
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.modelar_conjunto(
            caminhos, saida_base=saida_base, formatos=escolhidos,
            json_compacto=json_compacto, perfis_individuais=not sem_perfis,
        )
    except (FileNotFoundError, IngestionError, ValueError, OSError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


@app.command()
def pasta(
    entrada: str = typer.Argument(..., help="Pasta com os arquivos a analisar."),
    saida: str = typer.Option(".", "--saida", help="Pasta onde gravar os relatórios."),
    modo: str = typer.Option(
        "auto", "--modo",
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
    """Analisa todos os arquivos de uma pasta, escolhendo o modo sozinho.

    Um arquivo só vira perfil individual; vários viram lote comparativo. Se os
    arquivos parecem se relacionar, oferece o modo `modelo`, que descobre as
    chaves entre eles.
    """
    setup_logging()
    escolhidos = _parsear_formatos(formatos)

    pasta_entrada = Path(entrada)
    if not pasta_entrada.is_dir():
        typer.secho(f"Erro: '{entrada}' não é uma pasta.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    arquivos = sorted(
        str(p) for p in pasta_entrada.iterdir()
        if p.is_file() and p.name.lower().endswith(tuple(_EXTENSOES_SUPORTADAS))
    )
    if not arquivos:
        typer.secho(
            f"Erro: nenhum arquivo suportado em '{entrada}' "
            f"({', '.join(sorted(_EXTENSOES_SUPORTADAS))}).",
            fg=typer.colors.RED, err=True,
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
                arquivos, saida_base=saida_base, formatos=escolhidos,
                json_compacto=json_compacto,
            )
        elif escolhido == "individual":
            for arquivo in arquivos:
                profiler.processar_arquivo(
                    arquivo, saida_base=saida_base, formatos=escolhidos,
                    json_compacto=json_compacto, detectar_layout=not sem_deteccao_layout,
                    gerar_limpeza=gerar_limpeza,
                )
        else:
            _, falhas = profiler.processar_lote(
                arquivos, saida_base=saida_base, formatos=escolhidos,
                json_compacto=json_compacto, detectar_layout=not sem_deteccao_layout,
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
    saida_base: str = typer.Option("conferencia", "--saida-base",
                                   help="Prefixo dos arquivos gerados."),
    formatos: str = _OPCAO_FORMATOS,
    json_compacto: bool = _OPCAO_JSON_COMPACTO,
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    """Compara duas versões da mesma base e mostra o que mudou.

    Schema (coluna que sumiu ou apareceu), volume, quais registros entraram e
    saíram pela chave, e as colunas que continuam no arquivo mas mudaram de
    tipo ou pararam de vir preenchidas — o defeito de extração que passa
    despercebido porque o nome da coluna não mudou.
    """
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.conferir_versoes(
            anterior, nova, saida_base=saida_base, formatos=escolhidos,
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
) -> None:
    """Mostra a evolução de qualidade de 2+ extrações, na ordem informada."""
    setup_logging()
    escolhidos = _parsear_formatos(formatos)
    try:
        profiler = _construir_profiler(limite_amostra, kpis, vocabularios)
        profiler.analisar_historico(
            caminhos, saida_base=saida_base, formatos=escolhidos,
            json_compacto=json_compacto,
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
    """Congela o que a base é hoje num contrato YAML.

    Tipos, colunas obrigatórias, unicidade, domínio das categorias e as regras
    de negócio que valem em 100% das linhas. O arquivo é feito para ser
    editado: o Recon propõe, você decide o que exigir.
    """
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
    contrato_arquivo: str = typer.Option(..., "--contrato", help="YAML gerado por `recon contrato`."),
    limite_amostra: int = _OPCAO_LIMITE,
    kpis: str | None = _OPCAO_KPIS,
    vocabularios: str | None = _OPCAO_VOCABULARIOS,
) -> None:
    """Confere uma extração contra um contrato e lista o que saiu da linha.

    Sai com código 1 quando há violação grave, para poder ser usado em script
    (ex.: checagem automática a cada nova extração).
    """
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
    """Gera o dicionário de dados em XLSX — uma aba por tabela.

    Formato pensado para circular: anexar num chamado, filtrar no Excel,
    usar como documentação da base.
    """
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


@app.command()
def janela() -> None:
    """Abre o Recon em janela, sem terminal.

    Mesma análise dos outros comandos, com "Procurar" abrindo o Explorer no
    lugar de caminho digitado à mão. No Windows, dois cliques em `Recon.pyw`
    chegam aqui sem passar pelo cmd.
    """
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
    """Mostra a versão instalada do Recon."""
    typer.echo(f"Recon {__version__}")


if __name__ == "__main__":
    app()

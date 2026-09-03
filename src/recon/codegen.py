"""Geração do script de limpeza a partir dos achados do perfil.

Converte os achados do payload (colunas a converter, sentinelas a tratar,
grafias a padronizar, dtype a reduzir) num script pandas pronto para rodar,
com cada passo comentado com o motivo. Lê o arquivo original e devolve um
DataFrame novo, sem sobrescrever nada.
"""
from typing import Any

from loguru import logger

_INDENTACAO = "    "


def _comentario(valor: Any) -> str:
    """Transforma texto externo em uma única linha segura para comentário."""
    return " ".join(str(valor).splitlines())


def _texto_docstring(valor: Any) -> str:
    """Impede que metadados externos fechem o docstring do script gerado."""
    return _comentario(valor).replace("\\", "\\\\").replace('"""', '\\\"\\\"\\\"')


def _var(nome: str) -> str:
    limpo = "".join(ch if ch.isalnum() else "_" for ch in str(nome).lower()).strip("_")
    return limpo or "tabela"


def _literal(valor: Any) -> str:
    return repr(str(valor))


def _leitura(payload: dict[str, Any], caminho_origem: str) -> list[str]:
    """Monta a chamada de leitura já com os ajustes de layout detectados."""
    meta = payload["metadados_execucao"]
    layout = meta.get("layout") or {}
    extras: list[str] = []

    if layout.get("linha_cabecalho"):
        extras.append(f"header={layout['linha_cabecalho']}")
    if layout.get("linhas_rodape_removidas"):
        extras.append(f"skipfooter={layout['linhas_rodape_removidas']}")

    # Datas ISO num CSV são convertidas na leitura do profiler. Sem repetir a
    # conversão aqui, o script devolveria as mesmas colunas como texto e todo o
    # resto do arquivo (ordem entre datas, série temporal) deixaria de valer.
    datas = [
        c["Coluna"] for c in payload.get("colunas", [])
        if c.get("Tipo_Inferred") == "Data / Hora"
    ]

    tabela = str(meta["tabela"])
    if caminho_origem.lower().endswith((".xlsx", ".xls", ".xlsb")):
        aba = tabela.split("__", 1)[-1] if "__" in tabela else 0
        argumentos = [f"r{_literal(caminho_origem)}", f"sheet_name={_literal(aba)}"]
        argumentos += extras
        leitura = f"pd.read_excel({', '.join(argumentos)})"
    else:
        argumentos = [f"r{_literal(caminho_origem)}"]
        # Sem separador e encoding, o script gerado lê com os padrões do pandas
        # (`,` e utf-8) e quebra no arquivo brasileiro típico. Os dois vêm da
        # detecção que a ingestão já fez, então o script reproduz a mesma leitura.
        if layout.get("separador") and layout["separador"] != ",":
            argumentos.append(f"sep={_literal(layout['separador'])}")
        if layout.get("encoding") and str(layout["encoding"]).lower() not in ("utf-8", "utf8"):
            argumentos.append(f"encoding={_literal(layout['encoding'])}")
        if datas:
            argumentos.append(f"parse_dates={[str(d) for d in datas]!r}")
        argumentos += extras
        if layout.get("linhas_rodape_removidas"):
            # `skipfooter` no read_csv exige o engine python.
            argumentos.append("engine='python'")
        leitura = f"pd.read_csv({', '.join(argumentos)})"

    linhas = ["# ── Leitura ─────────────────────────────────────────────────────"]
    if layout.get("avisos"):
        for aviso in layout["avisos"]:
            linhas.append(
                f"# {_comentario(aviso['tipo'])}: {_comentario(aviso['mensagem'])[:100]}"
            )
    linhas.append(f"df = {leitura}")
    return linhas


def _passos_por_coluna(payload: dict[str, Any]) -> list[str]:
    linhas: list[str] = []

    for coluna in payload["colunas"]:
        nome = coluna["Coluna"]
        alertas = coluna.get("Alertas", {})
        qualidade = coluna.get("Qualidade", {})
        otimizacao = coluna.get("Otimizacao") or {}
        # (motivo do achado, código que aplica) — o motivo vira comentário.
        passos: list[tuple[str, str]] = []

        if "Vazia" in coluna.get("Caracteristica", ""):
            passos.append((
                "coluna 100% nula",
                f"df = df.drop(columns=[{_literal(nome)}])",
            ))
            linhas.extend(_bloco(nome, passos))
            continue

        sentinelas = qualidade.get("sentinelas", {})
        if sentinelas.get("tem_sentinela"):
            valores = [v["valor"] for v in sentinelas["valores"]]
            passos.append((
                f"{sentinelas['pct_total']:.1%} dos valores são marcador de ausência",
                f"df[{_literal(nome)}] = df[{_literal(nome)}].replace("
                f"{valores!r}, None)",
            ))

        inconsistencia = qualidade.get("inconsistencia_normalizacao", {})
        if inconsistencia.get("tem_inconsistencia"):
            passos.append((
                f"{inconsistencia['valores_unicos_atual']} grafias para "
                f"{inconsistencia['valores_unicos_normalizado']} valores reais",
                f"df[{_literal(nome)}] = "
                f"df[{_literal(nome)}].str.strip().str.upper()",
            ))

        virou_data = bool(alertas.get("data_como_texto"))
        if virou_data:
            passos.append((
                "data armazenada como texto",
                f"df[{_literal(nome)}] = pd.to_datetime("
                f"df[{_literal(nome)}], errors='coerce', format='mixed')",
            ))

        if coluna.get("Dado_Sensivel_LGPD", "Nenhum") != "Nenhum":
            passos.append((
                f"dado pessoal ({coluna['Dado_Sensivel_LGPD']}) — LGPD",
                f"df[{_literal(nome)}] = df[{_literal(nome)}].map(\n"
                f"{_INDENTACAO}lambda v: hashlib.sha256(str(v).encode()).hexdigest()[:16]\n"
                f"{_INDENTACAO}if pd.notna(v) else v\n)",
            ))

        if qualidade.get("mojibake", {}).get("tem_mojibake"):
            passos.append((
                "encoding corrompido na origem — corrige o que dá, mas o certo "
                "é reprocessar a carga",
                f"df[{_literal(nome)}] = df[{_literal(nome)}].map(\n"
                f"{_INDENTACAO}lambda v: v.encode('latin-1', 'ignore')"
                f".decode('utf-8', 'ignore') if isinstance(v, str) else v\n)",
            ))

        # A sugestão de dtype foi calculada sobre a coluna antes da conversão
        # de data. Aplicá-la depois transformaria o datetime recém-criado em
        # `category`, desfazendo o passo anterior.
        if (not virou_data
                and otimizacao.get("dtype_sugerido")
                and otimizacao.get("economia_pct", 0) >= 0.3):
            passos.append((
                f"economiza {otimizacao.get('economia_mb', 0):.2f} MB "
                f"({otimizacao['economia_pct']:.0%})",
                f"df[{_literal(nome)}] = "
                f"df[{_literal(nome)}].astype({_literal(otimizacao['dtype_sugerido'])})",
            ))

        linhas.extend(_bloco(nome, passos))
    return linhas


def _bloco(nome: str, passos: list[tuple[str, str]]) -> list[str]:
    if not passos:
        return []
    linhas = [f"\n# ── {_comentario(nome)} ──"]
    for motivo, codigo in passos:
        linhas.append(f"# {_comentario(motivo)}")
        linhas.append(codigo)
    return linhas


def _passos_de_tabela(payload: dict[str, Any]) -> list[str]:
    meta = payload["metadados_execucao"]
    duplicatas = meta.get("duplicatas", {})
    linhas: list[str] = []

    if duplicatas.get("qtd_linhas_duplicadas"):
        linhas.append("\n# ── Tabela ──")
        linhas.append(
            f"# {duplicatas['qtd_linhas_duplicadas']:,} linha(s) integralmente duplicada(s)"
        )
        linhas.append("df = df.drop_duplicates()")

    redundantes = payload.get("colunas_redundantes") or []
    if redundantes:
        alvos = [r["coluna_redundante"] for r in redundantes]
        linhas.append(f"# colunas idênticas a outra: {_comentario(', '.join(alvos))}")
        linhas.append(f"df = df.drop(columns={alvos!r})")

    return linhas


def _avisos_nao_automatizaveis(payload: dict[str, Any]) -> list[str]:
    """O que o profiler achou mas não dá para consertar por código.

    Encoding corrompido, documento com dígito inválido e violação de regra de
    negócio precisam de decisão humana ou de correção na origem — emitir
    código que "resolve" isso seria esconder o problema, não tratá-lo.
    """
    pendencias: list[str] = []
    for coluna in payload["colunas"]:
        documento = coluna.get("Qualidade", {}).get("documento_invalido", {})
        if documento.get("tem_documento_invalido"):
            pendencias.append(
                f"{coluna['Coluna']}: tem formato de {documento['tipo']} mas só "
                f"{documento['pct_valido']:.0%} passam no dígito verificador — "
                "validar na origem"
            )
        pii = coluna.get("Qualidade", {}).get("pii_texto_livre", {})
        if pii.get("tem_pii"):
            pendencias.append(
                f"{coluna['Coluna']}: PII embutida em texto livre "
                f"({', '.join(sorted(pii['tipos']))}) — decidir anonimização"
            )

    for regra in payload.get("regras_negocio") or []:
        if regra["qtd_violacoes"]:
            pendencias.append(
                f"{regra['regra']}: {regra['qtd_violacoes']} violação(ões) — "
                "conferir na origem"
            )

    if not pendencias:
        return []
    linhas = [
        "",
        "# ── Pendências que este script NÃO resolve ──────────────────────",
        "# Precisam de decisão sua ou de correção na origem:",
    ]
    linhas += [f"#   - {_comentario(p)}" for p in pendencias]
    return linhas


def gerar_script_limpeza(payload: dict[str, Any], caminho_origem: str) -> str:
    """Monta o script de limpeza correspondente a um perfil.

    Cada passo carrega, em comentário, o achado que o motivou — para o script
    poder ser revisado linha a linha em vez de aceito no escuro.
    """
    meta = payload["metadados_execucao"]
    cabecalho = [
        '"""Script de limpeza gerado pelo Recon.',
        "",
        f"Tabela: {_texto_docstring(meta['tabela'])}",
        f"Origem: {_texto_docstring(caminho_origem)}",
        f"Gerado em: {meta['timestamp_utc'][:19]} UTC (Recon {meta['versao_profiler']})",
        "",
        "Cada passo abaixo veio de um achado do perfil e está comentado com o motivo.",
        "Revise antes de rodar: o profiler sugere, quem decide é você.",
        '"""',
        "import hashlib",
        "",
        "import pandas as pd",
        "",
    ]

    corpo = _leitura(payload, caminho_origem)
    corpo += _passos_de_tabela(payload)
    corpo += _passos_por_coluna(payload)

    rodape = [
        "",
        "# ── Resultado ───────────────────────────────────────────────────",
        "print(f'{len(df):,} linhas x {len(df.columns)} colunas após a limpeza')",
        "print(df.dtypes)",
    ]
    rodape += _avisos_nao_automatizaveis(payload)

    return "\n".join(cabecalho + corpo + rodape) + "\n"


def exportar_script_limpeza(
    payload: dict[str, Any], caminho_origem: str, caminho_saida: str
) -> None:
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(gerar_script_limpeza(payload, caminho_origem))
    logger.info(f"✓ Script de limpeza exportado: '{caminho_saida}'")


# ── Power Query (M) ─────────────────────────────────────────────────────────

def _m_literal(valor: Any) -> str:
    return '"' + str(valor).replace('"', '""') + '"'


def _m_tipo(tipo_inferred: str) -> str:
    if tipo_inferred == "Data / Hora":
        return "type datetime"
    if tipo_inferred == "Número Inteiro":
        return "Int64.Type"
    if tipo_inferred == "Número Decimal":
        return "type number"
    if tipo_inferred == "Booleano":
        return "type logical"
    return "type text"


def gerar_script_limpeza_m(payload: dict[str, Any], caminho_origem: str) -> str:
    """Os mesmos passos do script pandas, em Power Query (M).

    Quem entrega em Power BI não roda o `.py`: refaz na mão, no editor, os
    passos que o relatório descreveu. Este gera o M pronto para colar, sem
    precisar reimplementar os passos manualmente.
    """
    meta = payload["metadados_execucao"]
    layout = meta.get("layout") or {}
    passos: list[tuple[str, str]] = []

    if caminho_origem.lower().endswith((".xlsx", ".xls", ".xlsb")):
        aba = str(meta["tabela"]).split("__", 1)[-1]
        origem = (
            f"Excel.Workbook(File.Contents({_m_literal(caminho_origem)}), true)"
            f"{{[Item={_m_literal(aba)},Kind=\"Sheet\"]}}[Data]"
        )
    else:
        separador = layout.get("separador") or ","
        origem = (
            f"Csv.Document(File.Contents({_m_literal(caminho_origem)}),"
            f"[Delimiter={_m_literal(separador)}, Encoding=65001, QuoteStyle=QuoteStyle.Csv])"
        )
    passos.append(("Origem", origem))

    linha_cabecalho = int(layout.get("linha_cabecalho") or 0)
    anterior = "Origem"
    if linha_cabecalho:
        passos.append((
            "PulaPreambulo", f"Table.Skip({anterior}, {linha_cabecalho})"
        ))
        anterior = "PulaPreambulo"
    passos.append((
        "Cabecalho", f"Table.PromoteHeaders({anterior}, [PromoteAllScalars=true])"
    ))
    anterior = "Cabecalho"

    rodape = int(layout.get("linhas_rodape_removidas") or 0)
    if rodape:
        passos.append(("RemoveTotal", f"Table.RemoveLastN({anterior}, {rodape})"))
        anterior = "RemoveTotal"

    remover = [
        c["Coluna"] for c in payload["colunas"] if "Vazia" in c.get("Caracteristica", "")
    ]
    if remover:
        lista = ", ".join(_m_literal(c) for c in remover)
        passos.append(("RemoveVazias", f"Table.RemoveColumns({anterior}, {{{lista}}})"))
        anterior = "RemoveVazias"

    for coluna in payload["colunas"]:
        nome = coluna["Coluna"]
        if nome in remover:
            continue
        sentinelas = coluna.get("Qualidade", {}).get("sentinelas", {})
        if sentinelas.get("tem_sentinela"):
            for i, valor in enumerate(v["valor"] for v in sentinelas["valores"]):
                passo = f"Nulo_{_var(nome)}_{i}"
                passos.append((passo, (
                    f"Table.ReplaceValue({anterior}, {_m_literal(valor)}, null, "
                    f"Replacer.ReplaceValue, {{{_m_literal(nome)}}})"
                )))
                anterior = passo
        if coluna.get("Qualidade", {}).get("inconsistencia_normalizacao", {}).get(
            "tem_inconsistencia"
        ):
            passo = f"Padroniza_{_var(nome)}"
            passos.append((passo, (
                f"Table.TransformColumns({anterior}, {{{{{_m_literal(nome)}, "
                "each if _ = null then null else Text.Upper(Text.Trim(_)), type text}})"
            )))
            anterior = passo

    tipos = ", ".join(
        f"{{{_m_literal(c['Coluna'])}, {_m_tipo(c['Tipo_Inferred'])}}}"
        for c in payload["colunas"] if c["Coluna"] not in remover
    )
    if tipos:
        passos.append(("Tipos", f"Table.TransformColumnTypes({anterior}, {{{tipos}}})"))
        anterior = "Tipos"

    corpo = ",\n".join(f'    #"{nome}" = {expressao}' for nome, expressao in passos)
    cabecalho = "\n".join([
        "// Passos de limpeza gerados pelo Recon.",
        f"// Tabela: {_comentario(meta['tabela'])}",
        f"// Origem: {_comentario(caminho_origem)}",
        f"// Gerado em: {meta['timestamp_utc'][:19]} UTC (Recon {meta['versao_profiler']})",
        "//",
        "// Cole no editor avançado do Power Query. Revise antes de aplicar: o mascaramento",
        "// de dado pessoal e as violações de regra de negócio ficam de fora de propósito —",
        "// as duas coisas pedem decisão sua, não automação.",
        "",
    ])
    return f"{cabecalho}let\n{corpo}\nin\n    #\"{passos[-1][0]}\"\n"


def exportar_script_limpeza_m(
    payload: dict[str, Any], caminho_origem: str, caminho_saida: str
) -> None:
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(gerar_script_limpeza_m(payload, caminho_origem))
    logger.info(f"✓ Passos em Power Query exportados: '{caminho_saida}'")

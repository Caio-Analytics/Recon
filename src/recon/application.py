from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class AcaoAnalise:
    chave: str
    aba: str
    titulo: str
    explicacao: str
    minimo: int
    cor: str
    maximo: int | None = None
    arquivo_auxiliar: str | None = None


ACOES_INTERFACE: tuple[AcaoAnalise, ...] = (
    AcaoAnalise("individual", "Analisar arquivos", "Analisar arquivos",
                "Cria um perfil completo e separado para cada arquivo selecionado.", 1, "#a78bfa"),
    AcaoAnalise("lote", "Comparar qualidade", "Comparar arquivos em lote",
                "Prioriza arquivos com mais problemas, sem misturar os relatórios individuais.", 2, "#60a5fa"),
    AcaoAnalise("modelo", "Relações", "Entender relações entre tabelas",
                "Procura chaves, fatos, dimensões e possíveis cruzamentos entre tabelas.", 2, "#22d3ee"),
    AcaoAnalise("conferencia", "Versões", "Conferir duas versões",
                "Mostra o que mudou entre uma extração anterior e a nova: volume, schema e registros.", 2, "#fbbf24", 2),
    AcaoAnalise("historico", "Evolução", "Acompanhar histórico de qualidade",
                "Compara duas ou mais extrações na ordem escolhida e destaca tendências de qualidade.", 2, "#34d399"),
    AcaoAnalise("contrato", "Contrato", "Criar contrato de dados",
                "Registra a estrutura esperada da base em YAML para revisar e reutilizar nas próximas cargas.", 1, "#fb7185", 1),
    AcaoAnalise("validar", "Validar", "Validar contra contrato",
                "Confere uma nova carga contra um contrato revisado e aponta o que saiu do esperado.", 1, "#f97316", 1,
                "Contrato YAML de referência"),
    AcaoAnalise("dicionario", "Documentar", "Gerar dicionário de dados",
                "Cria uma planilha XLSX com tipos, exemplos, semântica e recomendações de cada coluna.", 1, "#38bdf8"),
    AcaoAnalise("url", "Fonte remota", "Analisar dados por URL",
                "Lê um CSV, JSON ou Parquet por link HTTP(S), inclusive URL assinada, sem salvar credenciais.", 1, "#a78bfa", 1),
    AcaoAnalise("consulta", "Banco local", "Analisar consulta local",
                "Executa somente SELECT ou WITH em SQLite ou DuckDB local e perfila o resultado.", 0, "#fbbf24", 0),
    AcaoAnalise("semantica", "Revisar", "Revisar classificações semânticas",
                "Gera um YAML para você confirmar ou corrigir a leitura dos campos antes das próximas análises.", 1, "#5eead4", 1),
)

FORMATOS_INTERFACE: tuple[tuple[str, str, str], ...] = (
    ("html", "HTML", "abre no navegador — é o relatório para ler e compartilhar"),
    ("json", "JSON", "dados estruturados para integrações ou automação"),
    ("markdown", "Markdown", "texto para wiki, ticket ou documentação"),
    ("pdf", "PDF", "versão estática para anexar ou imprimir"),
)
PREFIXO_SAIDA = "recon"


def resolver_pasta_saida(escolha: str, arquivos: Sequence[str]) -> Path:
    limpa = escolha.strip().strip('"').strip("'")
    if limpa:
        return Path(limpa).expanduser()
    if not arquivos:
        raise ValueError("Nenhum arquivo selecionado.")
    return Path(arquivos[0]).expanduser().resolve().parent


def validar_selecao(acao: AcaoAnalise, arquivos: Sequence[str]) -> str | None:
    if acao.chave == "url":
        url = arquivos[0].strip() if arquivos else ""
        if urlparse(url).scheme not in {"http", "https"}:
            return "Informe uma URL iniciada por http:// ou https://."
        return None
    if acao.chave == "consulta":
        return None
    if len(arquivos) < acao.minimo:
        return f"'{acao.titulo}' precisa de pelo menos {acao.minimo} arquivo(s)."
    if acao.maximo is not None and len(arquivos) > acao.maximo:
        return f"'{acao.titulo}' aceita exatamente {acao.maximo} arquivos, na ordem exibida."
    faltando = [arquivo for arquivo in arquivos if not Path(arquivo).is_file()]
    if faltando:
        return f"Não encontrei mais o arquivo: {Path(faltando[0]).name}. Selecione-o novamente."
    return None


def executar_analise(
    acao: AcaoAnalise,
    arquivos: Sequence[str],
    pasta_saida: Path,
    formatos: Sequence[str],
    vocabularios: str | None = None,
    arquivo_auxiliar: str | None = None,
    nome_contrato: str | None = None,
    conexao: str | None = None,
    sql: str | None = None,
) -> tuple[list[Path], list[tuple[str, str]]]:
    from .pipeline import DataProfiler

    pasta_saida.mkdir(parents=True, exist_ok=True)
    saida_base = str(pasta_saida / PREFIXO_SAIDA)
    profiler = DataProfiler(vocabularios=vocabularios)
    caminhos = [str(caminho) for caminho in arquivos]
    escolhidos = list(formatos) or ["html"]
    falhas: list[tuple[str, str]] = []

    if acao.chave == "individual":
        for caminho in caminhos:
            profiler.processar_arquivo(caminho, saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "lote":
        _, falhas = profiler.processar_lote(caminhos, saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "modelo":
        profiler.modelar_conjunto(caminhos, saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "conferencia":
        profiler.conferir_versoes(caminhos[0], caminhos[1], saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "historico":
        profiler.analisar_historico(caminhos, saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "contrato":
        from . import contrato as contrato_mod
        from .ingestion import carregar_arquivo

        quadro, nome = carregar_arquivo(caminhos[0], limite_linhas=profiler.limite_amostra)
        contrato = contrato_mod.gerar_contrato(profiler.processar_dataframe(quadro, nome))
        nome = (nome_contrato or f"{PREFIXO_SAIDA}_contrato.yaml").strip()
        caminho_nome = Path(nome)
        if caminho_nome.name != nome or caminho_nome.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError("O nome do contrato deve terminar em .yaml ou .yml e não pode incluir pastas.")
        destino = pasta_saida / caminho_nome
        contrato_mod.salvar_contrato(contrato, str(destino))
        return [destino], falhas
    elif acao.chave == "validar":
        from . import contrato as contrato_mod
        from .ingestion import carregar_arquivo

        if not arquivo_auxiliar:
            raise ValueError("Escolha o contrato YAML de referência.")
        quadro, nome = carregar_arquivo(caminhos[0], limite_linhas=profiler.limite_amostra)
        resultado = contrato_mod.conferir_contrato(
            profiler.processar_dataframe(quadro, nome), contrato_mod.carregar_contrato(arquivo_auxiliar)
        )
        destino = pasta_saida / f"{PREFIXO_SAIDA}_validacao.md"
        linhas = ["# Validação de contrato", "", resultado["resumo"], ""]
        if resultado.get("avisos"):
            linhas.extend(["## Avisos", *[f"- {aviso}" for aviso in resultado["avisos"]], ""])
        violacoes = [
            f"- {item['severidade']} **{item['tipo']}** — {item['mensagem']}"
            for item in resultado["violacoes"]
        ]
        linhas.extend(["## Violações", *(violacoes or ["- Nenhuma violação encontrada."])])
        destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return [destino], falhas
    elif acao.chave == "dicionario":
        from . import reporting
        from .ingestion import carregar_arquivo

        payloads = []
        for caminho in caminhos:
            quadro, nome = carregar_arquivo(caminho, limite_linhas=profiler.limite_amostra)
            payloads.append(profiler.processar_dataframe(quadro, nome))
        destino = pasta_saida / f"{PREFIXO_SAIDA}_dicionario.xlsx"
        reporting.exportar_dicionario_xlsx(payloads, str(destino))
        return [destino], falhas
    elif acao.chave == "url":
        profiler.processar_arquivo(caminhos[0], saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "consulta":
        if not conexao or not sql:
            raise ValueError("Informe a conexão local e uma consulta SELECT ou WITH.")
        profiler.processar_consulta(conexao, sql, saida_base=saida_base, formatos=escolhidos)
    elif acao.chave == "semantica":
        from . import semantics
        from .ingestion import carregar_arquivo

        quadro, nome = carregar_arquivo(caminhos[0], limite_linhas=profiler.limite_amostra)
        destino = pasta_saida / f"{PREFIXO_SAIDA}_correcoes_semanticas.yaml"
        semantics.exportar_modelo_de_correcoes(profiler.processar_dataframe(quadro, nome), str(destino))
        return [destino], falhas
    else:
        raise ValueError(f"Ação de interface desconhecida: {acao.chave}.")

    for padrao in (
        f"{PREFIXO_SAIDA}*.html", f"{PREFIXO_SAIDA}*.pdf", f"{PREFIXO_SAIDA}*.md",
        f"{PREFIXO_SAIDA}*.json",
    ):
        gerados = sorted(pasta_saida.glob(padrao))
        if gerados:
            return gerados, falhas
    return [], falhas


def abrir_no_explorador(caminho: Path) -> None:
    abrir_nativo = getattr(os, "startfile", None)
    if abrir_nativo is not None:
        abrir_nativo(str(caminho))
        return
    subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(caminho)], check=False)

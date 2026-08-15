"""Relatório do modelo de dados inferido para um conjunto de tabelas."""
from html import escape
from typing import Any

from loguru import logger

from ._html import _CSS


def _var(nome: str) -> str:
    limpo = "".join(ch if ch.isalnum() else "_" for ch in nome.lower()).strip("_")
    return limpo or "tabela"


def _mermaid(payload: dict[str, Any]) -> str:
    """Diagrama entidade-relacionamento em Mermaid.

    Renderiza direto no GitHub e no VS Code sem plugin — é o formato de
    diagrama que sobrevive num README, ao contrário de uma imagem gerada.
    """
    linhas = ["erDiagram"]
    for tabela in payload["tabelas"]:
        rotulo = _var(tabela["nome"]).upper()
        campos = []
        for chave in tabela["chaves_primarias"][:1]:
            campos.append(f"    string {_var(chave)} PK")
        for medida in tabela["medidas"][:3]:
            campos.append(f"    number {_var(medida)}")
        for atributo in tabela["atributos"][:3]:
            campos.append(f"    string {_var(atributo)}")
        linhas.append(f"  {rotulo} {{")
        linhas.extend(campos or ["    string sem_colunas_relevantes"])
        linhas.append("  }")
    for relacao in payload["relacionamentos"]:
        origem = _var(relacao["tabela_origem"]).upper()
        destino = _var(relacao["tabela_destino"]).upper()
        simbolo = "||--||" if relacao["cardinalidade"] == "1:1" else "}o--||"
        linhas.append(f'  {origem} {simbolo} {destino} : "{relacao["coluna_origem"]}"')
    return "```mermaid\n" + "\n".join(linhas) + "\n```"


def _tabela_md(linhas: list[list[Any]], cabecalhos: list[str]) -> str:
    out = ["| " + " | ".join(cabecalhos) + " |", "|" + "---|" * len(cabecalhos)]
    for linha in linhas:
        out.append("| " + " | ".join(str(v) for v in linha) + " |")
    return "\n".join(out)


def _preambulo_carregamento(payload: dict[str, Any]) -> str:
    linhas = ["```python", "import pandas as pd", ""]
    for tabela in payload["tabelas"]:
        origem = tabela["origem"] or f"{tabela['nome']}.csv"
        if "::" in origem:
            arquivo, aba = origem.split("::", 1)
            linhas.append(
                f'{_var(tabela["nome"])} = pd.read_excel(r"{arquivo}", sheet_name="{aba}")'
            )
        elif origem.lower().endswith((".xlsx", ".xls", ".xlsb")):
            linhas.append(f'{_var(tabela["nome"])} = pd.read_excel(r"{origem}")')
        else:
            linhas.append(f'{_var(tabela["nome"])} = pd.read_csv(r"{origem}")')
    linhas.append("```")
    return "\n".join(linhas)


def exportar_modelo_markdown(payload: dict[str, Any], caminho: str) -> None:
    meta = payload["metadados_execucao"]
    partes: list[str] = [f"# Modelo de Dados Inferido — {meta['conjunto']}", ""]
    partes.append(
        f"- Tabelas: {meta['total_tabelas']} | Relacionamentos: "
        f"{meta['total_relacionamentos']} | Análises sugeridas: "
        f"{meta['total_analises_sugeridas']}"
    )

    partes.append("\n## Tabelas\n")
    partes.append(_tabela_md(
        [[t["nome"], t["papel"], f"{t['linhas']:,}", t["colunas"],
          ", ".join(f"`{c}`" for c in t["chaves_primarias"]) or "—",
          f"{t['score_qualidade']}", t["justificativa"]]
         for t in payload["tabelas"]],
        ["Tabela", "Papel", "Linhas", "Colunas", "Chave primária", "Qualidade", "Por quê"],
    ))

    partes.append("\n## Relacionamentos\n")
    if payload["relacionamentos"]:
        partes.append(_tabela_md(
            [[f"`{r['tabela_origem']}.{r['coluna_origem']}`",
              f"`{r['tabela_destino']}.{r['coluna_destino']}`",
              r["cardinalidade"], f"{r['contencao_linhas']:.1%}", f"{r['confianca']:.0%}",
              " · ".join(filter(None, [
                  "⚠️ tipos diferentes" if r["tipos_incompativeis"] else "",
                  f"⚠️ {r['pct_orfaos']:.1%} órfãos" if r["pct_orfaos"] > 0 else "",
              ])) or "ok"]
             for r in payload["relacionamentos"]],
            ["De", "Para", "Cardinalidade", "Linhas cobertas", "Confiança", "Observação"],
        ))
        partes.append("")
        partes.append(_mermaid(payload))
    else:
        partes.append(
            "Nenhuma chave estrangeira detectada entre as tabelas. "
            "Elas parecem não se relacionar — ou a chave existe mas com valores "
            "formatados de forma diferente em cada arquivo."
        )

    if payload["avisos"]:
        partes.append("\n## Avisos de integridade\n")
        for aviso in payload["avisos"]:
            partes.append(f"- **{aviso['severidade']}** [{aviso['tipo']}] {aviso['mensagem']}")

    partes.append("\n## Como carregar as tabelas\n")
    partes.append(_preambulo_carregamento(payload))

    partes.append("\n## Análises sugeridas\n")
    if payload["analises_sugeridas"]:
        partes.append(
            "Cada bloco abaixo é código pronto para rodar sobre os DataFrames carregados acima.\n"
        )
        for i, analise in enumerate(payload["analises_sugeridas"], start=1):
            partes.append(f"### {i}. {analise['titulo']}\n")
            partes.append(analise["descricao"] + "\n")
            partes.append("```python\n" + analise["pandas"] + "\n```\n")
            partes.append("<details><summary>Equivalente em SQL</summary>\n")
            partes.append("```sql\n" + analise["sql"] + "\n```\n")
            partes.append("</details>\n")
    else:
        partes.append(
            "Nenhuma análise cruzada sugerida — sem relacionamentos entre as tabelas, "
            "cada uma só rende análise isolada (veja o relatório individual de cada uma)."
        )

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(partes) + "\n")
    logger.info(f"✓ Modelo (Markdown) exportado: '{caminho}'")


def _e(valor: Any) -> str:
    return escape(str(valor), quote=False)


def exportar_modelo_html(payload: dict[str, Any], caminho: str) -> None:
    meta = payload["metadados_execucao"]
    partes: list[str] = [
        f"<h1>Modelo de Dados Inferido — {_e(meta['conjunto'])}</h1>",
        f'<p class="sub">{meta["total_tabelas"]} tabelas · '
        f'{meta["total_relacionamentos"]} relacionamentos · '
        f'{meta["total_analises_sugeridas"]} análises sugeridas</p>',
    ]

    partes.append("<h2>Tabelas</h2><div class='tabela-wrap'><table><thead><tr>"
                  "<th>Tabela</th><th>Papel</th><th>Linhas</th><th>Chave primária</th>"
                  "<th>Qualidade</th><th>Por quê</th></tr></thead><tbody>")
    for t in payload["tabelas"]:
        chaves = ", ".join(f"<code>{_e(c)}</code>" for c in t["chaves_primarias"]) or "—"
        partes.append(
            f"<tr><td><b>{_e(t['nome'])}</b></td><td>{_e(t['papel'])}</td>"
            f"<td>{t['linhas']:,}</td><td>{chaves}</td>"
            f"<td>{t['score_qualidade']}</td><td>{_e(t['justificativa'])}</td></tr>"
        )
    partes.append("</tbody></table></div>")

    partes.append("<h2>Relacionamentos</h2>")
    if payload["relacionamentos"]:
        partes.append("<div class='tabela-wrap'><table><thead><tr><th>De</th><th>Para</th>"
                      "<th>Cardinalidade</th><th>Cobertura</th><th>Confiança</th>"
                      "<th>Observação</th></tr></thead><tbody>")
        for r in payload["relacionamentos"]:
            marcas = []
            if r["tipos_incompativeis"]:
                marcas.append("tipos diferentes")
            if r["pct_orfaos"] > 0:
                marcas.append(f"{r['pct_orfaos']:.1%} órfãos")
            obs = (f"<span class='alerta'>{_e(' · '.join(marcas))}</span>"
                   if marcas else "ok")
            partes.append(
                f"<tr><td><code>{_e(r['tabela_origem'])}.{_e(r['coluna_origem'])}</code></td>"
                f"<td><code>{_e(r['tabela_destino'])}.{_e(r['coluna_destino'])}</code></td>"
                f"<td>{_e(r['cardinalidade'])}</td><td>{r['contencao_linhas']:.1%}</td>"
                f"<td>{r['confianca']:.0%}</td><td>{obs}</td></tr>"
            )
        partes.append("</tbody></table></div>")
    else:
        partes.append("<p class='vazio'>Nenhuma chave estrangeira detectada.</p>")

    if payload["avisos"]:
        partes.append("<h2>Avisos de integridade</h2><ul>")
        for aviso in payload["avisos"]:
            partes.append(
                f"<li><b>{_e(aviso['severidade'])}</b> [{_e(aviso['tipo'])}] "
                f"{_e(aviso['mensagem'])}</li>"
            )
        partes.append("</ul>")

    partes.append("<h2>Análises sugeridas</h2>")
    for i, analise in enumerate(payload["analises_sugeridas"], start=1):
        partes.append(
            f"<div class='coluna'><h3>{i}. {_e(analise['titulo'])}</h3>"
            f"<div class='meta'>{_e(analise['descricao'])}</div>"
            f"<pre><code>{_e(analise['pandas'])}</code></pre></div>"
        )

    documento = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Modelo — {_e(meta['conjunto'])}</title>"
        f"<style>{_CSS}\npre {{ overflow-x: auto; background: var(--fundo); "
        "border: 1px solid var(--borda); border-radius: 8px; padding: .75rem; "
        "font-size: 12.5px; }</style></head>"
        f"<body><main>{''.join(partes)}</main></body></html>"
    )
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(documento)
    logger.info(f"✓ Modelo (HTML) exportado: '{caminho}'")

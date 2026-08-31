"""Relatório consolidado de lote: vários arquivos num HTML só.

`perfilar` descreve um único arquivo. O lote compara vários arquivos entre
si — quais prestam e por onde começar — o que exige comparação lado a lado,
não relatórios individuais empilhados.

Por isso a saída é um arquivo único, com um painel de comparação no topo e
cada tabela em bloco recolhível abaixo. Um HTML por arquivo obrigaria a abrir
doze abas para descobrir qual tem problema.
"""
from html import escape
from typing import Any

from loguru import logger

from .. import quality
from ._graficos import CSS_GRAFICOS, barra_completude
from ._html import _CSS, _cor_score

_MAX_PROBLEMAS_POR_TABELA = 5


def _e(valor: Any) -> str:
    return escape(str(valor), quote=False)


_CSS_LOTE = CSS_GRAFICOS + """
details.tabela { border: 1px solid var(--borda); border-radius: 10px; margin-bottom: .6rem;
                 background: var(--fundo-alt); }
details.tabela > summary { cursor: pointer; padding: .8rem 1rem; font-weight: 600;
                           list-style: none; display: flex; align-items: center; gap: .75rem; }
details.tabela > summary::-webkit-details-marker { display: none; }
details.tabela > summary::before { content: "▸"; color: var(--texto-fraco); }
details.tabela[open] > summary::before { content: "▾"; }
details.tabela .corpo { padding: 0 1rem 1rem; }
.nota { display: inline-flex; align-items: center; justify-content: center;
        width: 1.9rem; height: 1.9rem; border-radius: 50%; font-weight: 700;
        color: #fff; font-size: .85rem; flex: none; }
.resumo-linha { color: var(--texto-fraco); font-weight: 400; font-size: .85rem;
                margin-left: auto; text-align: right; }
.mini { font-size: 12.5px; }
.mini td, .mini th { padding: .3rem .5rem; }
"""


def _painel_comparativo(perfis: list[dict[str, Any]]) -> str:
    """Tabela de comparação entre os arquivos do lote."""
    linhas = []
    for p in sorted(perfis, key=lambda x: x["score"]):
        cor = _cor_score(p["score"])
        alertas = []
        if p["amostrado"]:
            alertas.append("amostrado")
        if p["duplicadas"]:
            alertas.append(f"{p['duplicadas']:,} duplicadas")
        if p["sensiveis"]:
            alertas.append(f"{p['sensiveis']} col. LGPD")
        linhas.append(
            f"<tr><td><b>{_e(p['tabela'])}</b></td>"
            f'<td><span class="nota" style="background:{cor}">{p["nota"]}</span> '
            f'{p["score"]:.0f}</td>'
            f"<td>{p['linhas']:,}</td><td>{p['colunas']}</td>"
            f"<td>{p['comprometidas']}</td>"
            f"<td>{p['alta']}</td>"
            f"<td>{_e(', '.join(alertas)) or '—'}</td></tr>"
        )
    return (
        '<div class="tabela-wrap"><table><thead><tr>'
        "<th>Arquivo</th><th>Qualidade</th><th>Linhas</th><th>Colunas</th>"
        "<th>Col. comprometidas</th><th>Achados 🔴</th><th>Observações</th>"
        "</tr></thead><tbody>" + "".join(linhas) + "</tbody></table></div>"
    )


def _bloco_tabela(payload: dict[str, Any], aberto: bool) -> str:
    meta = payload["metadados_execucao"]
    score = meta.get("score_qualidade", {})
    recomendacoes = quality.ordenar_por_prioridade(payload["recomendacoes_etl"])
    criticas = [r for r in recomendacoes if r["Prioridade"] == quality.PRIORIDADE_ALTA]
    cor = _cor_score(float(score.get("score", 0)))

    problemas = "".join(
        f"<li><code>{_e(r['Coluna'])}</code> — {_e(r['Acao'])}</li>"
        for r in criticas[:_MAX_PROBLEMAS_POR_TABELA]
    )
    resto = len(criticas) - _MAX_PROBLEMAS_POR_TABELA
    if resto > 0:
        problemas += f"<li class='vazio'>+{resto} outros achados de prioridade alta</li>"

    colunas = "".join(
        f"<tr><td><code>{_e(c['Coluna'])}</code></td>"
        f"<td>{_e(c['Tipo_Inferred'])}</td><td>{_e(c['Semantica_IA'])}</td>"
        f"<td>{c['Pct_Nulos']:.1f}%</td><td>{c['Qtd_Unicos']:,}</td>"
        f"<td>{barra_completude(float(c['Pct_Nulos']), float(c.get('Qualidade', {}).get('sentinelas', {}).get('pct_total', 0) or 0))}</td>"
        f"<td>{_e(c['Caracteristica'])}</td></tr>"
        for c in payload["colunas"]
    )

    avisos_layout = ""
    layout = meta.get("layout") or {}
    if layout.get("avisos"):
        itens = "".join(
            f"<li><b>{_e(a['severidade'])}</b> {_e(a['mensagem'])}</li>"
            for a in layout["avisos"]
        )
        avisos_layout = f"<p class='sub'>Como o arquivo foi lido:</p><ul>{itens}</ul>"

    amostragem = (
        '<p class="sub"><b class="alerta">⚠️ Amostragem aplicada</b> — unicidade e '
        "duplicata valem para a amostra, não para a tabela inteira.</p>"
        if meta.get("amostragem_aplicada") else ""
    )

    return (
        f'<details class="tabela"{" open" if aberto else ""}>'
        f'<summary><span class="nota" style="background:{cor}">{score.get("nota", "?")}</span>'
        f'<span>{_e(meta["tabela"])}</span>'
        f'<span class="resumo-linha">{meta["linhas_originais"]:,} linhas · '
        f'{meta["total_colunas"]} colunas · {len(criticas)} achados 🔴</span></summary>'
        f'<div class="corpo">{amostragem}{avisos_layout}'
        + (f"<p class='sub'>Principais problemas:</p><ol>{problemas}</ol>" if problemas else
           "<p class='vazio'>Nenhum achado de prioridade alta.</p>")
        + '<div class="tabela-wrap"><table class="mini"><thead><tr><th>Coluna</th>'
          "<th>Tipo</th><th>Semântica</th><th>% Nulos</th><th>Únicos</th>"
          "<th>Completude</th><th>Característica</th></tr></thead><tbody>"
        + colunas + "</tbody></table></div></div></details>"
    )


def exportar_lote_html(payloads: list[dict[str, Any]], caminho: str, titulo: str) -> None:
    """Consolida os perfis de vários arquivos num relatório único."""
    perfis = []
    for payload in payloads:
        meta = payload["metadados_execucao"]
        score = meta.get("score_qualidade", {})
        perfis.append({
            "tabela": meta["tabela"],
            "score": float(score.get("score", 0)),
            "nota": score.get("nota", "?"),
            "linhas": meta["linhas_originais"],
            "colunas": meta["total_colunas"],
            "comprometidas": score.get("colunas_comprometidas", 0),
            "alta": sum(1 for r in payload["recomendacoes_etl"] if "ALTA" in r["Prioridade"]),
            "amostrado": meta.get("amostragem_aplicada", False),
            "duplicadas": meta.get("duplicatas", {}).get("qtd_linhas_duplicadas", 0),
            "sensiveis": meta["resumo_qualidade"]["colunas_sensiveis_lgpd"],
        })

    total_linhas = sum(p["linhas"] for p in perfis)
    total_alta = sum(p["alta"] for p in perfis)
    pior = min(perfis, key=lambda p: p["score"]) if perfis else None
    media = sum(p["score"] for p in perfis) / len(perfis) if perfis else 0.0

    cartoes = [
        ("Arquivos", f"{len(perfis)}"),
        ("Linhas no total", f"{total_linhas:,}"),
        ("Qualidade média", f"{media:.0f}"),
        ("Achados 🔴", f"{total_alta}"),
        ("Pior arquivo", pior["tabela"] if pior else "—"),
    ]

    partes = [
        f"<h1>Perfilamento em lote — {_e(titulo)}</h1>",
        f'<p class="sub">{len(perfis)} arquivo(s) · {total_linhas:,} linhas no total. '
        "A tabela abaixo ordena do pior para o melhor: comece por cima.</p>",
        '<div class="cartoes">'
        + "".join(
            f'<div class="cartao"><div class="rotulo">{_e(r)}</div>'
            f'<div class="valor">{_e(v)}</div></div>' for r, v in cartoes
        )
        + "</div>",
        "<h2>Comparação entre os arquivos</h2>",
        _painel_comparativo(perfis),
        "<h2>Detalhe de cada arquivo</h2>",
        "<p class='sub'>Clique para abrir. O de pior qualidade já vem aberto.</p>",
    ]

    ordenados = sorted(payloads, key=lambda p: p["metadados_execucao"]["score_qualidade"]["score"])
    partes += [_bloco_tabela(p, aberto=(i == 0)) for i, p in enumerate(ordenados)]

    documento = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Lote — {_e(titulo)}</title><style>{_CSS}{_CSS_LOTE}</style></head>"
        f"<body><main>{''.join(partes)}</main></body></html>"
    )
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(documento)
    logger.info(f"✓ Relatório de lote exportado: '{caminho}' ({len(perfis)} arquivos)")

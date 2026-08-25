"""Relatório HTML autocontido.

Um arquivo único, sem CSS ou JS externo — é o formato que circula por e-mail
e abre em qualquer máquina corporativa sem depender de ferramenta instalada.
Acompanha o tema do sistema (claro/escuro) e imprime em PDF sem quebrar.
"""
from html import escape
from typing import Any

from loguru import logger

from .. import quality
from ._graficos import CSS_GRAFICOS, barra_completude, graficos_da_coluna

_CSS = CSS_GRAFICOS + """
:root {
  --fundo: #ffffff; --fundo-alt: #f6f7f9; --borda: #e2e5ea;
  --texto: #1a1d21; --texto-fraco: #5c636e; --acento: #2563eb;
  --alta: #dc2626; --media: #d97706; --baixa: #059669;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fundo: #14171a; --fundo-alt: #1c2024; --borda: #2c3138;
    --texto: #e6e8eb; --texto-fraco: #9aa2ad; --acento: #60a5fa;
    --alta: #f87171; --media: #fbbf24; --baixa: #34d399;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.25rem 4rem; background: var(--fundo); color: var(--texto);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 1180px; margin: 0 auto; }
h1 { font-size: 1.7rem; margin: 0 0 .25rem; }
h2 { font-size: 1.2rem; margin: 2.5rem 0 .75rem; padding-bottom: .35rem;
     border-bottom: 1px solid var(--borda); }
h3 { font-size: 1rem; margin: 1.5rem 0 .5rem; }
p.sub { color: var(--texto-fraco); margin: 0 0 1.5rem; }
code { background: var(--fundo-alt); padding: .1em .35em; border-radius: 4px;
       font: 13px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; }
.cartoes { display: flex; flex-wrap: wrap; gap: .75rem; margin: 1rem 0 0; }
.cartao { flex: 1 1 150px; background: var(--fundo-alt); border: 1px solid var(--borda);
          border-radius: 10px; padding: .8rem 1rem; }
.cartao .rotulo { font-size: .75rem; text-transform: uppercase; letter-spacing: .04em;
                  color: var(--texto-fraco); }
.cartao .valor { font-size: 1.5rem; font-weight: 600; margin-top: .15rem; }
.score { display: flex; align-items: center; gap: 1.25rem; background: var(--fundo-alt);
         border: 1px solid var(--borda); border-radius: 12px; padding: 1.1rem 1.4rem; }
.score .nota { font-size: 2.6rem; font-weight: 700; line-height: 1; }
.score .barra { flex: 1; height: 10px; background: var(--borda); border-radius: 999px;
                overflow: hidden; }
.score .barra span { display: block; height: 100%; border-radius: 999px; }
.tabela-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th, td { text-align: left; padding: .5rem .65rem; border-bottom: 1px solid var(--borda);
         vertical-align: top; }
th { position: sticky; top: 0; background: var(--fundo); font-weight: 600;
     color: var(--texto-fraco); font-size: .78rem; text-transform: uppercase;
     letter-spacing: .03em; }
tbody tr:hover { background: var(--fundo-alt); }
.tag { display: inline-block; padding: .1em .5em; border-radius: 999px; font-size: .72rem;
       font-weight: 600; border: 1px solid currentColor; white-space: nowrap; }
.p-alta { color: var(--alta); } .p-media { color: var(--media); } .p-baixa { color: var(--baixa); }
.coluna { border: 1px solid var(--borda); border-radius: 10px; padding: .9rem 1.1rem;
          margin-bottom: .75rem; background: var(--fundo-alt); }
.coluna h3 { margin: 0 0 .1rem; font-size: .98rem; }
.coluna .meta { color: var(--texto-fraco); font-size: .82rem; margin-bottom: .5rem; }
.coluna ul { margin: 0; padding-left: 1.1rem; }
.coluna li { margin: .15rem 0; }
.alerta { color: var(--media); }
.vazio { color: var(--texto-fraco); font-style: italic; }
@media print {
  body { padding: 0; } .coluna, .cartao, .score { break-inside: avoid; }
  th { position: static; }
}
"""

_MAX_PROBLEMAS_DESTAQUE = 6

_CLASSE_PRIORIDADE = {
    quality.PRIORIDADE_ALTA: "p-alta",
    quality.PRIORIDADE_MEDIA: "p-media",
    quality.PRIORIDADE_BAIXA: "p-baixa",
    quality.PRIORIDADE_INFO: "p-baixa",
}


def _e(valor: Any) -> str:
    return escape(str(valor), quote=False)


def _num(valor: Any) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, int):
        return f"{valor:,}"
    if isinstance(valor, float):
        return f"{valor:,.2f}"
    return str(valor)


def _pct(fracao: float | None) -> str:
    return "—" if fracao is None else f"{fracao:.1%}"


def _cor_score(score: float) -> str:
    if score >= 75:
        return "var(--baixa)"
    if score >= 50:
        return "var(--media)"
    return "var(--alta)"


def _tabela(cabecalhos: list[str], linhas: list[list[str]]) -> str:
    if not linhas:
        return '<p class="vazio">Nada a reportar nesta seção.</p>'
    cabecalho = "".join(f"<th>{_e(h)}</th>" for h in cabecalhos)
    corpo = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in linha) + "</tr>" for linha in linhas
    )
    return f'<div class="tabela-wrap"><table><thead><tr>{cabecalho}</tr></thead><tbody>{corpo}</tbody></table></div>'


def _bloco_coluna(coluna: dict[str, Any]) -> str:
    from ._markdown import _alertas_coluna, _linha_testes

    extras = coluna.get("Stats_Extra") or {}
    qual = coluna.get("Qualidade", {})
    itens: list[str] = []

    base = (
        f"Nulos: <b>{_num(coluna['Qtd_Nulos'])}</b> ({coluna['Pct_Nulos']:.1f}%)"
    )
    if qual.get("nulos_efetivos_qtd", 0) > coluna["Qtd_Nulos"]:
        base += f" · nulos efetivos <b>{qual['nulos_efetivos_pct']:.1f}%</b>"
    base += f" · Únicos: <b>{_num(coluna['Qtd_Unicos'])}</b> ({_pct(coluna['Ratio_Unicidade'])})"
    itens.append(base)

    if "min" in extras:
        itens.append(
            f"Faixa: {_num(extras['min'])} → {_num(extras['max'])} · média {_num(extras.get('media'))}"
            f" · mediana {_num(extras.get('mediana'))} · desvio {_num(extras.get('desvio_padrao'))}"
        )
    if "min_data" in extras:
        itens.append(
            f"Período: {_e(extras['min_data'][:10])} → {_e(extras['max_data'][:10])} "
            f"({_num(extras.get('range_dias'))} dias, {_num(extras.get('meses_cobertos'))} meses)"
        )
    if "str_len_min" in extras:
        itens.append(
            f"Comprimento: {_num(extras['str_len_min'])}–{_num(extras['str_len_max'])} "
            f"(média {_num(extras['str_len_media'])})"
        )
    if "qtd_true" in extras:
        itens.append(
            f"Verdadeiros: {_num(extras['qtd_true'])} ({_pct(extras['pct_true'])}) · "
            f"Falsos: {_num(extras['qtd_false'])}"
        )

    outliers = extras.get("outliers_iqr") or {}
    if outliers.get("qtd_outliers_total"):
        itens.append(
            f"Outliers: {_num(outliers['qtd_outliers_total'])} fora de "
            f"[{_num(outliers['limite_inferior'])}, {_num(outliers['limite_superior'])}] "
            f"— {_e(outliers.get('metodo', 'IQR'))}"
        )

    top = extras.get("distribuicao_top5") or []
    if top:
        itens.append(
            "Mais frequentes: "
            + ", ".join(f"<code>{_e(d['valor'])}</code> ({d['frequencia_pct']})" for d in top)
        )

    if coluna.get("Semantica_Origem") and coluna["Semantica_Origem"] != "Unmatched":
        itens.append(
            f"Semântica inferida ({_pct(coluna.get('Semantica_Score'))} de confiança): "
            f"{_e(coluna['Semantica_Origem'])}"
        )

    if coluna.get("Semantica_Conclusiva") is False:
        alternativas = [
            f"{h['semantica']} ({_pct(h['confianca'])})"
            for h in (coluna.get("Semantica_Hipoteses") or [])
            if h["semantica"] != coluna["Semantica_IA"]
        ]
        if alternativas:
            itens.append(
                '<span class="alerta">Classificação não conclusiva — outras leituras: '
                + _e(", ".join(alternativas[:3])) + "</span>"
            )

    if coluna.get("Amostra_Valores"):
        amostra = str(coluna["Amostra_Valores"])
        if len(amostra) > 200:
            amostra = amostra[:200] + "…"
        itens.append(f"Amostra: <code>{_e(amostra)}</code>")

    testes = _linha_testes(extras.get("testes_hipotese") or {})
    if testes:
        itens.append("Testes: " + _e(" · ".join(testes)))

    otim = coluna.get("Otimizacao") or {}
    if otim.get("dtype_sugerido"):
        itens.append(
            f"Otimização: <code>{_e(otim['dtype_atual'])}</code> → "
            f"<code>{_e(otim['dtype_sugerido'])}</code> economiza "
            f"{_num(otim.get('economia_mb'))} MB ({_pct(otim.get('economia_pct'))})"
        )

    for alerta in _alertas_coluna(coluna):
        itens.append(f'<span class="alerta">{_e(alerta)}</span>')

    semantica = _e(coluna["Semantica_IA"])
    if coluna.get("Dominio") and coluna["Dominio"] != coluna["Semantica_IA"]:
        semantica += f" · domínio: {_e(coluna['Dominio'])}"

    pct_sent = float(qual.get("sentinelas", {}).get("pct_total", 0.0) or 0.0)
    completude = barra_completude(float(coluna.get("Pct_Nulos", 0.0)), pct_sent)
    legenda = (
        '<div class="legenda-completude"><span class="leg-ok">preenchido</span>'
        + ('<span class="leg-sent">nulo disfarçado</span>' if pct_sent > 0 else "")
        + ('<span class="leg-nulo">nulo</span>' if coluna.get("Pct_Nulos", 0) > 0 else "")
        + "</div>"
    ) if completude else ""

    lista = "".join(f"<li>{item}</li>" for item in itens)
    return (
        f'<div class="coluna"><h3><code>{_e(coluna["Coluna"])}</code></h3>'
        f'<div class="meta">{_e(coluna["Tipo_Inferred"])} · {semantica} · '
        f'{_e(coluna["Caracteristica"])}</div>'
        f'{completude}{legenda}{graficos_da_coluna(coluna)}'
        f'<ul>{lista}</ul></div>'
    )


def exportar_html(payload: dict[str, Any], caminho: str) -> None:
    meta = payload["metadados_execucao"]
    resumo = meta["resumo_qualidade"]
    score = meta.get("score_qualidade", {})
    duplicatas = meta.get("duplicatas", {})
    partes: list[str] = []

    partes.append(f"<h1>Perfilamento — {_e(meta['tabela'])}</h1>")
    partes.append(
        f'<p class="sub">{meta["linhas_analisadas"]:,} linhas analisadas de '
        f'{meta["linhas_originais"]:,} · {meta["total_colunas"]} colunas · '
        f'gerado em {_e(meta["timestamp_utc"][:19])} UTC</p>'
    )

    if meta.get("amostragem_aplicada"):
        partes.append(
            '<p class="sub"><b class="alerta">⚠️ Amostragem aplicada.</b> As métricas de '
            'unicidade, chave primária e duplicata valem para a amostra, não para a tabela '
            'inteira — numa amostra elas só podem ser subestimadas, o que gera "chave '
            'primária potencial" que não existe na base completa.</p>'
        )

    risco = meta.get("risco_lgpd") or {}
    if risco.get("colunas_sensiveis"):
        colunas = ", ".join(
            f"<code>{_e(c['coluna'])}</code> ({_e(c['tipo'])})"
            for c in risco["colunas_sensiveis"][:6]
        )
        partes.append(
            f'<h2>Exposição de dado pessoal — {_e(risco["nivel"])}</h2>'
            f'<p class="sub">{colunas}. {_e(risco["recomendacao"])}</p>'
        )

    if score:
        largura = max(0.0, min(100.0, float(score["score"])))
        cor = _cor_score(largura)
        penalidades = "".join(
            f"<li><b>{_e(p['dimensao'])}</b> — {p['pontos_perdidos']} pontos</li>"
            for p in score.get("penalidades", [])[:5]
        )
        partes.append(
            f'<div class="score"><div><div class="nota" style="color:{cor}">'
            f'{score["nota"]}</div></div><div style="flex:1">'
            f'<div><b>{score["score"]}</b> / 100 de qualidade</div>'
            f'<div class="barra"><span style="width:{largura}%;background:{cor}"></span></div>'
            f'</div></div>'
        )
        if penalidades:
            partes.append(
                f"<p class='sub' style='margin-top:.75rem'>Principais penalidades:</p>"
                f"<ul>{penalidades}</ul>"
            )
        criticas = score.get("colunas_criticas") or []
        if criticas:
            itens = "".join(
                f"<li><code>{_e(c['coluna'])}</code> — {c['dano']:.0%} comprometida "
                f"({_e(', '.join(c['motivos']))})</li>"
                for c in criticas[:5]
            )
            partes.append(
                f"<p class='sub'>Colunas mais comprometidas "
                f"({score.get('colunas_comprometidas', 0)} no total):</p><ul>{itens}</ul>"
            )

    cartoes = [
        ("Colunas", f"{meta['total_colunas']}"),
        ("Com nulos", f"{resumo['colunas_com_nulos']}"),
        ("100% vazias", f"{resumo['colunas_100pct_nulas']}"),
        ("Sensíveis LGPD", f"{resumo['colunas_sensiveis_lgpd']}"),
        ("Linhas duplicadas", f"{duplicatas.get('qtd_linhas_duplicadas', 0):,}"),
        ("Recomendações", f"{resumo['total_recomendacoes']}"),
    ]
    partes.append(
        '<div class="cartoes">'
        + "".join(
            f'<div class="cartao"><div class="rotulo">{_e(r)}</div>'
            f'<div class="valor">{_e(v)}</div></div>'
            for r, v in cartoes
        )
        + "</div>"
    )

    layout = meta.get("layout") or {}
    if layout.get("avisos"):
        partes.append("<h2>Como o arquivo foi lido</h2>")
        partes.append(
            "<p class='sub'>A tabela analisada não é literalmente o que está no arquivo — "
            "o layout foi ajustado antes de perfilar.</p><ul>"
        )
        for aviso in layout["avisos"]:
            partes.append(
                f"<li><b>{_e(aviso['severidade'])}</b> [{_e(aviso['tipo'])}] "
                f"{_e(aviso['mensagem'])}</li>"
            )
        partes.append("</ul>")

    recomendacoes = quality.ordenar_por_prioridade(payload["recomendacoes_etl"])

    # O leitor de HTML costuma ser quem não vai ler o relatório inteiro. A
    # lista curta do que é crítico precisa vir antes da tabela completa.
    criticas = [r for r in recomendacoes if r["Prioridade"] == quality.PRIORIDADE_ALTA]
    if criticas:
        itens = "".join(
            f"<li><code>{_e(r['Coluna'])}</code> — {_e(r['Acao'])}</li>"
            for r in criticas[:_MAX_PROBLEMAS_DESTAQUE]
        )
        restantes = len(criticas) - _MAX_PROBLEMAS_DESTAQUE
        sobra = (f"<p class='sub'>(+{restantes} outras de prioridade alta na tabela abaixo)</p>"
                 if restantes > 0 else "")
        partes.append(f"<h2>Principais problemas</h2><ol>{itens}</ol>{sobra}")

    partes.append("<h2>Recomendações de ETL</h2>")
    partes.append(_tabela(
        ["Prioridade", "Camada", "Coluna", "Ação"],
        [[
            f'<span class="tag {_CLASSE_PRIORIDADE.get(r["Prioridade"], "")}">{_e(r["Prioridade"])}</span>',
            _e(r["Camada"]), f'<code>{_e(r["Coluna"])}</code>', _e(r["Acao"]),
        ] for r in recomendacoes],
    ))

    partes.append("<h2>Visão geral das colunas</h2>")
    partes.append(_tabela(
        ["Coluna", "Tipo", "Semântica", "% Nulos", "Únicos", "Característica"],
        [[
            f'<code>{_e(c["Coluna"])}</code>', _e(c["Tipo_Inferred"]), _e(c["Semantica_IA"]),
            f'{c["Pct_Nulos"]:.1f}%', f'{c["Qtd_Unicos"]:,}', _e(c["Caracteristica"]),
        ] for c in payload["colunas"]],
    ))

    partes.append("<h2>Detalhe por coluna</h2>")
    partes.extend(_bloco_coluna(c) for c in payload["colunas"])

    partes.append("<h2>Relações entre colunas</h2>")
    linhas_rel: list[list[str]] = []
    for d in payload.get("dependencias_funcionais", []):
        seta = "↔" if d["tipo"].startswith("Equivalência") else "→"
        linhas_rel.append([_e(d["tipo"]), f'<code>{_e(d["determinante"])}</code> {seta} '
                           f'<code>{_e(d["dependente"])}</code>', _e(d["descricao"])])
    for r in payload.get("colunas_redundantes", []):
        linhas_rel.append(["Coluna redundante",
                           f'<code>{_e(r["coluna"])}</code> = <code>{_e(r["coluna_redundante"])}</code>',
                           _e(r["descricao"])])
    for c in payload.get("chaves_compostas", []):
        linhas_rel.append(["Chave composta",
                           " + ".join(f'<code>{_e(x)}</code>' for x in c["colunas"]),
                           _e(c["descricao"])])
    for c in payload.get("correlacoes", []):
        linhas_rel.append([_e(c["metrica"]),
                           f'<code>{_e(c["coluna_a"])}</code> ~ <code>{_e(c["coluna_b"])}</code>',
                           f'{_num(c["valor"])} ({_e(c["forca"])})'])
    partes.append(_tabela(["Tipo", "Colunas", "Detalhe"], linhas_rel))

    if payload.get("regras_negocio"):
        partes.append("<h2>Regras de negócio inferidas</h2>")
        partes.append(
            "<p class='sub'>Regras que o dado obedece — e as linhas que não obedecem, "
            "que são erro concreto para conferir na origem.</p><ul>"
        )
        for regra in payload["regras_negocio"]:
            marca = "⚠️" if regra["qtd_violacoes"] else "✅"
            partes.append(
                f"<li>{marca} <b>{_e(regra['regra'])}</b> "
                f"({_e(regra['tipo'])}, {regra['conformidade']:.1%} das linhas) — "
                f"{_e(regra['descricao'])}</li>"
            )
        partes.append("</ul>")

    if payload.get("hierarquias"):
        partes.append("<h2>Hierarquias</h2><ul>")
        partes.extend(f"<li>{_e(h['descricao'])}</li>" for h in payload["hierarquias"])
        partes.append("</ul>")

    if payload.get("explicacoes_de_medidas"):
        partes.append("<h2>O que explica cada medida</h2><ul>")
        partes.extend(
            f"<li>{_e(e['descricao'])}</li>" for e in payload["explicacoes_de_medidas"]
        )
        partes.append("</ul>")

    partes.append("<h2>Gap Analysis de KPIs</h2>")
    partes.append(_tabela(
        ["KPI", "Nome", "Status", "Cobertura", "Semânticas ausentes"],
        [[_e(g["kpi_id"]), _e(g["kpi_nome"]), _e(g["status"]), _e(g["cobertura_pct"]),
          _e(", ".join(g["semanticas_ausentes"]) or "—")]
         for g in payload["gap_analysis_kpis"]],
    ))

    if payload.get("analise_temporal_series"):
        primeira = payload["analise_temporal_series"][0]
        partes.append("<h2>Análise temporal</h2>")
        partes.append(
            f'<p class="sub">Séries agregadas por período ({_e(primeira["agregacao"])}), '
            f'referência <code>{_e(primeira["coluna_temporal_referencia"])}</code>.</p>'
        )
        partes.append(_tabela(
            ["Coluna", "Pontos", "Estacionária", "Autocorrelacionada"],
            [[
                f'<code>{_e(t["coluna"])}</code>', f'{t["n_pontos"]:,}',
                _num(t["adf"].get("estacionaria")) if t["adf"].get("aplicavel") else "N/A",
                _num(t["ljung_box"].get("autocorrelacionada")) if t["ljung_box"].get("aplicavel") else "N/A",
            ] for t in payload["analise_temporal_series"]],
        ))

    documento = (
        "<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Perfilamento — {_e(meta['tabela'])}</title><style>{_CSS}</style></head>"
        f"<body><main>{''.join(partes)}</main></body></html>"
    )

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(documento)
    logger.info(f"✓ HTML exportado: '{caminho}'")

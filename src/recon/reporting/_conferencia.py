"""Relatório da conferência entre duas versões da mesma base.

`perfilar` descreve um único arquivo. Este relatório compara duas versões da
mesma base, uso típico a cada nova extração: o que mudou de schema, quais
registros entraram e saíram, e que colunas mudaram de comportamento sem
mudar de nome.
"""
from html import escape
from typing import Any

from loguru import logger

from ._html import _CSS


def _e(valor: Any) -> str:
    return escape(str(valor), quote=False)


def _cartao(rotulo: str, valor: Any) -> str:
    return (
        f'<div class="cartao"><div class="rotulo">{_e(rotulo)}</div>'
        f'<div class="valor">{_e(valor)}</div></div>'
    )


def _linhas_variacao(payload: dict[str, Any]) -> list[list[str]]:
    return [
        [v["coluna"], v["severidade"], f"{v['pct_nulos_a']:.1f}% → {v['pct_nulos_b']:.1f}%",
         f"{v['unicos_a']:,} → {v['unicos_b']:,}",
         f"{v['tipo_a']} → {v['tipo_b']}" if v["mudou_tipo"] else v["tipo_a"],
         v["descricao"]]
        for v in payload["variacoes_de_coluna"]
    ]


def exportar_conferencia_markdown(payload: dict[str, Any], caminho: str) -> None:
    p = payload
    partes = [
        f"# Conferência — `{p['tabela_a']}` × `{p['tabela_b']}`",
        "",
        f"- Linhas: **{p['linhas_a']:,}** → **{p['linhas_b']:,}**"
        + (f" ({p['variacao_linhas']:+.1%})" if p.get("variacao_linhas") is not None else ""),
        f"- Colunas em comum: **{p['colunas_comuns']}**",
    ]
    if p.get("linhas_a_total_desconhecido") or p.get("linhas_b_total_desconhecido"):
        partes.append(
            "- **Volume parcial:** ao menos uma leitura foi limitada; os totais originais não "
            "foram contabilizados e a variação de volume não é calculada."
        )
    elif p.get("amostragem_a") or p.get("amostragem_b"):
        partes.append(
            "- **Amostragem aplicada:** os volumes são do arquivo inteiro, mas mudanças por "
            "registro e por coluna descrevem as linhas amostradas."
        )
    if p["colunas_so_em_a"]:
        partes.append(f"- Só na versão anterior: {', '.join(f'`{c}`' for c in p['colunas_so_em_a'])}")
    if p["colunas_so_em_b"]:
        partes.append(f"- Só na versão nova: {', '.join(f'`{c}`' for c in p['colunas_so_em_b'])}")
    partes.append("")

    if p.get("avisos"):
        partes.append("## O que merece atenção\n")
        for aviso in p["avisos"]:
            partes.append(f"- {aviso['severidade']} **{aviso['tipo']}** — {aviso['mensagem']}")
        partes.append("")

    if p.get("chave_comparada"):
        partes.append(f"## Registros, pela chave `{p['chave_comparada']}`\n")
        partes.append(f"- Em ambas as versões: **{p['chaves_em_ambas']:,}**")
        partes.append(f"- Saíram (só na anterior): **{p['chaves_so_em_a']:,}**")
        partes.append(f"- Entraram (só na nova): **{p['chaves_so_em_b']:,}**")
        if p.get("comparacao_registros_amostral"):
            partes.append("- Comparação de registros indicativa: ao menos uma versão foi amostrada.")
        for rotulo, chave in (("Saíram", "exemplos_sairam"), ("Entraram", "exemplos_entraram")):
            if p.get(chave):
                partes.append(f"- {rotulo}, exemplos: {', '.join(f'`{v}`' for v in p[chave][:10])}")
        partes.append("")
    else:
        partes.append(f"## Registros\n\n{p.get('motivo_sem_chave', '')}\n")

    if p["variacoes_de_coluna"]:
        partes.append("## Colunas que mudaram de comportamento\n")
        partes.append("| Coluna | Severidade | Nulos | Distintos | Tipo | O que mudou |")
        partes.append("|---|---|---|---|---|---|")
        for linha in _linhas_variacao(p):
            partes.append("| " + " | ".join(linha) + " |")
        partes.append("")
    else:
        partes.append("## Colunas que mudaram de comportamento\n\nNenhuma.\n")

    if p.get("drifts_de_distribuicao"):
        partes.append("## Mudanças de distribuição\n")
        for drift in p["drifts_de_distribuicao"]:
            partes.append(f"- **{drift['coluna']}** ({drift['tipo']}) — {drift['descricao']}")
        partes.append("")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(partes))
    logger.info(f"✓ Conferência (Markdown) exportada: '{caminho}'")


def exportar_conferencia_html(payload: dict[str, Any], caminho: str) -> None:
    p = payload
    partes: list[str] = [
        f"<h1>Conferência — {_e(p['tabela_a'])} × {_e(p['tabela_b'])}</h1>",
        '<p class="sub">O que mudou entre as duas versões da mesma base: schema, '
        "volume, registros e comportamento das colunas.</p>",
    ]

    variacao = (
        f"{p['variacao_linhas']:+.1%}" if p.get("variacao_linhas") is not None else "—"
    )
    cartoes = [
        _cartao("Linhas antes", f"{p['linhas_a']:,}"),
        _cartao("Linhas depois", f"{p['linhas_b']:,}"),
        _cartao("Variação", variacao),
        _cartao("Colunas em comum", p["colunas_comuns"]),
    ]
    if p.get("chave_comparada"):
        cartoes += [
            _cartao("Registros saíram", f"{p['chaves_so_em_a']:,}"),
            _cartao("Registros entraram", f"{p['chaves_so_em_b']:,}"),
        ]
    partes.append(f'<div class="cartoes">{"".join(cartoes)}</div>')
    if p.get("linhas_a_total_desconhecido") or p.get("linhas_b_total_desconhecido"):
        partes.append(
            "<p class='sub'><b>Volume parcial:</b> pelo menos uma leitura foi limitada e o "
            "total original não pôde ser contado. Os cartões mostram linhas analisadas; por "
            "isso a variação de volume não foi calculada.</p>"
        )
    elif p.get("amostragem_a") or p.get("amostragem_b"):
        partes.append(
            "<p class='sub'><b>Amostragem aplicada:</b> os volumes são do arquivo inteiro, "
            "mas mudanças de registros e comportamento de colunas descrevem as linhas amostradas.</p>"
        )

    if p.get("avisos"):
        partes.append("<h2>O que merece atenção</h2><ul>")
        for aviso in p["avisos"]:
            partes.append(
                f"<li><b>{_e(aviso['severidade'])} {_e(aviso['tipo'])}</b> — "
                f"{_e(aviso['mensagem'])}</li>"
            )
        partes.append("</ul>")

    partes.append("<h2>Schema</h2>")
    for rotulo, chave in (
        ("Só na versão anterior", "colunas_so_em_a"),
        ("Só na versão nova", "colunas_so_em_b"),
    ):
        colunas = p[chave]
        partes.append(
            f"<h3>{_e(rotulo)}</h3><p class='sub'>"
            + (", ".join(f"<code>{_e(c)}</code>" for c in colunas) if colunas else "Nenhuma.")
            + "</p>"
        )

    partes.append("<h2>Registros</h2>")
    if p.get("chave_comparada"):
        aviso_amostra = (
            " <b>Comparação indicativa:</b> ao menos uma versão foi analisada por amostragem."
            if p.get("comparacao_registros_amostral") else ""
        )
        partes.append(
            f"<p class='sub'>Comparados pela chave <code>{_e(p['chave_comparada'])}</code>: "
            f"{p['chaves_em_ambas']:,} em ambas, {p['chaves_so_em_a']:,} saíram, "
            f"{p['chaves_so_em_b']:,} entraram.{aviso_amostra}</p>"
        )
        for rotulo, chave in (("Saíram", "exemplos_sairam"), ("Entraram", "exemplos_entraram")):
            if p.get(chave):
                exemplos = ", ".join(f"<code>{_e(v)}</code>" for v in p[chave][:10])
                partes.append(f"<p class='sub'><b>{_e(rotulo)}</b>: {exemplos}</p>")
    else:
        partes.append(f"<p class='sub'>{_e(p.get('motivo_sem_chave', ''))}</p>")

    partes.append("<h2>Colunas que mudaram de comportamento</h2>")
    linhas = _linhas_variacao(p)
    if linhas:
        cabecalho = ("Coluna", "Severidade", "Nulos", "Distintos", "Tipo", "O que mudou")
        corpo = "".join(
            "<tr>" + "".join(f"<td>{_e(c)}</td>" for c in linha) + "</tr>" for linha in linhas
        )
        partes.append(
            '<div class="tabela-wrap"><table><thead><tr>'
            + "".join(f"<th>{_e(c)}</th>" for c in cabecalho)
            + f"</tr></thead><tbody>{corpo}</tbody></table></div>"
        )
    else:
        partes.append(
            "<p class='sub'>Nenhuma. As colunas em comum mantiveram tipo, preenchimento e "
            "cardinalidade.</p>"
        )

    if p.get("drifts_de_distribuicao"):
        partes.append("<h2>Mudanças de distribuição</h2><ul>")
        partes.extend(
            f"<li><code>{_e(d['coluna'])}</code> — {_e(d['descricao'])}</li>"
            for d in p["drifts_de_distribuicao"]
        )
        partes.append("</ul>")

    documento = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Conferência — {_e(p['tabela_a'])} × {_e(p['tabela_b'])}</title>"
        f"<style>{_CSS}</style></head>"
        f"<body><main>{''.join(partes)}</main></body></html>"
    )
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(documento)
    logger.info(f"✓ Conferência (HTML) exportada: '{caminho}'")

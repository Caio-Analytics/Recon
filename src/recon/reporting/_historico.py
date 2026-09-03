"""Relatórios de evolução longitudinal de perfis de dados."""

from __future__ import annotations

from html import escape
from typing import Any

from loguru import logger

from ._html import _CSS


def _e(valor: Any) -> str:
    return escape(str(valor))


def exportar_historico_markdown(payload: dict[str, Any], caminho: str) -> None:
    linhas = ["# Histórico de qualidade", "", payload["resumo"], ""]
    linhas.extend([
        "| Extração | Linhas | Colunas | Score | Nulos | Recomendações |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for extracao in payload["extracoes"]:
        volume = (
            "não contabilizado"
            if extracao.get("linhas_total_desconhecido")
            else f"{extracao['linhas']:,}"
        )
        amostra = (
            f" (amostra: {extracao['linhas_analisadas']:,}; cobertura "
            f"{extracao['cobertura_amostra_pct']:.3f}%)"
            if extracao.get("amostragem_aplicada") else ""
        )
        linhas.append(
            f"| {extracao['arquivo']} | {volume}{amostra} | {extracao['colunas']} | "
            f"{extracao['score']:.1f} | {extracao['colunas_com_nulos']} | "
            f"{extracao['recomendacoes']} |"
        )
    if payload["alertas"]:
        linhas.extend(["", "## Alertas"])
        linhas.extend(f"- {alerta}" for alerta in payload["alertas"])
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")
    logger.info(f"✓ Histórico (Markdown) exportado: '{caminho}'")


def exportar_historico_html(payload: dict[str, Any], caminho: str) -> None:
    def _volume(extracao: dict[str, Any]) -> str:
        if extracao.get("linhas_total_desconhecido"):
            return f"{extracao['linhas_analisadas']:,} analisadas<br><small>total não contabilizado</small>"
        if extracao.get("amostragem_aplicada"):
            return (
                f"{extracao['linhas']:,}<br><small>{extracao['linhas_analisadas']:,} analisadas "
                f"({extracao['cobertura_amostra_pct']:.3f}%)</small>"
            )
        return f"{extracao['linhas']:,}"

    corpo = "".join(
        "<tr>" + "".join(
            f"<td>{valor if indice == 1 else _e(valor)}</td>" for indice, valor in enumerate((
                extracao["arquivo"], _volume(extracao), extracao["colunas"],
                f"{extracao['score']:.1f}", extracao["colunas_com_nulos"],
                extracao["recomendacoes"],
            ))
        ) + "</tr>"
        for extracao in payload["extracoes"]
    )
    alertas = "".join(f"<li>{_e(alerta)}</li>" for alerta in payload["alertas"])
    extracoes = payload["extracoes"]
    scores = [float(extracao["score"]) for extracao in extracoes]
    minimo, maximo = min(scores), max(scores)
    amplitude = max(maximo - minimo, 1.0)
    pontos = " ".join(
        f"{indice * 100 / max(len(scores) - 1, 1):.1f},{100 - ((score - minimo) / amplitude * 84 + 8):.1f}"
        for indice, score in enumerate(scores)
    )
    primeiro, ultimo = extracoes[0], extracoes[-1]
    volume = "—" if ultimo.get("linhas_total_desconhecido") else f"{ultimo['linhas']:,}"
    cartoes = "".join([
        f'<div class="cartao"><div class="rotulo">Última qualidade</div><div class="valor">{ultimo["score"]:.1f}</div></div>',
        f'<div class="cartao"><div class="rotulo">Variação de score</div><div class="valor">{ultimo["score"] - primeiro["score"]:+.1f}</div></div>',
        f'<div class="cartao"><div class="rotulo">Último volume</div><div class="valor">{volume}</div></div>',
        f'<div class="cartao"><div class="rotulo">Alertas</div><div class="valor">{len(payload["alertas"])}</div></div>',
    ])
    documento = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Histórico de qualidade</title><style>{_CSS}
.tendencia{{margin:1rem 0 1.5rem;padding:1rem;border:1px solid var(--borda);border-radius:10px;background:var(--fundo-alt)}} .tendencia svg{{width:100%;height:110px;overflow:visible}} .tendencia polyline{{fill:none;stroke:var(--acento);stroke-width:3;stroke-linecap:round;stroke-linejoin:round}} small{{color:var(--texto-fraco)}}
</style><main><header class="cabecalho-relatorio"><div class="marca">Recon · evolução da qualidade</div><h1>Histórico de qualidade</h1><p class="sub">{_e(payload['resumo'])}</p></header>
<section><div class="cartoes">{cartoes}</div><div class="tendencia"><b>Evolução do score</b><br><small>O gráfico mostra a variação relativa da qualidade entre as extrações informadas.</small><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Evolução do score"><polyline points="{pontos}"/></svg></div></section>
<table><thead><tr><th>Extração</th><th>Linhas</th><th>Colunas</th><th>Score</th><th>Com nulos</th><th>Recomendações</th></tr></thead><tbody>{corpo}</tbody></table>
{f'<section class="alertas"><h2>Alertas</h2><ul>{alertas}</ul></section>' if alertas else ''}</main></html>"""
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(documento)
    logger.info(f"✓ Histórico (HTML) exportado: '{caminho}'")

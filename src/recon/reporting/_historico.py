"""Relatórios de evolução longitudinal de perfis de dados."""

from __future__ import annotations

from html import escape
from typing import Any

from loguru import logger


def _e(valor: Any) -> str:
    return escape(str(valor))


def exportar_historico_markdown(payload: dict[str, Any], caminho: str) -> None:
    linhas = ["# Histórico de qualidade", "", payload["resumo"], ""]
    linhas.extend([
        "| Extração | Linhas | Colunas | Score | Nulos | Recomendações |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for extracao in payload["extracoes"]:
        linhas.append(
            f"| {extracao['arquivo']} | {extracao['linhas']:,} | {extracao['colunas']} | "
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
    corpo = "".join(
        "<tr>" + "".join(
            f"<td>{_e(valor)}</td>" for valor in (
                extracao["arquivo"], f"{extracao['linhas']:,}", extracao["colunas"],
                f"{extracao['score']:.1f}", extracao["colunas_com_nulos"],
                extracao["recomendacoes"],
            )
        ) + "</tr>"
        for extracao in payload["extracoes"]
    )
    alertas = "".join(f"<li>{_e(alerta)}</li>" for alerta in payload["alertas"])
    documento = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>Histórico de qualidade</title><style>
body{{font:16px/1.55 system-ui,sans-serif;margin:2rem;max-width:1050px;color:#172033}} h1{{margin-bottom:.25rem}}
.sub{{color:#60708a}} table{{width:100%;border-collapse:collapse;margin:1.4rem 0}} th,td{{padding:.65rem;border-bottom:1px solid #dce2ea;text-align:left}} th{{color:#526078;font-size:.8rem;text-transform:uppercase}} .alertas{{background:#fff7ed;border:1px solid #fed7aa;padding:1rem;border-radius:8px}}
</style><main><h1>Histórico de qualidade</h1><p class="sub">{_e(payload['resumo'])}</p>
<table><thead><tr><th>Extração</th><th>Linhas</th><th>Colunas</th><th>Score</th><th>Com nulos</th><th>Recomendações</th></tr></thead><tbody>{corpo}</tbody></table>
{f'<section class="alertas"><h2>Alertas</h2><ul>{alertas}</ul></section>' if alertas else ''}</main></html>"""
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(documento)
    logger.info(f"✓ Histórico (HTML) exportado: '{caminho}'")

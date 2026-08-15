"""Relatório Markdown para leitura humana.

A versão anterior era um índice: listava as colunas e as recomendações, mas
nenhuma estatística por coluna — mínimo, máximo, média, outlier e amostra
existiam só no JSON. Aqui o `.md` passa a ser autossuficiente.
"""
from typing import Any

from loguru import logger

from .. import quality

_MAX_PROBLEMAS_DESTAQUE = 6


def _num(valor: Any) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, int):
        return f"{valor:,}"
    if isinstance(valor, float):
        return f"{valor:,.2f}" if abs(valor) >= 0.01 or valor == 0 else f"{valor:.6g}"
    return str(valor)


def _pct(fracao: float | None) -> str:
    return "—" if fracao is None else f"{fracao:.1%}"


def _tabela(linhas: list[list[Any]], cabecalhos: list[str]) -> str:
    out = ["| " + " | ".join(cabecalhos) + " |", "|" + "---|" * len(cabecalhos)]
    for linha in linhas:
        out.append("| " + " | ".join(str(v) for v in linha) + " |")
    return "\n".join(out)


def _linha_testes(testes: dict[str, Any]) -> list[str]:
    fragmentos: list[str] = []

    shapiro = testes.get("shapiro_wilk") or {}
    if shapiro.get("aplicavel"):
        relevante = " — desvio relevante" if shapiro.get("desvio_relevante") else " — desvio pequeno"
        fragmentos.append(
            f"Shapiro-Wilk W={_num(shapiro.get('estatistica_w'))} p={_num(shapiro.get('p_valor'))}"
            f" (normal provável: {'sim' if shapiro.get('normal_provavel') else 'não'}{relevante})"
        )

    ic = testes.get("intervalo_confianca_media_95") or {}
    if ic.get("aplicavel"):
        fragmentos.append(
            f"IC95% da média: [{_num(ic.get('limite_inferior'))}, {_num(ic.get('limite_superior'))}]"
        )

    dist = testes.get("distribuicao_provavel") or {}
    if dist.get("aplicavel"):
        conclusiva = "" if dist.get("escolha_conclusiva", True) else " (empate técnico com a segunda)"
        fragmentos.append(
            f"Distribuição provável: {dist.get('distribuicao')} "
            f"[AIC {_num(dist.get('aic'))}{conclusiva}]"
        )

    chi2 = testes.get("qui_quadrado_uniformidade") or {}
    if chi2.get("aplicavel"):
        fragmentos.append(
            f"Qui-quadrado de uniformidade p={_num(chi2.get('p_valor'))} "
            f"(uniforme provável: {'sim' if chi2.get('distribuicao_uniforme_provavel') else 'não'}, "
            f"V de Cramér={_num(chi2.get('v_cramer'))})"
        )

    return fragmentos


def _alertas_coluna(coluna: dict[str, Any]) -> list[str]:
    alertas: list[str] = []
    qual = coluna.get("Qualidade", {})
    flags = coluna.get("Alertas", {})

    sent = qual.get("sentinelas", {})
    if sent.get("tem_sentinela"):
        valores = ", ".join(f"`{v['valor']}` ({_pct(v['pct'])})" for v in sent["valores"][:3])
        alertas.append(f"⚠️ Nulos disfarçados: {valores} — total {_pct(sent['pct_total'])}")

    inc = qual.get("inconsistencia_normalizacao", {})
    if inc.get("tem_inconsistencia"):
        exemplo = " / ".join(f"`{v}`" for v in inc["exemplos"][0]["variantes"][:4])
        alertas.append(
            f"⚠️ Mesma informação com grafias diferentes ({exemplo}) — "
            f"{inc['valores_unicos_atual']} valores viram {inc['valores_unicos_normalizado']} "
            "após padronizar"
        )

    if qual.get("mojibake", {}).get("tem_mojibake"):
        exemplo = qual["mojibake"]["exemplos"][0][:40]
        alertas.append(f"⚠️ Encoding corrompido na origem (ex.: `{exemplo}`)")

    pii = qual.get("pii_texto_livre", {})
    if pii.get("tem_pii"):
        alertas.append(f"🔒 PII embutida em texto livre: {', '.join(sorted(pii['tipos']))}")

    documento = qual.get("documento_invalido", {})
    if documento.get("tem_documento_invalido"):
        alertas.append(
            f"⚠️ Tem formato de {documento['tipo']} em {_pct(documento['pct_formato'])} dos "
            f"valores, mas só {_pct(documento['pct_valido'])} passam no dígito verificador"
        )

    if flags.get("mistura_tipos", {}).get("tem_mistura"):
        alertas.append(f"⚠️ Mistura de tipos: {flags['mistura_tipos']['tipos_detectados']}")

    if flags.get("data_como_texto"):
        alertas.append("⚠️ Data armazenada como texto")

    if coluna.get("Dado_Sensivel_LGPD", "Nenhum") != "Nenhum":
        alertas.append(
            f"🔒 Dado sensível LGPD ({coluna['Dado_Sensivel_LGPD']}) — valores mascarados"
            + (", estatísticas de posição suprimidas"
               if flags.get("stats_suprimidas_lgpd") else "")
        )

    return alertas


def _bloco_coluna(coluna: dict[str, Any]) -> list[str]:
    extras = coluna.get("Stats_Extra") or {}
    partes: list[str] = []

    semantica = coluna["Semantica_IA"]
    if coluna.get("Dominio") and coluna["Dominio"] != semantica:
        semantica += f" · domínio: {coluna['Dominio']}"

    partes.append(
        f"#### `{coluna['Coluna']}` — {coluna['Tipo_Inferred']} · {semantica} · "
        f"{coluna['Caracteristica']}"
    )

    if coluna.get("Semantica_Origem") and coluna["Semantica_Origem"] != "Unmatched":
        partes.append(
            f"- Semântica inferida ({_pct(coluna.get('Semantica_Score'))} de confiança): "
            f"{coluna['Semantica_Origem']}"
        )

    # Quando a inferência não fecha, mostrar as alternativas é mais útil (e
    # mais honesto) do que exibir um único rótulo com cara de certeza.
    if coluna.get("Semantica_Conclusiva") is False:
        alternativas = [
            f"{h['semantica']} ({_pct(h['confianca'])})"
            for h in (coluna.get("Semantica_Hipoteses") or [])
            if h["semantica"] != coluna["Semantica_IA"]
        ]
        if alternativas:
            partes.append(
                "- ⚠️ Classificação não conclusiva — outras leituras possíveis: "
                + ", ".join(alternativas[:3])
            )

    qual = coluna.get("Qualidade", {})
    linha_base = (
        f"- Nulos: {_num(coluna['Qtd_Nulos'])} ({coluna['Pct_Nulos']:.1f}%)"
    )
    if qual.get("nulos_efetivos_qtd", 0) > coluna["Qtd_Nulos"]:
        linha_base += f" · **nulos efetivos: {qual['nulos_efetivos_pct']:.1f}%** (com sentinelas)"
    linha_base += (
        f" · Únicos: {_num(coluna['Qtd_Unicos'])} ({_pct(coluna['Ratio_Unicidade'])})"
    )
    partes.append(linha_base)

    if "min" in extras:
        partes.append(
            f"- Faixa: {_num(extras['min'])} → {_num(extras['max'])} · "
            f"média {_num(extras.get('media'))} · mediana {_num(extras.get('mediana'))} · "
            f"desvio {_num(extras.get('desvio_padrao'))} · "
            f"assimetria {_num(extras.get('assimetria'))}"
        )
    if "min_data" in extras:
        linha_data = (
            f"- Período: {extras['min_data'][:10]} → {extras['max_data'][:10]} "
            f"({_num(extras.get('range_dias'))} dias, {_num(extras.get('meses_cobertos'))} meses)"
        )
        if extras.get("qtd_datas_futuras"):
            linha_data += f" · ⚠️ {_num(extras['qtd_datas_futuras'])} data(s) no futuro"
        if extras.get("qtd_meses_sem_registro"):
            linha_data += f" · ⚠️ {_num(extras['qtd_meses_sem_registro'])} mês(es) sem registro"
        partes.append(linha_data)
    if "str_len_min" in extras:
        partes.append(
            f"- Comprimento: {_num(extras['str_len_min'])}–{_num(extras['str_len_max'])} "
            f"(média {_num(extras['str_len_media'])}"
            + (", fixo" if extras.get("comprimento_fixo") else "") + ")"
        )
    if "qtd_true" in extras:
        partes.append(
            f"- Verdadeiros: {_num(extras['qtd_true'])} ({_pct(extras['pct_true'])}) · "
            f"Falsos: {_num(extras['qtd_false'])}"
        )

    outliers = extras.get("outliers_iqr") or {}
    if outliers.get("qtd_outliers_total"):
        partes.append(
            f"- Outliers: {_num(outliers['qtd_outliers_total'])} fora de "
            f"[{_num(outliers['limite_inferior'])}, {_num(outliers['limite_superior'])}] "
            f"— método {outliers.get('metodo', 'IQR')}"
        )

    top = extras.get("distribuicao_top5") or []
    if top:
        partes.append(
            "- Mais frequentes: "
            + ", ".join(f"`{d['valor']}` ({d['frequencia_pct']})" for d in top)
        )

    if coluna.get("Amostra_Valores"):
        amostra = coluna["Amostra_Valores"]
        if len(amostra) > 200:
            amostra = amostra[:200] + "…"
        partes.append(f"- Amostra: {amostra}")

    testes = _linha_testes(extras.get("testes_hipotese") or {})
    if testes:
        partes.append("- Testes: " + " · ".join(testes))

    benford = extras.get("benford")
    if benford:
        veredito = "aderente" if benford["aderente"] else "**não aderente**"
        partes.append(
            f"- Lei de Benford: {veredito} (desvio máximo {_pct(benford['desvio_maximo_absoluto'])})"
        )

    otim = coluna.get("Otimizacao") or {}
    if otim.get("dtype_sugerido"):
        partes.append(
            f"- Otimização: `{otim['dtype_atual']}` → `{otim['dtype_sugerido']}` "
            f"economiza {_num(otim.get('economia_mb'))} MB ({_pct(otim.get('economia_pct'))})"
        )

    for alerta in _alertas_coluna(coluna):
        partes.append(f"- {alerta}")

    return partes


def exportar_markdown(payload: dict[str, Any], caminho: str) -> None:
    meta = payload["metadados_execucao"]
    resumo = meta["resumo_qualidade"]
    score = meta.get("score_qualidade", {})
    duplicatas = meta.get("duplicatas", {})

    partes: list[str] = [f"# Relatório de Perfilamento — {meta['tabela']}", ""]

    if score:
        partes.append(
            f"## Qualidade geral: **{score['score']}/100** (nota {score['nota']})\n"
        )
        if score.get("penalidades"):
            partes.append("O que mais pesou contra o score:\n")
            for p in score["penalidades"][:5]:
                partes.append(
                    f"- **{p['dimensao']}** — {p['pontos_perdidos']} pontos "
                    f"(intensidade {_pct(p['intensidade'])})"
                )
            partes.append("")

    linhas_resumo = [
        f"- Linhas originais: {meta['linhas_originais']:,} | Analisadas: {meta['linhas_analisadas']:,}",
        f"- Colunas: {meta['total_colunas']} | Com nulos: {resumo['colunas_com_nulos']} | "
        f"100% vazias: {resumo['colunas_100pct_nulas']} | Sensíveis LGPD: {resumo['colunas_sensiveis_lgpd']}",
    ]
    if duplicatas.get("qtd_linhas_duplicadas"):
        linhas_resumo.append(
            f"- Linhas duplicadas: {duplicatas['qtd_linhas_duplicadas']:,} "
            f"({_pct(duplicatas['pct_linhas_duplicadas'])})"
        )
    if meta.get("amostragem_aplicada"):
        linhas_resumo.append(
            "- ⚠️ Amostragem aplicada: métricas de unicidade e duplicata referem-se à amostra, "
            "não à tabela inteira"
        )
    linhas_resumo.append(
        f"- Semânticas mapeadas: {', '.join(resumo['semanticas_encontradas']) or 'Nenhuma'}"
    )
    linhas_resumo.append(
        f"- KPIs habilitados: {resumo['kpis_habilitados']} | "
        f"Total de recomendações: {resumo['total_recomendacoes']}"
    )
    partes.append("\n".join(linhas_resumo))

    layout = meta.get("layout") or {}
    if layout.get("avisos"):
        partes.append("\n## Como o arquivo foi lido\n")
        partes.append(
            "A tabela analisada não é literalmente o que está no arquivo — o DataScope "
            "ajustou o layout antes de perfilar:\n"
        )
        for aviso in layout["avisos"]:
            partes.append(f"- **{aviso['severidade']}** [{aviso['tipo']}] {aviso['mensagem']}")

    recomendacoes = quality.ordenar_por_prioridade(payload["recomendacoes_etl"])
    criticas = [r for r in recomendacoes if r["Prioridade"] == quality.PRIORIDADE_ALTA]
    if criticas:
        partes.append("\n## Principais problemas\n")
        for i, r in enumerate(criticas[:_MAX_PROBLEMAS_DESTAQUE], start=1):
            partes.append(f"{i}. `{r['Coluna']}` — {r['Acao']}")
        if len(criticas) > _MAX_PROBLEMAS_DESTAQUE:
            partes.append(
                f"\n_(+{len(criticas) - _MAX_PROBLEMAS_DESTAQUE} outras de prioridade alta na "
                "seção de recomendações)_"
            )

    partes.append("\n## Visão geral das colunas\n")
    partes.append(_tabela(
        [[c["Coluna"], c["Tipo_Inferred"], c["Semantica_IA"], f"{c['Pct_Nulos']:.1f}%",
          f"{c['Qtd_Unicos']:,}", c["Caracteristica"]] for c in payload["colunas"]],
        ["Coluna", "Tipo", "Semântica", "% Nulos", "Únicos", "Característica"],
    ))

    partes.append("\n## Detalhe por coluna\n")
    for coluna in payload["colunas"]:
        partes.extend(_bloco_coluna(coluna))
        partes.append("")

    partes.append("\n## Recomendações ETL\n")
    if recomendacoes:
        for r in recomendacoes:
            partes.append(f"- **{r['Prioridade']}** [{r['Camada']}] `{r['Coluna']}` — {r['Acao']}")
    else:
        partes.append("Nenhuma recomendação gerada.")

    partes.append("\n## Relações entre colunas\n")
    tem_relacao = False
    if payload.get("dependencias_funcionais"):
        tem_relacao = True
        partes.append("**Dependências funcionais**\n")
        for d in payload["dependencias_funcionais"]:
            seta = "↔" if d["tipo"].startswith("Equivalência") else "→"
            partes.append(f"- `{d['determinante']}` {seta} `{d['dependente']}`: {d['descricao']}")
        partes.append("")
    if payload.get("colunas_redundantes"):
        tem_relacao = True
        partes.append("**Colunas redundantes**\n")
        for r in payload["colunas_redundantes"]:
            partes.append(f"- {r['descricao']}")
        partes.append("")
    if payload.get("chaves_compostas"):
        tem_relacao = True
        partes.append("**Chaves compostas candidatas**\n")
        for c in payload["chaves_compostas"]:
            partes.append(f"- {c['descricao']}")
        partes.append("")
    if payload.get("correlacoes"):
        tem_relacao = True
        partes.append("**Correlações relevantes**\n")
        partes.append(_tabela(
            [[c["coluna_a"], c["coluna_b"], c["metrica"], _num(c["valor"]), c["forca"]]
             for c in payload["correlacoes"]],
            ["Coluna A", "Coluna B", "Métrica", "Valor", "Força"],
        ))
        partes.append("")
    if not tem_relacao:
        partes.append("Nenhuma relação relevante detectada entre as colunas.")

    if payload.get("regras_negocio"):
        partes.append("\n## Regras de negócio inferidas\n")
        partes.append(
            "Regras que o dado obedece — e as linhas que não obedecem, que são erro "
            "concreto para conferir na origem.\n"
        )
        for regra in payload["regras_negocio"]:
            marca = "⚠️ " if regra["qtd_violacoes"] else "✅ "
            partes.append(
                f"- {marca}**{regra['regra']}** ({regra['tipo']}, "
                f"{regra['conformidade']:.1%} das linhas) — {regra['descricao']}"
            )
            if regra["exemplos_violacao"]:
                partes.append(f"  - Exemplos: `{regra['exemplos_violacao']}`")

    if payload.get("hierarquias"):
        partes.append("\n## Hierarquias\n")
        for h in payload["hierarquias"]:
            partes.append(f"- {h['descricao']}")

    if payload.get("explicacoes_de_medidas"):
        partes.append("\n## O que explica cada medida\n")
        for e in payload["explicacoes_de_medidas"]:
            partes.append(f"- {e['descricao']}")

    partes.append("\n## Gap Analysis de KPIs\n")
    partes.append(_tabela(
        [[g["kpi_id"], g["kpi_nome"], g["status"], g["cobertura_pct"],
          ", ".join(g["semanticas_ausentes"]) or "—"]
         for g in payload["gap_analysis_kpis"]],
        ["KPI", "Nome", "Status", "Cobertura", "Semânticas ausentes"],
    ))

    if payload.get("analise_temporal_series"):
        partes.append("\n## Análise Temporal (ADF / Ljung-Box)\n")
        primeira = payload["analise_temporal_series"][0]
        partes.append(
            f"Séries agregadas por período ({primeira['agregacao']}) usando "
            f"`{primeira['coluna_temporal_referencia']}` como referência temporal.\n"
        )
        for t in payload["analise_temporal_series"]:
            adf, lb = t["adf"], t["ljung_box"]
            estac = ("sim" if adf.get("estacionaria") else "não") if adf.get("aplicavel") else "N/A"
            autoc = ("sim" if lb.get("autocorrelacionada") else "não") if lb.get("aplicavel") else "N/A"
            partes.append(
                f"- `{t['coluna']}` ({t['n_pontos']} pontos) — estacionária: {estac} | "
                f"autocorrelacionada: {autoc}"
            )

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(partes) + "\n")
    logger.info(f"✓ Markdown exportado: '{caminho}'")

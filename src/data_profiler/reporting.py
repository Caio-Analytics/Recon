"""Exportação do payload de profiling: JSON (IA/código), Markdown (humano)
e Parquet (opcional, BI)."""
import json
import math
import re
from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger


def sanear_floats(obj: Any) -> Any:
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanear_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanear_floats(v) for v in obj]
    return obj


def nome_seguro(nome_tabela: str) -> str:
    return re.sub(r"[^\w\-]", "_", nome_tabela)


def exportar_json(payload: Dict[str, Any], caminho: str) -> None:
    payload_limpo = sanear_floats(payload)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(payload_limpo, f, ensure_ascii=False, indent=4, default=str)
    logger.info(f"✓ JSON exportado: '{caminho}'")


def exportar_parquet(payload: Dict[str, Any], caminho_base: str) -> None:
    nome_tab = payload["metadados_execucao"]["tabela"]
    nome_safe = nome_seguro(nome_tab)

    df_cols = pd.DataFrame(payload["colunas"])
    df_cols["Stats_Extra"] = df_cols["Stats_Extra"].apply(
        lambda x: json.dumps(sanear_floats(x), ensure_ascii=False, default=str) if isinstance(x, dict) else str(x)
    )
    df_cols["alerta_data_texto"] = df_cols["Alertas"].apply(lambda x: x.get("data_como_texto", False))
    df_cols["alerta_mistura_tipos"] = df_cols["Alertas"].apply(
        lambda x: json.dumps(x.get("mistura_tipos", {}), ensure_ascii=False)
    )
    df_cols = df_cols.drop(columns=["Alertas"])
    df_cols.to_parquet(f"{caminho_base}_{nome_safe}_columns.parquet", index=False)
    arquivos_gerados = 1

    pd.DataFrame(payload["recomendacoes_etl"]).to_parquet(
        f"{caminho_base}_{nome_safe}_recommendations.parquet", index=False
    )
    arquivos_gerados += 1

    if payload["dependencias_funcionais"]:
        pd.DataFrame(payload["dependencias_funcionais"]).to_parquet(
            f"{caminho_base}_{nome_safe}_dependencies.parquet", index=False
        )
        arquivos_gerados += 1

    df_gaps = pd.DataFrame(payload["gap_analysis_kpis"])
    df_gaps["semanticas_presentes"] = df_gaps["semanticas_presentes"].apply(json.dumps)
    df_gaps["semanticas_ausentes"] = df_gaps["semanticas_ausentes"].apply(json.dumps)
    df_gaps.to_parquet(f"{caminho_base}_{nome_safe}_gap_analysis.parquet", index=False)
    arquivos_gerados += 1

    meta = dict(payload["metadados_execucao"])
    meta["resumo_qualidade"] = json.dumps(sanear_floats(meta["resumo_qualidade"]), ensure_ascii=False)
    pd.DataFrame([meta]).to_parquet(f"{caminho_base}_{nome_safe}_metadata.parquet", index=False)
    arquivos_gerados += 1

    logger.info(f"✓ Parquet exportado: {arquivos_gerados} arquivos com prefixo '{caminho_base}_{nome_safe}_'")


def _tabela_markdown(linhas: list, cabecalhos: list) -> str:
    out = ["| " + " | ".join(cabecalhos) + " |", "|" + "---|" * len(cabecalhos)]
    for linha in linhas:
        out.append("| " + " | ".join(str(v) for v in linha) + " |")
    return "\n".join(out)


def _formatar_linha_testes_hipotese(nome_coluna: str, testes_hipotese: Dict[str, Any]) -> Optional[str]:
    """Formata os testes de hipótese aplicáveis de uma coluna em uma única
    linha Markdown. Retorna None se nenhum teste for aplicável (evita poluir
    o relatório com "N/A" para cada teste não aplicável)."""
    fragmentos = []

    shapiro = testes_hipotese.get("shapiro_wilk") or {}
    if shapiro.get("aplicavel"):
        normal = "sim" if shapiro.get("normal_provavel") else "não"
        fragmentos.append(f"Shapiro-Wilk p={shapiro.get('p_valor')} (normal prov.: {normal})")

    ic = testes_hipotese.get("intervalo_confianca_media_95") or {}
    if ic.get("aplicavel"):
        fragmentos.append(f"IC95% média: [{ic.get('limite_inferior')}, {ic.get('limite_superior')}]")

    dist = testes_hipotese.get("distribuicao_provavel") or {}
    if dist.get("aplicavel"):
        fragmentos.append(f"Distribuição provável: {dist.get('distribuicao')}")

    chi2 = testes_hipotese.get("qui_quadrado_uniformidade") or {}
    if chi2.get("aplicavel"):
        uniforme = "sim" if chi2.get("distribuicao_uniforme_provavel") else "não"
        fragmentos.append(f"Qui-quadrado uniformidade p={chi2.get('p_valor')} (uniforme prov.: {uniforme})")

    if not fragmentos:
        return None
    return f"- `{nome_coluna}`: " + " | ".join(fragmentos)


def exportar_markdown(payload: Dict[str, Any], caminho: str) -> None:
    meta = payload["metadados_execucao"]
    resumo = meta["resumo_qualidade"]

    partes = [f"# Relatório de Perfilamento — {meta['tabela']}", ""]
    partes.append(
        f"- Linhas originais: {meta['linhas_originais']:,} | Analisadas: {meta['linhas_analisadas']:,}\n"
        f"- Colunas: {meta['total_colunas']} | Com nulos: {resumo['colunas_com_nulos']} | "
        f"100% vazias: {resumo['colunas_100pct_nulas']} | Sensíveis LGPD: {resumo['colunas_sensiveis_lgpd']}\n"
        f"- Semânticas mapeadas: {', '.join(resumo['semanticas_encontradas']) or 'Nenhuma'}\n"
        f"- KPIs habilitados: {resumo['kpis_habilitados']} | Total de recomendações: {resumo['total_recomendacoes']}"
    )

    partes.append("\n## Colunas\n")
    partes.append(_tabela_markdown(
        [[c["Coluna"], c["Tipo_Inferred"], c["Semantica_IA"], f"{c['Pct_Nulos']:.1f}%", c["Caracteristica"]] for c in payload["colunas"]],
        ["Coluna", "Tipo", "Semântica", "% Nulos", "Característica"],
    ))

    partes.append("\n## Recomendações ETL\n")
    if payload["recomendacoes_etl"]:
        for r in sorted(payload["recomendacoes_etl"], key=lambda x: x.get("Prioridade", "")):
            partes.append(f"- **{r['Prioridade']}** [{r['Camada']}] `{r['Coluna']}` — {r['Acao']}")
    else:
        partes.append("Nenhuma recomendação gerada.")

    partes.append("\n## Dependências Funcionais\n")
    if payload["dependencias_funcionais"]:
        for d in payload["dependencias_funcionais"]:
            partes.append(f"- `{d['determinante']}` → `{d['dependente']}`: {d['descricao']}")
    else:
        partes.append("Nenhuma dependência funcional detectada.")

    partes.append("\n## Gap Analysis de KPIs\n")
    partes.append(_tabela_markdown(
        [[g["kpi_id"], g["kpi_nome"], g["status"], g["cobertura_pct"]] for g in payload["gap_analysis_kpis"]],
        ["KPI", "Nome", "Status", "Cobertura"],
    ))

    linhas_testes_hipotese = []
    for c in payload["colunas"]:
        testes_hipotese = (c.get("Stats_Extra") or {}).get("testes_hipotese") or {}
        if not testes_hipotese:
            continue
        linha = _formatar_linha_testes_hipotese(c["Coluna"], testes_hipotese)
        if linha:
            linhas_testes_hipotese.append(linha)

    if linhas_testes_hipotese:
        partes.append("\n## Testes Estatísticos\n")
        partes.extend(linhas_testes_hipotese)

    if payload.get("analise_temporal_series"):
        partes.append("\n## Análise Temporal (ADF / Ljung-Box)\n")
        for t in payload["analise_temporal_series"]:
            adf, lb = t["adf"], t["ljung_box"]
            estac = adf.get("estacionaria") if adf.get("aplicavel") else "N/A"
            autoc = lb.get("autocorrelacionada") if lb.get("aplicavel") else "N/A"
            partes.append(f"- `{t['coluna']}` (ref: `{t['coluna_temporal_referencia']}`) — estacionária: {estac} | autocorrelacionada: {autoc}")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(partes) + "\n")
    logger.info(f"✓ Markdown exportado: '{caminho}'")

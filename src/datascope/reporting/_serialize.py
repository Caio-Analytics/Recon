"""Saneamento e serialização do payload (JSON e Parquet)."""
import json
import math
import re
from typing import Any

import pandas as pd
from loguru import logger


def sanear_floats(obj: Any) -> Any:
    """Converte NaN/Infinity para None recursivamente.

    JSON não tem representação para float não-finito; sem isso o arquivo sai
    sintaticamente inválido para qualquer parser estrito.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanear_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanear_floats(v) for v in obj]
    return obj


def nome_seguro(nome_tabela: str) -> str:
    return re.sub(r"[^\w\-]", "_", nome_tabela)


def gerar_nome_unico(nome_tabela: str, usados: set[str]) -> str:
    """Nome de arquivo seguro e único dentro de uma execução.

    `nome_seguro` colapsa caracteres diferentes no mesmo `_`, então duas abas
    chamadas `Vendas 2024` e `Vendas-2024` gerariam o mesmo arquivo e uma
    sobrescreveria a outra sem aviso.
    """
    base = nome_seguro(nome_tabela)
    candidato = base
    contador = 2
    while candidato in usados:
        candidato = f"{base}_{contador}"
        contador += 1
    usados.add(candidato)
    return candidato


def exportar_json(payload: dict[str, Any], caminho: str, compacto: bool = False) -> None:
    """Exporta o payload completo.

    `compacto` remove a indentação: o JSON é o formato pensado para ir num
    prompt de IA, e numa tabela com centenas de colunas a indentação de 4
    espaços chega a dobrar o tamanho sem agregar nada ao consumidor.
    """
    payload_limpo = sanear_floats(payload)
    with open(caminho, "w", encoding="utf-8") as f:
        if compacto:
            json.dump(payload_limpo, f, ensure_ascii=False, separators=(",", ":"), default=str)
        else:
            json.dump(payload_limpo, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"✓ JSON exportado: '{caminho}'")


def _serializar_colunas_dict(df: pd.DataFrame, colunas: list) -> pd.DataFrame:
    for coluna in colunas:
        if coluna in df.columns:
            df[coluna] = df[coluna].apply(
                lambda x: json.dumps(sanear_floats(x), ensure_ascii=False, default=str)
            )
    return df


def exportar_parquet(payload: dict[str, Any], caminho_base: str, nome_safe: str) -> None:
    """Exporta as seções tabulares do payload em Parquet, para consumo em BI.

    Campos aninhados viram JSON em string: Parquet suporta struct, mas um
    schema aninhado profundo e esparso é desconfortável de consultar na maioria
    das ferramentas de BI.
    """
    arquivos = 0

    df_cols = pd.DataFrame(payload["colunas"])
    df_cols = _serializar_colunas_dict(
        df_cols, ["Stats_Extra", "Alertas", "Qualidade", "Otimizacao"]
    )
    df_cols.to_parquet(f"{caminho_base}_{nome_safe}_columns.parquet", index=False)
    arquivos += 1

    pd.DataFrame(payload["recomendacoes_etl"]).to_parquet(
        f"{caminho_base}_{nome_safe}_recommendations.parquet", index=False
    )
    arquivos += 1

    for chave, sufixo in (
        ("dependencias_funcionais", "dependencies"),
        ("correlacoes", "correlations"),
        ("analise_temporal_series", "timeseries"),
    ):
        if payload.get(chave):
            df = pd.DataFrame(payload[chave])
            if chave == "analise_temporal_series":
                df = _serializar_colunas_dict(df, ["adf", "ljung_box"])
            df.to_parquet(f"{caminho_base}_{nome_safe}_{sufixo}.parquet", index=False)
            arquivos += 1

    df_gaps = pd.DataFrame(payload["gap_analysis_kpis"])
    for coluna in ("semanticas_presentes", "semanticas_ausentes"):
        df_gaps[coluna] = df_gaps[coluna].apply(json.dumps)
    df_gaps.to_parquet(f"{caminho_base}_{nome_safe}_gap_analysis.parquet", index=False)
    arquivos += 1

    meta = dict(payload["metadados_execucao"])
    for chave in ("resumo_qualidade", "score_qualidade", "duplicatas"):
        if chave in meta:
            meta[chave] = json.dumps(sanear_floats(meta[chave]), ensure_ascii=False)
    pd.DataFrame([meta]).to_parquet(f"{caminho_base}_{nome_safe}_metadata.parquet", index=False)
    arquivos += 1

    logger.info(f"✓ Parquet exportado: {arquivos} arquivos com prefixo '{caminho_base}_{nome_safe}_'")

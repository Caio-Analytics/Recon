"""Exportação do payload de profiling: JSON (IA/código), Markdown (humano,
Task 9) e Parquet (opcional, BI)."""
import json
import math
import re
from typing import Any, Dict

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

    pd.DataFrame(payload["recomendacoes_etl"]).to_parquet(
        f"{caminho_base}_{nome_safe}_recommendations.parquet", index=False
    )

    if payload["dependencias_funcionais"]:
        pd.DataFrame(payload["dependencias_funcionais"]).to_parquet(
            f"{caminho_base}_{nome_safe}_dependencies.parquet", index=False
        )

    df_gaps = pd.DataFrame(payload["gap_analysis_kpis"])
    df_gaps["semanticas_presentes"] = df_gaps["semanticas_presentes"].apply(json.dumps)
    df_gaps["semanticas_ausentes"] = df_gaps["semanticas_ausentes"].apply(json.dumps)
    df_gaps.to_parquet(f"{caminho_base}_{nome_safe}_gap_analysis.parquet", index=False)

    meta = dict(payload["metadados_execucao"])
    meta["resumo_qualidade"] = json.dumps(sanear_floats(meta["resumo_qualidade"]), ensure_ascii=False)
    pd.DataFrame([meta]).to_parquet(f"{caminho_base}_{nome_safe}_metadata.parquet", index=False)

    logger.info(f"✓ Parquet exportado: 5 arquivos com prefixo '{caminho_base}_{nome_safe}_'")

"""Carregamento de CSV/XLSX/XLS/XLSB com detecção de encoding e separador."""
import os
from typing import List, Optional, Tuple, Union

import pandas as pd
from charset_normalizer import from_path
from loguru import logger


class FileFormatError(Exception):
    """Extensão de arquivo não suportada pelo profiler."""


class EncodingDetectionError(Exception):
    """Falha ao detectar o encoding de um arquivo CSV."""


def detectar_encoding(caminho: str) -> str:
    try:
        resultado = from_path(caminho).best()
        if resultado is None:
            raise EncodingDetectionError(f"Não foi possível detectar encoding de '{caminho}'")
        encoding = resultado.encoding or "utf-8"
        logger.info(f"Encoding detectado: '{encoding}'")
        return encoding
    except EncodingDetectionError:
        raise
    except Exception as e:
        logger.warning(f"Falha na detecção de encoding: {e}. Usando utf-8.")
        return "utf-8"


def carregar_arquivo(
    caminho: str, aba_excel: Optional[Union[str, int]] = 0
) -> Tuple[pd.DataFrame, str]:
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: '{caminho}'")

    extensao = os.path.splitext(caminho)[1].lower()
    nome_base = os.path.splitext(os.path.basename(caminho))[0]

    if extensao == ".csv":
        encoding = detectar_encoding(caminho)
        for sep in [",", ";", "\t", "|"]:
            try:
                df = pd.read_csv(caminho, encoding=encoding, sep=sep, low_memory=False)
                if len(df.columns) > 1:
                    logger.info(f"CSV carregado com separador '{sep}' | Shape: {df.shape}")
                    return df, nome_base
            except Exception:
                continue
        df = pd.read_csv(caminho, encoding=encoding, sep=None, engine="python", low_memory=False)
        logger.info(f"CSV carregado via engine automático | Shape: {df.shape}")
        return df, nome_base

    engines = {".xlsx": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
    if extensao not in engines:
        raise FileFormatError(
            f"Extensão '{extensao}' não suportada. Use .csv, .xlsx, .xls ou .xlsb."
        )

    engine = engines[extensao]
    try:
        xl = pd.ExcelFile(caminho, engine=engine)
        abas = xl.sheet_names
        aba_alvo: str = abas[aba_excel] if isinstance(aba_excel, int) else str(aba_excel)
        df_raw = pd.read_excel(caminho, sheet_name=aba_alvo, engine=engine)
        df = df_raw if isinstance(df_raw, pd.DataFrame) else pd.DataFrame()
        nome_tabela = f"{nome_base}__{aba_alvo}"
        logger.info(f"[{extensao}] Aba '{aba_alvo}' carregada | Shape: {df.shape}")
        return df, nome_tabela
    except Exception as e:
        raise FileFormatError(f"Falha ao ler '{caminho}' ({extensao}): {e}") from e


def carregar_todas_abas_excel(caminho: str) -> List[Tuple[pd.DataFrame, str]]:
    extensao = os.path.splitext(caminho)[1].lower()
    engines = {".xlsx": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
    engine = engines.get(extensao, "openpyxl")

    xl = pd.ExcelFile(caminho, engine=engine)
    nome_base = os.path.splitext(os.path.basename(caminho))[0]
    resultado = []
    for aba in xl.sheet_names:
        df_aba = pd.read_excel(caminho, sheet_name=aba, engine=engine)
        df_aba = df_aba if isinstance(df_aba, pd.DataFrame) else pd.DataFrame()
        nome_tabela = f"{nome_base}__{aba}"
        logger.info(f"Aba '{aba}' carregada | Shape: {df_aba.shape}")
        resultado.append((df_aba, nome_tabela))
    return resultado

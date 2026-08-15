import csv
import os
from collections.abc import Sequence
from typing import Literal

import pandas as pd
from charset_normalizer import from_path
from loguru import logger

from . import layout as layout_mod

ExcelEngine = Literal["xlrd", "openpyxl", "pyxlsb"]

_ENGINES_EXCEL: dict[str, ExcelEngine] = {".xlsx": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
_SEPARADORES_CANDIDATOS: Sequence[str] = (",", ";", "\t", "|")
_LINHAS_AMOSTRA_SNIFF = 50


class IngestionError(Exception):
    pass


class FileFormatError(IngestionError):
    pass


class EncodingDetectionError(IngestionError):
    pass


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


def detectar_separador(caminho: str, encoding: str) -> str:
    try:
        with open(caminho, encoding=encoding, errors="replace", newline="") as f:
            amostra = [linha for _, linha in zip(range(_LINHAS_AMOSTRA_SNIFF), f, strict=False) if linha.strip()]
    except OSError as e:
        raise FileFormatError(f"Falha ao ler '{caminho}' para detectar o separador: {e}") from e

    if not amostra:
        return ","

    melhor_sep = ","
    melhor_chave = (False, 0)
    for sep in _SEPARADORES_CANDIDATOS:
        try:
            linhas = [linha for linha in csv.reader(amostra, delimiter=sep) if linha]
        except csv.Error:
            continue
        if not linhas:
            continue
        contagens = [len(linha) for linha in linhas]
        n_campos = contagens[0]
        if n_campos < 2:
            continue
        chave = (all(c == n_campos for c in contagens), n_campos)
        if chave > melhor_chave:
            melhor_chave, melhor_sep = chave, sep

    if melhor_chave[1] < 2:
        logger.info("Nenhum separador produz mais de uma coluna — tratando como CSV de coluna única.")
        return ","
    return melhor_sep


def _ler_csv(caminho: str, encoding: str, sep: str) -> pd.DataFrame:
    try:
        return pd.read_csv(caminho, encoding=encoding, sep=sep, engine="pyarrow")
    except Exception as e:
        logger.debug(f"Engine pyarrow recusou o arquivo ({e}); usando o engine C.")
        return pd.read_csv(caminho, encoding=encoding, sep=sep, low_memory=False)


_LINHAS_INSPECAO_LAYOUT = 40


def _matriz_crua_csv(caminho: str, encoding: str, sep: str) -> pd.DataFrame:
    try:
        with open(caminho, encoding=encoding, errors="replace", newline="") as f:
            cruas = [
                linha for _, linha in zip(range(_LINHAS_INSPECAO_LAYOUT), f, strict=False)
            ]
        linhas = list(csv.reader(cruas, delimiter=sep))
    except (OSError, csv.Error):
        return pd.DataFrame()
    if not linhas:
        return pd.DataFrame()
    largura = max(len(linha) for linha in linhas)
    normalizadas = [
        [(c.strip() or None) for c in linha] + [None] * (largura - len(linha))
        for linha in linhas
    ]
    return pd.DataFrame(normalizadas)


def _anexar_layout(df: pd.DataFrame, lay: layout_mod.Layout) -> pd.DataFrame:
    df.attrs["layout"] = lay
    return df


def _preparar_corpo(
    df: pd.DataFrame, avisos_iniciais: list
) -> tuple[pd.DataFrame, layout_mod.Layout]:
    df, lay = layout_mod.analisar_corpo(df)
    lay.avisos = list(avisos_iniciais) + lay.avisos
    return df, lay


def _carregar_csv_com_layout(
    caminho: str, detectar: bool, linha_cabecalho: int | None
) -> pd.DataFrame:
    encoding = detectar_encoding(caminho)
    sep = detectar_separador(caminho, encoding)

    inicio = linha_cabecalho or 0
    avisos: list = []
    if detectar and linha_cabecalho is None:
        inicio, avisos = layout_mod.detectar_linha_cabecalho(
            _matriz_crua_csv(caminho, encoding, sep)
        )

    df = _ler_csv(caminho, encoding, sep) if inicio == 0 else pd.read_csv(
        caminho, encoding=encoding, sep=sep, skiprows=inicio, low_memory=False
    )
    if detectar:
        df, lay = _preparar_corpo(df, avisos)
        lay.linha_cabecalho = inicio
        _anexar_layout(df, lay)
    logger.info(f"CSV carregado com separador {sep!r} | Shape: {df.shape}")
    return df


def _carregar_aba_com_layout(
    caminho: str, aba: str, engine: ExcelEngine, detectar: bool,
    linha_cabecalho: int | None,
) -> pd.DataFrame:
    inicio = linha_cabecalho or 0
    avisos: list = []
    if detectar and linha_cabecalho is None:
        bruto = pd.read_excel(
            caminho, sheet_name=aba, engine=engine, header=None,
            nrows=_LINHAS_INSPECAO_LAYOUT,
        )
        if isinstance(bruto, pd.DataFrame):
            inicio, avisos = layout_mod.detectar_linha_cabecalho(bruto)

    lido = pd.read_excel(caminho, sheet_name=aba, engine=engine, header=inicio)
    df = lido if isinstance(lido, pd.DataFrame) else pd.DataFrame()
    if detectar and not df.empty:
        df, lay = _preparar_corpo(df, avisos)
        lay.linha_cabecalho = inicio
        _anexar_layout(df, lay)
    return df


def carregar_arquivo(
    caminho: str,
    aba_excel: str | int | None = 0,
    detectar_layout: bool = True,
    linha_cabecalho: int | None = None,
) -> tuple[pd.DataFrame, str]:
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: '{caminho}'")

    extensao = os.path.splitext(caminho)[1].lower()
    nome_base = os.path.splitext(os.path.basename(caminho))[0]

    if extensao == ".csv":
        try:
            df = _carregar_csv_com_layout(caminho, detectar_layout, linha_cabecalho)
        except FileFormatError:
            raise
        except Exception as e:
            raise FileFormatError(f"Falha ao ler o CSV '{caminho}': {e}") from e
        return df, nome_base

    if extensao not in _ENGINES_EXCEL:
        raise FileFormatError(
            f"Extensão '{extensao}' não suportada. Use .csv, .xlsx, .xls ou .xlsb."
        )

    engine = _ENGINES_EXCEL[extensao]
    try:
        xl = pd.ExcelFile(caminho, engine=engine)
        abas = xl.sheet_names
        if isinstance(aba_excel, int):
            if not -len(abas) <= aba_excel < len(abas):
                raise FileFormatError(
                    f"Aba de índice {aba_excel} não existe em '{caminho}' "
                    f"({len(abas)} aba(s): {', '.join(map(str, abas))})."
                )
            aba_alvo = abas[aba_excel]
        else:
            aba_alvo = str(aba_excel)
        df = _carregar_aba_com_layout(
            caminho, str(aba_alvo), engine, detectar_layout, linha_cabecalho
        )
        nome_tabela = f"{nome_base}__{aba_alvo}"
        logger.info(f"[{extensao}] Aba '{aba_alvo}' carregada | Shape: {df.shape}")
        return df, nome_tabela
    except FileFormatError:
        raise
    except Exception as e:
        raise FileFormatError(f"Falha ao ler '{caminho}' ({extensao}): {e}") from e


def listar_abas(caminho: str) -> list[str]:
    extensao = os.path.splitext(caminho)[1].lower()
    if extensao not in _ENGINES_EXCEL or not os.path.exists(caminho):
        return []
    try:
        return [str(aba) for aba in pd.ExcelFile(caminho, engine=_ENGINES_EXCEL[extensao]).sheet_names]
    except Exception:
        return []


def carregar_todas_abas_excel(
    caminho: str, detectar_layout: bool = True
) -> list[tuple[pd.DataFrame, str]]:
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: '{caminho}'")

    extensao = os.path.splitext(caminho)[1].lower()
    engine = _ENGINES_EXCEL.get(extensao, "openpyxl")
    nome_base = os.path.splitext(os.path.basename(caminho))[0]

    try:
        xl = pd.ExcelFile(caminho, engine=engine)
        resultado = []
        for aba in xl.sheet_names:
            df_aba = _carregar_aba_com_layout(
                caminho, str(aba), engine, detectar_layout, None
            )
            logger.info(f"Aba '{aba}' carregada | Shape: {df_aba.shape}")
            resultado.append((df_aba, f"{nome_base}__{aba}"))
        return resultado
    except Exception as e:
        raise FileFormatError(f"Falha ao ler '{caminho}' ({extensao}): {e}") from e

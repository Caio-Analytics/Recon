import bz2
import csv
import gzip
import lzma
import os
import zipfile
from collections.abc import Sequence
from typing import Literal

import pandas as pd
from charset_normalizer import from_bytes
from loguru import logger

from . import layout as layout_mod

ExcelEngine = Literal["xlrd", "openpyxl", "pyxlsb"]

_ENGINES_EXCEL: dict[str, ExcelEngine] = {".xlsx": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
_SEPARADORES_CANDIDATOS: Sequence[str] = (",", ";", "\t", "|")
_LINHAS_AMOSTRA_SNIFF = 50





_EXTENSOES_TEXTO = frozenset({".csv", ".tsv", ".txt"})
_COMPACTADAS = (".gz", ".bz2", ".zip", ".xz", ".zst")

EXTENSOES_SUPORTADAS: tuple[str, ...] = (
    ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".xlsb", ".parquet",
    ".csv.gz", ".tsv.gz", ".txt.gz", ".csv.zip",
)




EXTENSOES_DESCOBERTAS: tuple[str, ...] = tuple(
    e for e in EXTENSOES_SUPORTADAS if not e.startswith(".txt")
)


def _partes_da_extensao(caminho: str) -> tuple[str, str]:
    nome = os.path.basename(caminho).lower()
    compactacao = next((c for c in _COMPACTADAS if nome.endswith(c)), "")
    if compactacao:
        nome = nome[: -len(compactacao)]
    return os.path.splitext(nome)[1], compactacao


def formato_de(caminho: str) -> str:
    extensao, _ = _partes_da_extensao(caminho)
    if extensao in _EXTENSOES_TEXTO:
        return "texto"
    if extensao in _ENGINES_EXCEL:
        return "excel"
    if extensao == ".parquet":
        return "parquet"
    return "desconhecido"


class IngestionError(Exception):
    pass


class FileFormatError(IngestionError):
    pass


class EncodingDetectionError(IngestionError):
    pass






_BYTES_AMOSTRA_ENCODING = 256_000


def _amostra_bytes(caminho: str, compactacao: str = "", limite: int = _BYTES_AMOSTRA_ENCODING) -> bytes:
    if compactacao == ".gz":
        with gzip.open(caminho, "rb") as f:
            return f.read(limite)
    if compactacao == ".bz2":
        with bz2.open(caminho, "rb") as f:
            return f.read(limite)
    if compactacao in (".xz", ".zst"):
        with lzma.open(caminho, "rb") as f:
            return f.read(limite)
    if compactacao == ".zip":
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            if not nomes:
                return b""
            with z.open(nomes[0]) as f:
                return f.read(limite)
    with open(caminho, "rb") as f:
        return f.read(limite)


def detectar_encoding(caminho: str, compactacao: str = "") -> str:
    try:
        amostra = _amostra_bytes(caminho, compactacao)
        resultado = from_bytes(amostra).best() if amostra else None
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


def detectar_separador(caminho: str, encoding: str, compactacao: str = "") -> str:
    try:
        texto = _amostra_bytes(caminho, compactacao).decode(encoding, errors="replace")
    except (OSError, LookupError, zipfile.BadZipFile) as e:
        raise FileFormatError(f"Falha ao ler '{caminho}' para detectar o separador: {e}") from e
    amostra = [
        linha + "\n"
        for linha in texto.splitlines()[:_LINHAS_AMOSTRA_SNIFF]
        if linha.strip()
    ]

    if not amostra:
        return ","

    melhor_sep = ","
    melhor_chave = (0.0, 0)
    for sep in _SEPARADORES_CANDIDATOS:
        try:
            linhas = [linha for linha in csv.reader(amostra, delimiter=sep) if linha]
        except csv.Error:
            continue
        if not linhas:
            continue
        contagens = [len(linha) for linha in linhas]
        
        
        
        
        n_campos = max(set(contagens), key=contagens.count)
        if n_campos < 2:
            continue
        consistencia = contagens.count(n_campos) / len(contagens)
        chave = (round(consistencia, 3), n_campos)
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





TAMANHO_LEITURA_EM_BLOCOS = 300 * 1024 * 1024
_LINHAS_POR_BLOCO = 200_000


def _ler_csv_amostrado(
    caminho: str, encoding: str, sep: str, skiprows: int, limite: int
) -> tuple[pd.DataFrame, int]:
    total = 0
    pedacos: list[pd.DataFrame] = []
    leitor = pd.read_csv(
        caminho, encoding=encoding, sep=sep, skiprows=skiprows or None,
        chunksize=_LINHAS_POR_BLOCO, low_memory=False,
    )
    guardadas = 0
    for bloco in leitor:
        total += len(bloco)
        if guardadas >= limite:
            continue
        cabem = min(len(bloco), limite - guardadas)
        if cabem == len(bloco):
            pedacos.append(bloco)
        else:
            pedacos.append(bloco.sample(n=cabem, random_state=42).sort_index())
        guardadas += cabem

    df = pd.concat(pedacos, ignore_index=True) if pedacos else pd.DataFrame()
    logger.info(
        f"Leitura em blocos: {total:,} linhas no arquivo, {len(df):,} carregadas para análise."
    )
    return df, total


def _matriz_crua_csv(caminho: str, encoding: str, sep: str, compactacao: str = "") -> pd.DataFrame:
    try:
        texto = _amostra_bytes(caminho, compactacao).decode(encoding, errors="replace")
        cruas = texto.splitlines()[:_LINHAS_INSPECAO_LAYOUT]
        linhas = list(csv.reader(cruas, delimiter=sep))
    except (OSError, csv.Error, LookupError, zipfile.BadZipFile):
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
    caminho: str, detectar: bool, linha_cabecalho: int | None, limite_linhas: int | None = None
) -> pd.DataFrame:
    _, compactacao = _partes_da_extensao(caminho)
    encoding = detectar_encoding(caminho, compactacao)
    sep = detectar_separador(caminho, encoding, compactacao)

    inicio = linha_cabecalho or 0
    avisos: list = []
    if detectar and linha_cabecalho is None:
        inicio, avisos = layout_mod.detectar_linha_cabecalho(
            _matriz_crua_csv(caminho, encoding, sep, compactacao)
        )

    grande = (
        limite_linhas is not None
        and os.path.getsize(caminho) > TAMANHO_LEITURA_EM_BLOCOS
    )
    if grande and limite_linhas is not None:
        df, total_arquivo = _ler_csv_amostrado(caminho, encoding, sep, inicio, limite_linhas)
        df.attrs["linhas_originais"] = total_arquivo
        df = layout_mod.converter_datas_iso(df)
        if detectar:
            df, lay = _preparar_corpo(df, avisos)
            lay.linha_cabecalho, lay.separador, lay.encoding = inicio, sep, encoding
            _anexar_layout(df, lay)
            df.attrs["linhas_originais"] = total_arquivo
        return df

    df = (
        _ler_csv(caminho, encoding, sep) if inicio == 0
        
        else pd.read_csv(caminho, encoding=encoding, sep=sep, skiprows=inicio, low_memory=False)
    )
    
    
    
    
    df = layout_mod.converter_datas_iso(df)
    if detectar:
        df, lay = _preparar_corpo(df, avisos)
        lay.linha_cabecalho = inicio
        lay.separador = sep
        lay.encoding = encoding
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


def _carregar_parquet(caminho: str) -> pd.DataFrame:
    try:
        return pd.read_parquet(caminho)
    except Exception as e:
        raise FileFormatError(f"Falha ao ler o Parquet '{caminho}': {e}") from e


def carregar_arquivo(
    caminho: str,
    aba_excel: str | int | None = 0,
    detectar_layout: bool = True,
    linha_cabecalho: int | None = None,
    limite_linhas: int | None = None,
) -> tuple[pd.DataFrame, str]:
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: '{caminho}'")

    extensao, compactacao = _partes_da_extensao(caminho)
    nome_base = os.path.basename(caminho)
    for sufixo in (compactacao, extensao):
        if sufixo and nome_base.lower().endswith(sufixo):
            nome_base = nome_base[: -len(sufixo)]

    formato = formato_de(caminho)
    if formato == "parquet":
        df = _carregar_parquet(caminho)
        logger.info(f"Parquet carregado | Shape: {df.shape}")
        return df, nome_base

    if formato == "texto":
        try:
            df = _carregar_csv_com_layout(
                caminho, detectar_layout, linha_cabecalho, limite_linhas
            )
        except FileFormatError:
            raise
        except Exception as e:
            raise FileFormatError(f"Falha ao ler o CSV '{caminho}': {e}") from e
        return df, nome_base

    if formato != "excel":
        raise FileFormatError(
            f"Extensão '{extensao or 'sem extensão'}' não suportada. Use: "
            f"{', '.join(EXTENSOES_SUPORTADAS)}."
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
    extensao, _ = _partes_da_extensao(caminho)
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

    extensao, _ = _partes_da_extensao(caminho)
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

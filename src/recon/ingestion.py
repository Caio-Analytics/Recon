"""Carregamento de CSV/XLSX/XLS/XLSB com detecção de encoding e separador."""
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

# Texto separado por delimitador, qualquer que seja o nome da extensão. O
# detector de separador já resolve tabulação e ponto e vírgula — recusar `.tsv`
# e `.txt` por causa da extensão era barrar arquivo que a ferramenta já sabia
# ler. As compactadas o pandas abre sozinho, pelo sufixo.
_EXTENSOES_TEXTO = frozenset({".csv", ".tsv", ".txt"})
_COMPACTADAS = (".gz", ".bz2", ".zip", ".xz", ".zst")
# Aceitas quando o usuário aponta o arquivo.
EXTENSOES_SUPORTADAS: tuple[str, ...] = (
    ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".xlsb", ".parquet",
    ".csv.gz", ".tsv.gz", ".txt.gz", ".csv.zip",
)
# Procuradas ao varrer uma pasta. `.txt` fica de fora de propósito: pasta de
# trabalho tem `leiame.txt`, `notas.txt` e log de sistema, e varrer tudo isso
# como se fosse tabela enche o relatório de lixo. Apontado na mão, continua
# valendo — quem escolheu o arquivo sabe o que ele é.
EXTENSOES_DESCOBERTAS: tuple[str, ...] = tuple(
    e for e in EXTENSOES_SUPORTADAS if not e.startswith(".txt")
)


def _partes_da_extensao(caminho: str) -> tuple[str, str]:
    """(extensão lógica, extensão de compactação) de um caminho.

    `vendas.csv.gz` devolve `('.csv', '.gz')`; `vendas.xlsx`, `('.xlsx', '')`.
    """
    nome = os.path.basename(caminho).lower()
    compactacao = next((c for c in _COMPACTADAS if nome.endswith(c)), "")
    if compactacao:
        nome = nome[: -len(compactacao)]
    return os.path.splitext(nome)[1], compactacao


def formato_de(caminho: str) -> str:
    """`texto`, `excel`, `parquet` ou `desconhecido`."""
    extensao, _ = _partes_da_extensao(caminho)
    if extensao in _EXTENSOES_TEXTO:
        return "texto"
    if extensao in _ENGINES_EXCEL:
        return "excel"
    if extensao == ".parquet":
        return "parquet"
    return "desconhecido"


class IngestionError(Exception):
    """Base para todas as falhas tipadas de ingestão."""


class FileFormatError(IngestionError):
    """Extensão de arquivo não suportada pelo profiler."""


class EncodingDetectionError(IngestionError):
    """Falha ao detectar o encoding de um arquivo CSV."""


# Bytes lidos para adivinhar o encoding. Antes o detector lia o arquivo
# inteiro: num CSV de 1 GB isso é um passo caro antes de qualquer análise, e a
# resposta não melhora depois dos primeiros parágrafos. Ler por amostra também
# é o que permite detectar dentro de um arquivo compactado.
_BYTES_AMOSTRA_ENCODING = 256_000


def _amostra_bytes(caminho: str, compactacao: str = "", limite: int = _BYTES_AMOSTRA_ENCODING) -> bytes:
    """Primeiros bytes já descompactados do arquivo."""
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
    """Escolhe o separador pela *consistência* do número de campos por linha.

    A heurística anterior aceitava o primeiro separador que produzisse mais de
    uma coluna, e caía num sniffer genérico quando nenhum produzia. Isso
    corrompia CSV de coluna única em silêncio: `nome\\nAna\\nBruno` virava duas
    colunas `['n', 'me']`, com a letra "o" eleita separador.

    Aqui um separador só vence se todas as linhas da amostra se dividirem no
    mesmo número de campos, e uma única coluna é um resultado legítimo — não
    um sinal de falha.
    """
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
        # A largura típica é a *moda*, não a da primeira linha: num arquivo com
        # título ("RELATÓRIO DE PESSOAL") a primeira linha tem um campo só com
        # qualquer separador, e o candidato certo era descartado logo de saída —
        # o arquivo inteiro acabava lido como coluna única.
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
    """Lê o CSV preferindo o engine pyarrow (multi-thread, ~10× mais rápido
    que o engine C nesta carga), com queda para o engine C quando o pyarrow
    recusa o arquivo — ele é bem mais estrito com CSV malformado, que é
    justamente o tipo de arquivo que este profiler existe para analisar."""
    try:
        return pd.read_csv(caminho, encoding=encoding, sep=sep, engine="pyarrow")
    except Exception as e:
        logger.debug(f"Engine pyarrow recusou o arquivo ({e}); usando o engine C.")
        # `encoding_errors="replace"` porque a amostra que decide o encoding
        # olha só o início do arquivo — um export de sistema legado pode ter
        # uma dúzia de bytes corrompidos lá pelo meio (o mesmo byte virando
        # letras diferentes em palavras diferentes é sinal de que a fonte já
        # estava quebrada antes de chegar aqui). Travar a análise inteira de
        # um arquivo de 100+ MB por uma dúzia de bytes é pior que substituir
        # por "�" e avisar — `_avisar_se_encoding_teve_substituicao` cuida do
        # aviso.
        return pd.read_csv(
            caminho, encoding=encoding, sep=sep, low_memory=False, encoding_errors="replace"
        )


_LINHAS_INSPECAO_LAYOUT = 40

# Acima deste tamanho, o CSV é lido em blocos e amostrado durante a leitura.
# O caminho normal carrega o arquivo inteiro e só depois amostra, o que custa
# 5-6× o tamanho do arquivo em RAM — um CSV de 2 GB simplesmente não abre numa
# máquina de 8 GB, e é justamente onde a amostra seria mais necessária.
TAMANHO_LEITURA_EM_BLOCOS = 300 * 1024 * 1024
_LINHAS_POR_BLOCO = 200_000


def _ler_csv_amostrado(
    caminho: str, encoding: str, sep: str, skiprows: int, limite: int
) -> tuple[pd.DataFrame, int]:
    """Lê o CSV em blocos e devolve (amostra, total de linhas do arquivo).

    A amostragem é sistemática por bloco — de cada bloco entra a mesma fração,
    determinística. Não é uniforme sobre o arquivo inteiro como a amostra do
    pipeline, mas preserva a ordem e a distribuição por faixa do arquivo, que
    é o que importa quando o dado vem ordenado por data.
    """
    total = 0
    pedacos: list[pd.DataFrame] = []
    leitor = pd.read_csv(
        caminho, encoding=encoding, sep=sep, skiprows=skiprows or None,
        chunksize=_LINHAS_POR_BLOCO, low_memory=False, encoding_errors="replace",
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
    """Primeiras linhas do CSV como matriz, sem interpretar cabeçalho.

    `read_csv(header=None)` fixa a largura pela primeira linha — num arquivo
    com título de uma célula, todas as linhas seguintes viram "linha ruim" e
    são descartadas, e a detecção de layout ficaria cega. Ler com `csv.reader`
    e preencher até a largura máxima preserva o formato real do arquivo.
    """
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


def _avisar_se_encoding_teve_substituicao(
    df: pd.DataFrame, avisos: list, encoding: str
) -> None:
    """Verifica se sobrou caractere de substituição ("�") depois da leitura
    tolerante e, se sim, deixa isso visível no relatório em vez de silencioso.

    `encoding_errors="replace"` evita a análise inteira travar por um byte
    corrompido, mas trocar sem avisar esconderia justamente o tipo de defeito
    que esta ferramenta existe para apontar.
    """
    colunas_texto = df.select_dtypes(include=["object", "str"]).columns
    if colunas_texto.empty:
        return
    afetadas = [
        str(c) for c in colunas_texto
        if df[c].astype(str).str.contains("�", regex=False).any()
    ]
    if not afetadas:
        return
    avisos.append({
        "tipo": "encoding_substituido",
        "severidade": "🟡 MÉDIA",
        "mensagem": (
            f"Byte que não decodifica em '{encoding}' foi substituído por "
            f"\"�\" em {len(afetadas)} coluna(s): {', '.join(afetadas[:6])}"
            f"{'…' if len(afetadas) > 6 else ''}. Provável origem: bytes "
            "corrompidos no arquivo de origem, não erro de detecção — "
            "confira o valor original na fonte antes de usar essas colunas."
        ),
    })


def _anexar_layout(df: pd.DataFrame, lay: layout_mod.Layout) -> pd.DataFrame:
    """Guarda o diagnóstico de layout no próprio DataFrame.

    Via `attrs` para não mudar a assinatura de `carregar_arquivo` — o pipeline
    lê de lá na hora de montar o payload.
    """
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
        _avisar_se_encoding_teve_substituicao(df, avisos, encoding)
        df = layout_mod.converter_datas_iso(df)
        if detectar:
            df, lay = _preparar_corpo(df, avisos)
            lay.linha_cabecalho, lay.separador, lay.encoding = inicio, sep, encoding
            _anexar_layout(df, lay)
            df.attrs["linhas_originais"] = total_arquivo
        return df

    df = (
        _ler_csv(caminho, encoding, sep) if inicio == 0
        # O pyarrow não aceita `skiprows`: arquivo com preâmbulo cai no engine C.
        else pd.read_csv(
            caminho, encoding=encoding, sep=sep, skiprows=inicio, low_memory=False,
            encoding_errors="replace",
        )
    )
    _avisar_se_encoding_teve_substituicao(df, avisos, encoding)
    # Aplicado aos dois caminhos de propósito. Os engines discordam sobre data
    # ISO — o pyarrow converte o que tem hora, o C não converte nada — e o
    # mesmo arquivo saía com tipos diferentes só por ter, ou não, um título em
    # cima. Aqui os dois terminam no mesmo lugar.
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
    """Parquet já vem tipado e sem preâmbulo — não há layout a detectar.

    Entrou na lista de entrada porque a ferramenta já *exportava* Parquet e não
    lia: quem guardou a camada Silver em Parquet não conseguia perfilá-la.
    """
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
    """Carrega um arquivo, corrigindo o layout de planilha feita à mão.

    `detectar_layout=False` volta ao comportamento cru (cabeçalho na primeira
    linha, nada removido); `linha_cabecalho` força a linha manualmente.
    """
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
    """Nomes das abas de um Excel — vazio para qualquer outro formato.

    Existe para a CLI poder avisar que há abas fora da análise: perfilar
    silenciosamente só a primeira aba de um arquivo com cinco é a forma mais
    fácil de alguém concluir coisa errada sobre os dados.
    """
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

"""
exploratory_profiler.py — Edição Suprema v7.0
─────────────────────────────────────────────────────────────────
Profiler Exploratório Máximo para Análise de CSV e XLSX.
Compatível com Python 3.11 | Pandas 2.1.4 | NumPy 1.24.4

Novas capacidades v7.0 (sobre a v6.0):
  - [scipy.stats]      Teste de normalidade Shapiro-Wilk para colunas numéricas
  - [scipy.stats]      Teste de uniformidade Chi-quadrado para colunas categóricas
  - [scipy.stats]      Intervalo de confiança 95% para a média (t-distribution)
  - [scipy.stats]      Detecção de distribuição provável (normal / lognormal / uniforme / exponencial)
  - [statsmodels]      Teste de estacionariedade ADF para colunas temporais
  - [statsmodels]      Detecção de autocorrelação (Ljung-Box) em séries numéricas ordenadas
  - [unidecode]        Normalização de texto robusta (substitui lógica manual NFD)
  - [pyxlsb]           Suporte nativo a arquivos .xlsb (Excel Binary Workbook)
  - [xlrd]             Suporte nativo a arquivos .xls (Excel legado)
  - [python-dateutil]  Parser de datas multilingual com fallback robusto
  - [loguru]           Sistema de log estruturado com níveis, cores e arquivo de saída

Bibliotecas utilizadas:
  chardet | jellyfish | loguru | numpy | openpyxl | pandas | pyarrow
  python-dateutil | pyxlsb | scipy | statsmodels | tqdm | unidecode | xlrd
"""

import os
import re
import json
import unicodedata
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union, Set

import chardet
import numpy as np
import pandas as pd
import jellyfish
from tqdm import tqdm
from loguru import logger
from unidecode import unidecode
from dateutil import parser as dateutil_parser

# SciPy — testes estatísticos
from scipy import stats as scipy_stats

# Statsmodels — testes de série temporal
try:
    from statsmodels.tsa.stattools import adfuller, acf
    from statsmodels.stats.diagnostic import acorr_ljungbox
    _STATSMODELS_OK = True
except ImportError:
    _STATSMODELS_OK = False

# ─────────────────────────────────────────────────────────────
# CONSTANTES E TAXONOMIA SEMÂNTICA COMPLETA
# ─────────────────────────────────────────────────────────────

# Thresholds globais
THRESHOLD_FUZZY_PADRAO: float = 0.85
THRESHOLD_FUZZY_CURTO: float = 0.95      # Tokens <= 3 chars exigem mais precisão
THRESHOLD_QUASE_CHAVE: float = 0.95      # n_unicos / total_linhas >= X → quase-chave
THRESHOLD_QUASI_CONSTANTE: float = 0.95  # top_value_freq >= X → quasi-constante
THRESHOLD_MISTO_TIPOS: float = 0.05      # >= X% de valores numericos em coluna texto → misto
THRESHOLD_OUTLIER_IQR: float = 1.5       # Multiplicador IQR padrão
THRESHOLD_PADRAO_ESTRUTURADO: float = 0.75
THRESHOLD_DATA_TEXTO: float = 0.80
AMOSTRA_ANALISE: int = 200               # Tamanho da amostra para detecções baseadas em conteúdo

# ── CATEGORIAS FORTES (match exato por token) ──────────────────────────────
# Regra: um token exato da coluna deve estar nesta lista.
# Ambiguidade resolvida: tokens temporais removidos de "Perfil do Colaborador".
# "Resultado de Avaliação" e "Contato / Rede" presentes como categorias fortes.
CATEGORIAS_FORTES: Dict[str, List[str]] = {
    "Chave Identificadora (ID)": [
        "id", "cod", "codigo", "code", "key", "number", "matricula", "mat",
        "cpf", "cnpj", "registro", "chave", "identifier", "iden", "nr", "num", "pk", "fk",
    ],
    "Data / Calendário": [
        "date", "dt", "data", "time", "timestamp", "periodo", "competencia",
        "admissao", "demissao", "nascimento", "vencimento", "inicio", "fim",
        "prazo", "realizacao", "referencia", "vigencia", "expiracao",
    ],
    "Status / Indicador / Flag": [
        "status", "flg", "flag", "is", "has", "state", "situacao",
        "enforced", "ativo", "inativo", "habilitado", "bloqueado",
    ],
    "Valor Financeiro": [
        "salario", "salary", "wage", "remuneracao", "vlr", "valor",
        "custo", "cost", "preco", "price", "receita", "revenue",
        "despesa", "expense", "budget", "orcamento", "bonus",
        "comissao", "honorario", "verba", "provisao", "encargo",
    ],
    "Quantidade / Métrica": [
        "qtd", "quantidade", "count", "total", "volume", "horas", "carga",
        "duracao", "frequencia", "score", "nota", "percentual", "pct",
        "indice", "taxa", "ratio", "proporcao", "media",
    ],
    "Texto Descritivo Livre": [
        "desc", "descricao", "description", "obs", "observacao", "comentario",
        "justificativa", "detalhe", "motivo", "complemento", "historico",
        "task", "function", "resumo", "anotacao", "mensagem",
    ],
    "Nome / Identificação Pessoal": [
        "nome", "name", "colaborador", "funcionario", "empregado",
        "pessoa", "participante", "aluno", "candidato", "usuario", "user",
    ],
    "Contato / Rede": [
        "email", "mail", "telefone", "celular", "ramal",
        "whatsapp", "contato", "fone", "phone",
    ],
    "Resultado de Avaliação": [
        "resultado", "result", "aprovacao", "reprovacao", "conceito",
        "avaliacao", "desempenho", "conclusao", "outcome", "performance",
        "feedback", "rating", "classificacao",
    ],
}

# ── CATEGORIAS FUZZY (match por similaridade Jaro-Winkler) ────────────────
# "admissao", "demissao", "nascimento" removidos — vivem exclusivamente nas Fortes (temporal).
CATEGORIAS_FUZZY: Dict[str, List[str]] = {
    "Localização Geográfica": [
        "country", "province", "city", "facility", "pais", "cidade",
        "estado", "regiao", "municipio", "cep", "uf", "endereco", "local",
        "latitude", "longitude", "bairro", "logradouro",
    ],
    "Estrutura Organizacional": [
        "department", "company", "business", "hierarquia", "departamento",
        "diretoria", "gerencia", "setor", "area", "divisao", "celula",
        "squad", "lotacao", "unidade", "filial", "subsidiaria",
    ],
    "Perfil do Colaborador": [
        "gender", "nationality", "career", "workforce", "staff",
        "genero", "nacionalidade", "idade", "raca", "escolaridade",
        "deficiencia", "etnia",
    ],
    "Cargo / Função": [
        "cargo", "funcao", "nivel", "grade", "posicao", "categoria",
        "classe", "faixa", "perfil", "role", "position", "job",
        "title", "occupation", "hierarquia",
    ],
    "Curso / Treinamento": [
        "curso", "treinamento", "capacitacao", "formacao", "modulo",
        "trilha", "programa", "workshop", "disciplina", "tema",
        "course", "training", "learning", "certificacao",
    ],
}

# Padrões de data e estruturados
_PADROES_DATA: List[str] = [
    r"^\d{4}-\d{2}-\d{2}$",
    r"^\d{2}/\d{2}/\d{4}$",
    r"^\d{2}-\d{2}-\d{4}$",
    r"^\d{4}/\d{2}/\d{2}$",
    r"^\d{2}\.\d{2}\.\d{4}$",
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",
    r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}",
    r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}",
    r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)?$",
]

_PADROES_ESTRUTURADOS: Dict[str, str] = {
    "CPF":      r"^\d{3}[.\-]?\d{3}[.\-]?\d{3}[.\-]?\d{2}$",
    "CNPJ":     r"^\d{2}[.\-]?\d{3}[.\-]?\d{3}[\/\-]?\d{4}[.\-]?\d{2}$",
    "CEP":      r"^\d{5}[-\s]?\d{3}$",
    "E-mail":   r"^[\w.+\-]+@[\w\-]+\.[\w\-]{2,}$",
    "Telefone": r"^[\(\+]?\d[\d\s\-\(\)]{6,14}\d$",
    "UUID":     r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
}

# Tokens que indicam que a coluna é uma chave de sistema (inibe CEP/Telefone)
_TOKENS_CHAVE_SISTEMA: Set[str] = {"id", "code", "number", "key", "cod", "pk", "fk", "identifier"}


# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DE LOG (loguru)
# ─────────────────────────────────────────────────────────────
# Remove o handler padrão do loguru e reconfigura com formato customizado
logger.remove()
logger.add(
    sink=lambda msg: print(msg, end="", flush=True),
    format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}",
    level="DEBUG",
    colorize=True,
)
# Handler opcional para arquivo — ativado se LOG_FILE estiver definido no ambiente
_LOG_FILE = os.environ.get("PROFILER_LOG_FILE")
if _LOG_FILE:
    logger.add(
        sink=_LOG_FILE,
        format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}",
        level="DEBUG",
        rotation="10 MB",
        encoding="utf-8",
    )

# Alias de conveniência mantendo compatibilidade com chamadas log("info", msg) anteriores
def log(nivel: str, msg: str) -> None:
    _mapa = {"info": logger.info, "warn": logger.warning, "error": logger.error, "debug": logger.debug}
    _mapa.get(nivel.lower(), logger.info)(msg)


def _normalizar(texto: str) -> str:
    """
    Normaliza texto para comparação semântica.
    Usa unidecode para transliteração robusta (cobre cirílico, grego, acentos latinos, etc.)
    seguido de lowercase e strip.
    """
    return unidecode(str(texto)).lower().strip()


def _tokenizar(nome_col: str) -> List[str]:
    """Separa camelCase, snake_case, kebab-case e outros separadores em tokens."""
    nome = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(nome_col))
    nome = _normalizar(nome)
    return [p for p in re.split(r"[_\s\-\.]+", nome) if p]


def _detectar_encoding(caminho: str) -> str:
    """Detecta encoding do arquivo via chardet com fallback para utf-8."""
    try:
        with open(caminho, "rb") as f:
            raw = f.read(100_000)
        resultado = chardet.detect(raw)
        enc = resultado.get("encoding") or "utf-8"
        log("info", f"Encoding detectado: '{enc}' (confiança: {resultado.get('confidence', 0):.0%})")
        return enc
    except Exception as e:
        log("warn", f"Falha na detecção de encoding: {e}. Usando utf-8.")
        return "utf-8"


# ─────────────────────────────────────────────────────────────
# INGESTÃO DE ARQUIVO
# ─────────────────────────────────────────────────────────────

def carregar_arquivo(caminho: str, aba_excel: Optional[Union[str, int]] = 0) -> Tuple[pd.DataFrame, str]:
    """
    Carrega CSV, XLSX, XLS ou XLSB automaticamente.
    - CSV: detecção de encoding via chardet + tentativa de múltiplos separadores
    - XLSX: openpyxl
    - XLS: xlrd (formato Excel legado até 2003)
    - XLSB: pyxlsb (Excel Binary Workbook — formato compacto corporativo)
    Retorna (DataFrame, nome_tabela_inferido).
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: '{caminho}'")

    extensao = os.path.splitext(caminho)[1].lower()
    nome_base = os.path.splitext(os.path.basename(caminho))[0]

    if extensao == ".csv":
        encoding = _detectar_encoding(caminho)
        for sep in [",", ";", "\t", "|"]:
            try:
                df = pd.read_csv(caminho, encoding=encoding, sep=sep, low_memory=False)
                if len(df.columns) > 1:
                    log("info", f"CSV carregado com separador '{sep}' | Shape: {df.shape}")
                    return df, nome_base
            except Exception:
                continue
        df = pd.read_csv(caminho, encoding=encoding, sep=None, engine="python", low_memory=False)
        log("info", f"CSV carregado via engine automático | Shape: {df.shape}")
        return df, nome_base

    elif extensao == ".xlsx":
        try:
            xl = pd.ExcelFile(caminho, engine="openpyxl")
            abas = xl.sheet_names
            log("info", f"XLSX com {len(abas)} aba(s): {abas}")
            aba_alvo: str = abas[aba_excel] if isinstance(aba_excel, int) else str(aba_excel)
            df_raw = pd.read_excel(caminho, sheet_name=aba_alvo, engine="openpyxl")
            df: pd.DataFrame = df_raw if isinstance(df_raw, pd.DataFrame) else pd.DataFrame()
            nome_tabela = f"{nome_base}__{aba_alvo}"
            log("info", f"Aba '{aba_alvo}' carregada | Shape: {df.shape}")
            return df, nome_tabela
        except Exception as e:
            raise RuntimeError(f"Falha ao ler XLSX '{caminho}': {e}")

    elif extensao == ".xls":
        # Formato legado Excel 97-2003 — requer xlrd
        try:
            xl = pd.ExcelFile(caminho, engine="xlrd")
            abas = xl.sheet_names
            log("info", f"XLS (legado) com {len(abas)} aba(s): {abas}")
            aba_alvo_xls: str = abas[aba_excel] if isinstance(aba_excel, int) else str(aba_excel)
            df_xls = pd.read_excel(caminho, sheet_name=aba_alvo_xls, engine="xlrd")
            df_xls_typed: pd.DataFrame = df_xls if isinstance(df_xls, pd.DataFrame) else pd.DataFrame()
            nome_tabela_xls = f"{nome_base}__{aba_alvo_xls}"
            log("info", f"XLS aba '{aba_alvo_xls}' carregada | Shape: {df_xls_typed.shape}")
            return df_xls_typed, nome_tabela_xls
        except Exception as e:
            raise RuntimeError(f"Falha ao ler XLS '{caminho}': {e}")

    elif extensao == ".xlsb":
        # Excel Binary Workbook — formato compacto muito usado em exports corporativos SAP/Oracle
        try:
            xl = pd.ExcelFile(caminho, engine="pyxlsb")
            abas = xl.sheet_names
            log("info", f"XLSB (binário) com {len(abas)} aba(s): {abas}")
            aba_alvo_xlsb: str = abas[aba_excel] if isinstance(aba_excel, int) else str(aba_excel)
            df_xlsb = pd.read_excel(caminho, sheet_name=aba_alvo_xlsb, engine="pyxlsb")
            df_xlsb_typed: pd.DataFrame = df_xlsb if isinstance(df_xlsb, pd.DataFrame) else pd.DataFrame()
            nome_tabela_xlsb = f"{nome_base}__{aba_alvo_xlsb}"
            log("info", f"XLSB aba '{aba_alvo_xlsb}' carregada | Shape: {df_xlsb_typed.shape}")
            return df_xlsb_typed, nome_tabela_xlsb
        except Exception as e:
            raise RuntimeError(f"Falha ao ler XLSB '{caminho}': {e}")

    else:
        raise ValueError(f"Extensão '{extensao}' não suportada. Use .csv, .xlsx, .xls ou .xlsb.")


def carregar_todas_abas_excel(caminho: str) -> List[Tuple[pd.DataFrame, str]]:
    """
    Carrega TODAS as abas de um XLSX, XLS ou XLSB.
    Seleciona o engine correto automaticamente por extensão.
    """
    extensao = os.path.splitext(caminho)[1].lower()
    _ENGINE_MAP = {".xlsx": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
    engine = _ENGINE_MAP.get(extensao, "openpyxl")

    xl = pd.ExcelFile(caminho, engine=engine)
    nome_base = os.path.splitext(os.path.basename(caminho))[0]
    resultado = []
    for aba in xl.sheet_names:
        df_aba = pd.read_excel(caminho, sheet_name=aba, engine=engine)
        df_aba_typed: pd.DataFrame = df_aba if isinstance(df_aba, pd.DataFrame) else pd.DataFrame()
        nome_tabela = f"{nome_base}__{aba}"
        log("info", f"Aba '{aba}' carregada | Shape: {df_aba_typed.shape}")
        resultado.append((df_aba_typed, nome_tabela))
    return resultado


# ─────────────────────────────────────────────────────────────
# ENGINE SEMÂNTICA
# ─────────────────────────────────────────────────────────────

def inferir_semantica(nome_col: str, detectado_padrao: str = "Nenhum") -> Dict[str, Any]:
    """
    Pipeline de inferência em 4 estágios:
      1. Fallback por conteúdo (padrão estruturado detectado)
      2. Match exato por tokens (Categorias Fortes) — score graduado por especificidade
      3. Match fuzzy adaptativo com threshold dinâmico (Categorias Fuzzy)
      4. Fallback: Genérico / Não mapeado
    """
    # ── Estágio 1: Conteúdo prevalece sobre nome ──────────────────────────
    _MAPA_PADRAO_SEMANTICA = {
        "CPF":      ("Chave Identificadora (ID)", "Inferred by Content — CPF"),
        "CNPJ":     ("Chave Identificadora (ID)", "Inferred by Content — CNPJ"),
        "UUID":     ("Chave Identificadora (ID)", "Inferred by Content — UUID"),
        "E-mail":   ("Contato / Rede",            "Inferred by Content — E-mail"),
        "Telefone": ("Contato / Rede",             "Inferred by Content — Telefone"),
        "CEP":      ("Localização Geográfica",     "Inferred by Content — CEP"),
    }
    if detectado_padrao in _MAPA_PADRAO_SEMANTICA:
        sem, origem = _MAPA_PADRAO_SEMANTICA[detectado_padrao]
        return {"semantica": sem, "confianca_score": 1.0, "origem": origem}

    # ── Estágio 2: Match exato por tokens ─────────────────────────────────
    tokens = _tokenizar(nome_col)
    tokens_set = set(tokens)

    # Verifica quantos tokens da coluna estão em cada categoria
    # Score graduado: match de token mais específico recebe peso maior
    melhor_forte: Optional[str] = None
    max_tokens_forte: int = 0

    for categoria, palavras in CATEGORIAS_FORTES.items():
        palavras_set = set(palavras)
        intersecao = tokens_set & palavras_set
        if intersecao and len(intersecao) >= max_tokens_forte:
            # Desempate: prefere a categoria com o token mais longo (mais específico)
            if len(intersecao) > max_tokens_forte or (
                len(intersecao) == max_tokens_forte and
                max(len(w) for w in intersecao) > (
                    max(len(w) for w in (tokens_set & set(CATEGORIAS_FORTES.get(melhor_forte, []))))
                    if melhor_forte else 0
                )
            ):
                max_tokens_forte = len(intersecao)
                melhor_forte = categoria

    if melhor_forte:
        # Score graduado: token único curto = 0.90, token longo = 0.95, múltiplos tokens = 1.0
        palavras_match = tokens_set & set(CATEGORIAS_FORTES[melhor_forte])
        max_len = max(len(w) for w in palavras_match)
        if max_tokens_forte > 1:
            score_forte = 1.0
        elif max_len > 5:
            score_forte = 0.95
        else:
            score_forte = 0.90
        return {
            "semantica": melhor_forte,
            "confianca_score": score_forte,
            "origem": f"Strong Token Match ({', '.join(palavras_match)})"
        }

    # ── Estágio 3: Fuzzy Adaptativo ───────────────────────────────────────
    nome_limpo = _normalizar(nome_col)
    melhor_score: float = 0.0
    categoria_vencedora: str = "Genérico / Não mapeado"
    palavra_vencedora: str = ""

    for categoria, palavras_chave in CATEGORIAS_FUZZY.items():
        for palavra in palavras_chave:
            palavra_norm = _normalizar(palavra)
            threshold = THRESHOLD_FUZZY_CURTO if len(palavra_norm) <= 3 else THRESHOLD_FUZZY_PADRAO

            score_full = jellyfish.jaro_winkler_similarity(nome_limpo, palavra_norm)
            scores_tokens = [
                jellyfish.jaro_winkler_similarity(_normalizar(t), palavra_norm)
                for t in tokens
            ]
            score_final = max([score_full] + scores_tokens)

            if score_final >= threshold and score_final > melhor_score:
                melhor_score = score_final
                categoria_vencedora = categoria
                palavra_vencedora = palavra

    return {
        "semantica": categoria_vencedora,
        "confianca_score": round(melhor_score, 4),
        "origem": f"Fuzzy Match ({palavra_vencedora})" if palavra_vencedora else "Unmatched"
    }


# ─────────────────────────────────────────────────────────────
# ENGINE ESTATÍSTICA
# ─────────────────────────────────────────────────────────────

def _calcular_outliers_iqr(serie: pd.Series) -> Dict[str, Any]:
    """Calcula outliers via IQR. Retorna contagens e limites."""
    q1 = float(serie.quantile(0.25))
    q3 = float(serie.quantile(0.75))
    iqr = q3 - q1
    limite_inf = q1 - THRESHOLD_OUTLIER_IQR * iqr
    limite_sup = q3 + THRESHOLD_OUTLIER_IQR * iqr
    n_outliers_inf = int((serie < limite_inf).sum())
    n_outliers_sup = int((serie > limite_sup).sum())
    return {
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "iqr": round(iqr, 4),
        "limite_inferior": round(limite_inf, 4),
        "limite_superior": round(limite_sup, 4),
        "qtd_outliers_inferiores": n_outliers_inf,
        "qtd_outliers_superiores": n_outliers_sup,
        "qtd_outliers_total": n_outliers_inf + n_outliers_sup,
    }


def _calcular_distribuicao_top(serie: pd.Series, top_n: int = 5) -> List[Dict[str, Any]]:
    """Calcula distribuição de frequência dos top N valores. Seguro para qualquer tipo."""
    try:
        vc = serie.value_counts(normalize=True).head(top_n)
        return [
            {"valor": str(k), "frequencia_relativa": round(float(v), 4), "frequencia_pct": f"{v:.1%}"}
            for k, v in vc.items()
        ]
    except Exception:
        return []


def _detectar_mistura_tipos(serie_limpa: pd.Series, amostra_str: List[str]) -> Dict[str, Any]:
    """
    Detecta heterogeneidade de tipos em colunas object.
    Retorna se há mistura e a proporção de cada tipo detectado.
    """
    n = len(amostra_str)
    if n == 0:
        return {"tem_mistura": False}

    _RE_NUMERICO = re.compile(r"^-?\d+([.,]\d+)?$")
    _RE_DATA = re.compile("|".join(_PADROES_DATA))

    qtd_num = sum(1 for v in amostra_str if _RE_NUMERICO.match(v.replace(",", ".")))
    qtd_data = sum(1 for v in amostra_str if _RE_DATA.match(v))
    qtd_vazio = sum(1 for v in amostra_str if v.strip() == "")
    qtd_texto_puro = n - qtd_num - qtd_data - qtd_vazio

    proporcoes = {
        "numerico": round(qtd_num / n, 4),
        "data": round(qtd_data / n, 4),
        "texto_puro": round(qtd_texto_puro / n, 4),
        "vazio_ou_nulo": round(qtd_vazio / n, 4),
    }

    tipos_dominantes = [k for k, v in proporcoes.items() if v >= THRESHOLD_MISTO_TIPOS]
    tem_mistura = len(tipos_dominantes) > 1

    return {
        "tem_mistura": tem_mistura,
        "tipos_detectados": tipos_dominantes if tem_mistura else [],
        "proporcoes": proporcoes if tem_mistura else {},
    }


def analisar_estatisticas(serie: pd.Series, total_linhas: int) -> Dict[str, Any]:
    """
    Análise estatística completa e blindada.
    Cobre: tipagem, estatísticas descritivas, outliers IQR, comprimento de string,
    distribuição de frequência, mistura de tipos, quasi-constante e quase-chave.
    """
    nome_coluna = str(serie.name)

    # ── Nulos ──────────────────────────────────────────────────────────────
    nulos_qtd = int(serie.isna().sum())
    nulos_pct = round((nulos_qtd / total_linhas) * 100, 4) if total_linhas > 0 else 0.0

    serie_limpa = serie.dropna()
    n_validos = len(serie_limpa)
    n_unicos = int(serie_limpa.nunique())
    tipo_bruto = str(serie_limpa.dtype)

    # ── Amostra determinística (usada em toda análise de conteúdo) ─────────
    n_amostrar = min(AMOSTRA_ANALISE, n_validos)
    amostra_serie = serie_limpa.sample(n=n_amostrar, random_state=42) if n_validos > 0 else serie_limpa
    amostra_str = amostra_serie.astype(str).tolist()

    # Variáveis de saída
    flag_data_como_texto = False
    flag_padrao_estruturado = "Nenhum"
    estatisticas_extra: Dict[str, Any] = {}
    alerta_mistura_tipos: Dict[str, Any] = {"tem_mistura": False}

    # ── Classificação de tipo e estatísticas ───────────────────────────────
    if "float" in tipo_bruto or "int" in tipo_bruto:
        # Limpa inf/-inf para operações matemáticas
        numericos = serie_limpa.replace([np.inf, -np.inf], np.nan).dropna()

        if numericos.empty:
            tipo_amigavel = "Número (Apenas Inf/NaN)"
        elif (numericos % 1 == 0).all():
            tipo_amigavel = "Número Inteiro"
        else:
            tipo_amigavel = "Número Decimal"

        qtd_inf = int((serie_limpa.isin([np.inf, -np.inf])).sum())

        if not numericos.empty:
            std_val = float(numericos.std())
            media_val = float(numericos.mean())
            mediana_val = float(numericos.median())
            estatisticas_extra = {
                "min": round(float(numericos.min()), 6),
                "max": round(float(numericos.max()), 6),
                "media": round(media_val, 6),
                "mediana": round(mediana_val, 6),
                "desvio_padrao": round(std_val, 6),
                "coef_variacao": round(std_val / media_val, 4) if media_val != 0 else None,
                "assimetria": round(float(np.float64(numericos.skew())), 4),
                "curtose": round(float(np.float64(numericos.kurt())), 4),
                "qtd_negativos": int((numericos < 0).sum()),
                "qtd_zeros": int((numericos == 0).sum()),
                "qtd_inf": qtd_inf,
                "outliers_iqr": _calcular_outliers_iqr(numericos),
                "distribuicao_top5": _calcular_distribuicao_top(serie_limpa, 5),
            }

    elif "datetime" in tipo_bruto:
        tipo_amigavel = "Data / Hora"
        if n_validos > 0:
            estatisticas_extra = {
                "min_data": str(serie_limpa.min()),
                "max_data": str(serie_limpa.max()),
                "range_dias": (serie_limpa.max() - serie_limpa.min()).days,
                "distribuicao_top5": _calcular_distribuicao_top(serie_limpa, 5),
            }

    elif "bool" in tipo_bruto:
        tipo_amigavel = "Booleano"
        if n_validos > 0:
            true_pct = float(serie_limpa.sum()) / n_validos
            estatisticas_extra = {
                "qtd_true": int(serie_limpa.sum()),
                "qtd_false": n_validos - int(serie_limpa.sum()),
                "pct_true": round(true_pct, 4),
            }

    else:
        # ── Branch Texto / Object ──────────────────────────────────────────
        tipo_amigavel = "Texto"

        if amostra_str:
            # Detecção de data como texto
            matches_dt = sum(1 for v in amostra_str if any(re.match(p, v) for p in _PADROES_DATA))
            if len(amostra_str) > 0 and (matches_dt / len(amostra_str)) >= THRESHOLD_DATA_TEXTO:
                tipo_amigavel = "Texto (⚠️ Parece Data)"
                flag_data_como_texto = True
            else:
                # Detecção de padrão estruturado
                tokens_col = set(_tokenizar(nome_coluna))
                eh_chave_sistema = bool(tokens_col & _TOKENS_CHAVE_SISTEMA)
                for padrao_nome, regex in _PADROES_ESTRUTURADOS.items():
                    if eh_chave_sistema and padrao_nome in ("CEP", "Telefone"):
                        continue
                    matches_pad = sum(1 for v in amostra_str if re.match(regex, v))
                    if len(amostra_str) > 0 and (matches_pad / len(amostra_str)) >= THRESHOLD_PADRAO_ESTRUTURADO:
                        flag_padrao_estruturado = padrao_nome
                        break

                # Detecção de mistura de tipos
                alerta_mistura_tipos = _detectar_mistura_tipos(serie_limpa, amostra_str)

        # Estatísticas de comprimento de string
        if n_validos > 0:
            lens = serie_limpa.astype(str).str.len()
            comprimento_unico = int(lens.min()) == int(lens.max())
            estatisticas_extra = {
                "str_len_min": int(lens.min()),
                "str_len_max": int(lens.max()),
                "str_len_media": round(float(lens.mean()), 2),
                "str_len_std": round(float(lens.std()), 2) if n_validos > 1 else 0.0,
                "comprimento_fixo": comprimento_unico,
                "distribuicao_top5": _calcular_distribuicao_top(serie_limpa, 5),
            }

    # ── Classificação de Característica (mutuamente exclusiva, com prioridade) ──
    ratio_unicidade = n_unicos / total_linhas if total_linhas > 0 else 0.0

    # Avaliação de quasi-constante
    top_freq = 0.0
    if n_validos > 0 and n_unicos > 1:
        try:
            top_freq = float(serie_limpa.value_counts(normalize=True).iloc[0])
        except Exception:
            top_freq = 0.0

    if nulos_pct == 100.0:
        caracteristica = "⚠️ Coluna 100% Vazia"
    elif n_unicos == 0:
        caracteristica = "⚠️ Sem Valores Válidos"
    elif n_unicos == 1:
        caracteristica = "🔒 Valor Constante"
    elif top_freq >= THRESHOLD_QUASI_CONSTANTE and n_unicos > 1:
        caracteristica = f"⚠️ Quasi-Constante ({top_freq:.1%} em um único valor)"
    elif ratio_unicidade == 1.0 and total_linhas > 1:
        caracteristica = "🔑 Chave Primária Potencial"
    elif ratio_unicidade >= THRESHOLD_QUASE_CHAVE and total_linhas > 1:
        caracteristica = f"🔑 Quase-Chave ({ratio_unicidade:.1%} únicos — possível dado sujo)"
    elif "Data" in tipo_amigavel:
        caracteristica = "📅 Série Temporal"
    elif 1 < n_unicos <= 25:
        caracteristica = "🏷️ Categórica / Dimensão Curta"
    elif 25 < n_unicos <= 100:
        caracteristica = "📂 Dimensão Média"
    else:
        if "Texto" in tipo_amigavel:
            caracteristica = "📋 Dimensão Longa (Texto Livre)"
        elif "Número" in tipo_amigavel:
            caracteristica = "📊 Métrica Contínua"
        else:
            caracteristica = "📋 Atributo Geral"

    # ── Amostra de valores representativa ─────────────────────────────────
    # Para categóricas curtas: mostra todos os únicos reais
    # Para demais: amostra determinística da série limpa completa
    valores_amostra: List[str] = []
    if n_validos > 0:
        if n_unicos <= 25:
            valores_amostra = [str(v) for v in serie_limpa.unique().tolist()]
        else:
            valores_amostra = serie_limpa.drop_duplicates().sample(
                min(10, n_unicos), random_state=42
            ).astype(str).tolist()

    return {
        "tipo_dados": tipo_amigavel,
        "valores_unicos": n_unicos,
        "nulos_qtd": nulos_qtd,
        "nulos_pct": nulos_pct,
        "caracteristica": caracteristica,
        "ratio_unicidade": round(ratio_unicidade, 4),
        "amostra_representativa": valores_amostra,
        "estatisticas_adicionais": estatisticas_extra,   # Dict aninhado — não serializado
        "flags": {
            "is_date_as_text": flag_data_como_texto,
            "detected_pattern": flag_padrao_estruturado,
            "mistura_tipos": alerta_mistura_tipos,
        },
    }


# ─────────────────────────────────────────────────────────────
# ANÁLISE DE DEPENDÊNCIAS FUNCIONAIS
# ─────────────────────────────────────────────────────────────

def detectar_dependencias_funcionais(df: pd.DataFrame, colunas_meta: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detecta dependências funcionais entre pares de colunas.
    Lógica: Se agrupar por A e contar nunique(B) == 1 para todos os grupos → B é funcionalmente dependente de A.
    Foca em colunas com cardinalidade < 500 para eficiência.
    """
    dependencias = []

    # Filtra colunas com cardinalidade manejável para análise de FD
    candidatas = [
        m["Coluna"] for m in colunas_meta
        if m.get("Qtd_Unicos", 999999) < 500
        and m.get("Caracteristica", "") not in ("⚠️ Coluna 100% Vazia", "⚠️ Sem Valores Válidos")
    ]

    for i, col_a in enumerate(candidatas):
        for col_b in candidatas[i + 1:]:
            if col_a == col_b:
                continue
            try:
                # A → B
                max_unicos_b_por_a = df.groupby(col_a)[col_b].nunique().max()
                if max_unicos_b_por_a == 1:
                    dependencias.append({
                        "determinante": col_a,
                        "dependente": col_b,
                        "tipo": "Dependência Funcional Direta",
                        "descricao": f"'{col_a}' determina unicamente '{col_b}'. Candidate à desnormalização ou chave composta."
                    })
                # B → A
                max_unicos_a_por_b = df.groupby(col_b)[col_a].nunique().max()
                if max_unicos_a_por_b == 1:
                    dependencias.append({
                        "determinante": col_b,
                        "dependente": col_a,
                        "tipo": "Dependência Funcional Direta",
                        "descricao": f"'{col_b}' determina unicamente '{col_a}'. Candidate à desnormalização ou chave composta."
                    })
            except Exception:
                continue

    return dependencias


# ─────────────────────────────────────────────────────────────
# GAP ANALYSIS SEMÂNTICO
# ─────────────────────────────────────────────────────────────

# Base de regras de KPIs replicada aqui para gerar gaps sem depender do cross-profiler
_REGRAS_KPI_LOCAL = [
    {
        "id": "KPI_HR_001",
        "nome": "Volume de Esforço por Departamento",
        "semanticas": ["Estrutura Organizacional", "Quantidade / Métrica"],
    },
    {
        "id": "KPI_HR_002",
        "nome": "Distribuição de Liderança por Perfil",
        "semanticas": ["Perfil do Colaborador", "Cargo / Função"],
    },
    {
        "id": "KPI_HR_003",
        "nome": "Evolução de Custo de Pessoal",
        "semanticas": ["Valor Financeiro", "Data / Calendário"],
    },
    {
        "id": "KPI_HR_004",
        "nome": "Análise de Turnover",
        "semanticas": ["Perfil do Colaborador", "Data / Calendário"],
    },
    {
        "id": "KPI_TREIN_001",
        "nome": "Efetividade de Treinamentos",
        "semanticas": ["Curso / Treinamento", "Resultado de Avaliação"],
    },
    {
        "id": "KPI_GEO_001",
        "nome": "Distribuição Geográfica de Headcount",
        "semanticas": ["Localização Geográfica", "Estrutura Organizacional"],
    },
]


def gerar_gap_analysis(semanticas_presentes: Set[str]) -> List[Dict[str, Any]]:
    """
    Para cada regra KPI, reporta se está habilitada, parcialmente habilitada ou bloqueada.
    """
    gaps = []
    for regra in _REGRAS_KPI_LOCAL:
        exigidas = set(regra["semanticas"])
        presentes = exigidas & semanticas_presentes
        ausentes = exigidas - semanticas_presentes
        cobertura = len(presentes) / len(exigidas)

        if cobertura == 1.0:
            status = "✅ Habilitado"
        elif cobertura > 0:
            status = "⚠️ Parcialmente Habilitado"
        else:
            status = "❌ Bloqueado"

        gaps.append({
            "kpi_id": regra["id"],
            "kpi_nome": regra["nome"],
            "status": status,
            "cobertura_pct": f"{cobertura:.0%}",
            "semanticas_presentes": sorted(list(presentes)),
            "semanticas_ausentes": sorted(list(ausentes)),
            "recomendacao": (
                f"Inclua colunas com semântica: {', '.join(ausentes)}"
                if ausentes else "Tabela possui todos os requisitos para este KPI."
            ),
        })
    return gaps


# ─────────────────────────────────────────────────────────────
# CLASSE CORE ORQUESTRADORA
# ─────────────────────────────────────────────────────────────

class SASDataProfiler:
    """
    Orquestrador principal do profiler.
    Aceita DataFrame diretamente (processar_dataframe) ou
    caminho de arquivo CSV/XLSX (processar_arquivo).
    """

    def __init__(self, limite_amostra: int = 500_000):
        """
        limite_amostra: máximo de linhas usadas para análise.
        No SAS Viya com memória abundante, pode ser elevado sem restrição.
        """
        self.limite_amostra = limite_amostra

    def processar_arquivo(
        self,
        caminho: str,
        aba_excel: Optional[Union[str, int]] = 0,
        processar_todas_abas: bool = False,
        formato_saida: str = "json",
        caminho_base_saida: str = "profiler_output",
    ) -> List[Dict[str, Any]]:
        """
        Pipeline completo: carrega arquivo → processa → exporta.
        Para XLSX com processar_todas_abas=True, itera sobre todas as abas.
        Retorna lista de payloads (um por aba/arquivo).
        """
        extensao = os.path.splitext(caminho)[1].lower()
        resultados = []

        if processar_todas_abas and extensao in (".xlsx", ".xls"):
            pares = carregar_todas_abas_excel(caminho)
        else:
            df, nome = carregar_arquivo(caminho, aba_excel=aba_excel)
            pares = [(df, nome)]

        for df, nome_tabela in pares:
            payload = self.processar_dataframe(df, nome_tabela)
            self.exportar_resultado(payload, formato=formato_saida, caminho_base=caminho_base_saida)
            resultados.append(payload)

        return resultados

    def processar_dataframe(self, df: pd.DataFrame, nome_tabela: str) -> Dict[str, Any]:
        """
        Análise completa em memória.
        Inclui: perfil de colunas, recomendações ETL, dependências funcionais, gap analysis.
        """
        if df is None or df.empty:
            raise ValueError(f"DataFrame '{nome_tabela}' está vazio ou inválido.")

        total_linhas = len(df)
        df_alvo = (
            df.sample(n=self.limite_amostra, random_state=42)
            if total_linhas > self.limite_amostra
            else df
        )
        linhas_analisadas = len(df_alvo)

        log("info", f"{'─'*60}")
        log("info", f"Iniciando profiling: '{nome_tabela}'")
        log("info", f"Linhas totais: {total_linhas:,} | Analisando: {linhas_analisadas:,} | Colunas: {len(df_alvo.columns)}")
        log("info", f"{'─'*60}")

        lista_colunas: List[Dict[str, Any]] = []
        recomendacoes: List[Dict[str, Any]] = []
        semanticas_presentes: Set[str] = set()

        for coluna in tqdm(df_alvo.columns, desc=f"  Profilando '{nome_tabela}'", unit="col"):
            serie = df_alvo[coluna]
            stats = analisar_estatisticas(serie, linhas_analisadas)

            padrao_estruturado = stats["flags"]["detected_pattern"]
            sem = inferir_semantica(str(coluna), detectado_padrao=padrao_estruturado)

            if sem["semantica"] != "Genérico / Não mapeado":
                semanticas_presentes.add(sem["semantica"])

            # ── Registro de coluna ─────────────────────────────────────────
            registro: Dict[str, Any] = {
                # Identificação
                "Tabela_Origem":       str(nome_tabela),
                "Coluna":              str(coluna),
                # Tipo e Semântica
                "Tipo_Inferred":       stats["tipo_dados"],
                "Semantica_IA":        sem["semantica"],
                "Semantica_Score":     sem["confianca_score"],
                "Semantica_Origem":    sem["origem"],
                # Qualidade
                "Qtd_Unicos":          stats["valores_unicos"],
                "Ratio_Unicidade":     stats["ratio_unicidade"],
                "Qtd_Nulos":           stats["nulos_qtd"],
                "Pct_Nulos":           stats["nulos_pct"],
                # Classificação
                "Caracteristica":      stats["caracteristica"],
                # LGPD
                "Dado_Sensivel_LGPD":  padrao_estruturado,
                # Conteúdo
                "Amostra_Valores":     ", ".join(stats["amostra_representativa"]),
                # Alertas (dicts aninhados — não strings)
                "Alertas": {
                    "data_como_texto":  stats["flags"]["is_date_as_text"],
                    "mistura_tipos":    stats["flags"]["mistura_tipos"],
                },
                # Estatísticas descritivas completas (dict aninhado)
                "Stats_Extra":         stats["estatisticas_adicionais"],
            }
            lista_colunas.append(registro)

            # ── Geração de Recomendações Quantificadas ─────────────────────
            n_validos = linhas_analisadas - stats["nulos_qtd"]
            pct_validos = (n_validos / linhas_analisadas * 100) if linhas_analisadas > 0 else 0.0

            if "Vazia" in stats["caracteristica"]:
                recomendacoes.append({
                    "Tabela": nome_tabela, "Coluna": str(coluna),
                    "Prioridade": "🔴 ALTA", "Camada": "Bronze",
                    "Acao": f"Remover '{coluna}': 100% nulos. Zero impacto em dados úteis.",
                    "Linhas_Afetadas": 0,
                })

            if stats["flags"]["is_date_as_text"]:
                recomendacoes.append({
                    "Tabela": nome_tabela, "Coluna": str(coluna),
                    "Prioridade": "🔴 ALTA", "Camada": "Bronze",
                    "Acao": f"Converter '{coluna}' para Date/Datetime. Viabiliza filtros e JOINs temporais.",
                    "Linhas_Afetadas": n_validos,
                    "Pct_Impacto": f"{pct_validos:.1f}%",
                })

            if padrao_estruturado != "Nenhum":
                recomendacoes.append({
                    "Tabela": nome_tabela, "Coluna": str(coluna),
                    "Prioridade": "🔴 ALTA", "Camada": "Silver",
                    "Acao": f"LGPD: Mascarar/Hashear '{coluna}' ({padrao_estruturado}). Protege {n_validos:,} registros ({pct_validos:.1f}%).",
                    "Linhas_Afetadas": n_validos,
                    "Pct_Impacto": f"{pct_validos:.1f}%",
                })

            if "Chave Primária Potencial" in stats["caracteristica"]:
                recomendacoes.append({
                    "Tabela": nome_tabela, "Coluna": str(coluna),
                    "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
                    "Acao": f"Promover '{coluna}' como PK. {stats['valores_unicos']:,} valores únicos garantem integridade.",
                    "Linhas_Afetadas": n_validos,
                    "Pct_Impacto": f"{pct_validos:.1f}%",
                })

            if "Quase-Chave" in stats["caracteristica"]:
                recomendacoes.append({
                    "Tabela": nome_tabela, "Coluna": str(coluna),
                    "Prioridade": "🟡 MÉDIA", "Camada": "Bronze",
                    "Acao": f"'{coluna}' tem {stats['ratio_unicidade']:.1%} de unicidade — verificar duplicatas ou dados sujos antes de usar como chave.",
                    "Linhas_Afetadas": n_validos,
                    "Pct_Impacto": f"{pct_validos:.1f}%",
                })

            if "Quasi-Constante" in stats["caracteristica"]:
                recomendacoes.append({
                    "Tabela": nome_tabela, "Coluna": str(coluna),
                    "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
                    "Acao": f"'{coluna}' é quasi-constante. Avaliar remoção ou tratamento como constante no pipeline.",
                    "Linhas_Afetadas": n_validos,
                    "Pct_Impacto": f"{pct_validos:.1f}%",
                })

            if stats["flags"]["mistura_tipos"].get("tem_mistura"):
                tipos = stats["flags"]["mistura_tipos"].get("tipos_detectados", [])
                recomendacoes.append({
                    "Tabela": nome_tabela, "Coluna": str(coluna),
                    "Prioridade": "🔴 ALTA", "Camada": "Bronze",
                    "Acao": f"'{coluna}' contém mistura de tipos: {tipos}. Normalizar antes de qualquer transformação.",
                    "Linhas_Afetadas": n_validos,
                    "Pct_Impacto": f"{pct_validos:.1f}%",
                })

            # Outliers numéricos
            outliers_info = stats["estatisticas_adicionais"].get("outliers_iqr", {})
            if outliers_info.get("qtd_outliers_total", 0) > 0:
                n_out = outliers_info["qtd_outliers_total"]
                pct_out = round(n_out / linhas_analisadas * 100, 1) if linhas_analisadas > 0 else 0.0
                if pct_out > 1.0:  # Só reporta se > 1% de outliers
                    recomendacoes.append({
                        "Tabela": nome_tabela, "Coluna": str(coluna),
                        "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
                        "Acao": (
                            f"'{coluna}' tem {n_out:,} outliers IQR ({pct_out:.1f}%). "
                            f"Intervalo esperado: [{outliers_info['limite_inferior']}, {outliers_info['limite_superior']}]."
                        ),
                        "Linhas_Afetadas": n_out,
                        "Pct_Impacto": f"{pct_out:.1f}%",
                    })

        # ── Dependências Funcionais ────────────────────────────────────────
        log("info", "Analisando dependências funcionais entre colunas...")
        dependencias = detectar_dependencias_funcionais(df_alvo, lista_colunas)
        if dependencias:
            log("info", f"  → {len(dependencias)} dependência(s) funcional(is) encontrada(s).")
        else:
            log("info", "  → Nenhuma dependência funcional detectada.")

        # ── Gap Analysis ───────────────────────────────────────────────────
        log("info", "Gerando Gap Analysis de KPIs...")
        gaps = gerar_gap_analysis(semanticas_presentes)

        # ── Resumo de Qualidade ────────────────────────────────────────────
        total_colunas = len(lista_colunas)
        colunas_com_nulos = sum(1 for c in lista_colunas if c["Pct_Nulos"] > 0)
        colunas_sensiveis = sum(1 for c in lista_colunas if c["Dado_Sensivel_LGPD"] != "Nenhum")
        colunas_vazias = sum(1 for c in lista_colunas if "Vazia" in c["Caracteristica"])
        kpis_habilitados = sum(1 for g in gaps if "✅" in g["status"])

        if not recomendacoes:
            recomendacoes.append({
                "Tabela": nome_tabela, "Coluna": "N/A",
                "Prioridade": "🟢 INFO", "Camada": "N/A",
                "Acao": "Nenhuma anomalia crítica estrutural encontrada.",
                "Linhas_Afetadas": 0, "Pct_Impacto": "0%",
            })

        return {
            "metadados_execucao": {
                "tabela":              nome_tabela,
                "timestamp_utc":       datetime.utcnow().isoformat(),
                "versao_profiler":     "6.0-Supreme",
                "linhas_originais":    total_linhas,
                "linhas_analisadas":   linhas_analisadas,
                "total_colunas":       total_colunas,
                "resumo_qualidade": {
                    "colunas_com_nulos":   colunas_com_nulos,
                    "colunas_100pct_nulas": colunas_vazias,
                    "colunas_sensiveis_lgpd": colunas_sensiveis,
                    "semanticas_mapeadas": len(semanticas_presentes),
                    "semanticas_encontradas": sorted(list(semanticas_presentes)),
                    "kpis_habilitados":    kpis_habilitados,
                    "total_recomendacoes": len(recomendacoes),
                },
            },
            "colunas":                  lista_colunas,
            "recomendacoes_etl":        recomendacoes,
            "dependencias_funcionais":  dependencias,
            "gap_analysis_kpis":        gaps,
        }

    def exportar_resultado(
        self,
        payload: Dict[str, Any],
        formato: str = "json",
        caminho_base: str = "profiler_output",
    ) -> None:
        """
        Exporta o payload em JSON (estrutura completa) ou Parquet (tabelas planas separadas).
        JSON mantém Stats_Extra como dict aninhado.
        Parquet serializa Stats_Extra como string JSON para compatibilidade colunar.
        """
        formato = formato.lower()
        nome_tab = payload["metadados_execucao"]["tabela"]
        # Sanitiza nome da tabela para uso em nome de arquivo
        nome_safe = re.sub(r"[^\w\-]", "_", nome_tab)

        if formato == "json":
            caminho_out = f"{caminho_base}_{nome_safe}.json"
            with open(caminho_out, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=4, default=str)
            log("info", f"✓ JSON exportado: '{caminho_out}'")

        elif formato == "parquet":
            # Tabela de colunas — Stats_Extra serializado para string (único campo não-plano)
            df_cols = pd.DataFrame(payload["colunas"])
            df_cols["Stats_Extra"] = df_cols["Stats_Extra"].apply(
                lambda x: json.dumps(x, ensure_ascii=False, default=str) if isinstance(x, dict) else str(x)
            )
            df_cols["alerta_data_texto"] = df_cols["Alertas"].apply(lambda x: x.get("data_como_texto", False))
            df_cols["alerta_mistura_tipos"] = df_cols["Alertas"].apply(
                lambda x: json.dumps(x.get("mistura_tipos", {}), ensure_ascii=False)
            )
            df_cols = df_cols.drop(columns=["Alertas"])
            df_cols.to_parquet(f"{caminho_base}_{nome_safe}_columns.parquet", index=False)

            # Tabela de recomendações
            pd.DataFrame(payload["recomendacoes_etl"]).to_parquet(
                f"{caminho_base}_{nome_safe}_recommendations.parquet", index=False
            )

            # Tabela de dependências funcionais
            if payload["dependencias_funcionais"]:
                pd.DataFrame(payload["dependencias_funcionais"]).to_parquet(
                    f"{caminho_base}_{nome_safe}_dependencies.parquet", index=False
                )

            # Tabela de gap analysis
            df_gaps = pd.DataFrame(payload["gap_analysis_kpis"])
            df_gaps["semanticas_presentes"] = df_gaps["semanticas_presentes"].apply(json.dumps)
            df_gaps["semanticas_ausentes"] = df_gaps["semanticas_ausentes"].apply(json.dumps)
            df_gaps.to_parquet(f"{caminho_base}_{nome_safe}_gap_analysis.parquet", index=False)

            # Metadados de execução
            meta = payload["metadados_execucao"].copy()
            meta["resumo_qualidade"] = json.dumps(meta["resumo_qualidade"], ensure_ascii=False)
            meta["semanticas_encontradas"] = json.dumps(
                meta["resumo_qualidade"] if isinstance(meta["resumo_qualidade"], list)
                else meta.get("resumo_qualidade", ""), ensure_ascii=False
            )
            pd.DataFrame([meta]).to_parquet(
                f"{caminho_base}_{nome_safe}_metadata.parquet", index=False
            )

            log("info", f"✓ Parquet exportado: 4 arquivos com prefixo '{caminho_base}_{nome_safe}_'")

        else:
            raise ValueError(f"Formato '{formato}' inválido. Use 'json' ou 'parquet'.")


# ─────────────────────────────────────────────────────────────
# SIMULADOR / TESTE LOCAL
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log("info", "═" * 60)
    log("info", "SAS DataProfiler Supreme v6.0 — Modo de Teste Local")
    log("info", "═" * 60)

    # ── Exemplo 1: Processar DataFrame direto (compatibilidade com versões anteriores) ──
    df_teste = pd.DataFrame({
        "id_funcionario":      range(1000, 1050),
        "txtNomeCompleto":     [f"Colaborador_{i}" for i in range(50)],
        "salario_bruto":       [3500.50 if i % 3 != 0 else -np.inf for i in range(50)],
        "dt_admissao":         ["2024-01-15" if i % 2 == 0 else "15/03/2023" for i in range(50)],
        "cpf_colaborador":     ["123.456.789-00" for _ in range(48)] + [None, None],
        "email_corporativo":   [f"user{i}@empresa.com" for i in range(50)],
        "cod_departamento":    (["DEP01"] * 20 + ["DEP02"] * 15 + ["DEP03"] * 15),
        "nome_departamento":   (["Operações"] * 20 + ["TI"] * 15 + ["RH"] * 15),  # FD com cod_departamento
        "status_ativo":        (["Ativo"] * 47 + ["Inativo"] * 2 + [None]),
        "score_desempenho":    [float(i % 10) for i in range(50)],
        "campo_lixo_vazio":    [None] * 50,
        "tipo_misto":          (["123"] * 25 + ["texto_livre"] * 20 + ["2024-01-01"] * 5),
        "coluna_generica_01":  [f"VAL_{i}" for i in range(50)],  # Nome sem semântica, deve inferir por conteúdo
    })

    profiler = SASDataProfiler(limite_amostra=500_000)
    resultado = profiler.processar_dataframe(df_teste, nome_tabela="TB_FUNCIONARIOS_TESTE")
    profiler.exportar_resultado(resultado, formato="json", caminho_base="v6_teste_direto")

    log("info", "─" * 60)
    log("info", "Resumo de Execução:")
    resumo = resultado["metadados_execucao"]["resumo_qualidade"]
    for k, v in resumo.items():
        log("info", f"  {k}: {v}")

    log("info", "─" * 60)
    log("info", "Gap Analysis de KPIs:")
    for gap in resultado["gap_analysis_kpis"]:
        log("info", f"  [{gap['status']}] {gap['kpi_id']} — {gap['kpi_nome']} ({gap['cobertura_pct']})")

    log("info", "─" * 60)
    log("info", "Dependências Funcionais Detectadas:")
    for dep in resultado["dependencias_funcionais"]:
        log("info", f"  {dep['determinante']} → {dep['dependente']}")

    # ── Exemplo 2: Processar arquivo CSV/XLSX diretamente ──────────────────
    # Descomente e ajuste o caminho para testar ingestão de arquivo real:
    #
    # resultado_arquivo = profiler.processar_arquivo(
    #     caminho="seus_dados.csv",          # ou "planilha.xlsx"
    #     formato_saida="json",
    #     caminho_base_saida="profiler_output",
    # )
    #
    # Para XLSX com múltiplas abas:
    # resultados = profiler.processar_arquivo(
    #     caminho="planilha_multiplas_abas.xlsx",
    #     processar_todas_abas=True,
    #     formato_saida="parquet",
    #     caminho_base_saida="profiler_output",
    # )

    log("info", "═" * 60)
    log("info", "Profiling concluído com sucesso.")
    log("info", "═" * 60)
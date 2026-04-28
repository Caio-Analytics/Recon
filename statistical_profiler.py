"""
Analytic_Module.py — v2.0
──────────────────────────
Módulo de análise matemática/estatística de colunas.

MUDANÇAS vs v1:
  [BUG]  Colunas de data lidas como string (object) em CSVs nunca eram
         classificadas como "Data / Hora" — pandas não converte
         automaticamente. Adicionada detecção por regex de padrões
         de data nos valores da coluna.
  [BUG]  Retorno implícito None quando tipo != Texto e n_unicos > 25.
         Adicionado ramo explícito para tipos numéricos com alta cardinalidade.
  [BUG]  `valores_amostra` para o caso "Chave Primária" ficava vazio
         ([]) sendo que seria útil mostrar 3 exemplos para o analista
         confirmar visualmente.
  [MELHORIA] Detecção de padrões estruturados em texto: CPF, CNPJ,
         CEP, e-mail, telefone — muito comuns em bases de RH.
  [MELHORIA] Separação de "Dimensão Média" para colunas com 26-100
         únicos — antes caíam em "Dimensão Longa" sem distinção.
  [MELHORIA] Retorno inclui "flag_data_como_texto" para o Core gerar
         alerta específico de tipagem errada.
  [MELHORIA] Retorno inclui "flag_padrao_estruturado" (CPF, CEP etc.)
         para o Core gerar insight de mascaramento/privacidade.
"""

import re
import random
import pandas as pd


# ─────────────────────────────────────────────────────────────
# PADRÕES REGEX
# ─────────────────────────────────────────────────────────────

_PADROES_DATA = [
    # ── Datas puras ──────────────────────────────────────────
    r"^\d{4}-\d{2}-\d{2}$",                    # ISO:      2024-03-15
    r"^\d{2}/\d{2}/\d{4}$",                    # BR:       15/03/2024
    r"^\d{2}-\d{2}-\d{4}$",                    # BR traço: 15-03-2024
    r"^\d{4}/\d{2}/\d{2}$",                    # ISO //:   2024/03/15
    r"^\d{2}\.\d{2}\.\d{4}$",                  # Europeu:  15.03.2024

    # ── Datetime com hora (HH:MM ou HH:MM:SS) ────────────────
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",     # ISO:      2024-03-15T08:00
    r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}",      # BR hora:  15/03/2024 08:00
    r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}",      # BR hora:  15-03-2024 08:00

    # ── Com AM/PM (sistemas legados SAP/Oracle) ───────────────
    # Ex: 08/03/2004 00:00 AM  |  08/03/2004 12:00:00 PM
    r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)$",
    r"^\d{2}-\d{2}-\d{4}\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)$",

    # ── Com timezone no final (sistemas ERP/MDM) ──────────────
    # Ex: 08/03/2004 00:00:00 America/Sao_Paulo
    #     08/03/2004 00:00:00 Brasilia Standard Time
    #     08/03/2004 00:00:00 BRT
    r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}(:\d{2})?\s+\S+.*$",
    r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}(:\d{2})?\s+\S+.*$",
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?\s+\S+.*$",
]

_PADROES_ESTRUTURADOS = {
    "CPF": r"^\d{3}[.\-]?\d{3}[.\-]?\d{3}[.\-]?\d{2}$",
    "CNPJ": r"^\d{2}[.\-]?\d{3}[.\-]?\d{3}[\/\-]?\d{4}[.\-]?\d{2}$",
    "CEP": r"^\d{5}[-\s]?\d{3}$",
    "E-mail": r"^[\w.+\-]+@[\w\-]+\.[\w\-]{2,}$",
    "Telefone": r"^[\(\+]?\d[\d\s\-\(\)]{6,14}\d$",
}


def _detectar_data_em_texto(amostra: list) -> bool:
    """
    Verifica se a maioria dos valores não-nulos de uma coluna texto
    corresponde a algum padrão de data conhecido.
    """
    if not amostra:
        return False
    matches = sum(
        1 for v in amostra
        if any(re.match(p, str(v).strip()) for p in _PADROES_DATA)
    )
    return (matches / len(amostra)) >= 0.80  # 80% de match → é data


def _detectar_padrao_estruturado(amostra: list, nome_coluna: str = "") -> str | None:
    """
    Verifica se a coluna contém dados estruturados sensíveis (CPF, CNPJ, CEP etc.).
    Retorna o nome do padrão detectado ou None.

    TRAVA DE CONTEXTO (evita falsos positivos em sistemas corporativos):
    Colunas cujos nomes indiquem claramente uma chave estrutural de sistema
    (id, code, number, identifier, cost_center, hier...) são imunes aos
    detectores de CEP e Telefone — que são numéricos e facilmente confundidos
    com códigos SAP/MDM de 7-9 dígitos.
    CPF, CNPJ e E-mail continuam sendo verificados mesmo em chaves, pois
    é comum sistemas legados usarem CPF como identificador de colaborador.
    """
    if not amostra:
        return None

    # Termos que indicam chave estrutural de sistema
    _TERMOS_CHAVE_SISTEMA = {
        "id", "code", "number", "identifier", "cost_center",
        "hier", "position", "network", "user", "key", "index",
        "seq", "ref", "num", "cod", "codigo", "chave",
    }

    nome_norm = nome_coluna.lower()
    tokens_nome = set(re.split(r"[_\s\-\.]+", nome_norm))

    eh_chave_sistema = bool(tokens_nome & _TERMOS_CHAVE_SISTEMA)

    # Padrões que NÃO aplicamos se a coluna parece ser chave de sistema
    _IMUNES_EM_CHAVES = {"CEP", "Telefone"}

    for nome_padrao, regex in _PADROES_ESTRUTURADOS.items():
        if eh_chave_sistema and nome_padrao in _IMUNES_EM_CHAVES:
            continue  # Pula CEP e Telefone para colunas de chave corporativa

        matches = sum(1 for v in amostra if re.match(regex, str(v).strip()))
        if (matches / len(amostra)) >= 0.75:
            return nome_padrao

    return None


# ─────────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────

def analisar_matematica(serie: pd.Series, total_linhas: int) -> dict:
    """
    Analisa uma Series pandas e retorna um dicionário com:
        tipo_dados            : str
        n_unicos              : int
        pct_nulos             : float
        caracteristica        : str
        valores_amostra       : list
        flag_data_como_texto  : bool  — True se coluna texto parece data
        flag_padrao_estruturado: str | None — "CPF", "CEP", etc.
    """
    nulos = serie.isna().sum()
    pct_nulos = round((nulos / total_linhas) * 100, 1) if total_linhas > 0 else 0.0

    serie_limpa = serie.dropna()
    n_total_limpo = len(serie_limpa)
    n_unicos = serie_limpa.nunique()
    tipo_bruto = str(serie_limpa.dtype)

    # Flags extras — inicializados como bool explícito (nunca None/null no JSON)
    flag_data_como_texto = False
    flag_padrao_estruturado = False

    # ── 1. TRADUÇÃO DE TIPO ───────────────────────────────────
    if "float" in tipo_bruto:
        if n_total_limpo > 0 and all(x.is_integer() for x in serie_limpa):
            tipo_amigavel = "Número Inteiro (armazenado como Decimal por nulos)"
        else:
            tipo_amigavel = "Número Decimal"

    elif "int" in tipo_bruto:
        tipo_amigavel = "Número Inteiro"

    elif "datetime" in tipo_bruto:
        tipo_amigavel = "Data / Hora"

    elif "bool" in tipo_bruto:
        tipo_amigavel = "Booleano (Verdadeiro/Falso)"

    elif "object" in tipo_bruto or "string" in tipo_bruto:
        # Amostragem para detecção de padrões em texto
        amostra_valores = serie_limpa.astype(str).tolist()
        n_amostrar = min(50, len(amostra_valores))
        amostra = random.sample(amostra_valores, n_amostrar) if n_amostrar > 5 else amostra_valores

        if _detectar_data_em_texto(amostra):
            tipo_amigavel = "Texto (⚠️ Parece ser Data — verificar tipagem)"
            flag_data_como_texto = True
        else:
            tipo_amigavel = "Texto"
            padrao = _detectar_padrao_estruturado(amostra, str(serie.name))
            flag_padrao_estruturado = padrao if padrao is not None else False
    else:
        tipo_amigavel = tipo_bruto

    # ── 2. CARACTERÍSTICA E VALORES DE AMOSTRA ───────────────
    caracteristica = "N/A"
    valores_amostra = []

    if pct_nulos == 100.0:
        caracteristica = "⚠️ Coluna 100% Vazia — remover no Power Query"

    elif n_unicos == 0:
        caracteristica = "⚠️ Sem valores após remoção de nulos"

    elif n_unicos == total_linhas and total_linhas > 0:
        caracteristica = "🔑 Chave Primária Potencial (100% Única)"
        # Mostra 3 exemplos para confirmação visual
        valores_amostra = serie_limpa.astype(str).sample(
            min(3, n_total_limpo), random_state=42
        ).tolist()

    elif n_unicos == 1 and pct_nulos == 0:
        caracteristica = "🔒 Valor Constante (todos os registros iguais)"
        valores_amostra = serie_limpa.astype(str).unique().tolist()

    elif "Data" in tipo_amigavel:
        # Intercepta datas ANTES das réguas de cardinalidade.
        # Uma coluna de data com 48 únicos nunca é "Dimensão Média" —
        # é sempre uma Série Temporal, independente do volume de valores.
        # Cobre datetime nativo ("Data / Hora") e texto parseado
        # ("Texto (⚠️ Parece ser Data...)") pelo mesmo "Data" in check.
        caracteristica = "📅 Série Temporal (campo de data/hora)"

    elif 1 < n_unicos <= 25:
        caracteristica = "🏷️ Categórica / Dimensão Curta (Potencial Filtro/Flag)"
        valores_amostra = serie_limpa.astype(str).unique().tolist()

    elif 25 < n_unicos <= 100:
        caracteristica = "📂 Dimensão Média (Hierarquia ou Segmento)"
        valores_amostra = (
            serie_limpa.astype(str).drop_duplicates()
            .sample(min(10, n_unicos), random_state=42)
            .tolist()
        )

    else:
        # n_unicos > 100 — tipos não-data chegam aqui
        if "Texto" in tipo_amigavel:
            caracteristica = "📋 Dimensão Longa (Atributos Variados / Texto Livre)"
        elif "Número" in tipo_amigavel:
            caracteristica = "📊 Métrica Contínua (alta variabilidade numérica)"
        else:
            caracteristica = "📋 Alta Cardinalidade"

    # ── 3. NOTA DE AMOSTRAGEM ─────────────────────────────────
    # Indica ao Core se os valores_amostra são parciais ou completos
    if not valores_amostra:
        nota_amostra = "Não Elegível"
    elif n_unicos > len(valores_amostra):
        nota_amostra = f"Amostragem: {len(valores_amostra)} de {n_unicos} valores únicos"
    else:
        nota_amostra = None  # Todos os únicos estão presentes — sem nota necessária

    return {
        "tipo_dados": tipo_amigavel,
        "n_unicos": n_unicos,
        "pct_nulos": pct_nulos,
        "caracteristica": caracteristica,
        "valores_amostra": valores_amostra,
        "nota_amostra": nota_amostra,
        "flag_data_como_texto": flag_data_como_texto,
        "flag_padrao_estruturado": flag_padrao_estruturado,
    }
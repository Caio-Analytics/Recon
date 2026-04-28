
import re
import random
import pandas as pd






_PADROES_DATA = [
    
    r"^\d{4}-\d{2}-\d{2}$",                    
    r"^\d{2}/\d{2}/\d{4}$",                    
    r"^\d{2}-\d{2}-\d{4}$",                    
    r"^\d{4}/\d{2}/\d{2}$",                    
    r"^\d{2}\.\d{2}\.\d{4}$",                  

    
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",     
    r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}",      
    r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}",      

    
    
    r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)$",
    r"^\d{2}-\d{2}-\d{4}\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)$",

    
    
    
    
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
    if not amostra:
        return False
    matches = sum(
        1 for v in amostra
        if any(re.match(p, str(v).strip()) for p in _PADROES_DATA)
    )
    return (matches / len(amostra)) >= 0.80  


def _detectar_padrao_estruturado(amostra: list, nome_coluna: str = "") -> str | None:
    if not amostra:
        return None

    
    _TERMOS_CHAVE_SISTEMA = {
        "id", "code", "number", "identifier", "cost_center",
        "hier", "position", "network", "user", "key", "index",
        "seq", "ref", "num", "cod", "codigo", "chave",
    }

    nome_norm = nome_coluna.lower()
    tokens_nome = set(re.split(r"[_\s\-\.]+", nome_norm))

    eh_chave_sistema = bool(tokens_nome & _TERMOS_CHAVE_SISTEMA)

    
    _IMUNES_EM_CHAVES = {"CEP", "Telefone"}

    for nome_padrao, regex in _PADROES_ESTRUTURADOS.items():
        if eh_chave_sistema and nome_padrao in _IMUNES_EM_CHAVES:
            continue  

        matches = sum(1 for v in amostra if re.match(regex, str(v).strip()))
        if (matches / len(amostra)) >= 0.75:
            return nome_padrao

    return None






def analisar_matematica(serie: pd.Series, total_linhas: int) -> dict:
    nulos = serie.isna().sum()
    pct_nulos = round((nulos / total_linhas) * 100, 1) if total_linhas > 0 else 0.0

    serie_limpa = serie.dropna()
    n_total_limpo = len(serie_limpa)
    n_unicos = serie_limpa.nunique()
    tipo_bruto = str(serie_limpa.dtype)

    
    flag_data_como_texto = False
    flag_padrao_estruturado = False

    
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

    
    caracteristica = "N/A"
    valores_amostra = []

    if pct_nulos == 100.0:
        caracteristica = "⚠️ Coluna 100% Vazia — remover no Power Query"

    elif n_unicos == 0:
        caracteristica = "⚠️ Sem valores após remoção de nulos"

    elif n_unicos == total_linhas and total_linhas > 0:
        caracteristica = "🔑 Chave Primária Potencial (100% Única)"
        
        valores_amostra = serie_limpa.astype(str).sample(
            min(3, n_total_limpo), random_state=42
        ).tolist()

    elif n_unicos == 1 and pct_nulos == 0:
        caracteristica = "🔒 Valor Constante (todos os registros iguais)"
        valores_amostra = serie_limpa.astype(str).unique().tolist()

    elif "Data" in tipo_amigavel:
        
        
        
        
        
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
        
        if "Texto" in tipo_amigavel:
            caracteristica = "📋 Dimensão Longa (Atributos Variados / Texto Livre)"
        elif "Número" in tipo_amigavel:
            caracteristica = "📊 Métrica Contínua (alta variabilidade numérica)"
        else:
            caracteristica = "📋 Alta Cardinalidade"

    
    
    if not valores_amostra:
        nota_amostra = "Não Elegível"
    elif n_unicos > len(valores_amostra):
        nota_amostra = f"Amostragem: {len(valores_amostra)} de {n_unicos} valores únicos"
    else:
        nota_amostra = None  

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
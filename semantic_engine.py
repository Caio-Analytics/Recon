"""
Data_Module.py — v2.0
─────────────────────
Módulo de inferência semântica de nomes de colunas.

MUDANÇAS vs v1:
  [BUG]  Nomes com acentos falhavam silenciosamente no Jaro-Winkler
         porque não havia normalização unicode antes da comparação.
  [BUG]  camelCase (ex: "hireDate") nunca era separado em tokens,
         então "hire" e "Date" nunca matchavam individualmente.
  [MELHORIA] Categorias expandidas para cobrir vocabulário de RH
         em português e inglês de forma mais simétrica.
  [MELHORIA] Threshold fuzzy agora é 0.85 (era 0.88). O valor 0.88
         é alto demais para nomes curtos como "uf", "dt", "vlr" —
         esses nunca atingiam o score e caíam em "Genérico".
  [MELHORIA] Novo campo "confianca_score" numérico no retorno para
         que o Core possa usar como critério de ordenação de insights.
  [MELHORIA] Fallback explícito retorna dict completo (antes podia
         retornar sem o campo "confianca_score" e quebrar o Core).
"""

import re
import unicodedata
import jellyfish


# ─────────────────────────────────────────────────────────────
# 1. PADRÕES FORTES — match exato por substring
#    Ordem importa: primeiro match ganha.
# ─────────────────────────────────────────────────────────────
CATEGORIAS_FORTES = {
    "Chave Identificadora (ID)": [
        "_id", "cod_", "code_", "codigo", "code", "key", "number",
        "matricula", "mat_", "cpf", "cnpj", "registro", "chave",
        "identifier", "iden", "nr_", "num_",
    ],
    "Data / Calendário": [
        "_date", "_dt", "dt_", "data_", "_data", "time", "timestamp",
        "periodo", "competencia", "admissao", "demissao", "nascimento",
        "vencimento", "inicio", "fim", "prazo", "realizacao",
    ],
    "Status / Indicador / Flag": [
        "status", "flg_", "_flg", "is_", "has_", "state", "situacao",
        "enforced", "ativo", "inativo", "flag_", "_flag",
    ],
    "Valor Financeiro": [
        "salario", "salary", "wage", "remuneracao", "vlr_", "_valor",
        "custo", "cost", "preco", "price", "receita", "revenue",
        "despesa", "expense", "budget", "orcamento", "bonus",
        "comissao", "honorario",
    ],
    "Quantidade / Métrica": [
        "qtd_", "_qtd", "quantidade", "count", "total_", "_total",
        "volume", "horas", "carga", "duracao", "frequencia",
        "score", "nota_", "_nota", "percentual", "pct_", "_pct",
    ],
    "Texto Descritivo Livre": [
        "_desc", "descricao", "description", "obs_", "_obs",
        "observacao", "comentario", "justificativa", "detalhe",
        "motivo", "complemento", "historico", "task", "function",
    ],
    "Nome / Identificação Pessoal": [
        "nome", "name", "colaborador", "funcionario", "empregado",
        "pessoa", "participante", "aluno", "candidato",
    ],
}

# ─────────────────────────────────────────────────────────────
# 2. PADRÕES FUZZY — Jaro-Winkler por token
# ─────────────────────────────────────────────────────────────
CATEGORIAS_FUZZY = {
    "Localização Geográfica": [
        "country", "province", "city", "facility", "pais", "cidade",
        "estado", "regiao", "municipio", "cep", "uf", "endereco", "local",
    ],
    "Estrutura Organizacional": [
        "department", "company", "business", "cost_center", "hier",
        "departamento", "diretoria", "gerencia", "setor", "area",
        "divisao", "celula", "squad", "lotacao", "unidade",
    ],
    "Perfil do Colaborador": [
        "gender", "nationality", "birth", "hire", "termination",
        "expatriation", "career", "workforce", "staff", "genero",
        "nacionalidade", "nascimento", "admissao", "demissao",
    ],
    "Cargo / Função": [
        "cargo", "funcao", "nivel", "grade", "posicao", "categoria",
        "classe", "faixa", "perfil", "role", "position", "job",
        "title", "occupation",
    ],
    "Curso / Treinamento": [
        "curso", "treinamento", "capacitacao", "formacao", "modulo",
        "trilha", "programa", "workshop", "disciplina", "tema",
        "course", "training", "learning",
    ],
    "Resultado de Avaliação": [
        "resultado", "result", "aprovacao", "reprovacao", "conceito",
        "avaliacao", "desempenho", "conclusao", "situacao_curso",
        "outcome", "performance",
    ],
    "Contato / Rede": [
        "email", "address", "network", "access", "telefone",
        "celular", "ramal", "whatsapp", "contato",
    ],
}

THRESHOLD_FUZZY = 0.85  # era 0.88 — muito restritivo para nomes curtos


# ─────────────────────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas. Correção de bug v1."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()


def _tokenizar(nome_col: str) -> list:
    """
    Quebra o nome em tokens. Cobre snake_case, camelCase e espaços.
    Ex: 'hireDate'  → ['hire', 'date']
        'Dt_Admissao' → ['dt', 'admissao']
    """
    # Separar camelCase antes de normalizar
    nome = re.sub(r"([a-z])([A-Z])", r"\1_\2", nome_col)
    nome = _normalizar(nome)
    partes = re.split(r"[_\s\-\.]+", nome)
    return [p for p in partes if p]


# ─────────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────

def analisar_contexto(nome_col: str) -> dict:
    """
    Retorna:
        semantica      : str  — categoria inferida
        confianca      : str  — label legível
        confianca_score: float — 1.0 (exato), 0.0-1.0 (fuzzy), 0.0 (N/A)
    """
    nome_limpo = _normalizar(str(nome_col))

    # ── PASSO 1: Padrões Fortes ───────────────────────────────
    for categoria, palavras in CATEGORIAS_FORTES.items():
        if any(p in nome_limpo for p in palavras):
            return {
                "semantica": categoria,
                "confianca": "Alta (Padrão Exato)",
                "confianca_score": 1.0,
            }

    # ── PASSO 2: Fuzzy por token ──────────────────────────────
    tokens = _tokenizar(nome_col)
    melhor_score = 0.0
    categoria_vencedora = "Genérico / Não mapeado"

    for categoria, palavras_chave in CATEGORIAS_FUZZY.items():
        for palavra in palavras_chave:
            palavra_norm = _normalizar(palavra)

            # Score contra o nome completo
            score_full = jellyfish.jaro_winkler_similarity(nome_limpo, palavra_norm)

            # Score contra cada token individualmente
            scores_tokens = [
                jellyfish.jaro_winkler_similarity(_normalizar(t), palavra_norm)
                for t in tokens
            ]
            score_token = max(scores_tokens) if scores_tokens else 0.0

            score_final = max(score_full, score_token)

            if score_final > melhor_score and score_final >= THRESHOLD_FUZZY:
                melhor_score = score_final
                categoria_vencedora = categoria

    if categoria_vencedora != "Genérico / Não mapeado":
        return {
            "semantica": categoria_vencedora,
            "confianca": f"Média ({melhor_score * 100:.1f}%)",
            "confianca_score": melhor_score,
        }

    # ── FALLBACK ──────────────────────────────────────────────
    return {
        "semantica": "Genérico / Não mapeado",
        "confianca": "N/A",
        "confianca_score": 0.0,
    }
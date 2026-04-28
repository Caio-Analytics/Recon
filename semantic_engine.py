
import re
import unicodedata
import jellyfish






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

THRESHOLD_FUZZY = 0.85  






def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()


def _tokenizar(nome_col: str) -> list:
    
    nome = re.sub(r"([a-z])([A-Z])", r"\1_\2", nome_col)
    nome = _normalizar(nome)
    partes = re.split(r"[_\s\-\.]+", nome)
    return [p for p in partes if p]






def analisar_contexto(nome_col: str) -> dict:
    nome_limpo = _normalizar(str(nome_col))

    
    for categoria, palavras in CATEGORIAS_FORTES.items():
        if any(p in nome_limpo for p in palavras):
            return {
                "semantica": categoria,
                "confianca": "Alta (Padrão Exato)",
                "confianca_score": 1.0,
            }

    
    tokens = _tokenizar(nome_col)
    melhor_score = 0.0
    categoria_vencedora = "Genérico / Não mapeado"

    for categoria, palavras_chave in CATEGORIAS_FUZZY.items():
        for palavra in palavras_chave:
            palavra_norm = _normalizar(palavra)

            
            score_full = jellyfish.jaro_winkler_similarity(nome_limpo, palavra_norm)

            
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

    
    return {
        "semantica": "Genérico / Não mapeado",
        "confianca": "N/A",
        "confianca_score": 0.0,
    }
"""Fonte única de taxonomias semânticas e thresholds do profiler."""
from typing import Dict, List, Set

# ── Nomes de categorias/tipos referenciados fora deste módulo ──────────────
# Centralizados aqui para evitar cópias literais divergentes em quality.py,
# pipeline.py e semantics.py — uma renomeação de categoria só precisa mudar
# neste arquivo.
SEMANTICA_GENERICA: str = "Genérico / Não mapeado"
SEMANTICA_DATA_CALENDARIO: str = "Data / Calendário"
TIPO_DATA_HORA: str = "Data / Hora"

# ── Thresholds gerais ────────────────────────────────────────────────────
THRESHOLD_FUZZY_PADRAO: float = 0.85
THRESHOLD_FUZZY_CURTO: float = 0.95
THRESHOLD_QUASE_CHAVE: float = 0.95
THRESHOLD_QUASI_CONSTANTE: float = 0.95
THRESHOLD_MISTO_TIPOS: float = 0.05
THRESHOLD_OUTLIER_IQR: float = 1.5
THRESHOLD_PADRAO_ESTRUTURADO: float = 0.75
THRESHOLD_DATA_TEXTO: float = 0.80
AMOSTRA_ANALISE: int = 200

# ── Guarda contra dependência funcional trivial ─────────────────────────────
# Colunas com Ratio_Unicidade >= este valor não podem ser "determinante" de
# uma FD (uma chave quase-única "determina" trivialmente qualquer coluna).
THRESHOLD_DETERMINANTE_MAX_UNICIDADE: float = 0.98

# ── Testes de hipótese ───────────────────────────────────────────────────
ALPHA_SIGNIFICANCIA: float = 0.05
SHAPIRO_MIN_N: int = 20
SHAPIRO_MAX_N: int = 5000
CHI2_MIN_FREQ_ESPERADA: int = 5
CHI2_MAX_CATEGORIAS: int = 50
DIST_DETECTION_MIN_N: int = 20
ADF_MIN_N: int = 30
ANALISE_TEMPORAL_MAX_PONTOS: int = 50_000

# ── Categorias fortes (match exato por token) ───────────────────────────────
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

# ── Categorias fuzzy (Jaro-Winkler) ─────────────────────────────────────────
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

# ── Padrões de data e estruturados ──────────────────────────────────────────
PADROES_DATA: List[str] = [
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

PADROES_ESTRUTURADOS: Dict[str, str] = {
    "CPF":      r"^\d{3}[.\-]?\d{3}[.\-]?\d{3}[.\-]?\d{2}$",
    "CNPJ":     r"^\d{2}[.\-]?\d{3}[.\-]?\d{3}[\/\-]?\d{4}[.\-]?\d{2}$",
    "CEP":      r"^\d{5}[-\s]?\d{3}$",
    "E-mail":   r"^[\w.+\-]+@[\w\-]+(\.[\w\-]+)*\.[\w\-]{2,}$",
    "Telefone": r"^[\(\+]?\d[\d\s\-\(\)]{6,14}\d$",
    "UUID":     r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
}

TOKENS_CHAVE_SISTEMA: Set[str] = {"id", "code", "number", "key", "cod", "pk", "fk", "identifier"}

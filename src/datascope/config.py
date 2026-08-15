"""Fonte única de taxonomias semânticas e thresholds do profiler.

Este módulo é só dado: taxonomias, regexes, limiares e as regras de KPI
padrão. Toda a lógica que consome esses valores vive nos módulos de
análise (`patterns`, `semantics`, `statistics`, `hypothesis`,
`relationships`, `quality`).
"""
from typing import Any

# ── Versão do schema do payload ───────────────────────────────────────────
# Incrementada quando a estrutura do JSON exportado muda de forma que quebre
# um consumidor. Vai no payload para quem lê via código conseguir se adaptar.
SCHEMA_VERSION: str = "3.0"

# ── Nomes de categorias/tipos referenciados fora deste módulo ──────────────
# Centralizados aqui para evitar cópias literais divergentes em quality.py,
# pipeline.py e semantics.py — uma renomeação de categoria só precisa mudar
# neste arquivo.
SEMANTICA_GENERICA: str = "Genérico / Não mapeado"
SEMANTICA_DATA_CALENDARIO: str = "Data / Calendário"
SEMANTICA_CHAVE_ID: str = "Chave Identificadora (ID)"
TIPO_DATA_HORA: str = "Data / Hora"
TIPO_VAZIO: str = "Vazio / Sem Tipo Definido"

# ── Thresholds gerais ────────────────────────────────────────────────────
THRESHOLD_FUZZY_PADRAO: float = 0.85
THRESHOLD_FUZZY_CURTO: float = 0.95
THRESHOLD_QUASE_CHAVE: float = 0.95
THRESHOLD_QUASI_CONSTANTE: float = 0.95
THRESHOLD_MISTO_TIPOS: float = 0.05
THRESHOLD_OUTLIER_IQR: float = 1.5
THRESHOLD_PADRAO_ESTRUTURADO: float = 0.75
THRESHOLD_DATA_TEXTO: float = 0.80

# Amostra usada para detecção de padrão/mistura de tipos por regex. É barata
# (regex sobre strings) e define o piso de detecção: com 5.000 valores dá
# para enxergar contaminação na casa de 0,02%, contra 0,5% com 200.
AMOSTRA_ANALISE: int = 5_000

# Até esta cardinalidade a amostra representativa traz *todos* os valores
# distintos. Os gazetteers medem cobertura sobre o conjunto completo — uma
# coluna de UF tem 27 valores e precisa caber aqui inteira.
MAX_VALORES_AMOSTRA_COMPLETA: int = 50

# ── Guarda contra dependência funcional trivial ─────────────────────────────
# Colunas com Ratio_Unicidade >= este valor não podem ser "determinante" de
# uma FD (uma chave quase-única "determina" trivialmente qualquer coluna).
THRESHOLD_DETERMINANTE_MAX_UNICIDADE: float = 0.98
FD_MAX_CARDINALIDADE: int = 500

# ── Testes de hipótese ───────────────────────────────────────────────────
ALPHA_SIGNIFICANCIA: float = 0.05
SHAPIRO_MIN_N: int = 20
SHAPIRO_MAX_N: int = 5000
CHI2_MIN_FREQ_ESPERADA: int = 5
CHI2_MAX_CATEGORIAS: int = 50
DIST_DETECTION_MIN_N: int = 20
ADF_MIN_N: int = 30
ANALISE_TEMPORAL_MAX_PONTOS: int = 50_000
# Assimetria acima deste valor (em módulo) desqualifica o IQR clássico e
# aciona o boxplot ajustado por medcouple.
THRESHOLD_ASSIMETRIA_ROBUSTA: float = 1.0

# ── Sentinelas (nulos disfarçados) ──────────────────────────────────────────
# Proporção mínima da coluna que um candidato precisa ocupar para ser
# reportado como sentinela — evita acusar um valor legítimo raro.
THRESHOLD_SENTINELA_MIN_PCT: float = 0.005

# Comparação feita sobre o valor normalizado (unidecode + lower + strip).
SENTINELAS_TEXTO: frozenset[str] = frozenset({
    "", "-", "--", "---", ".", "..", "...", "?", "??", "???",
    "n/a", "na", "n.a.", "n/d", "nd", "null", "none", "nil", "nan",
    "#n/d", "#n/a", "#valor!", "#value!", "#ref!", "#nome?", "#name?", "#div/0!",
    "sem informacao", "sem informacoes", "nao informado", "nao informada",
    "nao consta", "nao se aplica", "nao disponivel", "nao identificado",
    "desconhecido", "desconhecida", "indefinido", "indefinida",
    "vazio", "branco", "em branco", "s/i", "s/d", "s/n", "ignorado",
})

# Só viram sentinela quando também são extremo (min/max) da distribuição —
# senão um -1 legítimo de uma coluna de saldo seria acusado.
SENTINELAS_NUMERICAS: frozenset[float] = frozenset({
    -1.0, -99.0, -999.0, -9999.0, -99999.0, -1.0e9,
    9999.0, 99999.0, 999999.0, 9999999.0, 99999999.0, 999999999.0,
})

SENTINELAS_DATA: frozenset[str] = frozenset({
    "1753-01-01",  # mínimo do SQL Server datetime
    "1899-12-30",  # epoch do Excel
    "1900-01-01", "1901-01-01", "1970-01-01",
    "2099-12-31", "9999-12-31",
})

# ── Categorias fortes (match exato por token) ───────────────────────────────
CATEGORIAS_FORTES: dict[str, list[str]] = {
    SEMANTICA_CHAVE_ID: [
        "id", "cod", "codigo", "code", "key", "number", "matricula", "mat",
        "cpf", "cnpj", "registro", "chave", "identifier", "iden", "nr", "num", "pk", "fk",
    ],
    SEMANTICA_DATA_CALENDARIO: [
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
CATEGORIAS_FUZZY: dict[str, list[str]] = {
    "Localização Geográfica": [
        "country", "province", "city", "facility", "pais", "cidade",
        "estado", "regiao", "municipio", "cep", "uf", "endereco", "local",
        "latitude", "longitude", "bairro", "logradouro",
    ],
    "Estrutura Organizacional": [
        "department", "company", "business", "hierarquia", "departamento",
        "diretoria", "gerencia", "setor", "area", "divisao", "celula",
        "squad", "lotacao", "unidade", "filial", "subsidiaria", "agencia",
        "coordenacao", "superintendencia", "nucleo", "equipe", "time",
    ],
    "Perfil do Colaborador": [
        "gender", "nationality", "career", "workforce", "staff",
        "genero", "nacionalidade", "idade", "raca", "escolaridade",
        "deficiencia", "etnia",
    ],
    "Cargo / Função": [
        "cargo", "funcao", "nivel", "grade", "posicao", "categoria",
        "classe", "faixa", "perfil", "role", "position", "job",
        "title", "occupation",
    ],
    "Curso / Treinamento": [
        "curso", "treinamento", "capacitacao", "formacao", "modulo",
        "trilha", "programa", "workshop", "disciplina", "tema",
        "course", "training", "learning", "certificacao",
    ],
}

# ── Qualificadores estruturais de nome de coluna ────────────────────────────
# Tokens que descrevem o *papel* da coluna, não a *entidade* de que ela trata.
# Em `nome_departamento` o `nome` é qualificador e `departamento` é a entidade:
# a coluna é sobre estrutura organizacional, não sobre uma pessoa. Sem essa
# distinção o desempate cai no comprimento da palavra e erra sistematicamente.
TOKENS_QUALIFICADORES: frozenset[str] = frozenset({
    "id", "cod", "codigo", "code", "key", "chave", "pk", "fk", "nr", "num",
    "number", "matricula", "mat", "iden", "identifier", "registro",
    "nome", "name", "desc", "descricao", "description", "sigla", "abrev",
    "tipo", "type", "categoria", "class", "flag", "flg", "status",
    "qtd", "quantidade", "total", "vlr", "valor", "pct", "percentual",
    "dt", "date", "data", "hora", "time", "timestamp",
})

# Peso do token qualificador no ranking semântico. Ele ainda conta (um
# `id_x` continua tendo cara de identificador) mas perde para a entidade
# quando as duas categorias competem.
PESO_TOKEN_QUALIFICADOR: float = 0.45
PESO_TOKEN_ENTIDADE: float = 1.0

# ── Padrões de data e estruturados ──────────────────────────────────────────
PADROES_DATA: list[str] = [
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

PADROES_ESTRUTURADOS: dict[str, str] = {
    "CPF":      r"^\d{3}[.\-]?\d{3}[.\-]?\d{3}[.\-]?\d{2}$",
    "CNPJ":     r"^\d{2}[.\-]?\d{3}[.\-]?\d{3}[\/\-]?\d{4}[.\-]?\d{2}$",
    "CEP":      r"^\d{5}[-\s]?\d{3}$",
    "E-mail":   r"^[\w.+\-]+@[\w\-]+(\.[\w\-]+)*\.[\w\-]{2,}$",
    "Telefone": r"^[\(\+]?\d[\d\s\-\(\)]{6,14}\d$",
    "UUID":     r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
}

# Padrões cujo valor é verificável por dígito verificador. Só entram no
# relatório como dado sensível se a validação passar na maioria da amostra —
# comprimento de dígito sozinho confunde timestamp epoch com CNPJ.
PADROES_COM_VALIDACAO: frozenset[str] = frozenset({"CPF", "CNPJ"})

# Mojibake: texto UTF-8 lido como latin-1 (`ção` → `Ã§Ã£o`) ou byte perdido.
PADRAO_MOJIBAKE: str = r"Ã[-¿–—‚-…]|Â[ -¿]|â€|ï¿½|�"

TOKENS_CHAVE_SISTEMA: set[str] = {"id", "code", "number", "key", "cod", "pk", "fk", "identifier"}

# Tipos inferidos que podem legitimamente ser chave. Um `Número Decimal` é
# quase-único por natureza (salário, medida) e não deve disparar o alerta de
# quase-chave / dado sujo.
TIPOS_ELEGIVEIS_CHAVE: frozenset[str] = frozenset({"Número Inteiro", "Texto", "Texto (⚠️ Parece Data)"})

# ── Correlação entre colunas ────────────────────────────────────────────────
CORRELACAO_MIN_ABS: float = 0.7
CORRELACAO_MAX_CARDINALIDADE_CAT: int = 50
CORRELACAO_MIN_N: int = 30

# ── Score de qualidade ──────────────────────────────────────────────────────
# Peso de cada penalidade no score 0-100 da tabela. Somados dão o desconto
# máximo possível; o score nunca fica negativo.
# `colunas_com_defeito` mede a *abrangência* da contaminação, que as demais
# dimensões não capturam: cada uma delas divide pelo total de colunas, então
# um defeito em 1 de 8 colunas nunca passa de 12,5% daquela dimensão — e uma
# tabela com seis colunas problemáticas, cada uma com um problema diferente,
# somava pouco em tudo e saía com nota alta.
PESOS_SCORE_QUALIDADE: dict[str, float] = {
    "colunas_com_defeito": 25.0,
    "nulos": 15.0,
    "sentinelas": 10.0,
    "duplicatas": 10.0,
    "colunas_vazias": 6.0,
    "mistura_tipos": 6.0,
    "inconsistencia_texto": 6.0,
    "documento_invalido": 6.0,
    "mojibake": 5.0,
    "lgpd_exposto": 5.0,
    "data_como_texto": 3.0,
    "colunas_redundantes": 3.0,
}

# ── Regras de gap analysis de KPI ───────────────────────────────────────────
# Conjunto padrão (domínio de RH). Substituível por arquivo YAML via
# `--kpis meu_dominio.yaml`, com a mesma estrutura: lista de {id, nome,
# semanticas}. Sem isso, o gap analysis vira ruído em qualquer tabela que
# não seja de pessoal.
REGRAS_KPI_PADRAO: list[dict[str, Any]] = [
    {"id": "KPI_HR_001", "nome": "Volume de Esforço por Departamento",
     "semanticas": ["Estrutura Organizacional", "Quantidade / Métrica"]},
    {"id": "KPI_HR_002", "nome": "Distribuição de Liderança por Perfil",
     "semanticas": ["Perfil do Colaborador", "Cargo / Função"]},
    {"id": "KPI_HR_003", "nome": "Evolução de Custo de Pessoal",
     "semanticas": ["Valor Financeiro", SEMANTICA_DATA_CALENDARIO]},
    {"id": "KPI_HR_004", "nome": "Análise de Turnover",
     "semanticas": ["Perfil do Colaborador", SEMANTICA_DATA_CALENDARIO]},
    {"id": "KPI_TREIN_001", "nome": "Efetividade de Treinamentos",
     "semanticas": ["Curso / Treinamento", "Resultado de Avaliação"]},
    {"id": "KPI_GEO_001", "nome": "Distribuição Geográfica de Headcount",
     "semanticas": ["Localização Geográfica", "Estrutura Organizacional"]},
]

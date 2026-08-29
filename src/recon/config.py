from typing import Any




SCHEMA_VERSION: str = "3.0"





SEMANTICA_GENERICA: str = "Genérico / Não mapeado"
SEMANTICA_DATA_CALENDARIO: str = "Data / Calendário"
SEMANTICA_CHAVE_ID: str = "Chave Identificadora (ID)"
SEMANTICA_TEXTO_LIVRE: str = "Texto Descritivo Livre"
SEMANTICA_NOME_PESSOA: str = "Nome / Identificação Pessoal"



SEMANTICA_ROTULO_ENTIDADE: str = "Rótulo / Nome de Entidade"


SEMANTICA_CATEGORIA: str = "Categoria / Classificação"
TIPO_DATA_HORA: str = "Data / Hora"
TIPO_VAZIO: str = "Vazio / Sem Tipo Definido"


THRESHOLD_FUZZY_PADRAO: float = 0.85
THRESHOLD_FUZZY_CURTO: float = 0.95
THRESHOLD_QUASE_CHAVE: float = 0.95
THRESHOLD_QUASI_CONSTANTE: float = 0.95
THRESHOLD_MISTO_TIPOS: float = 0.05
THRESHOLD_OUTLIER_IQR: float = 1.5
THRESHOLD_PADRAO_ESTRUTURADO: float = 0.75
THRESHOLD_DATA_TEXTO: float = 0.80




AMOSTRA_ANALISE: int = 5_000




MAX_VALORES_AMOSTRA_COMPLETA: int = 50




THRESHOLD_DETERMINANTE_MAX_UNICIDADE: float = 0.98
FD_MAX_CARDINALIDADE: int = 500


ALPHA_SIGNIFICANCIA: float = 0.05
SHAPIRO_MIN_N: int = 20
SHAPIRO_MAX_N: int = 5000
CHI2_MIN_FREQ_ESPERADA: int = 5
CHI2_MAX_CATEGORIAS: int = 50
DIST_DETECTION_MIN_N: int = 20
ADF_MIN_N: int = 30
ANALISE_TEMPORAL_MAX_PONTOS: int = 50_000


THRESHOLD_ASSIMETRIA_ROBUSTA: float = 1.0




THRESHOLD_SENTINELA_MIN_PCT: float = 0.005


SENTINELAS_TEXTO: frozenset[str] = frozenset({
    "", "-", "--", "---", ".", "..", "...", "?", "??", "???",
    "n/a", "na", "n.a.", "n/d", "nd", "null", "none", "nil", "nan",
    "#n/d", "#n/a", "#valor!", "#value!", "#ref!", "#nome?", "#name?", "#div/0!",
    "sem informacao", "sem informacoes", "nao informado", "nao informada",
    "nao consta", "nao se aplica", "nao disponivel", "nao identificado",
    "desconhecido", "desconhecida", "indefinido", "indefinida",
    "vazio", "branco", "em branco", "s/i", "s/d", "s/n", "ignorado",
})



SENTINELAS_NUMERICAS: frozenset[float] = frozenset({
    -1.0, -99.0, -999.0, -9999.0, -99999.0, -1.0e9,
    9999.0, 99999.0, 999999.0, 9999999.0, 99999999.0, 999999999.0,
})

SENTINELAS_DATA: frozenset[str] = frozenset({
    "1753-01-01",  
    "1899-12-30",  
    "1900-01-01", "1901-01-01", "1970-01-01",
    "2099-12-31", "9999-12-31",
})


CATEGORIAS_FORTES: dict[str, list[str]] = {
    SEMANTICA_CHAVE_ID: [
        "id", "cod", "codigo", "code", "key", "number", "matricula", "mat",
        "cpf", "cnpj", "registro", "chave", "identifier", "iden", "nr", "num", "pk", "fk",
    ],
    SEMANTICA_DATA_CALENDARIO: [
        "date", "dt", "data", "time", "timestamp", "periodo", "competencia",
        "admissao", "demissao", "nascimento", "vencimento", "inicio", "fim",
        "prazo", "realizacao", "referencia", "vigencia", "expiracao",
        
        
        
        
        
        "ano",
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
        "qtd", "quantidade", "count", "total", "volume", "horas", "dias", "carga",
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
    
    
    
    
    
    
    "Produto / Item": [
        "product", "item", "sku", "merchandise", "produto", "mercadoria",
        "insumo", "material", "ativo", "equipamento", "veiculo", "artigo",
        "marca", "brand", "modelo", "model",
    ],
    "Cargo / Função": [
        "cargo", "funcao", "nivel", "grade", "posicao", "categoria",
        "classe", "faixa", "perfil", "role", "position", "job",
        "title", "occupation",
    ],
    
    
    
    
    "Financeiro / Custo": [
        "custo", "cost", "centro de custo", "despesa", "orcamento", "budget",
        "financeiro", "finance", "contabil", "fiscal", "conta", "rateio",
    ],
    "Curso / Treinamento": [
        "curso", "treinamento", "capacitacao", "formacao", "modulo",
        "trilha", "programa", "workshop", "disciplina", "tema",
        "course", "training", "learning", "certificacao",
    ],
}






TOKENS_QUALIFICADORES: frozenset[str] = frozenset({
    "id", "cod", "codigo", "code", "key", "chave", "pk", "fk", "nr", "num",
    "number", "matricula", "mat", "iden", "identifier", "registro",
    "nome", "name", "desc", "descricao", "description", "sigla", "abrev",
    "tipo", "type", "categoria", "class", "flag", "flg", "status",
    "qtd", "quantidade", "total", "vlr", "valor", "pct", "percentual",
    "dt", "date", "data", "hora", "time", "timestamp",
    
    
    
    
    "dias",
})




PESO_TOKEN_QUALIFICADOR: float = 0.45
PESO_TOKEN_ENTIDADE: float = 1.0



DOMINIOS_DE_PESSOA: frozenset[str] = frozenset({"Perfil do Colaborador"})



CARDINALIDADE_MAX_CATEGORIA: int = 100


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




PADROES_COM_VALIDACAO: frozenset[str] = frozenset({"CPF", "CNPJ"})


PADRAO_MOJIBAKE: str = r"Ã[-¿–—‚-…]|Â[ -¿]|â€|ï¿½|�"

TOKENS_CHAVE_SISTEMA: set[str] = {"id", "code", "number", "key", "cod", "pk", "fk", "identifier"}




TIPOS_ELEGIVEIS_CHAVE: frozenset[str] = frozenset({"Número Inteiro", "Texto", "Texto (⚠️ Parece Data)"})


CORRELACAO_MIN_ABS: float = 0.7






REDUNDANCIA_PARCIAL_MINIMA: float = 0.9
REDUNDANCIA_PARCIAL_MAX_PARES: int = 400
CORRELACAO_MAX_CARDINALIDADE_CAT: int = 50
CORRELACAO_MIN_N: int = 30









DANO_POR_DEFEITO: dict[str, float] = {
    "coluna_vazia": 1.00,          
    "mojibake": 0.80,              
    "documento_invalido": 0.80,    
    "mistura_tipos": 0.70,         
    "sentinela": 0.60,             
    "pii_texto_livre": 0.60,       
    "inconsistencia_texto": 0.50,  
    "data_como_texto": 0.40,       
    
    
}


DANO_MAXIMO_NULOS: float = 1.0



PESO_DANO_COLUNAS: float = 0.85
PESO_DANO_TABELA: float = 0.15






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

# Data Profiler v2 — Fase 1 Implementation Plan

> ⚠️ **DOCUMENTO HISTÓRICO — SUPERADO.**
> Este plano descreve a Fase 1 (v2.0), concluída. A arquitetura, os
> módulos e as decisões descritas aqui **não refletem mais o código**.
> Para o estado atual, veja `docs/superpowers/specs/2026-08-15-recon-v3-design.md`.
> Mantido como registro do que foi decidido e por quê.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir os 5 scripts soltos e duplicados (`Profiller.py`, `statistical_profiler.py`, `semantic_engine.py`, `profiling_orchestrator.py`, `batch_profiler.py`) por um único pacote Python instalável (`data_profiler/`), correto, testado, com dependências modernas e com os testes estatísticos que hoje só existem no docstring.

**Architecture:** Pacote em camadas (`src/data_profiler/{ingestion,semantics,statistics,quality,reporting,pipeline,cli}.py`), cada módulo um conjunto de funções puras sem estado global. `pipeline.DataProfiler` orquestra os módulos. Saída dupla simultânea (JSON pra IA/código, Markdown pra humano) a cada execução, Parquet opcional.

**Tech Stack:** Python 3.11, pandas 3.0.5, numpy 2.4.6, scipy 1.17.1, statsmodels 0.14.6, rapidfuzz, charset-normalizer, typer, loguru, pytest.

## Global Constraints

- Python >= 3.11 (mesma versão já pinada em `.python-version`).
- pandas 3.0.5, numpy 2.4.6, pyarrow 25.0.0 — sem pin de compatibilidade com ambiente legado (decisão do usuário).
- Módulos/arquivos em inglês técnico; funções, campos de dado e chaves de saída em português, seguindo a convenção já usada no código existente (`analisar_estatisticas`, `Recomendacoes_ETL`, etc.).
- Nenhum módulo tem side-effect no import (sem `logger.add()` no nível de módulo) — logging é inicializado explicitamente via `setup_logging()`.
- Todo float não-finito (`NaN`/`Infinity`/`-Infinity`) deve ser saneado para `null` antes de qualquer serialização JSON.
- Cada bug da auditoria (NaN no JSON, FD trivial, `groupby` descartando nulos) vira teste de regressão explícito, não só corrigido silenciosamente.
- Arquivos legados (`statistical_profiler.py`, `semantic_engine.py`, `profiling_orchestrator.py`, `batch_profiler.py`, `Profiller.py`) só são removidos na última tarefa, depois que o pacote novo cobre 100% da funcionalidade.

---

## Task 1: Scaffolding do pacote

**Files:**
- Create: `pyproject.toml`
- Create: `src/data_profiler/__init__.py`
- Create: `src/data_profiler/config.py` (vazio por enquanto, só o módulo)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: pacote instalável via `pip install -e ".[dev]"`, comando `pytest` funcional na raiz.

- [ ] **Step 1: Criar `pyproject.toml`**

```toml
[project]
name = "data-profiler"
version = "2.0.0"
description = "Profiler exploratório de dados para CSV/XLSX/XLS/XLSB com inferência semântica, testes estatísticos e recomendações de ETL."
requires-python = ">=3.11"
dependencies = [
    "pandas==3.0.5",
    "numpy==2.4.6",
    "pyarrow==25.0.0",
    "openpyxl==3.1.5",
    "xlrd==2.0.2",
    "pyxlsb==1.0.10",
    "charset-normalizer==3.4.9",
    "rapidfuzz==3.14.5",
    "unidecode==1.4.0",
    "python-dateutil==2.9.0.post0",
    "scipy==1.17.1",
    "statsmodels==0.14.6",
    "loguru==0.7.3",
    "typer==0.27.1",
    "tqdm==4.70.0",
]

[project.optional-dependencies]
dev = ["pytest==9.1.1", "pytest-cov==7.1.0"]

[project.scripts]
data-profiler = "data_profiler.cli:app"

[build-system]
requires = ["setuptools>=83"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Criar estrutura de diretórios e arquivos vazios**

```bash
mkdir -p src/data_profiler tests
touch src/data_profiler/__init__.py
touch src/data_profiler/config.py
touch tests/__init__.py
```

- [ ] **Step 3: Criar `tests/conftest.py` com fixture de DataFrame sintético base**

```python
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def df_rh_exemplo() -> pd.DataFrame:
    return pd.DataFrame({
        "id_funcionario": range(1000, 1050),
        "nome_completo": [f"Colaborador_{i}" for i in range(50)],
        "salario_bruto": [3500.50 if i % 3 != 0 else np.nan for i in range(50)],
        "dt_admissao": pd.to_datetime(
            ["2020-01-15", "2021-03-10", "2022-06-20", "2023-09-01"] * 12 + ["2024-01-01"] * 2
        ),
        "cpf_colaborador": ["123.456.789-00"] * 48 + [None, None],
        "email_corporativo": [f"user{i}@empresa.com" for i in range(50)],
        "cod_departamento": (["DEP01"] * 20 + ["DEP02"] * 15 + ["DEP03"] * 15),
        "nome_departamento": (["Operações"] * 20 + ["TI"] * 15 + ["RH"] * 15),
        "status_ativo": (["Ativo"] * 47 + ["Inativo"] * 2 + [None]),
        "score_desempenho": [float(i % 10) for i in range(50)],
        "campo_lixo_vazio": [None] * 50,
    })
```

- [ ] **Step 4: Instalar em modo editável e confirmar que `pytest` roda (mesmo sem testes ainda)**

Run: `pip install -e ".[dev]" && pytest --collect-only`
Expected: instalação sem erro, `pytest` reporta "no tests ran" ou "0 collected" sem falha de import.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: scaffolding do pacote data_profiler"
```

---

## Task 2: `config.py` — taxonomias e thresholds (fonte única)

**Files:**
- Modify: `src/data_profiler/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `CATEGORIAS_FORTES: Dict[str, List[str]]`, `CATEGORIAS_FUZZY: Dict[str, List[str]]`, `PADROES_DATA: List[str]`, `PADROES_ESTRUTURADOS: Dict[str, str]`, `TOKENS_CHAVE_SISTEMA: Set[str]`, e todas as constantes `THRESHOLD_*`/`SHAPIRO_*`/`CHI2_*`/`ADF_*`/`ALPHA_SIGNIFICANCIA`/`AMOSTRA_ANALISE`/`ANALISE_TEMPORAL_MAX_PONTOS` listadas no Step 2.

- [ ] **Step 1: Escrever teste que verifica a taxonomia consolidada**

```python
# tests/test_config.py
from data_profiler import config


def test_categorias_fortes_tem_id_e_data():
    assert "id" in config.CATEGORIAS_FORTES["Chave Identificadora (ID)"]
    assert "cpf" in config.CATEGORIAS_FORTES["Chave Identificadora (ID)"]
    assert "data" in config.CATEGORIAS_FORTES["Data / Calendário"]


def test_categorias_fuzzy_tem_localizacao():
    assert "cidade" in config.CATEGORIAS_FUZZY["Localização Geográfica"]


def test_padroes_estruturados_tem_cpf_cnpj_email():
    assert set(config.PADROES_ESTRUTURADOS) >= {"CPF", "CNPJ", "CEP", "E-mail", "Telefone", "UUID"}


def test_threshold_determinante_max_unicidade_existe():
    assert 0.0 < config.THRESHOLD_DETERMINANTE_MAX_UNICIDADE < 1.0


def test_thresholds_testes_hipotese_existem():
    assert config.SHAPIRO_MIN_N == 20
    assert config.SHAPIRO_MAX_N == 5000
    assert config.CHI2_MIN_FREQ_ESPERADA == 5
    assert config.CHI2_MAX_CATEGORIAS == 50
    assert config.ADF_MIN_N == 30
    assert config.ALPHA_SIGNIFICANCIA == 0.05
```

- [ ] **Step 2: Rodar o teste e confirmar que falha** (config.py está vazio)

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: module 'data_profiler.config' has no attribute 'CATEGORIAS_FORTES'`

- [ ] **Step 3: Escrever `config.py` completo**

Taxonomia consolidada a partir da versão mais completa (`Profiller.py`), que já é superset da versão do pipeline legado:

```python
"""Fonte única de taxonomias semânticas e thresholds do profiler."""
from typing import Dict, List, Set

# ── Thresholds gerais (herdados de Profiller.py) ───────────────────────────
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
    "E-mail":   r"^[\w.+\-]+@[\w\-]+\.[\w\-]{2,}$",
    "Telefone": r"^[\(\+]?\d[\d\s\-\(\)]{6,14}\d$",
    "UUID":     r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
}

TOKENS_CHAVE_SISTEMA: Set[str] = {"id", "code", "number", "key", "cod", "pk", "fk", "identifier"}
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `pytest tests/test_config.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/config.py tests/test_config.py
git commit -m "feat: taxonomias e thresholds consolidados em config.py"
```

---

## Task 3: `ingestion.py` — carregamento de arquivo + exceções tipadas

**Files:**
- Create: `src/data_profiler/ingestion.py`
- Test: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: nada de outros módulos do pacote.
- Produces:
  - `class FileFormatError(Exception)`
  - `class EncodingDetectionError(Exception)`
  - `detectar_encoding(caminho: str) -> str`
  - `carregar_arquivo(caminho: str, aba_excel: Optional[Union[str, int]] = 0) -> Tuple[pd.DataFrame, str]`
  - `carregar_todas_abas_excel(caminho: str) -> List[Tuple[pd.DataFrame, str]]`

- [ ] **Step 1: Escrever testes para CSV (separador `;`), extensão não suportada e arquivo inexistente**

```python
# tests/test_ingestion.py
import pandas as pd
import pytest

from data_profiler.ingestion import carregar_arquivo, FileFormatError


def test_carregar_csv_separador_ponto_virgula(tmp_path):
    caminho = tmp_path / "dados.csv"
    caminho.write_text("id;nome\n1;Ana\n2;Bruno\n", encoding="utf-8")

    df, nome = carregar_arquivo(str(caminho))

    assert list(df.columns) == ["id", "nome"]
    assert len(df) == 2
    assert nome == "dados"


def test_carregar_arquivo_inexistente_levanta_file_not_found():
    with pytest.raises(FileNotFoundError):
        carregar_arquivo("/caminho/que/nao/existe.csv")


def test_extensao_nao_suportada_levanta_file_format_error(tmp_path):
    caminho = tmp_path / "dados.txt"
    caminho.write_text("qualquer coisa", encoding="utf-8")

    with pytest.raises(FileFormatError):
        carregar_arquivo(str(caminho))


def test_carregar_xlsx(tmp_path):
    caminho = tmp_path / "planilha.xlsx"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(caminho, index=False)

    df, nome = carregar_arquivo(str(caminho))

    assert list(df.columns) == ["a", "b"]
    assert nome == "planilha__Sheet1"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham** (módulo não existe ainda)

Run: `pytest tests/test_ingestion.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_profiler.ingestion'`

- [ ] **Step 3: Escrever `ingestion.py`**

```python
"""Carregamento de CSV/XLSX/XLS/XLSB com detecção de encoding e separador."""
import os
from typing import List, Optional, Tuple, Union

import pandas as pd
from charset_normalizer import from_path
from loguru import logger


class FileFormatError(Exception):
    """Extensão de arquivo não suportada pelo profiler."""


class EncodingDetectionError(Exception):
    """Falha ao detectar o encoding de um arquivo CSV."""


def detectar_encoding(caminho: str) -> str:
    try:
        resultado = from_path(caminho).best()
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


def carregar_arquivo(
    caminho: str, aba_excel: Optional[Union[str, int]] = 0
) -> Tuple[pd.DataFrame, str]:
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: '{caminho}'")

    extensao = os.path.splitext(caminho)[1].lower()
    nome_base = os.path.splitext(os.path.basename(caminho))[0]

    if extensao == ".csv":
        encoding = detectar_encoding(caminho)
        for sep in [",", ";", "\t", "|"]:
            try:
                df = pd.read_csv(caminho, encoding=encoding, sep=sep, low_memory=False)
                if len(df.columns) > 1:
                    logger.info(f"CSV carregado com separador '{sep}' | Shape: {df.shape}")
                    return df, nome_base
            except Exception:
                continue
        df = pd.read_csv(caminho, encoding=encoding, sep=None, engine="python", low_memory=False)
        logger.info(f"CSV carregado via engine automático | Shape: {df.shape}")
        return df, nome_base

    engines = {".xlsx": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
    if extensao not in engines:
        raise FileFormatError(
            f"Extensão '{extensao}' não suportada. Use .csv, .xlsx, .xls ou .xlsb."
        )

    engine = engines[extensao]
    try:
        xl = pd.ExcelFile(caminho, engine=engine)
        abas = xl.sheet_names
        aba_alvo: str = abas[aba_excel] if isinstance(aba_excel, int) else str(aba_excel)
        df_raw = pd.read_excel(caminho, sheet_name=aba_alvo, engine=engine)
        df = df_raw if isinstance(df_raw, pd.DataFrame) else pd.DataFrame()
        nome_tabela = f"{nome_base}__{aba_alvo}"
        logger.info(f"[{extensao}] Aba '{aba_alvo}' carregada | Shape: {df.shape}")
        return df, nome_tabela
    except Exception as e:
        raise FileFormatError(f"Falha ao ler '{caminho}' ({extensao}): {e}") from e


def carregar_todas_abas_excel(caminho: str) -> List[Tuple[pd.DataFrame, str]]:
    extensao = os.path.splitext(caminho)[1].lower()
    engines = {".xlsx": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
    engine = engines.get(extensao, "openpyxl")

    xl = pd.ExcelFile(caminho, engine=engine)
    nome_base = os.path.splitext(os.path.basename(caminho))[0]
    resultado = []
    for aba in xl.sheet_names:
        df_aba = pd.read_excel(caminho, sheet_name=aba, engine=engine)
        df_aba = df_aba if isinstance(df_aba, pd.DataFrame) else pd.DataFrame()
        nome_tabela = f"{nome_base}__{aba}"
        logger.info(f"Aba '{aba}' carregada | Shape: {df_aba.shape}")
        resultado.append((df_aba, nome_tabela))
    return resultado
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_ingestion.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/ingestion.py tests/test_ingestion.py
git commit -m "feat: módulo de ingestão com exceções tipadas e charset-normalizer"
```

---

## Task 4: `semantics.py` — inferência semântica com rapidfuzz

**Files:**
- Create: `src/data_profiler/semantics.py`
- Test: `tests/test_semantics.py`

**Interfaces:**
- Consumes: `config.CATEGORIAS_FORTES`, `config.CATEGORIAS_FUZZY`, `config.THRESHOLD_FUZZY_PADRAO`, `config.THRESHOLD_FUZZY_CURTO`.
- Produces: `normalizar(texto: str) -> str`, `tokenizar(nome_col: str) -> List[str]`, `inferir_semantica(nome_col: str, detectado_padrao: str = "Nenhum") -> Dict[str, Any]` retornando `{"semantica": str, "confianca_score": float, "origem": str}`.

- [ ] **Step 1: Escrever testes cobrindo match forte, fuzzy, fallback por conteúdo e nome genérico**

```python
# tests/test_semantics.py
from data_profiler.semantics import inferir_semantica, tokenizar


def test_tokenizar_separa_camel_case_e_snake_case():
    assert tokenizar("dt_admissao") == ["dt", "admissao"]
    assert tokenizar("hireDate") == ["hire", "date"]


def test_match_forte_por_token_exato():
    resultado = inferir_semantica("cod_departamento")
    assert resultado["semantica"] == "Chave Identificadora (ID)"
    assert resultado["confianca_score"] >= 0.90


def test_match_fuzzy_nome_com_erro_de_digitacao():
    resultado = inferir_semantica("cidde")  # "cidade" com erro de digitação
    assert resultado["semantica"] == "Localização Geográfica"


def test_fallback_por_conteudo_cpf_ignora_nome():
    resultado = inferir_semantica("campo_qualquer", detectado_padrao="CPF")
    assert resultado["semantica"] == "Chave Identificadora (ID)"
    assert resultado["confianca_score"] == 1.0


def test_nome_sem_semantica_cai_em_generico():
    resultado = inferir_semantica("xyzabc123")
    assert resultado["semantica"] == "Genérico / Não mapeado"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_semantics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_profiler.semantics'`

- [ ] **Step 3: Escrever `semantics.py`**

```python
"""Inferência semântica de nomes de coluna: match forte por token + fuzzy (rapidfuzz)."""
import re
from typing import Any, Dict, List, Optional

from rapidfuzz.distance import JaroWinkler
from unidecode import unidecode

from . import config


def normalizar(texto: str) -> str:
    return unidecode(str(texto)).lower().strip()


def tokenizar(nome_col: str) -> List[str]:
    nome = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(nome_col))
    nome = normalizar(nome)
    return [p for p in re.split(r"[_\s\-\.]+", nome) if p]


_MAPA_PADRAO_SEMANTICA = {
    "CPF":      ("Chave Identificadora (ID)", "Inferred by Content — CPF"),
    "CNPJ":     ("Chave Identificadora (ID)", "Inferred by Content — CNPJ"),
    "UUID":     ("Chave Identificadora (ID)", "Inferred by Content — UUID"),
    "E-mail":   ("Contato / Rede",            "Inferred by Content — E-mail"),
    "Telefone": ("Contato / Rede",            "Inferred by Content — Telefone"),
    "CEP":      ("Localização Geográfica",    "Inferred by Content — CEP"),
}


def inferir_semantica(nome_col: str, detectado_padrao: str = "Nenhum") -> Dict[str, Any]:
    if detectado_padrao in _MAPA_PADRAO_SEMANTICA:
        sem, origem = _MAPA_PADRAO_SEMANTICA[detectado_padrao]
        return {"semantica": sem, "confianca_score": 1.0, "origem": origem}

    tokens = tokenizar(nome_col)
    tokens_set = set(tokens)

    melhor_forte: Optional[str] = None
    max_tokens_forte = 0
    for categoria, palavras in config.CATEGORIAS_FORTES.items():
        intersecao = tokens_set & set(palavras)
        if intersecao and len(intersecao) >= max_tokens_forte:
            max_len_atual = max(len(w) for w in intersecao)
            max_len_melhor = (
                max(len(w) for w in (tokens_set & set(config.CATEGORIAS_FORTES[melhor_forte])))
                if melhor_forte else 0
            )
            if len(intersecao) > max_tokens_forte or max_len_atual > max_len_melhor:
                max_tokens_forte = len(intersecao)
                melhor_forte = categoria

    if melhor_forte:
        palavras_match = tokens_set & set(config.CATEGORIAS_FORTES[melhor_forte])
        max_len = max(len(w) for w in palavras_match)
        if max_tokens_forte > 1:
            score = 1.0
        elif max_len > 5:
            score = 0.95
        else:
            score = 0.90
        return {
            "semantica": melhor_forte,
            "confianca_score": score,
            "origem": f"Strong Token Match ({', '.join(palavras_match)})",
        }

    nome_limpo = normalizar(nome_col)
    melhor_score = 0.0
    categoria_vencedora = "Genérico / Não mapeado"
    palavra_vencedora = ""

    for categoria, palavras_chave in config.CATEGORIAS_FUZZY.items():
        for palavra in palavras_chave:
            palavra_norm = normalizar(palavra)
            threshold = (
                config.THRESHOLD_FUZZY_CURTO if len(palavra_norm) <= 3
                else config.THRESHOLD_FUZZY_PADRAO
            )
            score_full = JaroWinkler.similarity(nome_limpo, palavra_norm)
            scores_tokens = [
                JaroWinkler.similarity(normalizar(t), palavra_norm) for t in tokens
            ]
            score_final = max([score_full] + scores_tokens)

            if score_final >= threshold and score_final > melhor_score:
                melhor_score = score_final
                categoria_vencedora = categoria
                palavra_vencedora = palavra

    return {
        "semantica": categoria_vencedora,
        "confianca_score": round(melhor_score, 4),
        "origem": f"Fuzzy Match ({palavra_vencedora})" if palavra_vencedora else "Unmatched",
    }
```

`JaroWinkler.similarity` do `rapidfuzz.distance` retorna um score de 0.0 a 1.0, mesma escala e mesma semântica do `jellyfish.jaro_winkler_similarity` usado antes — substituição direta, sem mudar a lógica de threshold.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_semantics.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/semantics.py tests/test_semantics.py
git commit -m "feat: inferência semântica com rapidfuzz"
```

---

## Task 5: `statistics.py` (parte 1) — estatísticas descritivas + fix do bug NaN

**Files:**
- Create: `src/data_profiler/statistics.py`
- Test: `tests/test_statistics.py`

**Interfaces:**
- Consumes: `config.THRESHOLD_*`, `config.AMOSTRA_ANALISE`, `config.PADROES_DATA`, `config.PADROES_ESTRUTURADOS`, `config.TOKENS_CHAVE_SISTEMA`, `semantics.tokenizar` (reaproveitada para tokenizar o nome da coluna antes de checar `TOKENS_CHAVE_SISTEMA` — mesma função usada em `semantics.py`, evita duplicar a lógica de separação de camelCase/acentos).
- Produces:
  - `calcular_outliers_iqr(serie: pd.Series) -> Dict[str, Any]`
  - `calcular_distribuicao_top(serie: pd.Series, top_n: int = 5) -> List[Dict[str, Any]]`
  - `detectar_mistura_tipos(serie_limpa: pd.Series, amostra_str: List[str]) -> Dict[str, Any]`
  - `analisar_estatisticas(serie: pd.Series, total_linhas: int) -> Dict[str, Any]` — retorna dict com chaves `tipo_dados`, `valores_unicos`, `nulos_qtd`, `nulos_pct`, `caracteristica`, `ratio_unicidade`, `amostra_representativa`, `estatisticas_adicionais`, `flags` (mesma forma do `Profiller.py` atual, sem a chave `testes_hipotese` ainda — isso é a Task 6).

- [ ] **Step 1: Escrever teste que trava o bug do NaN e outros comportamentos centrais**

```python
# tests/test_statistics.py
import math

import numpy as np
import pandas as pd

from data_profiler.statistics import analisar_estatisticas


def test_coluna_numerica_com_menos_de_3_validos_nao_gera_nan():
    serie = pd.Series([5.0, 7.0], name="score")

    resultado = analisar_estatisticas(serie, total_linhas=2)

    assimetria = resultado["estatisticas_adicionais"]["assimetria"]
    curtose = resultado["estatisticas_adicionais"]["curtose"]
    assert assimetria is None or math.isfinite(assimetria)
    assert curtose is None or math.isfinite(curtose)


def test_coluna_100_pct_vazia():
    serie = pd.Series([None, None, None], name="campo_lixo")

    resultado = analisar_estatisticas(serie, total_linhas=3)

    assert resultado["caracteristica"] == "⚠️ Coluna 100% Vazia"
    assert resultado["nulos_pct"] == 100.0


def test_coluna_chave_primaria_potencial():
    serie = pd.Series(range(100), name="id")

    resultado = analisar_estatisticas(serie, total_linhas=100)

    assert "Chave Primária Potencial" in resultado["caracteristica"]


def test_cpf_detectado_mesmo_em_coluna_de_chave_sistema():
    serie = pd.Series(["123.456.789-00"] * 20, name="id_cpf")

    resultado = analisar_estatisticas(serie, total_linhas=20)

    assert resultado["flags"]["detected_pattern"] == "CPF"


def test_cep_nao_detectado_em_coluna_de_chave_sistema():
    # 5 dígitos numéricos batem no regex de CEP, mas o nome indica chave de
    # sistema (contém "id") — não deve ser marcado como CEP.
    serie = pd.Series([str(90000 + i) for i in range(20)], name="id_interno")

    resultado = analisar_estatisticas(serie, total_linhas=20)

    assert resultado["flags"]["detected_pattern"] != "CEP"


def test_mistura_de_tipos_detectada():
    serie = pd.Series(
        ["123"] * 10 + ["texto_livre"] * 10 + ["2024-01-01"] * 10, name="tipo_misto"
    )

    resultado = analisar_estatisticas(serie, total_linhas=30)

    assert resultado["flags"]["mistura_tipos"]["tem_mistura"] is True
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_statistics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_profiler.statistics'`

- [ ] **Step 3: Escrever `statistics.py` (parte 1 — sem os testes de hipótese, adicionados na Task 6)**

```python
"""Análise estatística descritiva por coluna: tipagem, outliers, mistura de
tipos, padrões estruturados e testes de hipótese (Task 6)."""
import math
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from . import config
from .semantics import tokenizar


def _valor_ou_none(x: float) -> Optional[float]:
    return round(float(x), 6) if math.isfinite(float(x)) else None


def calcular_outliers_iqr(serie: pd.Series) -> Dict[str, Any]:
    q1 = float(serie.quantile(0.25))
    q3 = float(serie.quantile(0.75))
    iqr = q3 - q1
    limite_inf = q1 - config.THRESHOLD_OUTLIER_IQR * iqr
    limite_sup = q3 + config.THRESHOLD_OUTLIER_IQR * iqr
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


def calcular_distribuicao_top(serie: pd.Series, top_n: int = 5) -> List[Dict[str, Any]]:
    try:
        vc = serie.value_counts(normalize=True).head(top_n)
        return [
            {"valor": str(k), "frequencia_relativa": round(float(v), 4), "frequencia_pct": f"{v:.1%}"}
            for k, v in vc.items()
        ]
    except Exception:
        return []


def detectar_mistura_tipos(serie_limpa: pd.Series, amostra_str: List[str]) -> Dict[str, Any]:
    n = len(amostra_str)
    if n == 0:
        return {"tem_mistura": False}

    re_numerico = re.compile(r"^-?\d+([.,]\d+)?$")
    re_data = re.compile("|".join(config.PADROES_DATA))

    qtd_num = sum(1 for v in amostra_str if re_numerico.match(v.replace(",", ".")))
    qtd_data = sum(1 for v in amostra_str if re_data.match(v))
    qtd_vazio = sum(1 for v in amostra_str if v.strip() == "")
    qtd_texto_puro = n - qtd_num - qtd_data - qtd_vazio

    proporcoes = {
        "numerico": round(qtd_num / n, 4),
        "data": round(qtd_data / n, 4),
        "texto_puro": round(qtd_texto_puro / n, 4),
        "vazio_ou_nulo": round(qtd_vazio / n, 4),
    }
    tipos_dominantes = [k for k, v in proporcoes.items() if v >= config.THRESHOLD_MISTO_TIPOS]
    tem_mistura = len(tipos_dominantes) > 1

    return {
        "tem_mistura": tem_mistura,
        "tipos_detectados": tipos_dominantes if tem_mistura else [],
        "proporcoes": proporcoes if tem_mistura else {},
    }


def analisar_estatisticas(serie: pd.Series, total_linhas: int) -> Dict[str, Any]:
    nulos_qtd = int(serie.isna().sum())
    nulos_pct = round((nulos_qtd / total_linhas) * 100, 4) if total_linhas > 0 else 0.0

    serie_limpa = serie.dropna()
    n_validos = len(serie_limpa)
    n_unicos = int(serie_limpa.nunique())
    tipo_bruto = str(serie_limpa.dtype)

    n_amostrar = min(config.AMOSTRA_ANALISE, n_validos)
    amostra_serie = serie_limpa.sample(n=n_amostrar, random_state=42) if n_validos > 0 else serie_limpa
    amostra_str = amostra_serie.astype(str).tolist()

    flag_data_como_texto = False
    flag_padrao_estruturado = "Nenhum"
    estatisticas_extra: Dict[str, Any] = {}
    alerta_mistura_tipos: Dict[str, Any] = {"tem_mistura": False}
    tipo_amigavel = "Desconhecido"

    if "float" in tipo_bruto or "int" in tipo_bruto:
        numericos = serie_limpa.replace([np.inf, -np.inf], np.nan).dropna()

        if numericos.empty:
            tipo_amigavel = "Número (Apenas Inf/NaN)"
        elif (numericos % 1 == 0).all():
            tipo_amigavel = "Número Inteiro"
        else:
            tipo_amigavel = "Número Decimal"

        qtd_inf = int(serie_limpa.isin([np.inf, -np.inf]).sum())

        if not numericos.empty:
            std_val = float(numericos.std())
            media_val = float(numericos.mean())
            estatisticas_extra = {
                "min": round(float(numericos.min()), 6),
                "max": round(float(numericos.max()), 6),
                "media": round(media_val, 6),
                "mediana": round(float(numericos.median()), 6),
                "desvio_padrao": _valor_ou_none(std_val),
                "coef_variacao": round(std_val / media_val, 4) if media_val != 0 and math.isfinite(std_val) else None,
                "assimetria": _valor_ou_none(numericos.skew()),
                "curtose": _valor_ou_none(numericos.kurt()),
                "qtd_negativos": int((numericos < 0).sum()),
                "qtd_zeros": int((numericos == 0).sum()),
                "qtd_inf": qtd_inf,
                "outliers_iqr": calcular_outliers_iqr(numericos),
                "distribuicao_top5": calcular_distribuicao_top(serie_limpa, 5),
            }

    elif "datetime" in tipo_bruto:
        tipo_amigavel = "Data / Hora"
        if n_validos > 0:
            estatisticas_extra = {
                "min_data": str(serie_limpa.min()),
                "max_data": str(serie_limpa.max()),
                "range_dias": (serie_limpa.max() - serie_limpa.min()).days,
                "distribuicao_top5": calcular_distribuicao_top(serie_limpa, 5),
            }

    elif "bool" in tipo_bruto:
        tipo_amigavel = "Booleano"
        if n_validos > 0:
            estatisticas_extra = {
                "qtd_true": int(serie_limpa.sum()),
                "qtd_false": n_validos - int(serie_limpa.sum()),
                "pct_true": round(float(serie_limpa.sum()) / n_validos, 4),
            }

    else:
        tipo_amigavel = "Texto"
        if amostra_str:
            matches_dt = sum(1 for v in amostra_str if any(re.match(p, v) for p in config.PADROES_DATA))
            if (matches_dt / len(amostra_str)) >= config.THRESHOLD_DATA_TEXTO:
                tipo_amigavel = "Texto (⚠️ Parece Data)"
                flag_data_como_texto = True
            else:
                tokens_col = set(tokenizar(str(serie.name)))
                eh_chave_sistema = bool(tokens_col & config.TOKENS_CHAVE_SISTEMA)
                for padrao_nome, regex in config.PADROES_ESTRUTURADOS.items():
                    if eh_chave_sistema and padrao_nome in ("CEP", "Telefone"):
                        continue
                    matches_pad = sum(1 for v in amostra_str if re.match(regex, v))
                    if (matches_pad / len(amostra_str)) >= config.THRESHOLD_PADRAO_ESTRUTURADO:
                        flag_padrao_estruturado = padrao_nome
                        break
                alerta_mistura_tipos = detectar_mistura_tipos(serie_limpa, amostra_str)

        if n_validos > 0:
            lens = serie_limpa.astype(str).str.len()
            estatisticas_extra = {
                "str_len_min": int(lens.min()),
                "str_len_max": int(lens.max()),
                "str_len_media": round(float(lens.mean()), 2),
                "str_len_std": round(float(lens.std()), 2) if n_validos > 1 else 0.0,
                "comprimento_fixo": int(lens.min()) == int(lens.max()),
                "distribuicao_top5": calcular_distribuicao_top(serie_limpa, 5),
            }

    ratio_unicidade = n_unicos / total_linhas if total_linhas > 0 else 0.0
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
    elif top_freq >= config.THRESHOLD_QUASI_CONSTANTE:
        caracteristica = f"⚠️ Quasi-Constante ({top_freq:.1%} em um único valor)"
    elif ratio_unicidade == 1.0 and total_linhas > 1:
        caracteristica = "🔑 Chave Primária Potencial"
    elif ratio_unicidade >= config.THRESHOLD_QUASE_CHAVE and total_linhas > 1:
        caracteristica = f"🔑 Quase-Chave ({ratio_unicidade:.1%} únicos — possível dado sujo)"
    elif "Data" in tipo_amigavel:
        caracteristica = "📅 Série Temporal"
    elif 1 < n_unicos <= 25:
        caracteristica = "🏷️ Categórica / Dimensão Curta"
    elif 25 < n_unicos <= 100:
        caracteristica = "📂 Dimensão Média"
    elif "Texto" in tipo_amigavel:
        caracteristica = "📋 Dimensão Longa (Texto Livre)"
    elif "Número" in tipo_amigavel:
        caracteristica = "📊 Métrica Contínua"
    else:
        caracteristica = "📋 Atributo Geral"

    valores_amostra: List[str] = []
    if n_validos > 0:
        if n_unicos <= 25:
            valores_amostra = [str(v) for v in serie_limpa.unique().tolist()]
        else:
            valores_amostra = (
                serie_limpa.drop_duplicates().sample(min(10, n_unicos), random_state=42).astype(str).tolist()
            )

    return {
        "tipo_dados": tipo_amigavel,
        "valores_unicos": n_unicos,
        "nulos_qtd": nulos_qtd,
        "nulos_pct": nulos_pct,
        "caracteristica": caracteristica,
        "ratio_unicidade": round(ratio_unicidade, 4),
        "amostra_representativa": valores_amostra,
        "estatisticas_adicionais": estatisticas_extra,
        "flags": {
            "is_date_as_text": flag_data_como_texto,
            "detected_pattern": flag_padrao_estruturado,
            "mistura_tipos": alerta_mistura_tipos,
        },
    }
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_statistics.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/statistics.py tests/test_statistics.py
git commit -m "feat: estatísticas descritivas com fix do bug de NaN no JSON"
```

---

## Task 6: `statistics.py` (parte 2) — testes de hipótese

**Files:**
- Modify: `src/data_profiler/statistics.py`
- Modify: `tests/test_statistics.py`

**Interfaces:**
- Consumes: `config.SHAPIRO_MIN_N`, `config.SHAPIRO_MAX_N`, `config.CHI2_MIN_FREQ_ESPERADA`, `config.CHI2_MAX_CATEGORIAS`, `config.DIST_DETECTION_MIN_N`, `config.ADF_MIN_N`, `config.ALPHA_SIGNIFICANCIA`.
- Produces:
  - `testar_normalidade_shapiro(numericos: pd.Series) -> Dict[str, Any]`
  - `testar_uniformidade_chi2(serie_categorica: pd.Series) -> Dict[str, Any]`
  - `calcular_intervalo_confianca_media(numericos: pd.Series) -> Dict[str, Any]`
  - `detectar_distribuicao_provavel(numericos: pd.Series) -> Dict[str, Any]`
  - `testar_estacionariedade_adf(serie_numerica_ordenada: pd.Series) -> Dict[str, Any]`
  - `testar_autocorrelacao_ljungbox(serie_numerica_ordenada: pd.Series) -> Dict[str, Any]`
  - `analisar_estatisticas(...)` passa a incluir `estatisticas_adicionais["testes_hipotese"]` para colunas numéricas com `n_validos >= 2`.

- [ ] **Step 1: Escrever testes para cada teste de hipótese, incluindo os casos de amostra insuficiente**

```python
# adicionar em tests/test_statistics.py
import pandas as pd

from data_profiler.statistics import (
    calcular_intervalo_confianca_media,
    detectar_distribuicao_provavel,
    testar_autocorrelacao_ljungbox,
    testar_estacionariedade_adf,
    testar_normalidade_shapiro,
    testar_uniformidade_chi2,
)


def test_shapiro_amostra_insuficiente_retorna_nao_aplicavel():
    resultado = testar_normalidade_shapiro(pd.Series([1.0, 2.0, 3.0]))
    assert resultado["aplicavel"] is False


def test_shapiro_normal_provavel_para_amostra_normal():
    import numpy as np
    rng = np.random.default_rng(42)
    serie = pd.Series(rng.normal(loc=0, scale=1, size=500))

    resultado = testar_normalidade_shapiro(serie)

    assert resultado["aplicavel"] is True
    assert resultado["normal_provavel"] is True


def test_chi2_categorias_demais_retorna_nao_aplicavel():
    serie = pd.Series([f"cat_{i}" for i in range(60)])
    resultado = testar_uniformidade_chi2(serie)
    assert resultado["aplicavel"] is False


def test_chi2_distribuicao_uniforme():
    serie = pd.Series((["A"] * 50 + ["B"] * 50 + ["C"] * 50))
    resultado = testar_uniformidade_chi2(serie)
    assert resultado["aplicavel"] is True
    assert resultado["distribuicao_uniforme_provavel"] is True


def test_ic_media_amostra_minima():
    resultado = calcular_intervalo_confianca_media(pd.Series([10.0, 20.0]))
    assert resultado["aplicavel"] is True
    assert resultado["limite_inferior"] <= resultado["media"] <= resultado["limite_superior"]


def test_distribuicao_provavel_amostra_insuficiente():
    resultado = detectar_distribuicao_provavel(pd.Series([1.0, 2.0, 3.0]))
    assert resultado["aplicavel"] is False


def test_distribuicao_provavel_detecta_normal():
    import numpy as np
    rng = np.random.default_rng(42)
    serie = pd.Series(rng.normal(loc=100, scale=15, size=500))

    resultado = detectar_distribuicao_provavel(serie)

    assert resultado["distribuicao"] == "normal"


def test_adf_amostra_insuficiente():
    resultado = testar_estacionariedade_adf(pd.Series(range(10), dtype=float))
    assert resultado["aplicavel"] is False


def test_ljungbox_amostra_insuficiente():
    resultado = testar_autocorrelacao_ljungbox(pd.Series(range(10), dtype=float))
    assert resultado["aplicavel"] is False


def test_analisar_estatisticas_inclui_testes_hipotese_para_numerica():
    from data_profiler.statistics import analisar_estatisticas
    serie = pd.Series(range(50), dtype=float)

    resultado = analisar_estatisticas(serie, total_linhas=50)

    assert "testes_hipotese" in resultado["estatisticas_adicionais"]
    assert "shapiro_wilk" in resultado["estatisticas_adicionais"]["testes_hipotese"]
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_statistics.py -v -k "shapiro or chi2 or ic_media or distribuicao_provavel or adf or ljungbox or testes_hipotese"`
Expected: FAIL — `ImportError: cannot import name 'testar_normalidade_shapiro'`

- [ ] **Step 3: Adicionar os testes de hipótese em `statistics.py`**

Adicionar os imports no topo do arquivo e as funções abaixo (antes de `analisar_estatisticas`):

```python
from scipy import stats as scipy_stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import adfuller
```

```python
def testar_normalidade_shapiro(numericos: pd.Series) -> Dict[str, Any]:
    n = len(numericos)
    if n < config.SHAPIRO_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.SHAPIRO_MIN_N})"}
    amostra = (
        numericos.sample(n=config.SHAPIRO_MAX_N, random_state=42)
        if n > config.SHAPIRO_MAX_N else numericos
    )
    estatistica, p_valor = scipy_stats.shapiro(amostra)
    return {
        "aplicavel": True,
        "estatistica": round(float(estatistica), 6),
        "p_valor": round(float(p_valor), 6),
        "normal_provavel": bool(p_valor > config.ALPHA_SIGNIFICANCIA),
        "n_amostra": int(len(amostra)),
    }


def testar_uniformidade_chi2(serie_categorica: pd.Series) -> Dict[str, Any]:
    contagens = serie_categorica.value_counts()
    n_categorias = len(contagens)
    n_total = int(contagens.sum())
    if n_categorias < 2:
        return {"aplicavel": False, "motivo": "Menos de 2 categorias distintas"}
    if n_categorias > config.CHI2_MAX_CATEGORIAS:
        return {"aplicavel": False, "motivo": f"Categorias demais (n={n_categorias} > {config.CHI2_MAX_CATEGORIAS})"}
    freq_esperada = n_total / n_categorias
    if freq_esperada < config.CHI2_MIN_FREQ_ESPERADA:
        return {
            "aplicavel": False,
            "motivo": f"Frequência esperada insuficiente ({freq_esperada:.1f} < {config.CHI2_MIN_FREQ_ESPERADA})",
        }
    estatistica, p_valor = scipy_stats.chisquare(contagens.to_numpy())
    return {
        "aplicavel": True,
        "estatistica": round(float(estatistica), 6),
        "p_valor": round(float(p_valor), 6),
        "distribuicao_uniforme_provavel": bool(p_valor > config.ALPHA_SIGNIFICANCIA),
        "n_categorias": int(n_categorias),
    }


def calcular_intervalo_confianca_media(numericos: pd.Series) -> Dict[str, Any]:
    n = len(numericos)
    if n < 2:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < 2)"}
    media = float(numericos.mean())
    erro_padrao = float(numericos.std(ddof=1)) / (n ** 0.5)
    if erro_padrao == 0.0 or not math.isfinite(erro_padrao):
        return {"aplicavel": True, "media": round(media, 6), "limite_inferior": round(media, 6), "limite_superior": round(media, 6)}
    limite_inf, limite_sup = scipy_stats.t.interval(0.95, df=n - 1, loc=media, scale=erro_padrao)
    return {
        "aplicavel": True,
        "media": round(media, 6),
        "limite_inferior": round(float(limite_inf), 6),
        "limite_superior": round(float(limite_sup), 6),
    }


def detectar_distribuicao_provavel(numericos: pd.Series) -> Dict[str, Any]:
    n = len(numericos)
    if n < config.DIST_DETECTION_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.DIST_DETECTION_MIN_N})"}

    valores = numericos.to_numpy()
    candidatos = {"normal": scipy_stats.norm}
    if (valores > 0).all():
        candidatos["lognormal"] = scipy_stats.lognorm
    if (valores >= 0).all():
        candidatos["uniforme"] = scipy_stats.uniform
        candidatos["exponencial"] = scipy_stats.expon

    melhor_nome: Optional[str] = None
    melhor_p = -1.0
    for nome, dist in candidatos.items():
        try:
            params = dist.fit(valores)
            _, p_valor = scipy_stats.kstest(valores, dist.name, args=params)
        except Exception:
            continue
        if p_valor > melhor_p:
            melhor_p = p_valor
            melhor_nome = nome

    if melhor_nome is None or melhor_p <= config.ALPHA_SIGNIFICANCIA:
        return {"aplicavel": True, "distribuicao": "Desconhecida", "p_valor": round(max(melhor_p, 0.0), 6)}
    return {"aplicavel": True, "distribuicao": melhor_nome, "p_valor": round(melhor_p, 6)}


def testar_estacionariedade_adf(serie_numerica_ordenada: pd.Series) -> Dict[str, Any]:
    n = len(serie_numerica_ordenada)
    if n < config.ADF_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.ADF_MIN_N})"}
    resultado = adfuller(serie_numerica_ordenada.to_numpy(), autolag="AIC")
    estatistica, p_valor = float(resultado[0]), float(resultado[1])
    return {
        "aplicavel": True,
        "estatistica": round(estatistica, 6),
        "p_valor": round(p_valor, 6),
        "estacionaria": bool(p_valor < config.ALPHA_SIGNIFICANCIA),
    }


def testar_autocorrelacao_ljungbox(serie_numerica_ordenada: pd.Series) -> Dict[str, Any]:
    n = len(serie_numerica_ordenada)
    if n < config.ADF_MIN_N:
        return {"aplicavel": False, "motivo": f"Amostra insuficiente (n={n} < {config.ADF_MIN_N})"}
    lags = max(1, min(10, n // 5))
    resultado = acorr_ljungbox(serie_numerica_ordenada, lags=[lags], return_df=True)
    estatistica = float(resultado["lb_stat"].iloc[0])
    p_valor = float(resultado["lb_pvalue"].iloc[0])
    return {
        "aplicavel": True,
        "estatistica": round(estatistica, 6),
        "p_valor": round(p_valor, 6),
        "autocorrelacionada": bool(p_valor < config.ALPHA_SIGNIFICANCIA),
        "lags": int(lags),
    }
```

Depois, dentro de `analisar_estatisticas`, no bloco `if not numericos.empty:` (branch numérica), adicionar a chave `testes_hipotese` ao dict `estatisticas_extra` já existente:

```python
            estatisticas_extra["testes_hipotese"] = {
                "shapiro_wilk": testar_normalidade_shapiro(numericos),
                "intervalo_confianca_media_95": calcular_intervalo_confianca_media(numericos),
                "distribuicao_provavel": detectar_distribuicao_provavel(numericos),
            }
```

E no branch de texto/categórica (bloco `else` de tipo, dentro do `if n_validos > 0:` que monta `estatisticas_extra` de string), adicionar:

```python
            if n_unicos <= config.CHI2_MAX_CATEGORIAS:
                estatisticas_extra["testes_hipotese"] = {
                    "qui_quadrado_uniformidade": testar_uniformidade_chi2(serie_limpa),
                }
```

- [ ] **Step 4: Rodar todos os testes de `statistics.py` e confirmar que passam**

Run: `pytest tests/test_statistics.py -v`
Expected: PASS (todos os testes, incluindo os da Task 5)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/statistics.py tests/test_statistics.py
git commit -m "feat: testes de hipótese (Shapiro-Wilk, qui², IC95%, distribuição, ADF, Ljung-Box)"
```

---

## Task 7: `quality.py` — dependências funcionais, gap analysis e recomendações ETL

**Files:**
- Create: `src/data_profiler/quality.py`
- Test: `tests/test_quality.py`

**Interfaces:**
- Consumes: `config.THRESHOLD_DETERMINANTE_MAX_UNICIDADE`.
- Produces:
  - `detectar_dependencias_funcionais(df: pd.DataFrame, colunas_meta: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `gerar_gap_analysis(semanticas_presentes: Set[str]) -> List[Dict[str, Any]]`
  - `gerar_recomendacoes_etl(nome_tabela: str, coluna: str, stats: Dict[str, Any], padrao_estruturado: str, linhas_analisadas: int) -> List[Dict[str, Any]]`

`colunas_meta` é uma lista de dicts, cada um com pelo menos as chaves `Coluna`, `Qtd_Unicos`, `Ratio_Unicidade`, `Caracteristica` — o mesmo formato que `pipeline.py` (Task 10) vai montar por coluna.

- [ ] **Step 1: Escrever testes que travam os dois bugs de FD (determinante trivial e `groupby` descartando nulos)**

```python
# tests/test_quality.py
import pandas as pd

from data_profiler.quality import detectar_dependencias_funcionais, gerar_gap_analysis


def _meta(coluna, qtd_unicos, ratio_unicidade, caracteristica="🏷️ Categórica / Dimensão Curta"):
    return {"Coluna": coluna, "Qtd_Unicos": qtd_unicos, "Ratio_Unicidade": ratio_unicidade, "Caracteristica": caracteristica}


def test_fd_real_e_detectada():
    df = pd.DataFrame({
        "cod_depto": ["D1"] * 5 + ["D2"] * 5,
        "nome_depto": ["Operações"] * 5 + ["TI"] * 5,
    })
    colunas_meta = [_meta("cod_depto", 2, 0.2), _meta("nome_depto", 2, 0.2)]

    fds = detectar_dependencias_funcionais(df, colunas_meta)

    determinantes = {f["determinante"] for f in fds}
    assert "cod_depto" in determinantes


def test_coluna_quase_chave_nao_vira_determinante_trivial():
    df = pd.DataFrame({
        "id_quase_unico": [f"ID{i}" for i in range(100)],
        "outra_coluna": (["X"] * 50 + ["Y"] * 50),
    })
    colunas_meta = [_meta("id_quase_unico", 100, 1.0), _meta("outra_coluna", 2, 0.02)]

    fds = detectar_dependencias_funcionais(df, colunas_meta)

    determinantes = {f["determinante"] for f in fds}
    assert "id_quase_unico" not in determinantes


def test_fd_considera_nulos_no_agrupador():
    df = pd.DataFrame({
        "cod_depto": ["D1", "D1", None, None],
        "nome_depto": ["Operações", "Operações", "TI", "RH"],
    })
    colunas_meta = [_meta("cod_depto", 2, 0.5), _meta("nome_depto", 3, 0.75)]

    fds = detectar_dependencias_funcionais(df, colunas_meta)

    # Com os 2 nulos de cod_depto agrupados juntos, nome_depto varia (TI/RH)
    # dentro desse grupo -> não deve ser reportado como "cod_depto determina nome_depto".
    determinantes_de_nome = [f for f in fds if f["dependente"] == "nome_depto"]
    assert all(f["determinante"] != "cod_depto" for f in determinantes_de_nome)


def test_gap_analysis_kpi_bloqueado_sem_semanticas():
    gaps = gerar_gap_analysis(set())
    assert all(g["status"] == "❌ Bloqueado" for g in gaps)


def test_gap_analysis_kpi_habilitado_com_semanticas_completas():
    gaps = gerar_gap_analysis({"Estrutura Organizacional", "Quantidade / Métrica"})
    gap_hr_001 = next(g for g in gaps if g["kpi_id"] == "KPI_HR_001")
    assert gap_hr_001["status"] == "✅ Habilitado"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_profiler.quality'`

- [ ] **Step 3: Escrever `quality.py`**

```python
"""Qualidade de dados: dependências funcionais, gap analysis de KPI e recomendações ETL."""
from typing import Any, Dict, List, Set

import pandas as pd

from . import config

_REGRAS_KPI: List[Dict[str, Any]] = [
    {"id": "KPI_HR_001", "nome": "Volume de Esforço por Departamento",
     "semanticas": ["Estrutura Organizacional", "Quantidade / Métrica"]},
    {"id": "KPI_HR_002", "nome": "Distribuição de Liderança por Perfil",
     "semanticas": ["Perfil do Colaborador", "Cargo / Função"]},
    {"id": "KPI_HR_003", "nome": "Evolução de Custo de Pessoal",
     "semanticas": ["Valor Financeiro", "Data / Calendário"]},
    {"id": "KPI_HR_004", "nome": "Análise de Turnover",
     "semanticas": ["Perfil do Colaborador", "Data / Calendário"]},
    {"id": "KPI_TREIN_001", "nome": "Efetividade de Treinamentos",
     "semanticas": ["Curso / Treinamento", "Resultado de Avaliação"]},
    {"id": "KPI_GEO_001", "nome": "Distribuição Geográfica de Headcount",
     "semanticas": ["Localização Geográfica", "Estrutura Organizacional"]},
]


def detectar_dependencias_funcionais(
    df: pd.DataFrame, colunas_meta: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    candidatas = [
        m["Coluna"] for m in colunas_meta
        if m.get("Qtd_Unicos", 999_999) < 500
        and m.get("Caracteristica", "") not in ("⚠️ Coluna 100% Vazia", "⚠️ Sem Valores Válidos")
    ]
    determinantes_validos = {
        m["Coluna"] for m in colunas_meta
        if m.get("Ratio_Unicidade", 1.0) < config.THRESHOLD_DETERMINANTE_MAX_UNICIDADE
    }

    dependencias = []
    for i, col_a in enumerate(candidatas):
        for col_b in candidatas[i + 1:]:
            if col_a == col_b:
                continue
            try:
                if col_a in determinantes_validos:
                    max_b_por_a = df.groupby(col_a, dropna=False)[col_b].nunique(dropna=False).max()
                    if max_b_por_a == 1:
                        dependencias.append({
                            "determinante": col_a, "dependente": col_b,
                            "tipo": "Dependência Funcional Direta",
                            "descricao": f"'{col_a}' determina unicamente '{col_b}'. Candidata à desnormalização ou chave composta.",
                        })
                if col_b in determinantes_validos:
                    max_a_por_b = df.groupby(col_b, dropna=False)[col_a].nunique(dropna=False).max()
                    if max_a_por_b == 1:
                        dependencias.append({
                            "determinante": col_b, "dependente": col_a,
                            "tipo": "Dependência Funcional Direta",
                            "descricao": f"'{col_b}' determina unicamente '{col_a}'. Candidata à desnormalização ou chave composta.",
                        })
            except Exception:
                continue
    return dependencias


def gerar_gap_analysis(semanticas_presentes: Set[str]) -> List[Dict[str, Any]]:
    gaps = []
    for regra in _REGRAS_KPI:
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
            "semanticas_presentes": sorted(presentes),
            "semanticas_ausentes": sorted(ausentes),
            "recomendacao": (
                f"Inclua colunas com semântica: {', '.join(sorted(ausentes))}"
                if ausentes else "Tabela possui todos os requisitos para este KPI."
            ),
        })
    return gaps


def gerar_recomendacoes_etl(
    nome_tabela: str,
    coluna: str,
    stats: Dict[str, Any],
    padrao_estruturado: str,
    linhas_analisadas: int,
) -> List[Dict[str, Any]]:
    recomendacoes: List[Dict[str, Any]] = []
    n_validos = linhas_analisadas - stats["nulos_qtd"]
    pct_validos = (n_validos / linhas_analisadas * 100) if linhas_analisadas > 0 else 0.0

    if "Vazia" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Bronze",
            "Acao": f"Remover '{coluna}': 100% nulos. Zero impacto em dados úteis.",
            "Linhas_Afetadas": 0,
        })

    if stats["flags"]["is_date_as_text"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Bronze",
            "Acao": f"Converter '{coluna}' para Date/Datetime. Viabiliza filtros e JOINs temporais.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if padrao_estruturado != "Nenhum":
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Silver",
            "Acao": f"LGPD: Mascarar/Hashear '{coluna}' ({padrao_estruturado}). Protege {n_validos:,} registros ({pct_validos:.1f}%).",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if "Chave Primária Potencial" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
            "Acao": f"Promover '{coluna}' como PK. {stats['valores_unicos']:,} valores únicos garantem integridade.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if "Quase-Chave" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Bronze",
            "Acao": f"'{coluna}' tem {stats['ratio_unicidade']:.1%} de unicidade — verificar duplicatas ou dados sujos antes de usar como chave.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if "Quasi-Constante" in stats["caracteristica"]:
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
            "Acao": f"'{coluna}' é quasi-constante. Avaliar remoção ou tratamento como constante no pipeline.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    if stats["flags"]["mistura_tipos"].get("tem_mistura"):
        tipos = stats["flags"]["mistura_tipos"].get("tipos_detectados", [])
        recomendacoes.append({
            "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🔴 ALTA", "Camada": "Bronze",
            "Acao": f"'{coluna}' contém mistura de tipos: {tipos}. Normalizar antes de qualquer transformação.",
            "Linhas_Afetadas": n_validos, "Pct_Impacto": f"{pct_validos:.1f}%",
        })

    outliers_info = stats["estatisticas_adicionais"].get("outliers_iqr", {})
    n_out = outliers_info.get("qtd_outliers_total", 0)
    if n_out > 0:
        pct_out = round(n_out / linhas_analisadas * 100, 1) if linhas_analisadas > 0 else 0.0
        if pct_out > 1.0:
            recomendacoes.append({
                "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": "🟡 MÉDIA", "Camada": "Silver",
                "Acao": (
                    f"'{coluna}' tem {n_out:,} outliers IQR ({pct_out:.1f}%). "
                    f"Intervalo esperado: [{outliers_info['limite_inferior']}, {outliers_info['limite_superior']}]."
                ),
                "Linhas_Afetadas": n_out, "Pct_Impacto": f"{pct_out:.1f}%",
            })

    return recomendacoes
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_quality.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/quality.py tests/test_quality.py
git commit -m "feat: dependências funcionais (sem trivial, com dropna=False), gap analysis e recomendações ETL"
```

---

## Task 8: `reporting.py` — saneamento de NaN, export JSON e Parquet

**Files:**
- Create: `src/data_profiler/reporting.py`
- Test: `tests/test_reporting.py`

**Interfaces:**
- Produces:
  - `sanear_floats(obj: Any) -> Any`
  - `nome_seguro(nome_tabela: str) -> str`
  - `exportar_json(payload: Dict[str, Any], caminho: str) -> None`
  - `exportar_parquet(payload: Dict[str, Any], caminho_base: str) -> None`

- [ ] **Step 1: Escrever teste que trava o bug de NaN cru no JSON**

```python
# tests/test_reporting.py
import json
import math

from data_profiler.reporting import exportar_json, sanear_floats


def test_sanear_floats_converte_nan_para_none():
    resultado = sanear_floats({"skew": float("nan"), "std": 1.5, "valores": [float("inf"), 2.0]})
    assert resultado == {"skew": None, "std": 1.5, "valores": [None, 2.0]}


def test_exportar_json_nunca_gera_token_nan_cru(tmp_path):
    payload = {"colunas": [{"nome": "x", "assimetria": float("nan")}]}
    caminho = tmp_path / "saida.json"

    exportar_json(payload, str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "NaN" not in conteudo
    dados = json.loads(conteudo)  # json.loads padrão rejeita NaN cru se não houvesse o saneamento
    assert dados["colunas"][0]["assimetria"] is None
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_reporting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_profiler.reporting'`

- [ ] **Step 3: Escrever a parte de `reporting.py` com saneamento + JSON + Parquet**

```python
"""Exportação do payload de profiling: JSON (IA/código), Markdown (humano,
Task 9) e Parquet (opcional, BI)."""
import json
import math
import re
from typing import Any, Dict

import pandas as pd
from loguru import logger


def sanear_floats(obj: Any) -> Any:
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanear_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanear_floats(v) for v in obj]
    return obj


def nome_seguro(nome_tabela: str) -> str:
    return re.sub(r"[^\w\-]", "_", nome_tabela)


def exportar_json(payload: Dict[str, Any], caminho: str) -> None:
    payload_limpo = sanear_floats(payload)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(payload_limpo, f, ensure_ascii=False, indent=4, default=str)
    logger.info(f"✓ JSON exportado: '{caminho}'")


def exportar_parquet(payload: Dict[str, Any], caminho_base: str) -> None:
    nome_tab = payload["metadados_execucao"]["tabela"]
    nome_safe = nome_seguro(nome_tab)

    df_cols = pd.DataFrame(payload["colunas"])
    df_cols["Stats_Extra"] = df_cols["Stats_Extra"].apply(
        lambda x: json.dumps(sanear_floats(x), ensure_ascii=False, default=str) if isinstance(x, dict) else str(x)
    )
    df_cols["alerta_data_texto"] = df_cols["Alertas"].apply(lambda x: x.get("data_como_texto", False))
    df_cols["alerta_mistura_tipos"] = df_cols["Alertas"].apply(
        lambda x: json.dumps(x.get("mistura_tipos", {}), ensure_ascii=False)
    )
    df_cols = df_cols.drop(columns=["Alertas"])
    df_cols.to_parquet(f"{caminho_base}_{nome_safe}_columns.parquet", index=False)

    pd.DataFrame(payload["recomendacoes_etl"]).to_parquet(
        f"{caminho_base}_{nome_safe}_recommendations.parquet", index=False
    )

    if payload["dependencias_funcionais"]:
        pd.DataFrame(payload["dependencias_funcionais"]).to_parquet(
            f"{caminho_base}_{nome_safe}_dependencies.parquet", index=False
        )

    df_gaps = pd.DataFrame(payload["gap_analysis_kpis"])
    df_gaps["semanticas_presentes"] = df_gaps["semanticas_presentes"].apply(json.dumps)
    df_gaps["semanticas_ausentes"] = df_gaps["semanticas_ausentes"].apply(json.dumps)
    df_gaps.to_parquet(f"{caminho_base}_{nome_safe}_gap_analysis.parquet", index=False)

    meta = dict(payload["metadados_execucao"])
    meta["resumo_qualidade"] = json.dumps(sanear_floats(meta["resumo_qualidade"]), ensure_ascii=False)
    pd.DataFrame([meta]).to_parquet(f"{caminho_base}_{nome_safe}_metadata.parquet", index=False)

    logger.info(f"✓ Parquet exportado: 5 arquivos com prefixo '{caminho_base}_{nome_safe}_'")
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_reporting.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/reporting.py tests/test_reporting.py
git commit -m "feat: saneamento de NaN/Inf e export JSON/Parquet"
```

---

## Task 9: `reporting.py` — relatório Markdown (formato humano)

**Files:**
- Modify: `src/data_profiler/reporting.py`
- Modify: `tests/test_reporting.py`

**Interfaces:**
- Consumes: mesmo `payload` que `exportar_json` (formato definido na Task 11/pipeline).
- Produces: `exportar_markdown(payload: Dict[str, Any], caminho: str) -> None`

- [ ] **Step 1: Escrever teste com um payload mínimo representativo**

```python
# adicionar em tests/test_reporting.py
from data_profiler.reporting import exportar_markdown


def _payload_minimo():
    return {
        "metadados_execucao": {
            "tabela": "TB_TESTE",
            "linhas_originais": 100,
            "linhas_analisadas": 100,
            "total_colunas": 2,
            "resumo_qualidade": {
                "colunas_com_nulos": 1, "colunas_100pct_nulas": 0,
                "colunas_sensiveis_lgpd": 1, "semanticas_mapeadas": 2,
                "semanticas_encontradas": ["Chave Identificadora (ID)", "Contato / Rede"],
                "kpis_habilitados": 0, "total_recomendacoes": 1,
            },
        },
        "colunas": [
            {"Coluna": "id", "Tipo_Inferred": "Número Inteiro", "Semantica_IA": "Chave Identificadora (ID)",
             "Pct_Nulos": 0.0, "Caracteristica": "🔑 Chave Primária Potencial"},
            {"Coluna": "cpf", "Tipo_Inferred": "Texto", "Semantica_IA": "Chave Identificadora (ID)",
             "Pct_Nulos": 2.0, "Caracteristica": "📋 Atributo Geral"},
        ],
        "recomendacoes_etl": [
            {"Tabela": "TB_TESTE", "Coluna": "cpf", "Prioridade": "🔴 ALTA", "Camada": "Silver",
             "Acao": "LGPD: Mascarar 'cpf' (CPF)."},
        ],
        "dependencias_funcionais": [],
        "gap_analysis_kpis": [
            {"kpi_id": "KPI_HR_001", "kpi_nome": "Volume de Esforço por Departamento",
             "status": "❌ Bloqueado", "cobertura_pct": "0%"},
        ],
        "analise_temporal_series": [],
    }


def test_exportar_markdown_gera_arquivo_com_secoes_esperadas(tmp_path):
    caminho = tmp_path / "relatorio.md"

    exportar_markdown(_payload_minimo(), str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "TB_TESTE" in conteudo
    assert "cpf" in conteudo
    assert "Recomendações ETL" in conteudo
    assert "KPI_HR_001" in conteudo
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `pytest tests/test_reporting.py -v -k markdown`
Expected: FAIL — `ImportError: cannot import name 'exportar_markdown'`

- [ ] **Step 3: Adicionar `exportar_markdown` em `reporting.py`**

```python
def _tabela_markdown(linhas: list, cabecalhos: list) -> str:
    out = ["| " + " | ".join(cabecalhos) + " |", "|" + "---|" * len(cabecalhos)]
    for linha in linhas:
        out.append("| " + " | ".join(str(v) for v in linha) + " |")
    return "\n".join(out)


def exportar_markdown(payload: Dict[str, Any], caminho: str) -> None:
    meta = payload["metadados_execucao"]
    resumo = meta["resumo_qualidade"]

    partes = [f"# Relatório de Perfilamento — {meta['tabela']}", ""]
    partes.append(
        f"- Linhas originais: {meta['linhas_originais']:,} | Analisadas: {meta['linhas_analisadas']:,}\n"
        f"- Colunas: {meta['total_colunas']} | Com nulos: {resumo['colunas_com_nulos']} | "
        f"100% vazias: {resumo['colunas_100pct_nulas']} | Sensíveis LGPD: {resumo['colunas_sensiveis_lgpd']}\n"
        f"- Semânticas mapeadas: {', '.join(resumo['semanticas_encontradas']) or 'Nenhuma'}\n"
        f"- KPIs habilitados: {resumo['kpis_habilitados']} | Total de recomendações: {resumo['total_recomendacoes']}"
    )

    partes.append("\n## Colunas\n")
    partes.append(_tabela_markdown(
        [[c["Coluna"], c["Tipo_Inferred"], c["Semantica_IA"], f"{c['Pct_Nulos']:.1f}%", c["Caracteristica"]] for c in payload["colunas"]],
        ["Coluna", "Tipo", "Semântica", "% Nulos", "Característica"],
    ))

    partes.append("\n## Recomendações ETL\n")
    if payload["recomendacoes_etl"]:
        for r in sorted(payload["recomendacoes_etl"], key=lambda x: x.get("Prioridade", "")):
            partes.append(f"- **{r['Prioridade']}** [{r['Camada']}] `{r['Coluna']}` — {r['Acao']}")
    else:
        partes.append("Nenhuma recomendação gerada.")

    partes.append("\n## Dependências Funcionais\n")
    if payload["dependencias_funcionais"]:
        for d in payload["dependencias_funcionais"]:
            partes.append(f"- `{d['determinante']}` → `{d['dependente']}`: {d['descricao']}")
    else:
        partes.append("Nenhuma dependência funcional detectada.")

    partes.append("\n## Gap Analysis de KPIs\n")
    partes.append(_tabela_markdown(
        [[g["kpi_id"], g["kpi_nome"], g["status"], g["cobertura_pct"]] for g in payload["gap_analysis_kpis"]],
        ["KPI", "Nome", "Status", "Cobertura"],
    ))

    if payload.get("analise_temporal_series"):
        partes.append("\n## Análise Temporal (ADF / Ljung-Box)\n")
        for t in payload["analise_temporal_series"]:
            adf, lb = t["adf"], t["ljung_box"]
            estac = adf.get("estacionaria") if adf.get("aplicavel") else "N/A"
            autoc = lb.get("autocorrelacionada") if lb.get("aplicavel") else "N/A"
            partes.append(f"- `{t['coluna']}` (ref: `{t['coluna_temporal_referencia']}`) — estacionária: {estac} | autocorrelacionada: {autoc}")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(partes) + "\n")
    logger.info(f"✓ Markdown exportado: '{caminho}'")
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_reporting.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add src/data_profiler/reporting.py tests/test_reporting.py
git commit -m "feat: relatório Markdown legível para humanos"
```

---

## Task 10: `pipeline.py` — orquestração + análise temporal cross-coluna

**Files:**
- Create: `src/data_profiler/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `ingestion.carregar_arquivo`, `ingestion.carregar_todas_abas_excel`, `semantics.inferir_semantica`, `statistics.analisar_estatisticas`, `statistics.testar_estacionariedade_adf`, `statistics.testar_autocorrelacao_ljungbox`, `quality.detectar_dependencias_funcionais`, `quality.gerar_gap_analysis`, `quality.gerar_recomendacoes_etl`, `reporting.exportar_json`, `reporting.exportar_markdown`, `reporting.exportar_parquet`, `config.ANALISE_TEMPORAL_MAX_PONTOS`.
- Produces:
  - `analisar_temporal_series(df: pd.DataFrame, colunas_meta: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `class DataProfiler`:
    - `__init__(self, limite_amostra: int = 500_000)`
    - `processar_dataframe(self, df: pd.DataFrame, nome_tabela: str) -> Dict[str, Any]`
    - `processar_arquivo(self, caminho: str, aba_excel=0, processar_todas_abas=False, saida_base="profiler_output", tambem_parquet=False) -> List[Dict[str, Any]]`

- [ ] **Step 1: Escrever testes de integração cobrindo o payload completo e a análise temporal (com e sem coluna de data)**

```python
# tests/test_pipeline.py
from data_profiler.pipeline import DataProfiler, analisar_temporal_series


def test_processar_dataframe_retorna_payload_completo(df_rh_exemplo):
    profiler = DataProfiler()

    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    assert resultado["metadados_execucao"]["tabela"] == "TB_TESTE"
    assert len(resultado["colunas"]) == len(df_rh_exemplo.columns)
    assert "recomendacoes_etl" in resultado
    assert "dependencias_funcionais" in resultado
    assert "gap_analysis_kpis" in resultado
    assert "analise_temporal_series" in resultado


def test_processar_dataframe_detecta_lgpd_no_cpf(df_rh_exemplo):
    profiler = DataProfiler()
    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    col_cpf = next(c for c in resultado["colunas"] if c["Coluna"] == "cpf_colaborador")
    assert col_cpf["Dado_Sensivel_LGPD"] == "CPF"


def test_processar_dataframe_detecta_fd_cod_para_nome_departamento(df_rh_exemplo):
    profiler = DataProfiler()
    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    determinantes = {d["determinante"] for d in resultado["dependencias_funcionais"]}
    assert "cod_departamento" in determinantes


def test_analise_temporal_ausente_sem_coluna_de_data():
    import pandas as pd
    df = pd.DataFrame({"valor": range(50)})
    colunas_meta = [{"Coluna": "valor", "Semantica_IA": "Genérico / Não mapeado", "Tipo_Inferred": "Número Inteiro", "Pct_Nulos": 0.0}]

    resultado = analisar_temporal_series(df, colunas_meta)

    assert resultado == []


def test_analise_temporal_roda_com_coluna_de_data(df_rh_exemplo):
    profiler = DataProfiler()
    resultado = profiler.processar_dataframe(df_rh_exemplo, "TB_TESTE")

    # dt_admissao é datetime e o nome bate em "Data / Calendário" -> deve ativar
    assert len(resultado["analise_temporal_series"]) > 0
    entrada = resultado["analise_temporal_series"][0]
    assert entrada["coluna_temporal_referencia"] == "dt_admissao"


def test_dataframe_vazio_levanta_value_error():
    import pandas as pd
    import pytest

    profiler = DataProfiler()
    with pytest.raises(ValueError):
        profiler.processar_dataframe(pd.DataFrame(), "TB_VAZIA")
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_profiler.pipeline'`

- [ ] **Step 3: Escrever `pipeline.py`**

```python
"""Orquestração do profiling: liga ingestion, semantics, statistics, quality e reporting."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union

import pandas as pd
from loguru import logger
from tqdm import tqdm

from . import config, ingestion, quality, reporting, semantics, statistics


def analisar_temporal_series(
    df: pd.DataFrame, colunas_meta: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    candidatas_data = [
        m for m in colunas_meta
        if m.get("Semantica_IA") == "Data / Calendário" and m.get("Tipo_Inferred") == "Data / Hora"
    ]
    if not candidatas_data:
        return []

    col_referencia = min(candidatas_data, key=lambda m: m["Pct_Nulos"])["Coluna"]
    df_ordenado = df.sort_values(by=col_referencia).reset_index(drop=True)

    colunas_numericas = [
        m["Coluna"] for m in colunas_meta
        if "Número" in m.get("Tipo_Inferred", "") and m["Coluna"] != col_referencia
    ]

    resultados = []
    for coluna in colunas_numericas:
        serie = df_ordenado[coluna].dropna()
        if len(serie) > config.ANALISE_TEMPORAL_MAX_PONTOS:
            serie = serie.iloc[: config.ANALISE_TEMPORAL_MAX_PONTOS]
        adf = statistics.testar_estacionariedade_adf(serie)
        ljung_box = statistics.testar_autocorrelacao_ljungbox(serie)
        if not adf.get("aplicavel") and not ljung_box.get("aplicavel"):
            continue
        resultados.append({
            "coluna": coluna,
            "coluna_temporal_referencia": col_referencia,
            "adf": adf,
            "ljung_box": ljung_box,
        })
    return resultados


class DataProfiler:
    def __init__(self, limite_amostra: int = 500_000):
        self.limite_amostra = limite_amostra

    def processar_dataframe(self, df: pd.DataFrame, nome_tabela: str) -> Dict[str, Any]:
        if df is None or df.empty:
            raise ValueError(f"DataFrame '{nome_tabela}' está vazio ou inválido.")

        total_linhas = len(df)
        df_alvo = df.sample(n=self.limite_amostra, random_state=42) if total_linhas > self.limite_amostra else df
        linhas_analisadas = len(df_alvo)

        logger.info(f"Iniciando profiling: '{nome_tabela}' | {linhas_analisadas:,}/{total_linhas:,} linhas | {len(df_alvo.columns)} colunas")

        lista_colunas: List[Dict[str, Any]] = []
        recomendacoes: List[Dict[str, Any]] = []
        semanticas_presentes: Set[str] = set()

        for coluna in tqdm(df_alvo.columns, desc=f"Profilando '{nome_tabela}'", unit="col"):
            serie = df_alvo[coluna]
            stats = statistics.analisar_estatisticas(serie, linhas_analisadas)
            padrao_estruturado = stats["flags"]["detected_pattern"]
            sem = semantics.inferir_semantica(str(coluna), detectado_padrao=padrao_estruturado)

            if sem["semantica"] != "Genérico / Não mapeado":
                semanticas_presentes.add(sem["semantica"])

            registro = {
                "Tabela_Origem": str(nome_tabela),
                "Coluna": str(coluna),
                "Tipo_Inferred": stats["tipo_dados"],
                "Semantica_IA": sem["semantica"],
                "Semantica_Score": sem["confianca_score"],
                "Semantica_Origem": sem["origem"],
                "Qtd_Unicos": stats["valores_unicos"],
                "Ratio_Unicidade": stats["ratio_unicidade"],
                "Qtd_Nulos": stats["nulos_qtd"],
                "Pct_Nulos": stats["nulos_pct"],
                "Caracteristica": stats["caracteristica"],
                "Dado_Sensivel_LGPD": padrao_estruturado,
                "Amostra_Valores": ", ".join(stats["amostra_representativa"]),
                "Alertas": {
                    "data_como_texto": stats["flags"]["is_date_as_text"],
                    "mistura_tipos": stats["flags"]["mistura_tipos"],
                },
                "Stats_Extra": stats["estatisticas_adicionais"],
            }
            lista_colunas.append(registro)
            recomendacoes.extend(
                quality.gerar_recomendacoes_etl(nome_tabela, str(coluna), stats, padrao_estruturado, linhas_analisadas)
            )

        logger.info("Analisando dependências funcionais...")
        dependencias = quality.detectar_dependencias_funcionais(df_alvo, lista_colunas)

        logger.info("Gerando gap analysis de KPIs...")
        gaps = quality.gerar_gap_analysis(semanticas_presentes)

        logger.info("Rodando análise temporal cross-coluna (se aplicável)...")
        analise_temporal = analisar_temporal_series(df_alvo, lista_colunas)

        total_colunas = len(lista_colunas)
        colunas_com_nulos = sum(1 for c in lista_colunas if c["Pct_Nulos"] > 0)
        colunas_sensiveis = sum(1 for c in lista_colunas if c["Dado_Sensivel_LGPD"] != "Nenhum")
        colunas_vazias = sum(1 for c in lista_colunas if "Vazia" in c["Caracteristica"])
        kpis_habilitados = sum(1 for g in gaps if "✅" in g["status"])

        if not recomendacoes:
            recomendacoes.append({
                "Tabela": nome_tabela, "Coluna": "N/A", "Prioridade": "🟢 INFO", "Camada": "N/A",
                "Acao": "Nenhuma anomalia crítica estrutural encontrada.", "Linhas_Afetadas": 0, "Pct_Impacto": "0%",
            })

        return {
            "metadados_execucao": {
                "tabela": nome_tabela,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "versao_profiler": "2.0-Fase1",
                "linhas_originais": total_linhas,
                "linhas_analisadas": linhas_analisadas,
                "total_colunas": total_colunas,
                "resumo_qualidade": {
                    "colunas_com_nulos": colunas_com_nulos,
                    "colunas_100pct_nulas": colunas_vazias,
                    "colunas_sensiveis_lgpd": colunas_sensiveis,
                    "semanticas_mapeadas": len(semanticas_presentes),
                    "semanticas_encontradas": sorted(semanticas_presentes),
                    "kpis_habilitados": kpis_habilitados,
                    "total_recomendacoes": len(recomendacoes),
                },
            },
            "colunas": lista_colunas,
            "recomendacoes_etl": recomendacoes,
            "dependencias_funcionais": dependencias,
            "gap_analysis_kpis": gaps,
            "analise_temporal_series": analise_temporal,
        }

    def processar_arquivo(
        self,
        caminho: str,
        aba_excel: Optional[Union[str, int]] = 0,
        processar_todas_abas: bool = False,
        saida_base: str = "profiler_output",
        tambem_parquet: bool = False,
    ) -> List[Dict[str, Any]]:
        import os
        extensao = os.path.splitext(caminho)[1].lower()

        if processar_todas_abas and extensao in (".xlsx", ".xls", ".xlsb"):
            pares = ingestion.carregar_todas_abas_excel(caminho)
        else:
            pares = [ingestion.carregar_arquivo(caminho, aba_excel=aba_excel)]

        resultados = []
        for df, nome_tabela in pares:
            payload = self.processar_dataframe(df, nome_tabela)
            nome_safe = reporting.nome_seguro(nome_tabela)
            reporting.exportar_json(payload, f"{saida_base}_{nome_safe}.json")
            reporting.exportar_markdown(payload, f"{saida_base}_{nome_safe}.md")
            if tambem_parquet:
                reporting.exportar_parquet(payload, saida_base)
            resultados.append(payload)
        return resultados
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Rodar a suíte inteira até aqui**

Run: `pytest -v`
Expected: PASS (todos os testes de todas as tasks anteriores)

- [ ] **Step 6: Commit**

```bash
git add src/data_profiler/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline.DataProfiler orquestrando ingestão, stats, qualidade e análise temporal"
```

---

## Task 11: `cli.py` — comandos `perfilar` e `lote`

**Files:**
- Create: `src/data_profiler/cli.py`
- Modify: `src/data_profiler/__init__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pipeline.DataProfiler`, `ingestion.FileFormatError`.
- Produces: `app: typer.Typer`, `setup_logging(log_file: Optional[str] = None) -> None`, comandos `perfilar` e `lote`.

- [ ] **Step 1: Escrever testes de CLI usando `typer.testing.CliRunner`**

```python
# tests/test_cli.py
import pandas as pd
from typer.testing import CliRunner

from data_profiler.cli import app

runner = CliRunner()


def test_perfilar_gera_json_e_markdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho_csv = tmp_path / "dados.csv"
    pd.DataFrame({"id": range(30), "valor": range(30)}).to_csv(caminho_csv, index=False)

    resultado = runner.invoke(app, ["perfilar", str(caminho_csv), "--saida-base", "saida"])

    assert resultado.exit_code == 0
    assert (tmp_path / "saida_dados.json").exists()
    assert (tmp_path / "saida_dados.md").exists()


def test_perfilar_arquivo_inexistente_retorna_codigo_erro(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    resultado = runner.invoke(app, ["perfilar", "nao_existe.csv"])

    assert resultado.exit_code != 0


def test_lote_processa_varios_arquivos_mesmo_com_um_falhando(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pd.DataFrame({"a": range(10)}).to_csv(tmp_path / "bom.csv", index=False)
    (tmp_path / "vazio.csv").write_text("", encoding="utf-8")

    resultado = runner.invoke(app, ["lote", str(tmp_path / "bom.csv"), str(tmp_path / "vazio.csv"), "--saida-base", "lote_saida"])

    assert (tmp_path / "lote_saida_bom.json").exists()
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_profiler.cli'`

- [ ] **Step 3: Escrever `cli.py`**

```python
"""CLI do data-profiler: `perfilar` (um arquivo) e `lote` (vários arquivos)."""
import sys
from typing import List, Optional

import typer
from loguru import logger

from .ingestion import FileFormatError
from .pipeline import DataProfiler

app = typer.Typer(help="Profiler exploratório de dados CSV/XLSX/XLS/XLSB.")


def setup_logging(log_file: Optional[str] = None) -> None:
    logger.remove()
    logger.add(lambda msg: print(msg, end="", flush=True), format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}", level="INFO", colorize=True)
    if log_file:
        logger.add(log_file, format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}", level="DEBUG", rotation="10 MB", encoding="utf-8")


@app.command()
def perfilar(
    caminho: str,
    todas_abas: bool = typer.Option(False, "--todas-abas"),
    aba: str = typer.Option("0", "--aba"),
    saida_base: str = typer.Option("profiler_output", "--saida-base"),
    tambem_parquet: bool = typer.Option(False, "--tambem-parquet"),
) -> None:
    setup_logging()
    aba_valor = int(aba) if aba.isdigit() else aba
    profiler = DataProfiler()
    try:
        profiler.processar_arquivo(
            caminho, aba_excel=aba_valor, processar_todas_abas=todas_abas,
            saida_base=saida_base, tambem_parquet=tambem_parquet,
        )
    except (FileNotFoundError, FileFormatError, ValueError) as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def lote(
    caminhos: List[str],
    saida_base: str = typer.Option("profiler_output", "--saida-base"),
    tambem_parquet: bool = typer.Option(False, "--tambem-parquet"),
) -> None:
    setup_logging()
    profiler = DataProfiler()
    falhas = 0
    for caminho in caminhos:
        try:
            profiler.processar_arquivo(caminho, saida_base=saida_base, tambem_parquet=tambem_parquet)
        except (FileNotFoundError, FileFormatError, ValueError) as e:
            falhas += 1
            typer.secho(f"Erro ao processar '{caminho}': {e}", fg=typer.colors.RED, err=True)
    if falhas == len(caminhos) and caminhos:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Expor `DataProfiler` em `__init__.py`**

```python
# src/data_profiler/__init__.py
from .pipeline import DataProfiler

__all__ = ["DataProfiler"]
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (3 testes)

- [ ] **Step 6: Commit**

```bash
git add src/data_profiler/cli.py src/data_profiler/__init__.py tests/test_cli.py
git commit -m "feat: CLI com comandos perfilar e lote"
```

---

## Task 12: Migração — remover arquivos legados

**Files:**
- Delete: `Profiller.py`, `statistical_profiler.py`, `semantic_engine.py`, `profiling_orchestrator.py`, `batch_profiler.py`
- Delete: `requirements.txt` (substituído por `pyproject.toml`)
- Modify: `.gitignore` (remover regras que não se aplicam mais ao layout `src/`, se houver)

**Interfaces:** nenhuma — task de limpeza, sem código novo.

- [ ] **Step 1: Confirmar que a suíte inteira passa antes de remover qualquer coisa**

Run: `pytest -v`
Expected: PASS (todos os testes de todas as tasks)

- [ ] **Step 2: Remover os arquivos legados**

```bash
git rm Profiller.py statistical_profiler.py semantic_engine.py profiling_orchestrator.py batch_profiler.py requirements.txt
```

- [ ] **Step 3: Rodar a suíte de novo para garantir que nada dependia dos arquivos removidos**

Run: `pytest -v`
Expected: PASS (nenhuma mudança de resultado — o pacote novo já era autossuficiente)

- [ ] **Step 4: Testar a CLI manualmente contra um arquivo real**

```bash
python -c "
import pandas as pd
pd.DataFrame({'id': range(100), 'nome': [f'Item {i}' for i in range(100)], 'valor': [i * 1.5 for i in range(100)]}).to_csv('/tmp/smoke_test.csv', index=False)
"
data-profiler perfilar /tmp/smoke_test.csv --saida-base /tmp/smoke_output
cat /tmp/smoke_output_smoke_test.md
```

Expected: comando roda sem erro, `/tmp/smoke_output_smoke_test.json` e `.md` são criados, o `.md` mostra a coluna `id` como "Chave Primária Potencial".

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove pipelines legados (statistical_profiler, semantic_engine, profiling_orchestrator, batch_profiler, Profiller.py)"
```

---

## Task 13: Push final e verificação

**Files:** nenhum arquivo novo — task de fechamento.

- [ ] **Step 1: Rodar a suíte completa com cobertura**

Run: `pytest --cov=data_profiler --cov-report=term-missing`
Expected: todos os testes passam; revisar manualmente qualquer módulo com cobertura muito baixa antes de prosseguir (não é bloqueante, é checagem de sanidade).

- [ ] **Step 2: Push para o repositório remoto**

```bash
git push origin main
```

- [ ] **Step 3: Confirmar no GitHub que o push chegou**

```bash
gh repo view Caio-Analytics/Data-Profiler-Engine --json pushedAt
```

Expected: `pushedAt` reflete o momento atual.

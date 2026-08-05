# 🔭 DataScope

**Profiler exploratório de dados para CSV, XLSX, XLS e XLSB** — infere semântica de colunas, roda testes estatísticos, detecta dependências funcionais e dados sensíveis (LGPD), e gera recomendações de ETL prontas pra usar. Saída simultânea em dois formatos: **JSON** (pra IA/código) e **Markdown** (pra leitura humana).

---

## ✨ O que ele faz

| Análise | Descrição |
|---|---|
| 🧠 **Inferência semântica** | Reconhece que `dt_admissao`, `cod_depto` e `salario_bruto` são "Data", "Chave Identificadora" e "Valor Financeiro" — mesmo com erro de digitação, via fuzzy matching |
| 📊 **Estatística descritiva** | Min/max/média/mediana/desvio, outliers (IQR), distribuição de frequência, tipo de dado real |
| 🔬 **Testes de hipótese** | Shapiro-Wilk (normalidade), qui-quadrado (uniformidade), IC 95%, distribuição provável, ADF (estacionariedade), Ljung-Box (autocorrelação) |
| 🔗 **Dependências funcionais** | Detecta relações tipo `cod_depto → nome_depto` entre colunas |
| 🔒 **LGPD** | Identifica CPF, CNPJ, e-mail, telefone, CEP (mesmo armazenados sem formatação) e **mascara automaticamente** nas amostras exportadas |
| ✅ **Recomendações ETL** | Lista priorizada de ações (🔴 alta / 🟡 média / 🟢 baixa) por coluna, camada Bronze/Silver |
| 📅 **Análise temporal** | ADF + Ljung-Box em colunas numéricas, ordenadas por uma coluna de data (CSV ou Excel) |

---

## 🚀 Instalação

### Com venv (recomendado, máquina pessoal)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Sem venv (máquina corporativa restrita — sem admin, sem venv)

Se sua política de TI bloqueia `venv` mas permite `pip`, instale tudo **só no seu usuário** (`--user`), sem tocar no Python global e sem precisar de admin:

```bash
pip install --user --upgrade pip
pip install --user -e ".[dev]"
```

O comando `datascope` vai parar em `~/.local/bin` — se o terminal não reconhecer o comando depois de instalar, adicione essa pasta ao PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

Se o `pip` recusar instalar com um erro tipo `externally-managed-environment` (comum em Python de sistema em distros mais novas), isso **não é permissão de admin** — é só uma trava de segurança do próprio `pip`. Contorna com:

```bash
pip install --user --break-system-packages -e ".[dev]"
```

**⚠️ Sem isolamento:** instalar `--user` (em vez de venv) coloca as dependências do DataScope no mesmo lugar que as de qualquer outro projeto Python que você rodar nessa máquina com `--user`. Se dois projetos precisarem de versões diferentes da mesma biblioteca, um vai sobrescrever o outro. Veja a seção de limpeza abaixo pra remover as dependências do DataScope quando for usar outro projeto.

Requer Python ≥ 3.11.

---

## 🖥️ Como usar

### Perfilar um único arquivo

```bash
datascope perfilar caminho/do/arquivo.csv
```

Gera dois arquivos no diretório atual:
- `profiler_output_arquivo.json` — estrutura completa, pra colar num prompt de IA ou consumir via código
- `profiler_output_arquivo.md` — relatório legível, com tabelas e recomendações

**Opções:**

```bash
datascope perfilar arquivo.xlsx --todas-abas              # processa todas as abas do Excel
datascope perfilar arquivo.xlsx --aba 1                   # processa só a aba de índice 1
datascope perfilar arquivo.csv --saida-base relatorios/q1 # prefixo customizado de saída
datascope perfilar arquivo.csv --tambem-parquet           # exporta também em Parquet (pipelines de BI)
```

### Perfilar vários arquivos de uma vez

```bash
datascope lote dados/*.csv dados/*.xlsx
```

Se um arquivo falhar (corrompido, formato inválido), o `lote` **continua processando os demais** — não aborta o lote inteiro.

### Ajuda

```bash
datascope --help
datascope perfilar --help
datascope lote --help
```

---

## 📁 Estrutura do projeto

```
DataScope/
├── pyproject.toml           ← comandos de instalação rodam AQUI (raiz do projeto)
├── src/datascope/
│   ├── config.py             taxonomias semânticas + todos os thresholds (fonte única)
│   ├── ingestion.py          carrega CSV/XLSX/XLS/XLSB, detecta encoding automaticamente
│   ├── semantics.py          infere semântica da coluna pelo nome (fuzzy matching)
│   ├── statistics.py         estatísticas descritivas + testes de hipótese por coluna
│   ├── quality.py            dependências funcionais, gap analysis de KPI, recomendações ETL
│   ├── reporting.py          exporta JSON (IA), Markdown (humano) e Parquet (opcional)
│   ├── pipeline.py           `DataProfiler` — orquestra tudo acima
│   └── cli.py                comandos de terminal `perfilar` e `lote`
└── tests/                    suíte pytest (um arquivo por módulo)
```

**Fluxo interno:** `cli.py` → `pipeline.DataProfiler` → carrega o arquivo (`ingestion`) → analisa cada coluna (`statistics` + `semantics`) → cruza colunas (`quality`) → exporta (`reporting`).

---

## 🧪 Rodando os testes

```bash
pytest -v
```

---

## 🔄 Reinstalação do zero

**Com venv:**

```bash
rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]"
```

**Sem venv (`--user`):**

```bash
pip uninstall -y datascope pandas numpy pyarrow openpyxl xlrd pyxlsb charset-normalizer rapidfuzz unidecode scipy statsmodels loguru typer tqdm pytest pytest-cov pandas-stubs && pip install --user -e ".[dev]"
```

### 🧹 Limpar tudo (liberar a máquina pra outro projeto)

No modo sem venv, as dependências ficam instaladas globalmente pro seu usuário. Pra remover tudo que o DataScope instalou e não deixar resíduo interferindo em outro projeto:

```bash
pip uninstall -y datascope pandas numpy pyarrow openpyxl xlrd pyxlsb charset-normalizer rapidfuzz unidecode scipy statsmodels loguru typer tqdm pytest pytest-cov pandas-stubs
```

Isso remove as dependências diretas (as mesmas do `pyproject.toml`). Algumas dependências transitivas pequenas e muito comuns (`six`, `packaging`, `python-dateutil` etc.) podem continuar instaladas — são inofensivas e geralmente usadas por outras bibliotecas Python também, então não vale a pena arriscar removê-las às cegas.

---

## 🧩 Extensões do VS Code

| Extensão | ID | Por quê |
|---|---|---|
| **Python** | `ms-python.python` | Suporte base a Python — execução, debug, ambientes |
| **Pylance** | `ms-python.vscode-pylance` | Já vem com a Python, é o motor de análise de tipos |
| **Ruff** | `charliermarsh.ruff` | Lint + formatação rápidos; substitui flake8/black com uma extensão só |
| **Even Better TOML** | `tamasfe.even-better-toml` | Syntax highlight/validação pro `pyproject.toml` |
| **Data Wrangler** | `ms-toolsai.datawrangler` | Visualiza e explora DataFrames pandas direto no VS Code — útil pra inspecionar o `.json`/`.parquet` que o DataScope gera |
| **Rainbow CSV** | `mechatroner.rainbow-csv` | Colore colunas de CSV, essencial pra olhar os arquivos de entrada rapidamente |
| **Excel Viewer** | `GrapeCity.gc-excelviewer` | Abre `.xlsx`/`.xls` direto no editor, sem precisar do Excel |
| **Jupyter** | `ms-toolsai.jupyter` | Pra explorar interativamente os módulos (`import datascope`) num notebook antes de rodar via CLI |

**Sobre os erros do Pylance:** os dois problemas reais que você reportou já foram corrigidos no código (tipo `Literal` errado em `ingestion.py`) e adicionamos `pandas-stubs` como dependência de dev — os stubs de tipo que vêm junto do próprio pandas são incompletos e costumam gerar bastante ruído falso-positivo no Pylance; o `pandas-stubs` é a definição de tipos oficial da comunidade, bem mais precisa. Depois de rodar `pip install -e ".[dev]"` de novo (ou `--user`, se for o seu caso) e reiniciar o VS Code (`Ctrl+Shift+P` → "Developer: Reload Window"), a maioria dos falsos positivos deve sumir. Se ainda aparecer bastante coisa, me manda a lista completa dos 9 problemas que eu olho os que sobraram.

---

## 🗺️ Roadmap

- **Fase 2** (planejada): correlação numérica entre colunas, detecção de linhas duplicadas, detecção de PII em texto livre, relatório visual (Excel/HTML)
- **Fase 3** (planejada): cruzamento de chaves entre múltiplos arquivos — detectar automaticamente que a coluna X do Arquivo A se relaciona com a coluna Y do Arquivo B

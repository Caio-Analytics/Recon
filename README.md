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

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

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

```bash
rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]"
```

---

## 🗺️ Roadmap

- **Fase 2** (planejada): correlação numérica entre colunas, detecção de linhas duplicadas, detecção de PII em texto livre, relatório visual (Excel/HTML)
- **Fase 3** (planejada): cruzamento de chaves entre múltiplos arquivos — detectar automaticamente que a coluna X do Arquivo A se relaciona com a coluna Y do Arquivo B

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

**Caminho relativo ou absoluto — os dois funcionam:**

```bash
datascope perfilar dados/vendas.csv               # relativo: a partir da pasta onde você rodou o comando
datascope perfilar /home/usuario/dados/vendas.csv  # absoluto: funciona de qualquer diretório
```

### Ajuda

```bash
datascope --help
datascope perfilar --help
datascope lote --help
```

---

## 🔬 Como a análise funciona

Visão técnica rápida do que roda por trás de cada item da tabela acima — não é exaustivo, mas dá pra entender o critério por trás de cada número/rótulo que sai no relatório.

- **Inferência semântica:** primeiro tenta match exato por token contra um dicionário PT/EN curado (`id`, `cpf`, `dt_admissao` → categorias fortes). Se não bate, cai pro fuzzy matching (Jaro-Winkler via `rapidfuzz`) contra as palavras-chave de cada categoria, com threshold mais rigoroso pra nomes curtos (`uf`, `cep`) pra evitar falso positivo. Padrão detectado no **conteúdo** da coluna (CPF, e-mail etc.) tem prioridade sobre o nome — uma coluna chamada `campo1` que só tem CPF ainda é classificada como identificador.
- **Testes de hipótese:** cada teste só roda com amostra mínima pra não reportar conclusão estatística sem sentido — Shapiro-Wilk exige n≥20 (amostra limitada a 5.000 pra não ficar hipersensível a desvios irrelevantes), qui-quadrado exige frequência esperada ≥5 por categoria, ADF e Ljung-Box exigem n≥30 **e** uma coluna de data na tabela pra estabelecer a ordem temporal — sem isso a análise temporal simplesmente não aparece no relatório, em vez de rodar numa ordem aleatória.
- **Dependências funcionais:** agrupa cada par de colunas com cardinalidade razoável (<500 valores únicos) e verifica se um valor de A sempre implica o mesmo valor de B (`cod_depto → nome_depto`). Colunas quase-únicas (≥98% de valores distintos, tipo um ID) são excluídas do lado "determinante" — senão qualquer ID "determina" trivialmente todas as outras colunas, o que não é uma dependência útil.
- **Detecção de LGPD:** regex pros formatos com pontuação (CPF, CNPJ, CEP, e-mail, telefone, UUID) **mais** uma heurística de comprimento de dígito pra número guardado sem formatação (10-11 dígitos = CPF, 13-14 = CNPJ — cobre o caso comum de coluna virar `int64` e perder a máscara). Os valores de amostra no relatório saem sempre mascarados quando um padrão é detectado.
- **Amostragem:** analisa até 500 mil linhas por padrão (configurável). Os testes estatísticos mais pesados usam subamostras determinísticas (seed fixa) — o mesmo arquivo sempre gera o mesmo resultado, mesmo rodando várias vezes.

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

## 🔄 Reinstalação do zero (com venv)

```bash
rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]"
```

---

## 🏢 Rotina completa pra máquina corporativa (sem venv, sem admin)

Sequência pra ver o que já está instalado, limpar, clonar de novo do zero e reinstalar — útil pra testar numa máquina restrita sem deixar resíduo pra outros projetos.

**1. Ver tudo que está instalado no seu usuário:**

```bash
pip list --user
```

**2. Limpar as dependências do DataScope** (remove as diretas do `pyproject.toml`; algumas transitivas pequenas e comuns como `six`/`packaging` podem continuar — são inofensivas e usadas por outras libs também, não vale arriscar remover às cegas):

```bash
pip uninstall -y datascope pandas numpy pyarrow openpyxl xlrd pyxlsb charset-normalizer rapidfuzz unidecode scipy statsmodels loguru typer tqdm pytest pytest-cov pandas-stubs
```

**3. Apagar a pasta local e clonar de novo** (rode a partir de fora da pasta `DataScope`, senão o shell perde a referência do diretório):

```bash
cd ~/Documentos/Programacao && rm -rf DataScope && git clone https://github.com/Caio-Analytics/DataScope.git && cd DataScope
```

**4. Instalar e testar:**

```bash
pip install --user -e ".[dev]" && pytest -v
```

---

## 🗺️ Roadmap

- **Fase 2** (planejada): correlação numérica entre colunas, detecção de linhas duplicadas, detecção de PII em texto livre, relatório visual (Excel/HTML)
- **Fase 3** (planejada): cruzamento de chaves entre múltiplos arquivos — detectar automaticamente que a coluna X do Arquivo A se relaciona com a coluna Y do Arquivo B

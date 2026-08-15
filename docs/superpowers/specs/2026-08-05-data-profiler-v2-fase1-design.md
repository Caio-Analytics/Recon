# Data Profiler v2 — Fase 1: Estabilização, Consolidação e Upgrade

> ⚠️ **DOCUMENTO HISTÓRICO — SUPERADO.**
> Este spec descreve a Fase 1 (v2.0), concluída. A arquitetura, os
> módulos e as decisões descritas aqui **não refletem mais o código**.
> Para o estado atual, veja `docs/superpowers/specs/2026-08-15-recon-v3-design.md`.
> Mantido como registro do que foi decidido e por quê.


Data: 2026-08-05
Status: Aprovado para planejamento de implementação

## Contexto

O projeto hoje é composto por 5 scripts soltos na raiz, resultado de duas
gerações de desenvolvimento que nunca convergiram:

- **Pipeline legado** (`statistical_profiler.py` + `semantic_engine.py` +
  `profiling_orchestrator.py`, chamado em lote por `batch_profiler.py`).
- **Pipeline novo** (`Profiller.py`, classe `SASDataProfiler`, "v6/v7
  Suprema"), mais completo (FDs, gap analysis, XLS/XLSB, LGPD), mas **quebrado**:
  importa `scipy`, `statsmodels`, `unidecode`, `pyxlsb`, `xlrd` e `loguru`,
  nenhum declarado em `requirements.txt` nem instalado — o módulo não
  executa. Além disso, o docstring anuncia testes estatísticos (Shapiro-Wilk,
  qui-quadrado, IC 95%, ADF, Ljung-Box) que nunca foram implementados —
  `scipy.stats`, `adfuller`, `acf`, `acorr_ljungbox` e `dateutil.parser` são
  importados e nunca chamados.

Auditoria também encontrou:

- Bug de serialização: colunas numéricas com `n_válidos < 3` produzem
  `skew`/`kurt` = `NaN`, e `json.dump(..., default=str)` não intercepta
  `NaN` (não é tratado pelo `default`) — o `.json` final contém o token cru
  `NaN`, inválido pela RFC 8259, quebrando parsers estritos (`JSON.parse`,
  a maioria dos conectores JSON de ferramentas de BI).
- Detecção de dependência funcional sem guarda contra colunas quase-chave:
  uma coluna com unicidade ≈100% "determina" trivialmente qualquer outra,
  poluindo a lista de FDs com resultados óbvios.
- `groupby()` usado na detecção de FD descarta silenciosamente linhas nulas
  no agrupador (comportamento padrão do pandas), superestimando a força da
  dependência encontrada.
- Taxonomias semânticas (`CATEGORIAS_FORTES`/`CATEGORIAS_FUZZY`) e thresholds
  divergiram entre os dois pipelines — correções feitas num lado não
  propagam para o outro.
- Dependências desatualizadas: `numpy==1.24.4` (atual: 2.4.6),
  `pandas==2.1.4` (atual: 3.0.5), `pyarrow==16.1.0` (atual: 25.0.0),
  `chardet==5.2.0` (atual: 7.4.3), `pytz==2024.1` (dados de fuso horário
  desatualizados).

Decisão do usuário: consolidar tudo num único pacote Python instalável,
remover os arquivos legados, atualizar para as versões mais recentes das
libs (incluindo pandas 3.0.x — o projeto não está mais preso a versões
específicas de um ambiente legado), e implementar de fato os testes
estatísticos hoje só prometidos no docstring. Cruzamento de dados entre
múltiplos arquivos (detecção de chaves de junção entre File A/B/C) fica
fora de escopo — é a Fase 3, desenhada separadamente no futuro.

## Objetivo da Fase 1

Chegar a um único codebase correto, testado e moderno — sem adicionar
capacidades analíticas novas além das que já estavam prometidas
(testes estatísticos) e do relatório humano. Correlação numérica,
detecção de linhas duplicadas, PII em texto livre, relatório
Excel/HTML visual completo ficam para a Fase 2.

## Arquitetura

Pacote instalável (`pip install -e .`), com CLI baseada em `typer`:

```
data_profiler/
├── pyproject.toml
├── src/data_profiler/
│   ├── __init__.py          # expõe DataProfiler (API pública)
│   ├── config.py            # taxonomias semânticas + thresholds (fonte única)
│   ├── ingestion.py         # carregar_arquivo / carregar_todas_abas: csv/xlsx/xls/xlsb + encoding
│   ├── semantics.py         # inferir_semantica: fuzzy (rapidfuzz) + match por token
│   ├── statistics.py        # analisar_estatisticas: descritivas, outliers, testes de hipótese
│   ├── quality.py           # detectar_dependencias_funcionais, gerar_gap_analysis, gerar_recomendacoes_etl
│   ├── reporting.py         # exportar_json, exportar_markdown, exportar_parquet (saneamento NaN/Inf)
│   ├── pipeline.py          # DataProfiler: orquestra os módulos acima
│   └── cli.py               # comandos `perfilar` e `lote`
└── tests/
    ├── test_ingestion.py
    ├── test_semantics.py
    ├── test_statistics.py
    ├── test_quality.py
    └── test_pipeline.py      # testes de integração ponta-a-ponta
```

Convenção de nomes: **módulos e arquivos em inglês técnico** (padrão de
pacote Python); **funções, campos de dado e chaves de saída em português**,
seguindo a convenção já usada no código existente (`analisar_estatisticas`,
`detectar_dependencias_funcionais`, `Recomendacoes_ETL`, etc.).

Cada módulo é um conjunto de funções puras (entrada de dados → saída de
dados), sem estado global nem side-effects no import — diferente do
`Profiller.py` atual, que chama `logger.remove()`/`logger.add()` assim que
o módulo é importado. Logging passa a ser inicializado explicitamente por
`setup_logging()`, chamada pelo `cli.py`.

### Fluxo de dados

`cli.py` → `pipeline.DataProfiler.processar_arquivo()` →
1. `ingestion` carrega o DataFrame (detecção de encoding/separador para
   CSV; engine correto por extensão para XLSX/XLS/XLSB).
2. Para cada coluna: `statistics.analisar_estatisticas()` roda descritivas,
   outliers IQR, detecção de mistura de tipos, padrão estruturado (CPF,
   CNPJ, etc.) e os testes de hipótese (ver seção própria); em paralelo,
   `semantics.inferir_semantica()` infere a categoria a partir do nome da
   coluna e do `detected_pattern` retornado por statistics.
3. `quality` roda sobre o conjunto de colunas já processadas: dependências
   funcionais, gap analysis de KPI, recomendações ETL.
4. Se houver coluna semântica "Data / Calendário" válida, roda a análise
   temporal cross-coluna (ADF + Ljung-Box) — ver seção própria.
5. `reporting` serializa o payload final em JSON **e** Markdown
   simultaneamente (e opcionalmente Parquet).

## Dependências (requirements / pyproject)

| Lib | Papel | Versão alvo | Observação |
|---|---|---|---|
| pandas | core | 3.0.5 | sem pin de compatibilidade com ambiente legado |
| numpy | core | 2.4.6 | |
| pyarrow | export Parquet, backend string | 25.0.0 | |
| openpyxl | leitura XLSX | 3.1.5 | já atual |
| xlrd | leitura XLS legado | 2.0.2 | |
| pyxlsb | leitura XLSB | 1.0.10 | |
| charset-normalizer | detecção de encoding | 3.4.x | substitui `chardet` |
| rapidfuzz | fuzzy matching semântico | 3.x | substitui `jellyfish` (mesma função Jaro-Winkler, backend C++) |
| unidecode | normalização de texto | 1.4.0 | |
| python-dateutil | parsing de data | 2.9.0.post0 | agora efetivamente usado (análise temporal) |
| scipy | testes estatísticos | 1.17.1 | agora efetivamente usado |
| statsmodels | ADF, Ljung-Box | 0.14.6 | agora efetivamente usado |
| loguru | logging estruturado | 0.7.3 | inicializado sob demanda, não no import |
| typer | CLI | 0.15.x | |
| tqdm | barra de progresso | 4.70.0 | |

`et-xmlfile`, `six`, `pytz`, `tzdata` saem da lista fixa — são transitivas
de outras libs, não é necessário pinar versão do que não é importado
diretamente.

A troca `chardet`→`charset-normalizer` e `jellyfish`→`rapidfuzz` preserva a
interface das funções que os usam (`_detectar_encoding`,
`inferir_semantica`); um conjunto de testes de regressão valida que as
decisões (encoding detectado, categoria semântica escolhida) permanecem
equivalentes às de hoje antes de trocar de vez.

## Novas capacidades estatísticas (testes de hipótese)

Cada teste tem guarda de sanidade contra amostras pequenas/inadequadas —
sem isso, o número existe mas não significa nada:

- **Shapiro-Wilk (normalidade)**: só roda se `n_válidos >= 20`; amostra
  limitada a 5.000 pontos (acima disso o teste rejeita normalidade por
  desvios irrelevantes). Retorna `estatistica`, `p_valor`,
  `normal_provavel` (`p_valor > 0.05`).
- **Qui-quadrado (uniformidade)**: só roda em colunas categóricas com
  frequência esperada por categoria ≥ 5 e até 50 categorias distintas;
  caso contrário retorna `{"aplicavel": false, "motivo": "..."}`.
- **Intervalo de confiança 95% da média** (distribuição t): qualquer
  numérica com `n_válidos >= 2`.
- **Detecção de distribuição provável**: ajusta normal / lognormal (só se
  todos os valores > 0) / uniforme / exponencial (só se todos ≥ 0) via
  `scipy.stats.<dist>.fit()`, testa aderência com Kolmogorov-Smirnov,
  reporta a distribuição de maior p-valor; se nenhuma ultrapassar o
  limiar, retorna `"Desconhecida"` em vez de forçar um palpite. Requer
  `n_válidos >= 20`.

Esses quatro testes ficam dentro de `Stats_Extra.testes_hipotese` de cada
coluna numérica/categórica, ao lado das estatísticas descritivas
existentes.

### Análise temporal cross-coluna (ADF + Ljung-Box)

Diferente dos testes acima, ADF (estacionariedade) e Ljung-Box
(autocorrelação) exigem uma *ordem temporal* — não fazem sentido
coluna a coluna isolada:

- Só ativam se a tabela tiver ao menos uma coluna com
  `Semantica_IA == "Data / Calendário"` e tipo `Data / Hora` válido
  (nula minoritariamente). Se houver mais de uma candidata, usa a com
  menor `Pct_Nulos`.
- O pipeline ordena uma cópia do DataFrame por essa coluna de referência
  e roda ADF + Ljung-Box em cada coluna numérica, nessa ordem, limitando a
  série a no máximo 50.000 pontos (performance).
- ADF só roda se `n_válidos >= 30` (recomendação padrão para o teste ter
  poder estatístico razoável). Ljung-Box usa `lags = min(10, n // 5)`.
- Resultado sai como seção própria e separada no payload —
  `analise_temporal_series` (lista, um item por coluna numérica testada,
  com `coluna`, `coluna_temporal_referencia`, `adf.{estatistica,p_valor,estacionaria}`,
  `ljung_box.{estatistica,p_valor,autocorrelacionada}`) — não dentro do
  registro de coluna individual, porque depende semanticamente de duas
  colunas (a numérica + a de data usada como referência).

## Saída: dois formatos simultâneos (IA + humano)

A cada execução, `reporting.py` gera dois arquivos a partir do mesmo
payload:

- **`<base>_<tabela>.json`** — estrutura completa (colunas, stats,
  recomendações, FDs, gaps, testes de hipótese, análise temporal), com
  todo float não-finito (`NaN`/`Infinity`/`-Infinity`) saneado para `null`
  antes da serialização. Formato pra consumo por IA/código — a estrutura
  atual (dict aninhado por coluna) já é adequada, não precisa de formato
  novo.
- **`<base>_<tabela>.md`** — relatório Markdown pra leitura humana:
  cabeçalho com metadados e resumo de qualidade, tabela de colunas
  (tipo/semântica/%nulos/característica), recomendações ETL priorizadas
  por emoji (🔴🟡🟢, já usado hoje), dependências funcionais, gap analysis
  de KPI, resumo dos testes estatísticos e da análise temporal (se houver).

Parquet continua existindo como formato **opcional adicional**
(`--tambem-parquet` na CLI / `formato_saida="parquet"` na API), para quem
consome via pipeline de BI — não faz parte do par padrão JSON+Markdown.

## CLI

```
data-profiler perfilar arquivo.csv [--todas-abas] [--aba 0] [--saida-base out] [--tambem-parquet]
data-profiler lote *.csv *.xlsx        # substitui batch_profiler.py
```

## Tratamento de erros

- `ingestion.py` levanta exceções tipadas (`FileFormatError`,
  `EncodingDetectionError`) em vez de `RuntimeError` genérico.
- `cli.py` captura no nível mais alto, imprime mensagem amigável e
  retorna código de saída ≠ 0 em caso de falha (hoje `orquestrar()` só
  faz `print` e `return` silencioso).
- No modo `lote`, falha em um arquivo não interrompe o processamento dos
  demais (mesmo comportamento do `batch_profiler.py` hoje, com erro
  tipado em vez de `except Exception` genérico).

## Testes

`pytest`, com fixtures de DataFrames sintéticos cobrindo especificamente
os bugs encontrados na auditoria — cada correção vira teste de regressão:
coluna numérica com `n_válidos < 3` (trava o bug do NaN no JSON), coluna
quase-chave (trava FD trivial), agrupador com nulos (trava o
`dropna=False`), CPF em coluna de chave de sistema (trava a supressão de
CEP/Telefone mas não de CPF/CNPJ/e-mail), coluna com mistura de tipos,
tabela sem coluna de data (a análise temporal deve ficar ausente, não
quebrar), tabela com coluna de data (a análise temporal deve rodar).

## Migração

Removidos ao final, substituídos inteiramente pelo pacote `data_profiler/`:
`statistical_profiler.py`, `semantic_engine.py`, `profiling_orchestrator.py`,
`batch_profiler.py`, `Profiller.py`.

## Fora de escopo (Fase 2 e além)

- Correlação numérica (Pearson/Spearman) entre colunas.
- Detecção de linhas duplicadas (`df.duplicated()`).
- Detecção de PII embutida em texto livre (não só colunas 100%
  estruturadas) — candidato a `presidio` ou regex aplicado também sobre
  "Texto Descritivo Livre".
- Relatório Excel/HTML com formatação visual completa (dashboard).
- `pandera`/Great Expectations para converter recomendações em contratos
  de dados executáveis.
- `polars` como motor alternativo para arquivos muito grandes.
- **Fase 3** (futura, spec própria): cruzamento entre múltiplos arquivos —
  detectar que a coluna X do Arquivo A é chave que se liga à coluna Y do
  Arquivo B e à coluna X do Arquivo C, etc.

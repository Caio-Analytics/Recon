# Recon v3 — Design da arquitetura atual

Data: 2026-08-15
Status: Implementado
Substitui: `2026-08-05-data-profiler-v2-fase1-design.md` (Fase 1, v2.0)

## O que a ferramenta é

**A ferramenta que se roda *antes* de começar a análise de verdade.**

Não é componente de pipeline. Não monitora nada ao longo do tempo. Não gera
contrato de dados para CI. É o que alguém abre quando recebe um arquivo — ou
cinco — que nunca viu, e precisa saber o que dá para usar antes de investir
meio dia estudando o dado.

O alvo é um analista experiente que quer **pular a fase de entender o
arquivo** e começar o trabalho real com boa parte do caminho andado.

### Restrições que moldaram o desenho

- **Máquina corporativa**: sem admin, sem venv, `pip install --user`. Nada de
  serviço externo, modelo de IA baixado ou dependência que exija compilação
  fora do que já vem em wheel.
- **Sem banco de dados**: o consumo é em pandas, sobre arquivo. Por isso o
  código gerado sai em pandas primeiro e SQL como alternativa.
- **Entrada é planilha**, frequentemente montada por gente — não export limpo
  de sistema.

## Arquitetura

```
src/recon/
├── config.py            só dado: taxonomias, thresholds, regras de KPI
├── ingestion.py         leitura CSV/XLSX/XLS/XLSB, encoding, separador
├── layout.py            cabeçalho real, linha de total, célula mesclada, blocos
├── patterns.py          documentos, mascaramento LGPD, sentinela, mojibake, shape, Benford
├── semantics/           cascata de inferência semântica
│   ├── vocabulary.py      abreviaturas e gazetteers (só dado)
│   ├── tokens.py          normalização, tokenização, expansão de abreviatura
│   ├── detectors.py       cinco detectores determinísticos + contexto
│   └── evidence.py        combinação por noisy-OR, ranking de hipóteses
├── hypothesis.py        testes de hipótese, seleção de distribuição, outliers robustos
├── statistics.py        estatísticas descritivas e qualidade por coluna
├── rules.py             regras de negócio inferidas
├── relationships.py     FD, duplicatas, redundância, correlação, hierarquia, séries
├── datamodel.py         chaves entre tabelas, fato × dimensão, grão, análises sugeridas
├── quality.py           recomendações de ETL, gap analysis, score
├── codegen.py           geração do script de limpeza
├── reporting/           JSON, Markdown, HTML, Parquet, modelo do conjunto
├── pipeline.py          DataProfiler — orquestração
└── cli.py               perfilar · modelar · lote · versao
```

Cada módulo é um conjunto de funções puras, sem estado global nem
side-effect no import. `config.py` é exclusivamente dado; a lógica que o
consome vive nos módulos de análise.

### Fluxo

**Uma tabela** (`perfilar`):
`ingestion` (+ `layout`) → por coluna: `statistics` + `patterns` +
`hypothesis` → semântica da tabela inteira (`semantics`, duas passadas) →
cruzamentos (`relationships`, `rules`) → priorização (`quality`) →
`reporting` (+ `codegen`).

**Conjunto de tabelas** (`modelar`): perfila cada uma e depois `datamodel`
descobre chaves, classifica papéis, mede grão e integridade, e monta as
análises sugeridas.

A semântica roda **depois** da descrição das colunas de propósito: os
detectores de conteúdo consomem o que `statistics` já apurou, em vez de
recalcular.

## Decisões de projeto e o porquê

### Inferência semântica: dois eixos e cascata de evidências

A coluna recebe um **papel** (o que ela é) e um **domínio** (sobre o que
fala). `nome_departamento` tem papel "Nome" e domínio "Estrutura
Organizacional"; achatar os dois num campo fazia `id_funcionario` virar
"Nome / Identificação Pessoal" e deixava o gap analysis cego.

Nenhum detector decide sozinho. Cada um emite evidência com peso e a
combinação é por **noisy-OR** (`1 - Π(1-peso)`). Cinco detectores
determinísticos, do mais forte ao mais fraco: conteúdo estruturado validado
por dígito verificador; gazetteer de valores; abreviatura reconstruída por
subsequência (`dpto` ⊂ `departamento`); dicionário e fuzzy; assinatura
estrutural.

Duas passadas: a segunda usa os domínios já confiantes para desambiguar o
resto. `dep` (departamento? dependente? depósito?) é insolúvel na coluna e
trivial na tabela.

Quando a melhor hipótese não se destaca da segunda, o relatório mostra as
alternativas em vez de fingir certeza.

**Medido**: numa extração de ERP com todos os nomes opacos (`mt_colab`,
`cd_dpto_lot`, `f27`, `x9`), o motor v2 acertava 1 de 12 colunas; o atual
acerta 12 de 12.

### Layout de planilha antes de qualquer análise

Arquivo de sistema começa na linha 1; planilha de gente tem título, "emitido
em", linha em branco e o cabeçalho na quinta linha. Sem tratar, o título vira
nome de coluna e a tipagem inteira vai junto — o relatório sai *bonito e
errado*, o pior resultado possível porque nada nele indica o problema.

Heurísticas conservadoras: na dúvida, mantêm o comportamento padrão. Cada
ajuste vira aviso explícito na seção "Como o arquivo foi lido".

### Estatística: efeito, não só p-valor

- **Distribuição provável por AIC**, não por p-valor. Ajustar com `fit()` e
  testar com `kstest` usando os mesmos parâmetros viola a premissa do teste e
  infla o p-valor — t de Student com 3 g.l. passava como normal. Distribuições
  em x>0 são ajustadas com locação fixa em zero, senão o ajuste de 3
  parâmetros é degenerado e vence sem descrever melhor.
- **Shapiro-Wilk com tamanho de efeito**: com n grande o p-valor vai a zero
  por desvio irrelevante. Vem acompanhado de W, assimetria e curtose.
- **Outlier robusto a assimetria**: boxplot ajustado por medcouple quando
  `|assimetria| ≥ 1`. O IQR fixo acusa a cauda legítima de uma lognormal.
- **Série temporal agregada por período** antes de ADF/Ljung-Box. Linha
  transacional não é série temporal.

### LGPD: suprimir, não só mascarar

Em coluna sensível as amostras saem mascaradas **e** as estatísticas de
posição (min, max, mediana, IC, limites de outlier) são suprimidas — o mínimo
de uma coluna de CPF é o CPF de alguém.

CPF/CNPJ exigem **dígito verificador**, não só formato: sem isso um timestamp
epoch em milissegundos (13 dígitos) virava CNPJ. Quando o formato bate e o
dígito não, o profiler reporta como documento suspeito em vez de silenciar.

### Chaves entre tabelas: contenção, não similaridade

`FK ⊆ PK`, mas raramente `FK ≈ PK` — a dimensão quase sempre tem valores que
o fato não usa, e o Jaccard subestimaria toda relação real.

O limiar de contenção afrouxa quando os nomes coincidem: duas colunas
`matricula` com metade dos valores batendo são a mesma chave com dado sujo;
duas colunas de nomes diferentes com metade batendo são coincidência. Uma
medida nunca é candidata a chave estrangeira.

Contenção é reportada em dois níveis: por valor distinto (para detectar) e
por linha (para responder "quantos registros eu perco num INNER JOIN?").

### Score de qualidade: abrangência além de cada defeito

Cada dimensão divide pelo total de colunas, então um defeito em 1 de 8 colunas
nunca passa de 12,5% daquela dimensão — e uma tabela com seis colunas
problemáticas, cada uma com um problema diferente, somava pouco em tudo e saía
com nota alta. A dimensão `colunas_com_defeito` mede a abrangência
diretamente.

As dimensões precisam ser **disjuntas**: usar `nulos_efetivos_pct` na dimensão
de nulos contava a sentinela duas vezes.

## Saídas

| Formato | Para quê |
|---|---|
| JSON | consumo por código ou colagem em prompt (`--json-compacto` encolhe) |
| Markdown | leitura humana, com detalhe por coluna |
| HTML | autocontido, circula por e-mail, sem CSS/JS externo |
| Parquet | consumo em BI |
| `limpeza.py` | script pandas que aplica as recomendações (`--gerar-limpeza`) |
| Modelo do conjunto | papéis, chaves, diagrama ER em Mermaid, análises sugeridas |

O script de limpeza traz cada passo comentado com o achado que o motivou, e
uma seção final com o que **não** dá para automatizar (documento inválido,
PII em texto livre, violação de regra) — emitir código que "resolve" isso
seria esconder o problema.

## Qualidade do código

- `ruff` (E,F,W,I,UP,B,C4,SIM) e `mypy` limpos, rodando em CI local.
- Cobertura ≈ 92%, com teste de regressão nomeado para cada bug corrigido.
- `py.typed` exportado.
- Python ≥ 3.12 (piso real das libs fixadas), validado em 3.14.

### Cenários de teste

Além dos unitários, três cenários de ponta a ponta em `test_cenarios.py`:
base com 60% das linhas contaminadas em várias dimensões simultâneas; duas
tabelas sem chave em comum (o relatório precisa dizer que não há relação, não
inventar uma); e tabela com chave compatível mas sem nenhuma medida (a relação
é reconhecida, mas nenhuma análise é prometida).

## Limitações conhecidas

- **Pesos de confiança não calibrados**: os números da cascata semântica foram
  escolhidos por julgamento, não ajustados sobre um corpus rotulado.
- **Threshold fuzzy de 0,85 é frouxo** — `unica_coluna` casa com `unidade`.
  Com a decisão agora sendo por peso combinado, o certo seria baixar o piso e
  deixar o peso ser proporcional à similaridade.
- **Gazetteer de municípios** cobre só as 27 capitais.

## Fora de escopo (decisão explícita do usuário)

- ~~Monitoramento de drift entre execuções.~~ Revisto depois: virou o
  `contrato` de dados + `conferência` entre versões (veja "Atualizações"
  abaixo) — o que ficou de fora foi só o monitoramento *contínuo*
  (agendado, tipo cron); a comparação sob demanda entre duas extrações
  passou a fazer sentido dentro do escopo da ferramenta.
- Geração de asserções para dbt / Great Expectations.
- Qualquer backend de IA (embeddings, LLM local). Foi implementado e
  **removido** a pedido: a cascata determinística resolve o caso de uso, e a
  dependência não cabe na máquina alvo.

## Atualizações desde este documento

Este spec registra o desenho no lançamento da v3. O que mudou desde então,
resumido — detalhe de cada um em `docs/TECNICO.md`:

- **Paralelização e leitura em blocos**: arquivo maior que a RAM passou a ser
  suportado (leitura por blocos com amostragem sistemática), e a fase de
  descrição por coluna distribui entre processos acima de um teto de
  trabalho (linhas × colunas).
- **Entrada comprimida e Parquet**: `.gz`/`.bz2`/`.zip`/`.xz`/`.zst`, `.tsv`/
  `.txt` e `.parquet` como formato de entrada, não só saída.
- **Contrato de dados e conferência entre versões**: congela o que a base é
  hoje num YAML editável e reconfere isso na extração seguinte; um relatório
  à parte compara duas extrações da mesma base (schema, linhas, colunas que
  mudaram de comportamento).
- **Dicionário de dados em XLSX** e **chave estrangeira composta** entre
  tabelas (mais de uma coluna).
- **Janela sem terminal** (`recon janela`, `Recon.pyw`), pro público que não
  usa linha de comando.
- **Bytes que não decodificam no encoding detectado** deixaram de derrubar a
  análise inteira — substituídos com aviso em vez de exceção.
- Uma leva de correções na inferência semântica, cada uma validada contra
  base pública real (dado de governo aberto): abreviatura especulativa de
  2 letras, qualificador de borda em nomenclatura inglesa
  (`SUPPLIER_CONTACT_CODE`), papel de "nome" refinado por domínio quando o
  nome é de instituição ou conceito (não de pessoa), e CNPJ deixando de
  contar como risco de exposição de dado pessoal — CNPJ identifica pessoa
  jurídica, fora do escopo da LGPD.

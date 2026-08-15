# 🔭 Recon

**A ferramenta que você roda *antes* de começar a análise de verdade.**

Você recebeu um arquivo — ou cinco — que nunca viu. O Recon perfila cada tabela (o que é lixo, o que é data, o que é chave, o que dá pra usar), descobre **como as tabelas se ligam entre si**, identifica quais são fato e quais são dimensão, e devolve **análises sugeridas com o código pronto pra rodar**. A ideia é chegar no trabalho real já com metade do caminho andado, em vez de gastar meio dia entendendo o dado.

Roda em CSV, XLSX, XLS e XLSB. Sem banco de dados, sem serviço externo, sem modelo de IA — só Python e as bibliotecas do `pyproject.toml`, instaláveis com `pip install --user` em máquina corporativa. Saída em **JSON** (pra colar num prompt ou consumir via código), **Markdown** e **HTML** (pra ler) e **Parquet** (pra BI).

---

## ✨ O que ele faz

| Análise | Descrição |
|---|---|
| 🧠 **Inferência semântica** | Cascata de evidências: dicionário, reconstrução de abreviatura (`cd_dpto_lot`), gazetteers de conteúdo (uma coluna `f27` com siglas de UF é geográfica), assinatura estrutural e contexto da tabela. Separa **papel** (o que a coluna é) de **domínio** (sobre o que ela fala), e devolve **hipóteses ranqueadas** quando não tem certeza |
| 📊 **Estatística descritiva** | Min/max/média/mediana/desvio, outliers robustos a assimetria, distribuição de frequência, tipo de dado real |
| 🔬 **Testes de hipótese** | Shapiro-Wilk com tamanho de efeito, qui-quadrado com V de Cramér, IC 95%, seleção de distribuição por AIC, ADF e Ljung-Box sobre série agregada |
| 🧹 **Sujeira de dados** | Nulos disfarçados (`N/A`, `-`, `#N/D`, `-1`, `999999`), grafias divergentes (`SP`/`sp`/`S.P.`), mojibake de encoding, documento com dígito verificador inválido |
| 🔗 **Relações entre colunas** | Dependências funcionais, equivalências 1:1, colunas idênticas, chaves compostas candidatas |
| 📈 **Correlação** | Pearson/Spearman (numérica), V de Cramér (categórica), razão de correlação η (mista) |
| 🔒 **LGPD** | Identifica CPF, CNPJ, e-mail, telefone, CEP (com validação de dígito verificador), **mascara** as amostras e **suprime** estatísticas que exporiam o valor real. Detecta PII embutida em texto livre |
| ✅ **Recomendações ETL** | Lista priorizada de ações (🔴 alta / 🟡 média / 🟢 baixa) por coluna, camada Bronze/Silver |
| 🎯 **Score de qualidade** | Nota 0-100 da tabela com as dimensões que mais pesaram contra |
| 📅 **Análise temporal** | ADF + Ljung-Box sobre a série **agregada por período**, com datas futuras e lacunas de calendário |
| 🗜️ **Otimização** | Sugestão de dtype com economia de memória estimada em MB |
| 📐 **Layout de planilha** | Acha o cabeçalho real (título, "emitido em", linha em branco antes dele), remove linha de TOTAL no rodapé, sinaliza célula mesclada e duas tabelas na mesma aba |
| 📜 **Regras de negócio** | Ordem entre datas (`dt_admissao <= dt_desligamento`), nulidade condicional, derivação aritmética (`vl_liquido = vl_bruto - vl_desconto`) — com as linhas que violam |
| 🧹 **Script de limpeza** | `--gerar-limpeza` emite um `.py` pandas que aplica as recomendações, cada passo comentado com o achado que o motivou |
| 🧩 **Modelo de dados** | Com 2+ tabelas (ou 2+ abas): descobre chaves estrangeiras, classifica fato × dimensão, mede integridade referencial e monta o diagrama ER |
| 💡 **Análises sugeridas** | Cruzamentos concretos com código **pandas e SQL prontos** — inclusive quando a medida está numa tabela e o eixo de análise em outra |

---

## 🚀 Começando

**Nunca usou Python nem terminal?** Vá direto para o **[GUIA.md](GUIA.md)** —
passo a passo com telas, sem precisar de permissão de administrador.

**Já tem Python?**

```bash
git clone https://github.com/Caio-Analytics/Recon.git
cd Recon
pip install --user -e .
recon
```

Digitar `recon` sozinho abre um menu que pergunta o que você quer. Dar Enter
em tudo funciona.

```
╭───────────────────────────────────────────────────────────────────╮
│ Recon 3.0.0                                                       │
│ Descubra o que tem nos seus arquivos antes de começar a analisar. │
╰───────────────────────────────────────────────────────────────────╯

Onde estão os arquivos? (Enter = pasta atual):

Encontrei 3 arquivo(s):
  1  empregados.csv       2.4 MB
  2  treinamentos.csv     8.1 MB
  3  cursos.csv           0.1 MB

O que você quer fazer?
  1  Comparar os arquivos  — um relatório só, do pior para o melhor
  2  Descobrir como se ligam  — chaves, fato × dimensão, análises prontas
  3  Analisar um por um  — relatório completo de cada arquivo
```

No fim, um arquivo `.html`: **clique duas vezes e abre no navegador**, sem
instalar mais nada.

**Requer Python ≥ 3.12** — não é escolha de estilo: `numpy` 2.5 e `scipy`
1.18, nas versões fixadas no `pyproject.toml`, declaram
`Requires-Python >= 3.12`, então o `pip` recusa a instalação em 3.11.

---

## 📖 Documentação

| Documento | Para quem |
|---|---|
| **[GUIA.md](GUIA.md)** | quem nunca usou Python: instalar do zero, com e sem VS Code |
| **[COMANDOS.md](COMANDOS.md)** | qual comando usar em cada situação, opções e receitas |
| [docs/TECNICO.md](docs/TECNICO.md) | como funciona por dentro: módulos, contrato do JSON, critérios |
| [docs/superpowers/specs/](docs/superpowers/specs/) | as decisões de projeto e o porquê de cada uma |

---

## 🖥️ Uso pela linha de comando

### O atalho: uma pasta inteira

```bash
recon pasta ./extracoes --saida ./relatorios
```

Lê a pasta e decide sozinho: um arquivo vira perfil individual; vários viram
lote comparativo (ou pergunta se você quer cruzar as tabelas). É o comando
para quem não quer pensar em qual modo usar.

### Perfilar um único arquivo

```bash
recon perfilar caminho/do/arquivo.csv
```

Gera dois arquivos no diretório atual:
- `profiler_output_arquivo.html` — relatório completo; **clique nele e abre renderizado no navegador**, em qualquer máquina, sem instalar nada
- `profiler_output_arquivo.json` — estrutura completa, pra colar num prompt de IA ou consumir via código

Prefere Markdown? `--formatos json,markdown`. O padrão é HTML porque um `.md` clicado abre no bloco de notas mostrando `##` e `|---|` crus para quem não tem visualizador.

**Opções:**

```bash
recon perfilar arquivo.xlsx --todas-abas               # processa todas as abas do Excel
recon perfilar arquivo.xlsx --aba 1                    # processa só a aba de índice 1
recon perfilar arquivo.csv --saida-base relatorios/q1  # prefixo customizado de saída
recon perfilar arquivo.csv --formatos json,markdown    # troca o HTML por Markdown
recon perfilar arquivo.csv --tambem-parquet            # atalho pra incluir Parquet
recon perfilar arquivo.csv --json-compacto             # JSON sem indentação (menor)
recon perfilar arquivo.csv --limite-amostra 100000     # teto de linhas analisadas
recon perfilar arquivo.csv --kpis meu_dominio.yaml     # regras de KPI próprias
recon perfilar arquivo.xlsx --linha-cabecalho 4        # força a linha do cabeçalho
recon perfilar arquivo.xlsx --sem-deteccao-layout      # lê o arquivo cru
recon perfilar arquivo.csv --gerar-limpeza             # emite o script de limpeza
```

Formatos válidos: `json`, `markdown`, `html`, `parquet` (padrão: `json,html`).

**Excel com várias abas:** por padrão o `perfilar` analisa só a primeira aba, mas avisa quando há outras. Use `--todas-abas` para gerar um relatório por aba, ou `recon modelar` para analisá-las juntas e descobrir como se relacionam.

### Regras de KPI de outro domínio

O gap analysis embutido é de RH. Em tabela de outro assunto ele vira ruído — troque por um YAML seu:

```yaml
kpis:
  - id: KPI_FIN_001
    nome: Receita por Região
    semanticas: [Valor Financeiro, Localização Geográfica]
  - id: KPI_FIN_002
    nome: Evolução de Custo
    semanticas: [Valor Financeiro, Data / Calendário]
```

```bash
recon perfilar vendas.csv --kpis kpis_financeiro.yaml
```

### Descobrir como várias tabelas se ligam

O `perfilar` olha uma tabela por vez. Quando você tem um conjunto — bases de empregados, de treinamentos e de cursos, por exemplo — o que interessa é como elas conversam:

```bash
recon modelar empregados.csv treinamentos.csv cursos.csv --saida-base rh
recon modelar rh_completo.xlsx --saida-base rh      # cada aba vira uma tabela
```

Gera um relatório do conjunto com:

- **Papel de cada tabela** — fato, dimensão, tabela ponte ou fato sem medida (eventos), com a justificativa estrutural
- **Chaves estrangeiras detectadas** por contenção de valores, com a cobertura real e a cardinalidade
- **Integridade referencial** — quantos registros do fato apontam para chave inexistente (os que somem num `INNER JOIN`), e chave que virou texto num arquivo e número no outro
- **Diagrama ER** em Mermaid, que renderiza direto no GitHub e no VS Code
- **Análises sugeridas** com o código pandas e SQL prontos

Num conjunto de RH real, a saída inclui coisas como:

> **Total de carga_horaria por diretoria** — soma de `carga_horaria` (de `cursos`) agrupada por `diretoria` (de `empregados`), a partir do fato `treinamentos`.
> ```python
> resultado = (
>     treinamentos
>     .merge(empregados, left_on="matricula", right_on="matricula", how="left")
>     .merge(cursos, left_on="cod_curso", right_on="cod_curso", how="left")
>     .groupby("diretoria", as_index=False)["carga_horaria"].sum()
>     .sort_values("carga_horaria", ascending=False)
> )
> ```

Repare que a medida (`carga_horaria`) mora na dimensão de cursos e o eixo (`diretoria`) na de empregados — o cruzamento que ninguém enxerga olhando uma planilha por vez. Medida não-aditiva (nota, índice, percentual) sai com `mean` em vez de `sum`.

**Opções:** `--sem-perfis` gera só o relatório do conjunto, sem o perfil individual de cada tabela. As demais opções (`--formatos`, `--limite-amostra`, `--kpis`, `--json-compacto`) funcionam igual ao `perfilar`.

### Perfilar vários arquivos de uma vez

```bash
recon lote dados/*.csv dados/*.xlsx
```

Se um arquivo falhar (corrompido, formato inválido), o `lote` **continua processando os demais** — não aborta o lote inteiro.

**Caminho relativo ou absoluto — os dois funcionam:**

```bash
recon perfilar dados/vendas.csv                # relativo: a partir da pasta onde você rodou o comando
recon perfilar /home/usuario/dados/vendas.csv  # absoluto: funciona de qualquer diretório
```

### Ajuda

```bash
recon --help
recon perfilar --help
recon lote --help
recon versao
```

---

## 🔬 Como a análise funciona

Visão técnica do critério por trás de cada número/rótulo que sai no relatório.

- **Inferência semântica (dois eixos):** a coluna recebe um **papel** (identificador, data, valor financeiro, quantidade, nome, contato) e um **domínio** (estrutura organizacional, cargo, curso, localidade, perfil). `nome_departamento` tem papel "Nome" e domínio "Estrutura Organizacional" — achatar os dois num campo só fazia `id_funcionario` virar "Nome / Identificação Pessoal" e deixava o gap analysis cego para colunas de departamento presentes na tabela.
- **Cascata de evidências:** nenhum detector decide sozinho. Cada um emite evidências com peso e a combinação é por **noisy-OR** (`1 - Π(1 - peso)`): duas pistas de 0,5 valem 0,75. É o que permite classificar um nome que nenhuma fonte resolveria isoladamente. Quando a melhor hipótese não se destaca da segunda, o relatório mostra as alternativas em vez de fingir certeza — e o campo `dominio` fica vazio em vez de afirmar um palpite.
- **Os cinco detectores determinísticos, do mais forte ao mais fraco:**
  1. *Conteúdo estruturado* — CPF/CNPJ validados por dígito verificador. Vence o nome: uma coluna `campo1` que só contém CPF é um identificador.
  2. *Gazetteer de valores* — conjuntos fechados conhecidos (27 siglas de UF, sexo, escolaridade, estado civil, meses, booleanos textuais, moedas ISO). É o que resolve o nome ilegível: `f27` cujos valores são siglas de UF é geográfica, e nenhuma análise do nome chegaria lá.
  3. *Abreviatura reconstruída* — abreviatura corporativa é a palavra com letras removidas **na ordem** (`dpto` ⊂ `de`**p**`ar`**t**`ament`**o**). Distância de edição erra esse caso; casamento por subsequência acerta. `mvto`→movimento, `lotac`→lotação, `nasc`→nascimento.
  4. *Dicionário e fuzzy* — match exato por token e Jaro-Winkler, agora rodando também sobre as abreviaturas já expandidas.
  5. *Assinatura estrutural* — a forma dos dados: inteiro único e crescente tem cara de chave sequencial; decimal de 2 casas, não negativo e assimétrico à direita tem cara de valor monetário.
- **Contexto da tabela:** a inferência roda em duas passadas. A primeira classifica o que dá isoladamente; a segunda usa os domínios já estabelecidos com confiança para desambiguar o resto. `dep` pode ser departamento, dependente ou depósito — é insolúvel olhando a coluna (nenhum modelo resolve) e trivial olhando a tabela: se `diretoria` está do lado, é departamento. Só colunas conclusivas entram no contexto, senão ele propagaria o próprio erro.
- **Detecção de LGPD:** regex para os formatos com pontuação **mais** validação de **dígito verificador** em CPF/CNPJ. Sem o DV, um timestamp epoch em milissegundos (13 dígitos) era classificado como CNPJ. Quando o formato bate e o DV não fecha, o profiler não silencia: reporta como documento suspeito (campo truncado, dígito perdido em conversão). Em coluna sensível as amostras saem mascaradas **e** as estatísticas de posição (min, max, mediana, IC, limites de outlier) são suprimidas — o mínimo de uma coluna de CPF é o CPF de alguém.
- **Nulos disfarçados:** catálogo de sentinelas textuais (`N/A`, `-`, `#N/D`, `NAO INFORMADO`), numéricas (`-1`, `999999` — só quando são extremo da distribuição) e de data (`1900-01-01`, epoch do Excel, `9999-12-31`). O relatório traz "nulos efetivos" ao lado dos nulos reais: uma coluna 30% preenchida com `N/A` reportava 0% de nulos.
- **Testes de hipótese:** cada teste só roda com amostra mínima. Shapiro-Wilk vem acompanhado da estatística W e de assimetria/curtose — com n grande o p-valor vai a zero por desvios irrelevantes e sozinho não informa nada. O qui-quadrado traz o V de Cramér pelo mesmo motivo.
- **Distribuição provável:** escolhida por **AIC**, não por p-valor. Ajustar os parâmetros com `fit()` e testar aderência com `kstest` usando esses mesmos parâmetros viola a premissa do teste e infla o p-valor — uma t de Student com 3 graus de liberdade passava como normal. As distribuições definidas em x>0 são ajustadas com locação fixa em zero, senão o ajuste de 3 parâmetros é degenerado e vence qualquer comparação sem descrever melhor os dados.
- **Outliers:** IQR clássico em distribuição simétrica, boxplot ajustado por **medcouple** quando `|assimetria| ≥ 1`. O fator fixo 1,5 pressupõe simetria e acusa a cauda direita legítima de uma lognormal (salário, receita) como anomalia.
- **Dependências funcionais:** fatoração em códigos inteiros uma única vez, poda pela condição necessária `nunique(determinante) ≥ nunique(dependente)`, e verificação O(n) sem ordenação. Colunas quase-únicas (≥98% distintos) são excluídas do lado determinante. Bijeções saem como **equivalência**, uma linha só, não duas FDs.
- **Análise temporal:** a série é **agregada por período** (diária, semanal ou mensal — a menor granularidade que ainda rende pontos suficientes) antes do ADF/Ljung-Box. Linhas transacionais não são série temporal: há várias linhas na mesma data e espaçamento irregular, e testar a ordenação bruta testa a ordem arbitrária dentro de cada dia. Colunas com característica de chave ficam de fora. O formato da data é inferido do conteúdo, não fixado em dia-primeiro.
- **Layout de planilha:** arquivo exportado de sistema começa na linha 1; planilha montada por uma pessoa tem título, data de emissão, linha em branco e o cabeçalho na quinta linha. Sem tratar isso, o título vira nome de coluna e a tipagem inteira vai junto — o relatório sai *bonito e errado*, que é o pior resultado possível porque nada nele indica o problema. A detecção acha a primeira linha larga o bastante, feita de texto, com rótulos distintos e seguida de dados. Linha de TOTAL no rodapé é identificada por rótulo ou por bater com a soma da coluna, e removida (senão distorce média, máximo e outlier). Depois de remover o rodapé, colunas que só eram texto por causa dele voltam a ser numéricas — com ida e volta verificada, para que `00123` nunca vire `123`. Todas as heurísticas são conservadoras: na dúvida, mantêm o comportamento padrão, e cada ajuste vira aviso explícito na seção "Como o arquivo foi lido".
- **Chaves entre tabelas:** detectadas por **contenção** de valores (`FK ⊆ PK`), não por similaridade — a dimensão quase sempre tem valores que o fato não usa, e o Jaccard subestimaria toda relação real. Os valores são normalizados antes de comparar, o que permite casar uma chave que virou `int64` num arquivo e ficou texto no outro (e avisar sobre o cast). O limiar de contenção afrouxa quando os nomes das colunas coincidem: duas colunas `matricula` com metade dos valores batendo são a mesma chave com dado sujo; duas colunas de nomes diferentes com metade batendo são coincidência. Uma medida nunca é candidata a chave estrangeira — `carga_horaria` (2 a 40) está inteiramente contida em qualquer `id` sequencial.
- **Fato × dimensão:** classificação estrutural, não pelo nome. Tabela que aponta para várias outras e carrega medidas é fato; tabela apontada e com chave própria é dimensão. Fato sem medida numérica não é anomalia — é tabela de evento, e continua sendo o centro da análise.
- **Amostragem:** analisa até 500 mil linhas por padrão (`--limite-amostra`). Acima disso o payload marca `amostragem_aplicada: true` — unicidade e duplicata passam a valer para a amostra, não para a tabela. Os testes pesados usam subamostras determinísticas (seed fixa): o mesmo arquivo sempre gera o mesmo resultado.

---

## 📁 Estrutura do projeto

```
Recon/
├── pyproject.toml           ← comandos de instalação rodam AQUI (raiz do projeto)
├── src/recon/
│   ├── config.py             taxonomias, thresholds e regras de KPI (fonte única, só dado)
│   ├── ingestion.py          carrega CSV/XLSX/XLS/XLSB, detecta encoding e separador
│   ├── layout.py             cabeçalho real, linha de total, célula mesclada, blocos
│   ├── patterns.py           documentos, mascaramento LGPD, sentinelas, mojibake, PII, Benford
│   ├── semantics/            cascata de inferência semântica
│   │   ├── vocabulary.py       abreviaturas e gazetteers (só dado)
│   │   ├── tokens.py           normalização, tokenização, expansão de abreviatura
│   │   ├── detectors.py        os cinco detectores determinísticos + contexto
│   │   └── evidence.py         combinação por noisy-OR e ranking de hipóteses
│   ├── hypothesis.py         testes de hipótese, seleção de distribuição, outliers robustos
│   ├── statistics.py         estatísticas descritivas e qualidade por coluna
│   ├── rules.py              ordem entre datas, nulidade condicional, derivação
│   ├── relationships.py      FD, duplicatas, redundância, correlação, hierarquia, séries
│   ├── codegen.py            gera o script de limpeza a partir dos achados
│   ├── datamodel.py          chaves entre tabelas, fato × dimensão, análises sugeridas
│   ├── quality.py            recomendações de ETL, gap analysis de KPI, score de qualidade
│   ├── reporting/            exporta JSON, Markdown, HTML e Parquet
│   ├── pipeline.py           `DataProfiler` — orquestra tudo acima
│   ├── interativo.py         menu no terminal para quem não decora comando
│   └── cli.py                comandos `perfilar`, `lote`, `modelar`, `pasta`, `versao`
└── tests/                    suíte pytest (um arquivo por módulo)
```

**Fluxo interno:** `cli.py` → `pipeline.DataProfiler` → carrega o arquivo (`ingestion`) → descreve cada coluna (`statistics` + `patterns` + `hypothesis`) → infere a semântica da **tabela inteira** (`semantics`, duas passadas) → cruza colunas (`relationships`) → prioriza (`quality`) → exporta (`reporting`).

A inferência semântica vem depois da descrição das colunas de propósito: os detectores de conteúdo consomem o que `statistics` já apurou (valores distintos, cardinalidade, assimetria) em vez de recalcular.

Cada módulo é um conjunto de funções puras sem estado global. `config.py` é só dado; a lógica que o consome vive nos módulos de análise.

---


## 🧪 Rodando os testes

```bash
pytest -v
```

Lint e checagem de tipos:

```bash
ruff check src tests && mypy
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

**2. Limpar as dependências do Recon** (remove as diretas do `pyproject.toml`; algumas transitivas pequenas e comuns como `six`/`packaging` podem continuar — são inofensivas e usadas por outras libs também, não vale arriscar remover às cegas):

```bash
pip uninstall -y recon pandas numpy pyarrow openpyxl xlrd pyxlsb charset-normalizer rapidfuzz unidecode scipy statsmodels pyyaml loguru typer tqdm pytest pytest-cov pandas-stubs
```

**3. Apagar a pasta local e clonar de novo** (rode a partir de fora da pasta `Recon`, senão o shell perde a referência do diretório):

```bash
cd ~/Documentos/Programacao && rm -rf Recon && git clone https://github.com/Caio-Analytics/Recon.git && cd Recon
```

**4. Instalar e testar:**

```bash
pip install --user -e ".[dev]" && pytest -v
```

---

## 🗺️ Roadmap

- **Fase 6** (planejada): dicionário de dados exportável (XLSX) e reconciliação entre duas versões da mesma base
- **Fase 6** (planejada): gráficos embutidos no HTML (histograma e série temporal por coluna)
- **Fase 6** (planejada): calibrar os pesos de confiança da cascata semântica sobre um corpus rotulado
- **Fase 6** (planejada): gazetteer de municípios brasileiros completo (hoje só as 27 capitais)

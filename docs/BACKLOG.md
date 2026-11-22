# Backlog do Recon

Revisado em 2026-11-22 a partir de uma leitura do código da `main`. Este
documento é um mapa de **onde o projeto pode melhorar**, organizado por área e
pelo tipo de conhecimento que cada item exige. Nem tudo aqui é para fazer já:
alguns itens são correções, outros são ideias para quem quiser pesquisar.

Se algo chamou sua atenção, comente na issue correspondente (ou abra uma) antes
de começar, e leia o [CONTRIBUTING.md](../CONTRIBUTING.md). Para itens marcados
com 🔴, abra uma issue ou discussão primeiro: a decisão de design importa mais
que o código.

## Como ler

Cada item tem um código (para citar em issues e PRs), um **perfil** e um
**tamanho**.

| Perfil | Significa |
|---|---|
| 🟢 | Bom para a primeira contribuição. O caminho está claro. |
| 🟡 | Exige entender um módulo ou ter conhecimento específico da área. |
| 🔴 | Exige decisão de design ou pesquisa. Converse antes de programar. |

Tamanho: **P** (algumas horas), **M** (alguns dias), **G** (semanas ou vários PRs).

O que a pessoa precisa saber vem nas **etiquetas de conhecimento**:
`[Python]` programação geral, `[Estatística]` estatística e probabilidade,
`[Séries temporais]`, `[Dados BR]` documentos e formatos brasileiros,
`[Qualidade de dados]`, `[Segurança]`, `[UX]` interface e acessibilidade,
`[DevOps]` CI, build e distribuição, `[Docs]` escrita técnica.

**Quem entende de estatística, mas programa pouco, tem a seção 2 inteira.** A
maioria dos itens ali precisa de uma decisão matemática, e o código é a parte
pequena. Descrever o método e os limiares num comentário de issue já é uma
contribuição.

## Sumário

1. [Privacidade e segurança](#1-privacidade-e-segurança)
2. [Estatística e matemática](#2-estatística-e-matemática)
3. [Semântica, documentos e dados brasileiros](#3-semântica-documentos-e-dados-brasileiros)
4. [Qualidade de dados e score](#4-qualidade-de-dados-e-score)
5. [Relações entre tabelas e modelagem](#5-relações-entre-tabelas-e-modelagem)
6. [Leitura de dados e desempenho](#6-leitura-de-dados-e-desempenho)
7. [Código gerado e exportação](#7-código-gerado-e-exportação)
8. [Relatórios](#8-relatórios)
9. [Interface gráfica e linha de comando](#9-interface-gráfica-e-linha-de-comando)
10. [Distribuição e instalação](#10-distribuição-e-instalação)
11. [Qualidade do código e testes](#11-qualidade-do-código-e-testes)
12. [Documentação e comunidade](#12-documentação-e-comunidade)
13. [Ideias para o futuro](#13-ideias-para-o-futuro)
14. [Fora de escopo](#14-fora-de-escopo)

---

## 1. Privacidade e segurança

O Recon promete mascarar dado pessoal nos relatórios. Esta seção reúne os
pontos em que isso não se sustenta hoje, e é por onde eu começaria.

### SEG-1 · Valores pessoais aparecem sem máscara em exemplos do relatório 🟡 M `[Python]` `[Segurança]` `[Qualidade de dados]`

**Prioridade alta.** A máscara é aplicada em `amostra_representativa`,
`distribuicao_top5` e nas estatísticas, mas vários outros campos copiam valores
brutos da coluna. Reproduzi com uma tabela sintética (coluna de nomes, coluna de
CPF e coluna de observações com e-mail e telefone) e encontrei valores reais em:

| Campo do JSON | O que vaza |
|---|---|
| `Qualidade.inconsistencia_normalizacao.exemplos[].variantes` | nomes completos |
| `Qualidade.mojibake.exemplos` | nomes com acento corrompido |
| `duplicatas_aproximadas[].exemplos[].variantes` | nomes completos |
| `recomendacoes_etl[].Acao` | nomes, dentro do texto da recomendação |
| `Qualidade.formato.exemplo_conforme` | e-mail e telefone de texto livre |
| `Stats_Extra.distribuicao_top5[].valor` | e-mail e telefone em colunas de texto livre |

CPF em coluna própria foi mascarado corretamente: o problema está nas colunas
de **nome** e de **texto livre**, onde a detecção de dado pessoal acontece
depois que os exemplos já foram montados.

**Proposta.** Aplicar a máscara em um único ponto, na saída da análise de cada
coluna (e na de duplicatas aproximadas), em vez de em cada campo. Escrever um
teste de regressão que percorre o JSON inteiro e falha se qualquer valor
sintético conhecido aparecer.

### SEG-2 · Abrir bancos SQLite somente para leitura 🟢 P `[Python]` `[Segurança]`

`ingestion.carregar_consulta` valida que o SQL começa com `select` ou `with`,
mas abre o SQLite com `sqlite3.connect(caminho)`: se o arquivo não existir, ele
é **criado**, e a conexão aceita escrita. O DuckDB já usa `read_only=True`.
Abrir com `file:{caminho}?mode=ro` (e `uri=True`) e testar que um caminho
inexistente gera erro claro.

### SEG-3 · Limites e tempo máximo na leitura de URLs 🟡 M `[Python]` `[Segurança]`

`_carregar_url` entrega a URL direto ao pandas, sem *timeout*, sem limite de
tamanho e sem amostragem para Parquet e JSON (só o CSV respeita `nrows`). Uma
URL grande ou lenta trava a análise ou esgota a memória. Baixar em blocos para
um arquivo temporário, com limite de bytes e *timeout*, e só então analisar.

### SEG-4 · Restringir o carregamento de recursos no PDF 🟡 P `[Python]` `[Segurança]`

`reporting/_pdf.py` usa `HTML(filename=...).write_pdf(...)` com o `url_fetcher`
padrão do WeasyPrint, que busca qualquer URL ou arquivo referenciado. Hoje os
valores são escapados no HTML, então não há injeção conhecida, mas os avisos de
segurança do WeasyPrint (CVE-2026-55073 e CVE-2026-106443) mostram que essa
camada é frágil. Passar um `url_fetcher` que aceita só `data:` e o próprio
relatório, com teste que garante que `file://` e `http://` são recusados.

### SEG-5 · Escape correto de caminhos no código gerado 🟢 P `[Python]`

Dois problemas relacionados, ambos verificados:

- `reporting/_modelo.py` coloca o caminho e o nome da aba direto em literais
  (`pd.read_excel(r"{arquivo}", sheet_name="{aba}")`). Uma aba com aspas gera
  código quebrado.
- `codegen.py` usa `r` + `repr()` (`r{_literal(caminho)}`). Para
  `C:\dados\a.csv`, o `repr` já dobra as barras e o prefixo `r` as mantém: o
  script lê `C:\\dados\\a.csv`. No Windows costuma funcionar por tolerância do
  sistema, mas é incorreto e pode falhar em caminhos de rede (`\\servidor\pasta`).

Gerar o literal só com `repr()` (sem o `r`) nos dois lugares e testar que o
script gerado compila e aponta para o mesmo caminho.

### SEG-6 · Auditoria de dependências na CI 🟢 P `[DevOps]` `[Segurança]`

Feito em 2026-11-22: job `auditoria` com `pip-audit` e `dependabot.yml`
mensal. Fica aqui como registro; veja DEV-3 para o próximo passo
(hashes no lock).

### SEG-7 · Tratar o `Recon.pyw` e os atalhos de abrir arquivo 🟢 P `[Python]` `[Segurança]`

`application.py` abre o resultado com `subprocess.run(["xdg-open"|"open", caminho])`
(sem `shell=True`, o que é bom), mas não tem caminho para o Windows, onde
`xdg-open` não existe e o equivalente é `os.startfile`. Tratar o Windows e
unificar com `gui.py`, que repete a lógica.

### SEG-8 · Política de retenção e limpeza de saídas 🔴 M `[Segurança]` `[UX]`

Os relatórios podem conter metadados corporativos (veja o
[SECURITY.md](../SECURITY.md)). Avaliar um comando `recon limpar` que apaga as
saídas geradas e avisos ao escolher uma pasta compartilhada ou sincronizada
(OneDrive, Dropbox).

---

## 2. Estatística e matemática

Aqui **conhecimento de estatística importa mais que de programação**. Os itens
descrevem o problema matemático. O código existente está em
[`hypothesis.py`](../src/recon/hypothesis.py),
[`statistics.py`](../src/recon/statistics.py) e
[`relationships.py`](../src/recon/relationships.py).

### Testes de hipótese e distribuições

#### EST-1 · Não dar conclusão de "normal" por falta de rejeição 🟡 M `[Estatística]`

`testar_normalidade_shapiro` marca `normal_provavel = p > 0,05`. Dois problemas:
(a) com n próximo de 5.000 (o teto), o teste rejeita desvios irrelevantes; com
n pequeno, quase nunca rejeita. (b) "não rejeitar" não é evidência de
normalidade. Propor um critério que combine o p-valor com tamanho de efeito
(assimetria, curtose, correlação do gráfico Q-Q), testar alternativas
(D'Agostino-Pearson, Anderson-Darling) e mudar o texto do relatório para
"compatível com a normal" quando for o caso.

#### EST-2 · Correção para múltiplos testes 🔴 M `[Estatística]`

Cada coluna recebe vários testes ao nível α = 0,05 (Shapiro, qui-quadrado, ADF,
Ljung-Box, correlações) sem ajuste. Numa tabela com 100 colunas, é esperado que
alguns "achados" apareçam só por acaso. Avaliar controle da taxa de falsas
descobertas (Benjamini-Hochberg) na camada de relatório, ou deixar de tratar o
p-valor isolado como alerta.

#### EST-3 · Intervalo de confiança da média: premissas e alternativas 🟡 M `[Estatística]`

`calcular_intervalo_confianca_media` usa o intervalo *t* de Student, que supõe
observações independentes e média aproximadamente normal. Em dados com forte
assimetria e n pequeno isso é impreciso. Além disso, se a tabela inteira é a
população (não uma amostra), um intervalo de confiança nem faz sentido
conceitual. Considerar *bootstrap* (percentil ou BCa), intervalo da mediana e
um aviso explícito sobre a interpretação.

#### EST-4 · Ampliar e validar a seleção de distribuição 🔴 G `[Estatística]`

`detectar_distribuicao_provavel` compara cinco famílias (normal, uniforme,
exponencial, lognormal, gama) por AIC. Pontos de melhoria:

- Faltam famílias comuns: Weibull, beta (para proporções em [0,1]), Pareto
  (caudas pesadas), *t* de Student, log-logística.
- **Dados inteiros de contagem** deveriam ser comparados com distribuições
  discretas (Poisson, binomial negativa), não com contínuas.
- A distância KS é calculada com parâmetros estimados dos mesmos dados; o
  valor não tem a distribuição usual. Ou se reporta só como medida descritiva
  (como já é feito) ou se usa Lilliefors/*bootstrap* paramétrico.
- Não detecta **bimodalidade/misturas** (teste *dip* de Hartigan, mistura de
  gaussianas com BIC).
- Dados arredondados ou com muitos empates (ex.: preços com centavos) violam a
  premissa de contínuo.
- Comparar AIC com BIC e relatar a sensibilidade da escolha.

#### EST-5 · Outliers: além do IQR ajustado 🔴 G `[Estatística]`

`calcular_outliers` usa IQR, com ajuste por *medcouple* quando a assimetria é
alta (Hubert & Vandervieren). Lacunas:

- Alternativas robustas: MAD / *z* modificado, Hampel.
- **Multivariado**: distância de Mahalanobis com estimador robusto (MCD),
  *Isolation Forest* (implementação própria ou dependência opcional).
- **Contextual**: outlier dentro de cada categoria (ex.: valor alto para a
  região, mas normal no total) e em séries temporais (resíduo de STL).
- Distinguir "outlier estatístico" de "valor sentinela" e de "erro de digitação"
  (hoje são análises separadas e podem se sobrepor).

#### EST-6 · Associação entre colunas: critério, viés e causalidade espúria 🔴 G `[Estatística]`

`analisar_correlacoes` só mantém pares com |Pearson| ≥ 0,7. Problemas:

- Relações **monótonas não lineares** (Spearman alto, Pearson baixo) e
  **não monotônicas** são descartadas. Considerar Spearman/Kendall como critério
  próprio, correlação de distância, informação mútua.
- Nenhum intervalo de confiança nem p-valor; um r = 0,7 com n = 30 é frágil.
- **V de Cramér sem correção de viés**: infla com muitas categorias e poucas
  linhas (correção de Bergsma 2013).
- A razão de correlação filtra por η ≥ 0,7, mas o valor mostrado é η²
  (≥ 0,49). O critério e o número exibido não coincidem.
- Em séries com tendência, correlação alta é frequentemente espúria; avaliar
  correlacionar as diferenças.
- Correlação parcial e paradoxo de Simpson (uma segunda variável explica o par).

#### EST-7 · Teste de Benford com critério mais rigoroso 🟡 M `[Estatística]`

`distribuicao_benford` considera "aderente" quando o maior desvio absoluto entre
frequências é < 0,05, um limite frouxo (5 pontos percentuais). Referências da
literatura (Nigrini) usam o desvio absoluto médio (MAD) com faixas
0,006 / 0,012 / 0,015. Também faltam: verificar se os dados cobrem ao menos 2–3
ordens de grandeza (senão Benford não se aplica e o "não aderente" é falso
alarme), testar o segundo dígito e os dois primeiros, e evitar a conversão para
texto (usar `log10`, muito mais rápido).

#### EST-8 · Estacionariedade e autocorrelação mais completas 🟡 M `[Séries temporais]` `[Estatística]`

- O teste ADF usa só o modelo com constante; faltam tendência (`ct`) e a
  **combinação com KPSS** (hipóteses opostas), que permite distinguir
  "estacionária", "com raiz unitária" e "inconclusivo".
- Ljung-Box usa um único *lag* (`min(10, n//5)`). Reportar vários e o gráfico da
  ACF/PACF.
- Detectar **sazonalidade** (periodograma, ACF nos lags sazonais, decomposição
  STL) e **mudanças de nível** (CUSUM, PELT).
- Teste de tendência de Mann-Kendall.
- Verificar qual ordenação é usada na série (índice da linha ou coluna de data)
  e informar isso no relatório.

#### EST-9 · Uniformidade de categorias: medir concentração, não só qui-quadrado 🟢 M `[Estatística]`

`testar_uniformidade_chi2` pergunta "as categorias são igualmente frequentes?",
raramente a pergunta útil. Acrescentar medidas de concentração: entropia
normalizada, índice de Gini-Simpson, HHI, razão top-1/top-2, e detectar
cauda longa (Zipf). Para amostras pequenas, teste exato multinomial.

#### EST-10 · Histograma com número de faixas adaptativo 🟢 P `[Estatística]`

`calcular_histograma` usa 18 faixas fixas. Usar a regra de Freedman-Diaconis ou
Scott e, para dados muito assimétricos e positivos, oferecer escala logarítmica.

### Estatística descritiva

#### EST-11 · Coeficiente de variação com média negativa 🟢 P `[Estatística]`

`coef_variacao = desvio / média` fica **negativo** quando a média é negativa, e
perde o sentido em escalas de intervalo (temperatura em °C). Usar `|média|`,
omitir quando há valores negativos e documentar a limitação.

#### EST-12 · Sugestão de tipo menor sem perder precisão 🟡 P `[Estatística]` `[Python]`

`sugerir_dtype` recomenda `float32` para toda coluna `float64` decimal e
`category` quando a razão de únicos é ≤ 0,5. `float32` tem ~7 dígitos
significativos: valores monetários grandes ou identificadores armazenados como
decimal perdem precisão. Só sugerir se a conversão ida e volta for exata na
coluna (`np.array_equal`), e para dinheiro sugerir inteiro em centavos ou
`Decimal`. O limite 0,5 da categoria também é arbitrário.

#### EST-13 · Estimar unicidade e cardinalidade em amostras 🔴 M `[Estatística]`

Quando a leitura é amostrada, "chave primária potencial" e a razão de unicidade
são calculadas sobre a amostra. A unicidade na amostra **subestima** a da base
inteira, mas "toda chave candidata" pode ser coincidência. Estudar estimadores
de número de valores distintos (Chao, GEE, *HyperLogLog*) e informar a
incerteza.

#### EST-14 · Análise de valores ausentes 🟡 M `[Estatística]` `[Qualidade de dados]`

Hoje só se conta o percentual de nulos. Faltam:

- **Padrão de ausência entre colunas** (colunas que ficam nulas juntas, matriz de
  coocorrência), que costuma revelar problemas de origem.
- Distinguir MCAR / MAR / MNAR (teste de Little, associação entre "está nulo" e
  outras colunas).
- Sugerir tratamento coerente com o mecanismo.

#### EST-15 · Mudança de distribuição entre versões 🟡 M `[Estatística]`

`_drifts_de_distribuicao` (comando `conferir`) compara só a **mediana** em
unidades de IQR da versão anterior. Não detecta mudança de variância, forma ou
caudas. Para colunas categóricas usa a distância de variação total. Considerar
KS de duas amostras, Wasserstein, PSI (comum em crédito) e tamanho de efeito, e
definir limiares por tamanho de amostra.

#### EST-16 · Datas futuras dependem do relógio da máquina 🟢 P `[Python]`

`perfilar_datas` compara com `pd.Timestamp.now()`: o resultado muda com o dia da
execução (relatórios não reproduzíveis) e comparar uma série com fuso horário
com esse valor sem fuso lança `TypeError` (**verificar**). Receber a data de
referência como parâmetro (com padrão "agora") e tratar `tz`.

---

## 3. Semântica, documentos e dados brasileiros

### BR-1 · CNPJ alfanumérico 🟡 M `[Dados BR]` `[Python]`

A Receita Federal passou a emitir CNPJ com letras e números a partir de julho
de 2026. `patterns.validar_cnpj` e `_digitos` mantêm só dígitos, então o novo
formato é rejeitado ou descaracterizado. O cálculo do dígito verificador usa o
valor ASCII do caractere menos 48. Atualizar a validação, a detecção de padrão,
o mascaramento e `_RE_PII_LIVRE`, mantendo compatibilidade com o formato antigo.

### BR-2 · Mais documentos e identificadores brasileiros 🟢 M `[Dados BR]`

Hoje: CPF e CNPJ. Candidatos, cada um com algoritmo de validação próprio:
PIS/NIS, título de eleitor, CNH, RENAVAM, placa Mercosul, CEP, chave de acesso de
NF-e (44 dígitos, módulo 11), inscrição estadual (varia por UF), código IBGE de
município. Cada um pode ser um PR independente.

### BR-3 · Dados pessoais internacionais e cartões 🟡 M `[Segurança]` `[Qualidade de dados]`

`_RE_PII_LIVRE` só reconhece CPF, CNPJ, e-mail e telefone brasileiro. Faltam
número de cartão (com validação de Luhn), IBAN, passaporte, endereço IP,
coordenadas de GPS e telefones em formato internacional. Mantê-los configuráveis
para não gerar falso positivo.

### BR-4 · Gazetteer de municípios completo 🟢 P `[Dados BR]`

O vocabulário cobre só as 27 capitais. Incluir os municípios do IBGE, com UF
para desambiguar homônimos, sem classificar como localização uma coluna de
nomes de pessoas por coincidência (ex.: "Vitória").

### BR-5 · Cobertura de vocabulários além de RH 🟡 M `[Qualidade de dados]`

As regras de KPI padrão são de RH. Criar pacotes de vocabulário e KPI para
outros domínios (vendas, finanças, saúde, logística, setor público), em YAML,
como exemplos em `examples/` e na documentação de `--vocabularios`.

### BR-6 · Calibrar os pesos da inferência semântica 🔴 G `[Estatística]` `[Qualidade de dados]`

Os números da cascata semântica vêm de julgamento, e o limiar fuzzy de 0,85 é
frouxo ([limitações](TECNICO.md#10-limitações-conhecidas)). Montar um conjunto
rotulado **sintético** de colunas e medir precisão e revocação por categoria
antes de mexer em limiares. Qualquer ajuste deve vir com esses números.

### BR-7 · Inferência por conteúdo, não só por nome 🔴 G `[Python]` `[Qualidade de dados]`

Colunas sem nome útil (`campo1`, `col_7`) dependem só dos valores. Fortalecer os
detectores de conteúdo (formatos, faixas, gazetteers) e medir o ganho contra o
BR-6.

### BR-8 · Detectar unidade e escala de medida 🔴 M `[Estatística]` `[Qualidade de dados]`

Distinguir moeda, percentual (0–1 vs 0–100), quantidade, tempo, e escala de
medida (nominal, ordinal, intervalo, razão). Isso melhora recomendações (ex.:
não somar percentuais, não calcular média de identificadores) e o coeficiente
de variação (EST-11).

---

## 4. Qualidade de dados e score

### QUA-1 · Validar e calibrar o score de qualidade 🔴 G `[Estatística]` `[Qualidade de dados]`

`calcular_score_qualidade` combina dano por coluna (peso 0,85) e dano da tabela
(0,15). Os pesos e as penalidades são julgamento, o que o próprio relatório
admite. Propor: (a) subpontuações por dimensão conhecida (completude,
unicidade, validade, consistência, atualidade; ver ISO/IEC 25012 e DAMA),
(b) análise de sensibilidade aos pesos, (c) faixa de incerteza quando a leitura
foi amostrada.

### QUA-2 · Mais regras de consistência entre colunas 🟡 M `[Qualidade de dados]`

`rules.py` cobre ordem entre datas, nulidade condicional e derivação. Ideias:
UF × município, CEP × UF, idade × data de nascimento, valor total = soma das
partes, status × data de encerramento, intervalos mutuamente exclusivos.

### QUA-3 · Aproximar duplicatas com menos custo 🔴 G `[Python]` `[Qualidade de dados]`

A busca de duplicatas aproximadas usa `rapidfuzz` com limiar fixo de 92 e teto
de 20 mil valores (comparação quadrática). Para bases maiores: *blocking*
(agrupar por prefixo ou som), LSH/MinHash, similaridade fonética para o
português (Soundex adaptado) e limiar adaptativo.

### QUA-4 · Dependências funcionais aproximadas 🔴 M `[Estatística]` `[Python]`

`detectar_dependencias_funcionais` limita a cardinalidade a 500 e busca
dependências exatas em pares de colunas. Em dados reais, erros de digitação
quebram a dependência exata. Estudar a medida *g3* (fração mínima de linhas a
remover) e algoritmos como TANE, além de dependências com mais de uma coluna no
lado esquerdo.

### QUA-5 · Detecção de colunas sensíveis por conteúdo, não só por padrão 🟡 M `[Segurança]` `[Qualidade de dados]`

Hoje um nome só é mascarado se a coluna é classificada como "nome de pessoa".
Colunas de texto livre com nomes, endereços ou e-mails misturados dependem do
detector de PII (BR-3). Avaliar uma lista de nomes e sobrenomes comuns
(gazetteer) para reduzir falsos negativos.

---

## 5. Relações entre tabelas e modelagem

### REL-1 · Relações entre tabelas sem chave explícita 🔴 G `[Qualidade de dados]` `[Estatística]`

`datamodel.detectar_relacionamentos` só considera como destino colunas já
classificadas como chave primária, e compara conjuntos de valores (contenção)
com apoio da similaridade de nomes. Se nenhuma tabela tem chave identificável,
nada é sugerido.

**Proposta.** Etapa opcional de hipóteses de relacionamento que combine nomes
semanticamente parecidos, sobreposição de valores, formatos e cardinalidade. O
resultado deve ser uma sugestão para revisão, não uma relação assumida.

**Guardas.** Não criar `join` automático. Definir limiares, mostrar a confiança
e oferecer validações que reduzam falsos positivos.

**Critério de aceite.** Cada hipótese informa as evidências, a confiança,
exemplos não sensíveis e uma forma de rejeitá-la. Bases sem evidência
suficiente não recebem sugestão. Deve continuar opcional até ser avaliada contra
conjuntos com relações conhecidas.

### REL-2 · Significância da sobreposição entre colunas 🔴 M `[Estatística]`

Duas colunas com valores `1..10` têm contenção de 100% por acaso. Os filtros
atuais (mínimo de distintos, cobertura) são heurísticos. Calcular a
probabilidade de a sobreposição observada ocorrer ao acaso (distribuição
hipergeométrica) e usar como critério adicional, junto de Jaccard e contenção.

### REL-3 · Relações com chave composta e muitos-para-muitos 🔴 G `[Qualidade de dados]`

Existe detecção de chaves compostas (`detectar_relacionamentos_compostos`), mas
não de tabelas associativas (muitos-para-muitos) nem de hierarquias entre
tabelas (autorrelacionamento, como funcionário → gestor).

### REL-4 · Diagrama do modelo de dados 🟡 M `[UX]` `[Python]`

O relatório de modelo lista relações em tabela. Um diagrama (SVG gerado em
Python, sem dependência externa, ou sintaxe Mermaid) ajuda muito a entender
fatos e dimensões.

### REL-5 · Comparar mais de duas versões 🟡 M `[Python]`

`conferir` compara duas extrações; `historico` olha a evolução de métricas.
Unir os dois: cadeia de comparações com a linha do tempo de mudanças de esquema.

---

## 6. Leitura de dados e desempenho

### ING-1 · Mais formatos de entrada 🟢 M `[Python]`

Lê CSV, TSV, Excel (`xlsx`, `xls`, `xlsb`), JSON, JSONL e Parquet. Faltam ODS
(LibreOffice, via `odfpy`), Feather/Arrow IPC, ORC, XML, e CSV com várias
tabelas na mesma planilha.

### ING-2 · Mais fontes de dados 🟡 M `[Python]`

`recon fonte` aceita SQLite e DuckDB. Avaliar PostgreSQL, SQL Server e MySQL
(extras opcionais, com driver separado), planilhas do Google, S3/GCS. Qualquer
fonte remota exige cuidado com credenciais: nunca na linha de comando nem em
log (ver SEG-3).

### ING-3 · Detectar e tratar codificação e separador com mais robustez 🟡 M `[Python]`

Testar arquivos com BOM, UTF-16, separador ambíguo, aspas desbalanceadas,
linhas de comentário e mistura de codificações. Cada caso novo vira um teste
nomeado, como manda o [CONTRIBUTING](../CONTRIBUTING.md).

### ING-4 · Leitura incremental e orçamento de memória 🔴 G `[Python]`

O Recon reserva uma fração da RAM e amostra quando o arquivo é maior. Estudar
leitura por blocos com estatísticas incrementais (média/variância de Welford,
*sketches* para quantis e cardinalidade) para analisar a base inteira sem
carregá-la, em vez de amostrar.

### ING-5 · Paralelização em Windows e macOS 🔴 M `[Python]`

`pipeline._processos_disponiveis` só usa processos com `fork` ou `forkserver`.
Em Windows e macOS (`spawn`), a análise é sempre sequencial. Além disso, cada
coluna é enviada ao processo-filho por *pickle*, o que copia os dados. Avaliar
memória compartilhada ou Arrow e **medir o ganho antes de adotar**.

### ING-6 · Um erro numa coluna não deve derrubar a análise 🟡 M `[Python]`

No caminho paralelo, qualquer exceção em uma coluna cancela tudo e o código cai
para o modo sequencial, repetindo o trabalho. Capturar o erro **por coluna**,
registrar no relatório ("coluna X não pôde ser analisada: motivo") e seguir.

### ING-7 · Reaproveitar resultados entre fases 🔴 G `[Python]`

Chamar as fases isoladas e depois o pipeline recomputa tudo, o que impede uso
incremental da API. Cachear estatísticas por coluna no `DataProfiler`.

### ING-8 · Reduzir cópias de memória nas estatísticas por coluna 🟡 M `[Python]`

`analisar_estatisticas` faz `value_counts` na coluna toda, `astype(str)` e
`str.len()` sobre todas as linhas, e `unique().tolist()`. Em bases grandes isso
multiplica o uso de memória. Medir com `tracemalloc` e trabalhar sobre a
amostra quando o resultado não exigir a coluna inteira.

### ING-9 · Avaliar Polars/PyArrow como motor 🔴 G `[Python]`

Pesquisa: o pandas é a base de todo o código. Medir o custo/benefício de um
caminho com Polars ou DuckDB para leitura e agregações pesadas, sem reescrever
a API.

---

## 7. Código gerado e exportação

### GEN-1 · Testar o script gerado de verdade 🟢 M `[Python]`

`codegen.py` tem 58% de cobertura e gera scripts de limpeza e pseudonimização.
Executar o script gerado sobre dados fictícios e conferir o resultado,
incluindo a exigência de `RECON_PSEUDONYMIZATION_KEY`.

### GEN-2 · Pseudonimização: revisar o desenho 🔴 M `[Segurança]` `[Estatística]`

O script usa HMAC-SHA256 com chave de ambiente, o que é correto. Pontos para
discutir: (a) valores de baixa entropia (CPF tem ~10⁹ combinações) continuam
vulneráveis a ataque por dicionário se a chave vazar; (b) tamanho da saída e
colisões; (c) preservar formato; (d) risco de reidentificação por combinação de
colunas (k-anonimato, l-diversidade).

### GEN-3 · Mais destinos para a limpeza gerada 🟡 M `[Python]`

Hoje: pandas, SQL e Power Query. Candidatos: Polars, dbt (modelo SQL), e
*notebook* Jupyter com a limpeza comentada.

### GEN-4 · Exportar o contrato para outros formatos 🔴 M `[Qualidade de dados]`

O contrato é YAML próprio. Estudar a exportação para esquemas conhecidos
(Frictionless Data / Table Schema, Open Data Contract Standard, JSON Schema).
A geração de asserções para dbt e Great Expectations está
[fora de escopo](#14-fora-de-escopo); o formato aberto é a alternativa.

---

## 8. Relatórios

### REP-1 · Acessibilidade do relatório HTML 🟡 M `[UX]`

O HTML já tem `lang="pt-BR"`, papéis ARIA e tema escuro. Falta uma auditoria
(axe, Lighthouse): contraste, ordem de foco, descrição textual dos gráficos SVG,
tabela com `<caption>`, navegação só por teclado, `prefers-reduced-motion`.

### REP-2 · Relatório em inglês e outros idiomas 🟡 G `[Docs]` `[Python]`

Todo o texto está em português, embutido no código. Extrair as mensagens para
um catálogo (gettext ou dicionários) e oferecer `--idioma en`. Abre o projeto
para quem não lê português. Combina com DOC-3.

### REP-3 · Mais gráficos 🟡 M `[Estatística]` `[UX]`

Hoje: histograma, barras, série mensal, SVG próprio. Ideias: gráfico Q-Q,
*box plot*, mapa de calor de correlação e de nulos, ACF, gráfico de Benford.
Cuidado com honestidade visual (eixos, escala) e acessibilidade.

### REP-4 · Relatório de comparação entre tabelas mais legível 🟡 M `[UX]`

Os relatórios de lote, modelo e conferência são densos. Pesquisar com quem usa:
quais perguntas as pessoas querem responder primeiro? Priorizar o resumo.

### REP-5 · Saída em novos formatos 🟢 M `[Python]`

Excel formatado com os principais achados, CSV dos alertas (para filtrar),
e JSON com esquema publicado (`jsonschema`) para integração.

### REP-6 · Esquema estável e versionado do JSON 🟡 M `[Python]` `[Docs]`

O contrato de saída está em [TECNICO.md](TECNICO.md#5-contrato-de-saída-json).
Publicar um JSON Schema versionado e testar que o payload o respeita, para que
integrações não quebrem sem aviso.

---

## 9. Interface gráfica e linha de comando

### UI-1 · Aposentar a interface Tk legada 🟡 M `[Python]`

`gui.py` (1.149 linhas) é a interface antiga, mantida por compatibilidade, e o
`Recon.pyw` ainda a usa para exibir erros. A interface atual é a Qt
(`gui_qt.py`). A manutenção em dobro aumenta a superfície de testes
(`tests/test_gui.py` exige `tkinter`, que não vem em toda distribuição Linux).
Remover `gui.py` e `test_gui.py`, trocar o `tkinter` do `Recon.pyw` por mensagem
de erro em PySide6 e registrar no CHANGELOG.

### UI-2 · Cancelar uma análise em andamento 🟡 M `[UX]` `[Python]`

A análise roda numa thread separada, mas não há botão para cancelar. Em bases
grandes, a pessoa só pode fechar a janela. Exige cancelamento cooperativo no
pipeline (verificar um sinal entre colunas).

### UI-3 · Barra de progresso com etapas 🟢 M `[UX]`

A barra reflete o `tqdm`. Mostrar também a etapa em linguagem simples
("Lendo o arquivo", "Analisando colunas", "Gerando relatório") e o tempo
estimado.

### UI-4 · Pré-visualização dos dados antes de analisar 🟡 M `[UX]`

Mostrar as primeiras linhas, o cabeçalho detectado e o separador, com opção de
corrigir (`--linha-cabecalho` na interface), antes de rodar a análise completa.

### UI-5 · Acessibilidade e usabilidade da janela 🟡 M `[UX]`

Os campos já têm nomes acessíveis. Revisar com leitor de tela (NVDA, Orca),
navegação por Tab, alto contraste, fonte escalável e janelas pequenas. Testes
manuais documentados valem como contribuição.

### UI-6 · Mensagens de erro compreensíveis 🟢 M `[UX]` `[Docs]`

Erros de leitura mostram exceções do pandas. Mapear os mais comuns (arquivo
aberto no Excel, senha, codificação, aba inexistente) para mensagens que
dizem o que fazer.

### UI-7 · Persistir preferências da janela 🟢 P `[Python]`

Lembrar a última pasta, o modo de análise e a pasta de saída (`QSettings`).

### UI-8 · Autocompletar e ajuda na linha de comando 🟢 P `[Python]`

O Typer suporta *shell completion* (`--install-completion`). Documentar, e
revisar os textos de `--help` para um iniciante.

### UI-9 · Modo `--json` para uso em scripts 🟡 M `[Python]`

Opção que imprime o resultado resumido em JSON no *stdout* e os logs em
*stderr*, com códigos de saída claros (0 ok, 1 erro, 2 alertas críticos), para
uso em CI.

---

## 10. Distribuição e instalação

### DEV-1 · Executável para Windows (`.exe`) para quem não usa Python 🔴 G `[DevOps]` `[Python]`

Evolução natural para o público não técnico: baixar, instalar e abrir a
janela, sem terminal. Caminho proposto, em duas etapas:

1. **Build experimental** (PyInstaller, modo `--onedir`, sem console) gerado na
   CI em `windows-latest`, só como artefato, para medir tamanho e conferir se a
   janela abre numa máquina limpa.
2. **Instalador** (Inno Setup, `Recon-Setup.exe`) publicado automaticamente numa
   Release a cada tag `v*`, com SHA-256.

Pontos de atenção:

- **WeasyPrint no Windows** depende de bibliotecas GTK/Pango que não vêm com o
  pip. Opções: empacotar as DLLs, gerar o PDF pelo Qt (`QPrinter`), ou deixar o
  PDF fora do `.exe` e manter o HTML. Testar primeiro a do Qt.
- **Tamanho**: pandas, scipy, statsmodels, pyarrow, duckdb e PySide6 juntos dão
  algumas centenas de MB. Medir antes de otimizar.
- **SmartScreen e antivírus**: sem assinatura, o Windows avisa "editor
  desconhecido". Ver DEV-3. Evitar `--onefile` (mais falsos positivos e abertura
  lenta).
- **PySide6 é LGPL**: compatível com MIT desde que as bibliotecas Qt fiquem como
  arquivos separados (`--onedir`), com aviso de licenças de terceiros
  (`THIRD_PARTY_LICENSES.txt` gerado no build).
- **Multiprocessing**: precisa de `multiprocessing.freeze_support()` no ponto de
  entrada, ou o `.exe` abre várias janelas.
- Criar um ponto de entrada próprio (`recon_app.py`) que abre a Qt direto, sem
  passar por `Recon.pyw` (ver UI-1). Converter `assets/recon.svg` em `.ico`.

### DEV-2 · Publicar no PyPI 🔴 M `[DevOps]`

Fluxo de release com GitHub Actions e *trusted publishing*, para `pip install`
funcionar sem clonar o repositório. Antes: verificar se o nome está livre,
decidir a política de versões (SemVer) e quem publica.

### DEV-3 · Assinatura de código e proveniência do build 🟡 M `[DevOps]` `[Segurança]`

- Assinar o `.exe` (SignPath Foundation para open source, ou Azure Trusted
  Signing).
- Publicar com *build provenance* (`actions/attest-build-provenance`).
- Usar `pip-compile --generate-hashes` para o lock exigir hashes e o `pip
  install --require-hashes` na CI.

### DEV-4 · Instalador/atalho para Windows e macOS 🟡 P `[DevOps]`

`instalar-atalho.sh` cobre Linux e macOS. Criar `instalar-atalho.ps1` para o
Windows. Se o DEV-1 sair, vira desnecessário no Windows.

### DEV-5 · Imagem Docker e Flatpak/AppImage 🟡 M `[DevOps]`

Docker para uso em servidores e pipelines (modo linha de comando), e AppImage ou
Flatpak para a janela no Linux.

### DEV-6 · Matriz de CI mais ampla 🟢 P `[DevOps]`

A CI roda em Ubuntu com Python 3.12–3.14. Acrescentar Windows e macOS, pelo
menos para os testes que não dependem de Qt/Chromium, para pegar problemas de
caminho, codificação e `fork` cedo.

### DEV-7 · Fazer o Dependabot atualizar o lock junto 🟡 P `[DevOps]`

O Dependabot altera só o `pyproject.toml`: ele não reconhece `requirements-dev.lock`
como arquivo de requisitos. Desde 2026-11-22 a CI falha se os dois divergirem
(`scripts/verificar_lock.py`), mas o lock ainda é regenerado à mão. Avaliar renomear
para `requirements-dev.txt` (nome que o Dependabot entende) ou uma ação que rode o
`pip-compile` no PR do Dependabot.

---

## 11. Qualidade do código e testes

### COD-1 · Cobertura nos módulos fracos 🟢 M `[Python]`

Total de 79% (piso da CI: 75%), mas há módulos abaixo: `reporting/_conferencia.py`
(54%), `codegen.py` (58%), `cli.py` (63%) e `__main__.py` (0%). Testes de
comportamento, não só de execução. Quando chegarem a 80%, subir o piso da CI.

### COD-2 · Testes baseados em propriedades 🟡 M `[Python]` `[Estatística]`

Usar a biblioteca `hypothesis` para propriedades que deveriam valer sempre:
a análise não quebra com qualquer `DataFrame`, o score fica em [0, 100], a
máscara nunca devolve o valor original, a análise é determinística. É a forma
mais eficiente de achar bugs como os de SEG-1 e EST-16.

### COD-3 · Verificar os resultados estatísticos contra referências 🟡 M `[Estatística]`

Comparar a saída de `hypothesis.py` com exemplos publicados (R, livros,
documentação do SciPy) em testes de regressão numéricos com tolerância.

### COD-4 · Reduzir `except Exception` 🟡 M `[Python]`

Há 20 capturas genéricas (`ingestion.py`, `hypothesis.py`, `relationships.py`,
`pipeline.py`). Algumas são legítimas (biblioteca externa lança vários tipos),
mas várias escondem falhas: `calcular_outliers` troca erro do *medcouple* por
`mc = 0.0` sem avisar. Registrar um aviso (`logger.debug`) e capturar o tipo
específico quando possível.

### COD-5 · Funções muito longas 🟡 M `[Python]`

`statistics.analisar_estatisticas` (≈250 linhas, `if/elif` por tipo),
`pipeline._processar_dataframe` e `datamodel.py` (1.087 linhas) são difíceis de
testar por partes. Separar por tipo de coluna (numérica, data, texto, booleana)
sem mudar o comportamento, apoiado pelos testes existentes.

### COD-6 · Configuração tipada e documentada 🟡 M `[Python]`

`config.py` (708 linhas) é só dado, mas os limiares não explicam de onde vêm.
Agrupar em *dataclasses* congeladas, com comentário de origem e unidade, e
permitir sobrescrever por YAML (`--limiares`).

### COD-7 · Injetar o relógio e a semente aleatória 🟢 P `[Python]`

`Timestamp.now()` e `random_state=42` espalhados dificultam teste e
reprodutibilidade. Centralizar em um parâmetro do `DataProfiler`.

### COD-8 · Testes de desempenho e de memória 🟡 M `[Python]`

Existem medições na documentação, mas não testes. Um *benchmark* pequeno na CI
(pytest-benchmark) com limite folgado detecta regressões grosseiras.

### COD-9 · Dependências: reduzir o peso 🔴 M `[Python]`

O `pyproject.toml` fixa 20 dependências de execução, várias pesadas
(`statsmodels` só para ADF, Ljung-Box e `medcouple`; `weasyprint` só para PDF;
`duckdb` só para uma fonte). Avaliar extras opcionais (`recon[pdf]`,
`recon[duckdb]`) e implementação própria do que for pequeno. Menos dependências
significam menos CVEs e instalação mais rápida.

### COD-10 · Documentar decisões de arquitetura 🟢 P `[Docs]`

Registros curtos de decisão (ADR) em `docs/decisoes/` para o que hoje só está
nos comentários: por que versões exatas, por que sem banco, por que interface
só local.

---

## 12. Documentação e comunidade

### DOC-1 · Tutorial com dados fictícios, passo a passo 🟢 M `[Docs]`

Um tutorial que usa o `examples/gerar_demo.py` e explica cada seção do
relatório com imagens, para quem nunca viu um *profiling*.

### DOC-2 · Explicar cada análise para quem não é de estatística 🟡 M `[Docs]` `[Estatística]`

Um glossário (assimetria, curtose, p-valor, ADF, Benford) em linguagem simples,
com link a partir do relatório HTML. Quem entende de estatística e gosta de
escrever ajuda muito aqui.

### DOC-3 · Documentação em inglês 🟡 M `[Docs]`

README, CONTRIBUTING e guia em inglês, para atrair contribuições de fora do
Brasil. Veja também REP-2.

### DOC-4 · Corrigir texto sobre o uso de memória 🟢 P `[Docs]`

O README diz que o Recon "reserva 30% da RAM disponível", mas
`ingestion._FRACAO_RAM_SEGURA = 0.70` e a mensagem do relatório diz "70% da RAM
disponível". Provavelmente o texto quer dizer "deixa 30% livres"; deixar claro.

### DOC-5 · Manter o guia do código fora do `.gitignore` 🟢 P `[Docs]`

O `.gitignore` lista `docs/GUIA_DO_CODIGO.md` como "anotações pessoais", mas o
README chegou a linkar o arquivo. Escrever uma versão pública: um passeio de
uma página pelo caminho de uma coluna no `pipeline`, para quem vai ler o código
pela primeira vez.

### DOC-6 · Site de documentação 🟡 M `[Docs]` `[DevOps]`

MkDocs Material ou Sphinx no GitHub Pages, com a documentação técnica, o
backlog e o histórico de versões.

### DOC-7 · Conjuntos de dados sintéticos de teste 🟢 M `[Qualidade de dados]`

Conjuntos fictícios com problemas conhecidos (nulos em padrão, CPF inválido,
datas trocadas, chaves órfãs) e o resultado esperado, úteis para testes,
exemplos e para avaliar BR-6 e REL-1. **Nunca** com dados reais.

### DOC-8 · Atualizar o CHANGELOG por versão 🟢 P `[Docs]`

O CHANGELOG descreve marcos, não versões, e remete a `git log`. Adotar
[Keep a Changelog](https://keepachangelog.com/pt-BR/) para facilitar quem
atualiza o pacote.

---

## 13. Ideias para o futuro

Sem prioridade nem prazo. Boas para discussões e pesquisa.

- **Perfil incremental** que atualiza o relatório quando chega uma extração
  nova, sem reprocessar tudo (ligado a ING-4 e ING-7).
- **Detecção de anomalias entre extrações** (volume, esquema, distribuição) com
  alertas por limiar, dentro do que o comando `historico` já faz.
- **Sugestão de modelo dimensional** (estrela/floco de neve) a partir das
  relações detectadas (REL-1, REL-3).
- **Plugins**: permitir detectores semânticos, regras de qualidade e formatos
  de saída externos, descobertos por *entry points*.
- **Rotulagem assistida**: interface para a pessoa corrigir a classificação
  semântica de uma coluna e salvar como vocabulário (hoje existe
  `revisar-semantica` por YAML) alimentando BR-6.
- **Explicações em linguagem natural** geradas por modelos de regras (sem
  serviço externo, mantendo o princípio local), como "esta coluna parece uma
  data de nascimento porque...".
- **Qualidade de dados geoespaciais** (coordenadas fora do país, inversão de
  latitude e longitude).
- **Dados em texto**: idioma, comprimento, repetição de modelos, spam.

---

## 14. Fora de escopo

Decisões registradas em [TECNICO.md](TECNICO.md#11-fora-de-escopo-decisão-explícita).
Mudar alguma delas pede uma discussão aberta antes:

- monitoramento contínuo de drift (o `historico` compara extrações dadas
  explicitamente);
- geração de asserções para dbt ou Great Expectations;
- integrações externas de modelagem. A inferência é determinística para manter a
  ferramenta local e compatível com máquinas corporativas restritas.

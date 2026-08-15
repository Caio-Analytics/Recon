# Recon — Guia de comandos

Referência rápida. Para o que a ferramenta faz, veja o `README.md`; para como
funciona por dentro, `docs/TECNICO.md`.

---

## Não quer decorar nada?

```bash
recon
```

Sem argumento nenhum, abre um menu que pergunta onde estão os arquivos, o que
você quer fazer e onde salvar. Dar Enter em tudo funciona. É o caminho
recomendado para quem usa a ferramenta esporadicamente.

O resto deste documento é para quem prefere digitar o comando direto.

---

## Qual comando usar?

| Sua situação | Comando |
|---|---|
| Não quero pensar em nada | `recon` (menu interativo) |
| Tenho **uma pasta** e quero direto | `recon pasta ./dados` |
| Tenho **um arquivo** e quero tudo sobre ele | `recon perfilar arquivo.csv` |
| Tenho **vários arquivos** e quero saber por onde começar | `recon lote *.csv` |
| Tenho **vários arquivos que se relacionam** | `recon modelar a.csv b.csv c.csv` |

Na dúvida, use `pasta`: ele conta os arquivos e decide (ou pergunta).

---

## `pasta` — o atalho

Lê uma pasta inteira e escolhe o modo sozinho.

```bash
recon pasta ./extracoes --saida ./relatorios
```

- **1 arquivo** → perfil individual, automático.
- **Vários arquivos** → pergunta no terminal: lote, modelo ou individual.
- `--sim` aceita a sugestão (lote) sem perguntar — útil em script.

```bash
recon pasta ./dados --saida ./out --sim              # direto pro lote
recon pasta ./dados --modo modelo                    # força o cruzamento
recon pasta ./dados --modo individual --gerar-limpeza
```

| Opção | O que faz |
|---|---|
| `--saida PASTA` | onde gravar os relatórios (padrão: pasta atual) |
| `--modo` | `auto` (padrão), `individual`, `lote`, `modelo` |
| `--sim` / `-s` | não pergunta nada |

---

## `perfilar` — um arquivo, em profundidade

```bash
recon perfilar vendas.csv
```

Gera `profiler_output_vendas.html` (clique e abre no navegador) e
`profiler_output_vendas.json`.

O relatório traz, por coluna: tipo real, semântica inferida com a trilha de
evidência, completude, distribuição em gráfico, outliers, testes estatísticos,
sujeira detectada e recomendação de ETL. Mais, no nível da tabela:
score de qualidade, dependências funcionais, correlações, regras de negócio,
hierarquias e análise temporal.

```bash
recon perfilar planilha.xlsx --todas-abas            # um relatório por aba
recon perfilar planilha.xlsx --aba 2                 # só a aba de índice 2
recon perfilar vendas.csv --gerar-limpeza            # emite o script pandas
recon perfilar vendas.csv --formatos json,markdown   # Markdown no lugar do HTML
recon perfilar vendas.csv --saida-base relatorios/q1
```

---

## `lote` — vários arquivos, comparados

```bash
recon lote dados/*.csv dados/*.xlsx
```

A saída principal é **um HTML só**, ordenado do pior para o melhor arquivo,
com o pior já aberto. A pergunta do lote é por onde começar, e ela se responde
comparando — não abrindo doze abas.

Se um arquivo falhar, o lote continua e reporta a falha no fim.

```bash
recon lote dados/*.csv --sem-consolidado    # só os relatórios individuais
```

---

## `modelar` — como as tabelas se ligam

```bash
recon modelar empregados.csv treinamentos.csv cursos.csv
recon modelar base_completa.xlsx            # cada aba vira uma tabela
```

Descobre chaves estrangeiras, classifica cada tabela como fato ou dimensão,
mede integridade referencial e granularidade, monta o diagrama ER e sugere
análises cruzadas **com código pandas e SQL prontos**.

```bash
recon modelar *.csv --sem-perfis      # só o relatório do conjunto
```

---

## Opções comuns a todos

| Opção | Padrão | Para quê |
|---|---|---|
| `--formatos` | `json,html` | `json`, `markdown`, `html`, `parquet`, separados por vírgula |
| `--saida-base` | `profiler_output` | prefixo dos arquivos gerados |
| `--json-compacto` | desligado | JSON sem indentação, menor para colar em prompt |
| `--limite-amostra` | `2000000` | teto de linhas analisadas; acima disso usa amostra |
| `--kpis` | regras de RH | YAML com regras de gap analysis próprias |
| `--gerar-limpeza` | desligado | emite um `.py` que aplica as recomendações |
| `--linha-cabecalho` | detecta | força a linha do cabeçalho (0 = primeira) |
| `--sem-deteccao-layout` | desligado | lê o arquivo cru, sem ajustar layout |

`recon versao` mostra a versão instalada.
`recon <comando> --help` mostra a ajuda de cada um.

---

## Receitas

**Recebi uma pasta e não sei o que tem nela**
```bash
recon pasta ./recebidos --saida ./analise
```

**Preciso entregar um relatório para alguém que não é técnico**
```bash
recon perfilar base.xlsx
```
Mande o `.html`. Abre em qualquer navegador, sem instalar nada.

**Quero começar a limpeza com meio caminho andado**
```bash
recon perfilar base.csv --gerar-limpeza
```
Revise o `_limpeza.py` gerado e rode.

**Quero colar o perfil num prompt de IA**
```bash
recon perfilar base.csv --formatos json --json-compacto
```

**Meu Excel tem título e linha de total atrapalhando**

Não precisa fazer nada — o Recon detecta e avisa no relatório. Se errar:
```bash
recon perfilar base.xlsx --linha-cabecalho 4
```

**As regras de KPI não são de RH**
```yaml
# kpis_financeiro.yaml
kpis:
  - id: KPI_FIN_001
    nome: Receita por Região
    semanticas: [Valor Financeiro, Localização Geográfica]
```
```bash
recon perfilar vendas.csv --kpis kpis_financeiro.yaml
```

**O arquivo é gigante e quero uma primeira olhada rápida**
```bash
recon perfilar enorme.csv --limite-amostra 200000
```
O relatório avisa que houve amostragem: unicidade e duplicata passam a valer
para a amostra, não para a tabela inteira.

# Guia de uso do Recon

## Qual caminho escolher?

| Situação | Caminho recomendado |
|---|---|
| Você prefere escolher arquivos numa janela | [Interface gráfica](#pela-interface-gráfica) |
| Você tem um CSV, Excel, JSON ou Parquet | [Terminal](#pelo-terminal) |
| Você usa siglas ou nomes próprios da área | [Vocabulário do seu negócio](#vocabulário-do-seu-negócio) |
| Você recebe a mesma base todo mês | [Contratos de dados](#contratos-de-dados) |
| Você quer experimentar sem abrir uma base real | [Demonstração segura](#demonstração-segura) |

## Pela interface gráfica

Com o ambiente virtual ativo, execute `recon janela`. Na primeira tela, escolha um objetivo:

1. **Analisar arquivos** gera um perfil separado para cada arquivo selecionado.
2. **Comparar arquivos em lote** ajuda a priorizar bases com mais problemas.
3. **Entender relações entre tabelas** procura chaves, fatos e dimensões.
4. **Conferir duas versões** compara uma extração anterior com a nova.
5. **Acompanhar histórico de qualidade** mostra a evolução de várias extrações, na ordem escolhida.

Depois, adicione os arquivos, escolha a pasta de saída e clique em **Analisar agora**. O relatório HTML abre em qualquer navegador.
Marque **PDF** quando precisar de uma cópia estática para anexar, imprimir ou guardar em processo. Use o HTML para explorar filtros e detalhes.
Se sua área usa siglas ou campos próprios, escolha também o YAML de vocabulário nessa tela. Ele vale apenas para a execução atual.

## Pelo terminal

```bash
recon perfilar dados.csv
recon lote janeiro.csv fevereiro.csv
recon modelar vendas.csv clientes.csv produtos.csv
recon historico jan.csv fev.csv mar.csv
recon conferir extracao_anterior.csv extracao_nova.csv
recon dicionario vendas.csv clientes.csv
```

Os arquivos devem ser informados no histórico em ordem cronológica. O resultado mostra volume, score, nulos, recomendações e alertas de queda de qualidade entre extrações.

## Fontes suportadas

Arquivos CSV, TSV, TXT, Excel, JSON e Parquet podem ser analisados. Para uma pasta com várias extrações, use:

```bash
recon pasta ./extracoes --modo auto
```

### Bancos locais, APIs e arquivos em nuvem

CSV, JSON e Parquet publicados por HTTPS podem ser perfilados diretamente, inclusive links assinados de S3, Azure Blob ou Google Cloud Storage:

```bash
recon perfilar "https://servidor.exemplo/export/vendas.csv?assinatura=..."
```

Para banco local, use uma consulta somente de leitura. SQLite e DuckDB são suportados sem cadastrar credenciais:

```bash
recon fonte sqlite:///dados/vendas.db --sql "SELECT * FROM vendas"
recon fonte duckdb:///dados/lake.duckdb --sql "SELECT * FROM fatos_venda"
```

Não inclua tokens, senhas ou strings de conexão de servidores remotos em relatórios ou no Git.

## Vocabulário do seu negócio

Use um YAML local para acrescentar termos próprios ao Recon:

```yaml
categorias_fuzzy:
  Operação Portuária: [navio, atracacao, berco, conteiner]
```

Informe o arquivo no comando:

```bash
recon perfilar dados.csv --vocabularios meu-dominio.yaml
```

O parâmetro também está disponível nos comandos que analisam uma base: perfil, lote, modelo, pasta, conferência, histórico, contrato, validação e dicionário.

## Contratos de dados

Crie um ponto de referência:

```bash
recon contrato dados.csv --saida contrato.yaml
```

O YAML pode ser editado para definir nulos máximos, faixas numéricas, valores novos permitidos e severidade de cada tipo de violação. Valide a próxima extração com:

```bash
recon validar dados_novos.csv --contrato contrato.yaml
```

Se o contrato foi criado a partir de uma amostra, o Recon não infere automaticamente unicidade, domínio fechado nem faixas numéricas: confirme essas regras na base inteira antes de torná-las obrigatórias.

## Onde ficam os resultados?

O HTML é a melhor opção para leitura e exploração. JSON e Parquet atendem integrações e ferramentas de dados; Markdown ajuda em revisões textuais. O comando informa a pasta e os arquivos gerados ao concluir. Trate qualquer relatório como documento interno: nomes de colunas e metadados podem revelar contexto corporativo.

## Demonstração segura

`examples/gerar_demo.py` cria uma base fictícia e relatórios em `Output/demo/`. É uma forma segura de explorar a interface e o HTML antes de usar dados da organização.

# Guia de uso do Recon

## Pela interface gráfica

Com o ambiente virtual ativo, execute `recon janela`. Na primeira tela, escolha um objetivo:

1. **Analisar arquivos** gera um perfil separado para cada arquivo selecionado.
2. **Comparar arquivos em lote** ajuda a priorizar bases com mais problemas.
3. **Entender relações entre tabelas** procura chaves, fatos e dimensões.
4. **Conferir duas versões** compara uma extração anterior com a nova.
5. **Acompanhar histórico de qualidade** mostra a evolução de várias extrações, na ordem escolhida.

Depois, adicione os arquivos, escolha a pasta de saída e clique em **Analisar agora**. O relatório HTML abre em qualquer navegador.
Se sua área usa siglas ou campos próprios, escolha também o YAML de vocabulário nessa mesma tela; ele vale apenas para aquela execução.

## Pelo terminal

```bash
recon perfilar dados.csv
recon lote janeiro.csv fevereiro.csv
recon modelar vendas.csv clientes.csv produtos.csv
recon historico jan.csv fev.csv mar.csv
```

Os arquivos devem ser informados no histórico em ordem cronológica. O resultado mostra volume, score, nulos, recomendações e alertas de queda de qualidade entre extrações.

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

### Bancos locais, APIs e arquivos em nuvem

CSV, JSON e Parquet publicados por HTTPS podem ser perfilados diretamente — isso inclui links assinados de S3, Azure Blob ou Google Cloud Storage:

```bash
recon perfilar "https://servidor.exemplo/export/vendas.csv?assinatura=..."
```

Para banco local, use uma consulta somente de leitura. SQLite e DuckDB são suportados sem cadastrar credenciais:

```bash
recon fonte sqlite:///dados/vendas.db --sql "SELECT * FROM vendas"
recon fonte duckdb:///dados/lake.duckdb --sql "SELECT * FROM fatos_venda"
```

Não coloque tokens, senhas ou strings de conexão de servidores remotos no relatório nem no Git.

O mesmo parâmetro está disponível em todos os comandos que analisam uma base: perfil, lote, modelo, pasta, conferência, histórico, contrato, validação e dicionário. O vocabulário vale somente para aquela execução.

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

## Demonstração segura

`examples/gerar_demo.py` cria uma base fictícia e relatórios em `Output/demo/`. É uma forma segura de explorar a interface e o HTML antes de usar dados da organização.

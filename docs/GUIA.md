# Guia de uso do Recon

## Pela interface gráfica

Com o ambiente virtual ativo, execute `recon janela`. Na primeira tela, escolha um objetivo:

1. **Analisar arquivos** gera um perfil separado para cada arquivo selecionado.
2. **Comparar arquivos em lote** ajuda a priorizar bases com mais problemas.
3. **Entender relações entre tabelas** procura chaves, fatos e dimensões.

Depois, adicione os arquivos, escolha a pasta de saída e clique em **Analisar agora**. O relatório HTML abre em qualquer navegador.

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

O mesmo parâmetro está disponível nos modos de lote, modelo, pasta e histórico. O vocabulário vale somente para aquela execução.

## Contratos de dados

Crie um ponto de referência:

```bash
recon contrato dados.csv --saida contrato.yaml
```

O YAML pode ser editado para definir nulos máximos, faixas numéricas, valores novos permitidos e severidade de cada tipo de violação. Valide a próxima extração com:

```bash
recon validar dados_novos.csv --contrato contrato.yaml
```

## Demonstração segura

`examples/gerar_demo.py` cria uma base fictícia e relatórios em `Output/demo/`. É uma forma segura de explorar a interface e o HTML antes de usar dados da organização.

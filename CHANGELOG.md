# Changelog

Resumo de alto nível da evolução do Recon, por tema (não por versão — consulte
`git log` para o histórico completo de commits).

## Fundação (Fase 1)

- Cria a arquitetura inicial de profiling de dados, com o scaffolding do pacote e as taxonomias e limiares consolidados numa fonte única.

## Perfilamento por coluna

- Leitura de arquivos com exceções tipadas, inferência semântica por fuzzy matching e estatística descritiva por coluna.

## Testes de hipótese e qualidade

- Testes de hipótese por coluna, dependências funcionais, gap analysis e recomendações de ETL; exportação em JSON, Parquet e Markdown.

## Primeiros comandos de CLI

- Comandos `perfilar` e `lote` no CLI, unificação das exceções de ingestão e remoção dos pipelines legados.


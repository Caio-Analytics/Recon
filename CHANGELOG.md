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

## Datas, CPF/CNPJ e leitura mais robusta

- Interpretação de datas brasileiras (dia primeiro), detecção de CPF/CNPJ armazenados como número e análise temporal para datas em texto.

## Robustez estatística e renomeação para datascope

- Protege o Shapiro-Wilk contra série constante, valida documentos e sujeira de conteúdo, sobe o piso para Python 3.12 e renomeia o pacote de `data_profiler` para `datascope`.

## Arquitetura v3: relações, regras e modelo de dados

- Detecção de layout de planilha feita à mão, relações entre colunas, regras de negócio, modelo de dados multi-tabela e a cascata de evidências semânticas.

## Relatório HTML e reescrita do núcleo

- Relatório HTML com detalhe por coluna, núcleo reescrito sobre os novos módulos e suíte de testes com regressão para cada bug corrigido.

## Usabilidade (Fase 5)

- Gráficos SVG por coluna, relatório consolidado de lote, menu interativo e comando de pasta.

## Renomeação para Recon e paridade HTML/Markdown

- Correção do score de qualidade, paridade entre relatório HTML e Markdown, e renomeação do pacote de `datascope` para `recon`.

## Documentação completa

- Guia de instalação sem permissão de administrador, referência de comandos, documentação técnica e cobertura de testes para gráficos, lote e menu.

## Correções de classificação semântica

- Ajustes de classificação semântica validados contra bases reais de RH e vendas, e leitura de arquivos comprimidos, TSV/TXT e Parquet.


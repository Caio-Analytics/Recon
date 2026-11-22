# Histórico de mudanças

Todas as mudanças relevantes do Recon são registradas aqui. O formato segue o
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem o
[Versionamento Semântico](https://semver.org/lang/pt-BR/).

Para o detalhe de cada alteração, consulte o `git log`. Para o que ainda não foi
feito, veja o [backlog](docs/BACKLOG.md).

## [Não lançado]

Nada ainda.

## [3.0.0] - 2026-11-22

Primeira versão publicada. Reúne a reescrita do núcleo (agosto de 2026), a interface
gráfica, os novos formatos e fontes de dados (setembro de 2026) e a abertura do
projeto para contribuições (novembro de 2026).

### Licença e comunidade

- A licença passa de CC BY-NC 4.0 para **MIT**, permitindo uso comercial e contribuições.
- Novo guia de contribuição completo, código de conduta, modelos de issue e de pull
  request, e política de segurança com relato privado de vulnerabilidades.
- Backlog reorganizado por área e por conhecimento exigido, com itens para quem
  entende de estatística, dados brasileiros, interface e infraestrutura.
- Dependabot mensal e agrupado, com espera de 14 dias para versões novas.
- O pacote passa a se chamar `recon-data-profiler` (o comando continua `recon` e o
  `import` continua `recon`).

### Adicionado

- **Análise de arquivos e tabelas**
  - Perfil por coluna: tipo real, nulos, unicidade, distribuição, estatísticas
    descritivas e testes de hipótese (normalidade, uniformidade, estacionariedade,
    autocorrelação, distribuição provável, Benford).
  - Detecção de layout de planilhas feitas à mão: cabeçalho real, linha de total,
    células mescladas e blocos.
  - Leitura de CSV, TSV, TXT, Excel (`xlsx`, `xls`, `xlsb`), JSON, Parquet, arquivos
    comprimidos, bancos locais SQLite e DuckDB, e URLs HTTPS.
  - Amostragem controlada pela memória disponível, com a cobertura registrada no relatório.
- **Semântica e dados brasileiros**
  - Inferência semântica por cascata de evidências, com vocabulários por domínio e
    revisão por YAML.
  - Validação de CPF e CNPJ, datas com o dia primeiro, números no formato `1.234,56` e
    detecção de dado pessoal conforme a LGPD, com mascaramento nos relatórios.
  - Exposição de dado pessoal como métrica própria e detecção de duplicatas
    aproximadas de pessoas.
- **Relações e modelo de dados**
  - Dependências funcionais, redundância entre colunas, chaves compostas e chaves com
    valores ausentes, correlações e hierarquias.
  - Modelo de dados multi-tabela: chaves estrangeiras, tabelas fato e dimensão, grão e
    cobertura temporal.
  - Regras de negócio inferidas (ordem entre datas, nulidade condicional, divisão e
    percentual) e pacotes de regras por domínio.
- **Qualidade e acompanhamento**
  - Score de qualidade com metodologia explícita, recomendações de ETL e gap analysis
    de KPIs.
  - Conferência entre duas versões, histórico longitudinal de qualidade com limiares
    reutilizáveis e contratos de dados em YAML (`contrato` e `validar`).
- **Saídas**
  - Relatório HTML interativo com gráficos SVG, tema escuro, filtros e navegação.
  - Relatórios em JSON, Markdown, Parquet e **PDF**, e dicionário de dados em XLSX.
  - Relatório consolidado de lote com resumo executivo.
  - Scripts de limpeza em pandas, SQL e **Power Query (M)**.
- **Interfaces**
  - Linha de comando: `perfilar`, `lote`, `modelar`, `pasta`, `conferir`, `historico`,
    `contrato`, `validar`, `dicionario`, `revisar-semantica`, `fonte`, `janela` e `versao`.
  - Menu interativo no terminal e interface gráfica em Qt (PySide6).
  - Execução por `python -m recon`, sem depender do PATH.

### Alterado

- Núcleo reescrito sobre novos módulos (arquitetura v3).
- Piso do Python elevado para 3.12.
- Dependências atualizadas: pandas 3.1.1, pyarrow 26.0.1, duckdb 2.0.0, scipy 1.18.1,
  entre outras, com o `requirements-dev.lock` regenerado.
- A CI passa a conferir se o lock acompanha o `pyproject.toml`.

### Corrigido

- Score de qualidade estável conforme a tabela cresce.
- Vocabulários semânticos isolados por execução, inclusive em análises concorrentes.
- Várias classificações semânticas: nomes de produto como dado pessoal, anos como
  rótulo, abreviações de duas letras, identificadores de empresa e telefones.
- Leitura de arquivos com bytes corrompidos e conversão de erros do leitor de CSV.
- Geração de PDF em todos os modos de relatório.
- Liberação dos recursos do Qt ao fechar a janela.
- Erro de lint (`SIM102`) e uso de `dt.dayofweek`, depreciado no pandas 3.1.

### Segurança

- Atualização do WeasyPrint (CVE-2026-55073 e CVE-2026-106443), do Pillow 13 e do
  Brotli 1.2.1 (CVE-2026-111497), com piso de versão no `pyproject.toml`.
- Neutralização de fórmulas nos dicionários XLSX e proteção contra exposição de dados
  nos relatórios.
- Pseudonimização com HMAC e chave por variável de ambiente nos scripts gerados.
- Auditoria de dependências (`pip-audit`) na CI.
- Remoção de dados reais dos testes e exemplos.

## Antes da 3.0 (sem versões publicadas)

O projeto nasceu em abril de 2026 como um profiler de dados e foi renomeado duas vezes:
de `data_profiler` para `datascope` e, em 15 de agosto de 2026, para `recon`.

### Fase 1 e 2: do profiler à CLI (abril a agosto de 2026)

- Arquitetura inicial de profiling, com taxonomias e limiares consolidados em um só lugar.
- Leitura de arquivos com exceções tipadas, inferência semântica por fuzzy matching e
  estatística descritiva por coluna.
- Testes de hipótese, dependências funcionais, gap analysis e recomendações de ETL.
- Exportação em JSON, Parquet e Markdown, e os primeiros comandos de CLI (`perfilar` e `lote`).
- Interpretação de datas brasileiras, detecção de CPF e CNPJ armazenados como número e
  análise temporal para datas em texto.
- Proteção do teste de Shapiro-Wilk contra série constante.

### Fase 3: arquitetura v3 (15 de agosto de 2026)

- Detecção de layout, relações entre colunas, regras de negócio, modelo de dados e a
  cascata de evidências semânticas.
- Relatório HTML com detalhe por coluna, gráficos SVG por coluna, relatório consolidado
  de lote, menu interativo e comando de pasta.
- Guia de instalação sem permissão de administrador e documentação técnica.

### Fase 4: contratos, comparação e interface (25 a 29 de agosto de 2026)

- Contratos de dados, conferência de versões, dicionário de dados, chaves compostas e
  a primeira interface gráfica.
- Scripts de limpeza em Power Query M, risco de exposição de dado pessoal e duplicatas
  aproximadas de pessoas.
- Licença CC BY-NC 4.0 (substituída pela MIT na 3.0.0) e remoção de dados reais de
  testes e exemplos.

[Não lançado]: https://github.com/Caio-Analytics/recon-data-profiler/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/Caio-Analytics/recon-data-profiler/releases/tag/v3.0.0

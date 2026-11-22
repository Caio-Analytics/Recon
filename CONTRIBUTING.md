# Contribuindo com o Recon

Obrigado por querer ajudar! Toda contribuição é bem-vinda: relatar um bug, sugerir
uma melhoria, corrigir um erro de digitação na documentação ou implementar uma
funcionalidade nova.

Este guia explica como preparar o ambiente, onde mexer no código e o que é
esperado de um pull request. Se algo aqui estiver confuso, isso também é um bug:
abra uma issue.

## Sumário

- [Formas de contribuir](#formas-de-contribuir)
- [Preparar o ambiente](#preparar-o-ambiente)
- [Rodar as verificações](#rodar-as-verificações)
- [Onde mexer no código](#onde-mexer-no-código)
- [Convenções do projeto](#convenções-do-projeto)
- [Dados de teste e privacidade](#dados-de-teste-e-privacidade)
- [Enviar um pull request](#enviar-um-pull-request)
- [Licença das contribuições](#licença-das-contribuições)

## Formas de contribuir

| Quero... | Como |
|---|---|
| Relatar um problema | Abra uma [issue de bug](https://github.com/Caio-Analytics/recon-data-profiler/issues/new?template=bug_report.yml). |
| Sugerir uma melhoria | Abra uma [sugestão](https://github.com/Caio-Analytics/recon-data-profiler/issues/new?template=feature_request.yml) ou comece uma [discussão](https://github.com/Caio-Analytics/recon-data-profiler/discussions). |
| Tirar uma dúvida de uso | Use as [Discussions](https://github.com/Caio-Analytics/recon-data-profiler/discussions), não as issues. |
| Começar a programar | Procure issues com o rótulo [`good first issue`](https://github.com/Caio-Analytics/recon-data-profiler/labels/good%20first%20issue) ou um item do [backlog](docs/BACKLOG.md). |
| Reportar uma vulnerabilidade | Siga o [SECURITY.md](SECURITY.md). **Não** abra issue pública. |

Para mudanças grandes (novo comando, novo formato de saída, mudança no contrato
JSON), abra uma issue antes de programar. Assim combinamos a abordagem e
ninguém perde trabalho.

## Preparar o ambiente

Requer **Python 3.12 ou superior** (o projeto é validado em 3.12, 3.13 e 3.14).

1. Faça um fork do repositório no GitHub e clone o seu fork:

   ```bash
   git clone https://github.com/<seu-usuario>/Recon.git
   cd recon-data-profiler
   git remote add upstream https://github.com/Caio-Analytics/recon-data-profiler.git
   ```

2. Crie um ambiente virtual e instale o projeto com as dependências de
   desenvolvimento e da interface gráfica:

   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   python -m pip install -r requirements-dev.lock
   python -m pip install PySide6==6.10.2
   python -m pip install -e . --no-deps
   ```

   O `requirements-dev.lock` fixa as mesmas versões usadas na CI. Se preferir,
   `python -m pip install -e ".[gui,dev]"` também funciona.

3. Instale o navegador usado pelos testes do relatório HTML:

   ```bash
   python -m playwright install chromium
   ```

### Dependências do sistema

Alguns pacotes precisam de bibliotecas do sistema operacional:

| Pacote | Para quê | Linux (Debian/Ubuntu) |
|---|---|---|
| WeasyPrint | Exportar relatórios em PDF | `sudo apt install libpango-1.0-0 libpangoft2-1.0-0` |
| PySide6 | Interface gráfica (`recon janela`) | `sudo apt install libegl1` |
| Playwright | Testes do HTML no navegador | `python -m playwright install --with-deps chromium` |

No macOS e no Windows, consulte a
[documentação de instalação do WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).
Os testes da interface Qt e do navegador são ignorados automaticamente quando
essas dependências não estão disponíveis, então você consegue contribuir mesmo
sem elas. A CI roda tudo.

## Rodar as verificações

Antes de enviar, rode o mesmo conjunto que a CI executa:

```bash
ruff check src tests                                 # estilo e lint
mypy                                                 # tipagem
QT_QPA_PLATFORM=offscreen pytest -q \
  --cov=src/recon --cov-fail-under=75                # testes + cobertura mínima
python -m build                                      # empacotamento
```

Dicas:

- `ruff check --fix src tests` corrige automaticamente boa parte dos avisos.
- `pytest tests/test_quality.py -q` roda só um arquivo; `pytest -k nome` filtra por nome.
- Para ver o resultado de uma mudança sem dados reais, gere a demonstração:
  `python examples/gerar_demo.py` (sai em `Output/demo/`).
- Para mudanças na interface, abra `recon janela` e confira visualmente. O teste
  automatizado da GUI não substitui essa conferência.

## Onde mexer no código

O mapa completo dos módulos está na [documentação técnica](docs/TECNICO.md#3-mapa-de-módulos).
O resumo:

```
src/recon/
├── config.py         só dado: taxonomias, limiares, regras de KPI
├── ingestion.py      leitura de CSV, Excel, JSON, Parquet, encoding
├── semantics/        inferência semântica de colunas
├── statistics.py     estatísticas descritivas por coluna
├── quality.py        recomendações e score de qualidade
├── relationships.py  dependências, duplicatas, correlação
├── datamodel.py      relações entre tabelas
├── reporting/        saídas: JSON, Markdown, HTML, PDF, XLSX
├── pipeline.py       DataProfiler: orquestra tudo
├── cli.py            comandos `recon ...`
└── gui_qt.py         interface gráfica
tests/                um arquivo de teste por módulo
```

Pontos de entrada comuns:

| Quero... | Onde mexer |
|---|---|
| Adicionar categoria semântica | `config.CATEGORIAS_FORTES` ou `CATEGORIAS_FUZZY` |
| Adicionar abreviatura ou conjunto de valores | `semantics/vocabulary.py` |
| Adicionar valor sentinela (`N/A`, `9999`...) | `config.SENTINELAS_*` |
| Ajustar sensibilidade de uma análise | limiares em `config.py` |
| Criar formato de saída | novo módulo em `reporting/`, exportado no `__init__` |
| Criar ou mudar um comando | `cli.py` (regra de análise fica no `pipeline`, não no comando) |

## Convenções do projeto

- **Idioma:** nomes de módulos e arquivos em inglês técnico; funções, variáveis,
  campos e chaves de saída em português. Documentação e mensagens em português.
- **Arquitetura:** `config.py` contém apenas dados. Módulos de análise são funções
  puras, sem estado global, e não importam `reporting` nem `cli`. CLI, menu e
  janela são cascas sobre o `DataProfiler`: a mesma entrada precisa gerar o
  mesmo relatório em qualquer interface.
- **Testes:** todo bug corrigido ganha um teste com nome descritivo e docstring
  explicando o que quebrava. Escreva o teste antes da correção sempre que possível.
- **Dependências:** as versões são fixadas exatamente. Se precisar adicionar ou
  atualizar uma, altere o `pyproject.toml` e regenere o lock:

  ```bash
  pip-compile --extra=dev --output-file=requirements-dev.lock --strip-extras pyproject.toml
  ```

- **Commits:** seguimos [Conventional Commits](https://www.conventionalcommits.org/pt-br/),
  como no histórico do projeto:

  ```
  feat(reporting): exporta perfil em PDF
  fix(gui): libera recursos do Qt ao fechar
  docs: corrige exemplo do comando lote
  test(datamodel): cobre chave com valores ausentes
  ```

  Tipos usados: `feat`, `fix`, `docs`, `test`, `refactor`, `style`, `chore`, `ci`.
  O escopo entre parênteses é opcional e costuma ser o módulo alterado.

## Dados de teste e privacidade

O Recon lida com dados pessoais e corporativos. Por isso:

- **Nunca** versione planilhas, extrações ou relatórios com dados reais, nem em
  testes nem em issues.
- Crie os dados dos testes no próprio código, com `pandas.DataFrame`, e grave
  arquivos em `tmp_path` (fixture do pytest).
- Use valores fictícios: CPFs e CNPJs gerados, nomes inventados.
- O `.gitignore` bloqueia `*.csv`, `*.xlsx`, `*.json`, `*.txt`, `*.html`, `Input/`
  e `Output/` justamente para evitar vazamentos. Se um arquivo **sintético**
  realmente precisar ser versionado, use `git add -f` e explique no pull request.

## Enviar um pull request

1. Atualize o seu fork e crie uma branch a partir da `main`:

   ```bash
   git fetch upstream
   git switch -c fix/descricao-curta upstream/main
   ```

2. Faça a mudança, com testes, e rode as [verificações](#rodar-as-verificações).
3. Atualize a documentação (`README.md`, `docs/GUIA.md`, `docs/TECNICO.md`) se a
   mudança afetar comandos, saídas ou a interface, e o `CHANGELOG.md` se for uma
   mudança visível para quem usa.
4. Envie a branch para o seu fork e abra o pull request para `Caio-Analytics/recon-data-profiler:main`.
   O modelo de PR traz um checklist; preencha o que se aplicar.
5. A CI precisa passar. Se ela falhar, abra o log da execução e corrija; se o
   erro não fizer sentido, comente no PR que a gente ajuda.

Pull requests pequenos e focados são revisados mais rápido. Prefira dois PRs
separados a um que resolve duas coisas.

## Código de conduta

Ao participar, você concorda em seguir o [Código de Conduta](CODE_OF_CONDUCT.md).

## Licença das contribuições

O Recon é distribuído sob a [licença MIT](LICENSE). Ao enviar uma contribuição,
você concorda que ela seja licenciada nos mesmos termos.

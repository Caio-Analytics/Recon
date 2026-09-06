# Recon

Recon é uma ferramenta local para conhecer uma base antes de analisá-la. Ela lê arquivos tabulares, identifica estrutura, qualidade, possíveis dados pessoais, semântica de colunas e relações entre tabelas, e gera relatórios HTML, JSON e Markdown.

Os dados permanecem na sua máquina: o Recon não depende de serviços externos.

## Escolha o que precisa fazer

| Se você quer... | Use |
|---|---|
| Entender um arquivo que acabou de receber | `recon perfilar dados.csv` |
| Comparar várias bases ou extrações | `recon lote janeiro.csv fevereiro.csv` |
| Descobrir como tabelas se relacionam | `recon modelar vendas.csv clientes.csv` |
| Conferir o que mudou entre duas versões | `recon conferir antes.csv depois.csv` |
| Acompanhar a qualidade de extrações recorrentes | `recon historico jan.csv fev.csv mar.csv` |
| Criar ou validar uma referência de qualidade | `recon contrato` e `recon validar` |

Em uma análise, o Recon mostra tipo real, nulos, unicidade, distribuição e exemplos protegidos quando há dado pessoal. Também aponta riscos de qualidade, recomendações de ETL, relações candidatas entre tabelas e mudanças entre extrações.

## Comece em poucos minutos

Requer Python 3.12 ou superior.

```bash
git clone https://github.com/Caio-Analytics/Recon.git
cd Recon
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[gui]"
```

Abra a interface gráfica:

```bash
recon janela
```

Ou gere um relatório pelo terminal:

```bash
recon perfilar dados.csv
```

O HTML é a saída principal: abra o arquivo gerado no navegador.

## Próximos comandos

```bash
recon perfilar dados.csv                 # perfil de uma tabela
recon lote janeiro.csv fevereiro.csv     # compara arquivos em lote
recon modelar vendas.csv clientes.csv    # relações entre tabelas
recon conferir antes.csv depois.csv      # mudança entre duas extrações
recon historico jan.csv fev.csv mar.csv  # evolução longitudinal
recon contrato dados.csv                 # cria contrato YAML editável
recon validar dados_novos.csv --contrato contrato.yaml
recon dicionario vendas.csv clientes.csv # gera dicionário XLSX
recon revisar-semantica dados.csv        # cria YAML para revisar classificações
recon pasta ./extracoes --modo auto      # analisa todos os arquivos de uma pasta
```

Use `recon --help` para ver todas as opções da versão instalada, inclusive consulta local em SQLite ou DuckDB com `recon fonte`.

Para visualizar sem usar informações reais:

```bash
.venv/bin/python examples/gerar_demo.py
```

O resultado fica em `Output/demo/`.

## Privacidade e arquivos grandes

O Recon reserva 30% da RAM disponível. Se uma leitura integral exceder o orçamento seguro, usa amostragem e registra a cobertura e as limitações no relatório. Em amostras, confirme chaves, duplicatas e categorias raras na base completa.

Relatórios podem conter metadados corporativos. Valores classificados como pessoais são mascarados, mas os outputs devem continuar sendo tratados como documentos internos.

O script de limpeza usa pseudonimização com HMAC para dados pessoais e exige a variável de ambiente `RECON_PSEUDONYMIZATION_KEY`. Guarde essa chave fora do script e dos relatórios; pseudonimizar não é o mesmo que anonimizar.

## Documentação

| Documento | Para quê |
|---|---|
| [Guia de uso](docs/GUIA.md) | Instalação, GUI e exemplos passo a passo. |
| [Documentação técnica](docs/TECNICO.md) | Arquitetura, payload, critérios e extensões. |
| [Guia do código](docs/GUIA_DO_CODIGO.md) | Primeiro contato com a base de código e os testes. |
| [Backlog](docs/BACKLOG.md) | Melhorias planejadas e limites conhecidos. |
| [Contribuição](CONTRIBUTING.md) | Como alterar e validar o projeto. |
| [Segurança e privacidade](SECURITY.md) | Como tratar dados e reportar vulnerabilidades. |

## Desenvolvimento

```bash
python -m pip install -r requirements-dev.lock
python -m pip install -e . --no-deps
pytest -q
```

O projeto verifica estilo com Ruff e tipos com Mypy na CI.

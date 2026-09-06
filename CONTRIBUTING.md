# Contribuindo com o Recon

## Antes de começar

Crie um ambiente de desenvolvimento e instale as dependências:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[gui,dev]"
```

## Fluxo de contribuição

1. Abra uma issue ou descreva claramente o problema que a mudança resolve.
2. Crie ou ajuste um teste que represente o comportamento esperado ou a regressão.
3. Faça a menor alteração possível em `src/recon/`.
4. Atualize a documentação quando a mudança afetar comandos, saídas ou a interface.
5. Execute as verificações antes de enviar a contribuição:

```bash
pytest -q --cov=src/recon --cov-fail-under=75
ruff check src tests
mypy src
python -m build
```

Para mudanças na interface, teste também `recon janela` em um ambiente gráfico. A validação automatizada da GUI não substitui uma conferência visual.

Não versione arquivos de entrada, relatórios ou planilhas com dados reais. O `.gitignore` cobre formatos comuns, mas a responsabilidade final é de quem contribui.

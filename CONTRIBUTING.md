# Contribuindo com o Recon

1. Crie um teste que descreva a mudança ou a regressão.
2. Faça a alteração menor possível em `src/recon/`.
3. Execute antes de abrir uma alteração:

```bash
pytest -q --cov=src/recon --cov-fail-under=75
ruff check src tests
mypy src
python -m build
```

Não versione arquivos de entrada, relatórios ou planilhas contendo dados reais. O `.gitignore` já cobre os formatos mais comuns, mas a responsabilidade final é de quem contribui.

"""Gera uma base fictícia e um relatório HTML para conhecer o Recon.

Uso, a partir da raiz do repositório:
    .venv/bin/python examples/gerar_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _importar_recon() -> type:
    """Permite executar o exemplo antes de instalar o pacote editável."""
    raiz = Path(__file__).resolve().parents[1]
    src = raiz / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from recon.pipeline import DataProfiler

    return DataProfiler


def criar_base() -> pd.DataFrame:
    """Cria vendas fictícias com sinais comuns de qualidade de dados."""
    gerador = np.random.default_rng(42)
    linhas = 320
    canais = np.array(["Loja", "Site", "Marketplace"])
    regioes = np.array(["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"])
    vendas = pd.DataFrame(
        {
            "id_venda": np.arange(10_001, 10_001 + linhas),
            "data_venda": pd.date_range("2025-01-02", periods=linhas, freq="D"),
            "id_cliente": gerador.integers(1_000, 1_110, size=linhas),
            "produto": gerador.choice(["Notebook", "Monitor", "Teclado", "Mouse"], size=linhas),
            "canal": gerador.choice(canais, size=linhas, p=[0.35, 0.45, 0.20]),
            "regiao": gerador.choice(regioes, size=linhas),
            "valor_venda": np.round(gerador.lognormal(5.2, 0.75, size=linhas), 2),
            "status": gerador.choice(["Concluída", "Pendente", "Cancelada"], size=linhas),
            "email_contato": [f"cliente{i % 110}@exemplo.com" for i in range(linhas)],
        }
    )
    vendas.loc[[8, 37, 119, 231], "canal"] = "N/A"
    vendas.loc[[15, 81, 177], "regiao"] = "sudeste"
    vendas.loc[[26, 92, 274], "valor_venda"] = np.nan
    vendas.loc[318, "valor_venda"] = 999_999.0
    return vendas


def main() -> None:
    raiz = Path(__file__).resolve().parents[1]
    destino = raiz / "Output" / "demo"
    destino.mkdir(parents=True, exist_ok=True)
    caminho_csv = destino / "vendas_demo.csv"
    criar_base().to_csv(caminho_csv, index=False)

    DataProfiler = _importar_recon()
    DataProfiler().processar_arquivo(
        str(caminho_csv),
        saida_base=str(destino / "recon_demo"),
        formatos=["html", "json", "markdown"],
    )
    print("Demonstração criada em:")
    print(destino / "recon_demo_vendas_demo.html")


if __name__ == "__main__":
    main()

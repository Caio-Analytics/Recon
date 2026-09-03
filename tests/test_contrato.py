"""Contrato editável: faixas, domínios e severidade por coluna."""

import pandas as pd

from recon.contrato import conferir_contrato, gerar_contrato
from recon.pipeline import DataProfiler


def test_contrato_respeita_faixa_e_severidade_configurada():
    base = DataProfiler().processar_dataframe(pd.DataFrame({"valor": [10, 20, 30]}), "base")
    contrato = gerar_contrato(base)
    esperado = contrato["colunas"][0]
    esperado["max_permitido"] = 25
    esperado["severidades"]["faixa"] = "🔴 ALTA"

    atual = DataProfiler().processar_dataframe(pd.DataFrame({"valor": [10, 99]}), "nova")
    resultado = conferir_contrato(atual, contrato)

    assert any(
        violacao["tipo"] == "Valor acima da faixa" and violacao["severidade"] == "🔴 ALTA"
        for violacao in resultado["violacoes"]
    )


def test_contrato_pode_aceitar_categoria_nova():
    base = DataProfiler().processar_dataframe(pd.DataFrame({"status": ["A", "B"]}), "base")
    contrato = gerar_contrato(base)
    esperado = contrato["colunas"][0]
    esperado["valores_permitidos"] = ["A", "B"]
    esperado["permitir_valores_novos"] = True

    atual = DataProfiler().processar_dataframe(pd.DataFrame({"status": ["A", "C"]}), "nova")
    resultado = conferir_contrato(atual, contrato)

    assert not any(violacao["tipo"] == "Valor fora do domínio" for violacao in resultado["violacoes"])

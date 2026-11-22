"""Regressão: nenhum valor pessoal bruto pode aparecer em exemplos do relatório.

Antes da correção, a máscara só cobria `amostra_representativa`, as estatísticas e o
`distribuicao_top5` de colunas com padrão estruturado. Outros campos copiavam valores
da coluna sem máscara: variantes de grafia, exemplos de encoding corrompido, exemplos
de formato, duplicatas aproximadas e o texto das recomendações de ETL. Em colunas de
nome e de texto livre, isso expunha nomes, e-mails e telefones no JSON, no HTML e no
Markdown.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from recon.pipeline import DataProfiler
from recon.reporting import exportar_html, exportar_markdown

from .conftest import gerar_cpfs

NOMES = [
    "José Carlos Silva",
    "jose carlos silva",
    "JosÃ© Antunes Lima",
    "Maria Aparecida Souza",
    "MARIA APARECIDA SOUZA",
    "Ana Paula Ferreira",
    "Carlos Eduardo Lima",
    "Pedro Henrique Alves",
]

# Trechos que só existem se o valor bruto vazou. Em minúsculas, para comparar sem caixa.
VALORES_PROIBIDOS = [
    "carlos silva",
    "jose carlos",
    "maria aparecida",
    "antunes lima",
    "ana paula",
    "maria.souza@gmail.com",
    "joao.lima@empresa.com.br",
    "98888-7777",
    "97777-1234",
]


@pytest.fixture(scope="module")
def payload() -> dict:
    n = 160
    cpfs = gerar_cpfs(3)
    cpf_digitos = cpfs[0].replace(".", "").replace("-", "")
    df = pd.DataFrame(
        {
            "nome_cliente": (NOMES * 20)[:n],
            "cpf": ([cpfs[0], cpf_digitos, cpfs[1]] * 60)[:n],
            "observacao": (
                [
                    "contato maria.souza@gmail.com ou 11 98888-7777 sobre o pedido",
                    "falar com joao.lima@empresa.com.br no 11 97777-1234 amanhã",
                ]
                * 80
            )[:n],
            "valor": range(n),
        }
    )
    return DataProfiler().processar_dataframe(df, "clientes")


def _todos_os_textos(objeto: object) -> list[str]:
    if isinstance(objeto, dict):
        return [t for v in objeto.values() for t in _todos_os_textos(v)]
    if isinstance(objeto, list):
        return [t for v in objeto for t in _todos_os_textos(v)]
    return [objeto] if isinstance(objeto, str) else []


def _vazamentos(texto: str) -> list[str]:
    minusculo = texto.lower()
    return [valor for valor in VALORES_PROIBIDOS if valor in minusculo]


def test_payload_json_nao_contem_valores_pessoais(payload: dict) -> None:
    achados = {
        valor: [t[:80] for t in _todos_os_textos(payload) if valor in t.lower()][:2]
        for valor in VALORES_PROIBIDOS
        if any(valor in t.lower() for t in _todos_os_textos(payload))
    }
    assert not achados, f"valores pessoais brutos no payload: {achados}"


def test_cpf_bruto_nao_aparece_no_payload(payload: dict) -> None:
    cpf = gerar_cpfs(1)[0]
    texto = json.dumps(payload, ensure_ascii=False, default=str)
    assert cpf not in texto
    assert cpf.replace(".", "").replace("-", "") not in texto


def test_relatorio_html_nao_contem_valores_pessoais(payload: dict, tmp_path: Path) -> None:
    destino = tmp_path / "relatorio.html"
    exportar_html(payload, str(destino))
    assert _vazamentos(destino.read_text(encoding="utf-8")) == []


def test_relatorio_markdown_nao_contem_valores_pessoais(payload: dict, tmp_path: Path) -> None:
    destino = tmp_path / "relatorio.md"
    exportar_markdown(payload, str(destino))
    assert _vazamentos(destino.read_text(encoding="utf-8")) == []


def test_exemplos_continuam_uteis_depois_de_mascarados(payload: dict) -> None:
    """A máscara não pode apagar o diagnóstico: as variantes de grafia seguem listadas."""
    coluna = next(c for c in payload["colunas"] if c["Coluna"] == "nome_cliente")
    inconsistencia = coluna["Qualidade"]["inconsistencia_normalizacao"]
    assert inconsistencia["tem_inconsistencia"]
    variantes = inconsistencia["exemplos"][0]["variantes"]
    assert len(variantes) >= 2
    assert all("*" in v for v in variantes)

    aproximadas = payload["duplicatas_aproximadas"]
    assert aproximadas
    assert all("*" in v for g in aproximadas[0]["exemplos"] for v in g["variantes"])


def test_texto_livre_com_pii_sai_redigido_nos_exemplos(payload: dict) -> None:
    coluna = next(c for c in payload["colunas"] if c["Coluna"] == "observacao")
    top = coluna["Stats_Extra"]["distribuicao_top5"]
    assert top
    assert all("REDIGIDO" in item["valor"] for item in top)
    formato = coluna["Qualidade"].get("formato", {})
    if formato.get("tem_formato"):
        assert "@" not in formato["exemplo_conforme"]

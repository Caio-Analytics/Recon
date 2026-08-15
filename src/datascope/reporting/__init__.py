"""Exportação do payload de profiling.

JSON para IA/código, Markdown e HTML para leitura humana, Parquet para BI.
"""
from ._html import exportar_html
from ._markdown import exportar_markdown
from ._modelo import exportar_modelo_html, exportar_modelo_markdown
from ._serialize import (
    exportar_json,
    exportar_parquet,
    gerar_nome_unico,
    nome_seguro,
    sanear_floats,
)

__all__ = [
    "exportar_html",
    "exportar_json",
    "exportar_markdown",
    "exportar_modelo_html",
    "exportar_modelo_markdown",
    "exportar_parquet",
    "gerar_nome_unico",
    "nome_seguro",
    "sanear_floats",
]

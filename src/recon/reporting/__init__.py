"""Exportação do payload de profiling.

JSON para IA/código, Markdown e HTML para leitura humana, Parquet para BI.
"""
from ._conferencia import exportar_conferencia_html, exportar_conferencia_markdown
from ._dicionario import exportar_dicionario_xlsx
from ._html import exportar_html
from ._lote import exportar_lote_html
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
    "exportar_conferencia_html",
    "exportar_conferencia_markdown",
    "exportar_dicionario_xlsx",
    "exportar_html",
    "exportar_lote_html",
    "exportar_json",
    "exportar_markdown",
    "exportar_modelo_html",
    "exportar_modelo_markdown",
    "exportar_parquet",
    "gerar_nome_unico",
    "nome_seguro",
    "sanear_floats",
]

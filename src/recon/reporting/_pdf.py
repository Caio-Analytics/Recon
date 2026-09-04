"""PDF de leitura a partir do HTML autocontido do Recon."""
from __future__ import annotations

from pathlib import Path

from loguru import logger


def exportar_pdf_de_html(caminho_html: str, caminho_pdf: str) -> None:
    """Converte o relatório HTML para PDF sem executar seu JavaScript.

    A fonte continua sendo o HTML, que é o formato interativo. O PDF é uma
    cópia estática para anexar em e-mail, processo ou documentação. WeasyPrint
    processa apenas HTML/CSS local, sem abrir URLs externas do relatório.
    """
    try:
        from weasyprint import HTML
    except ImportError as erro:
        raise RuntimeError(
            "Exportação PDF não está instalada. Reinstale o Recon com as dependências atuais."
        ) from erro
    Path(caminho_pdf).parent.mkdir(parents=True, exist_ok=True)
    HTML(filename=caminho_html).write_pdf(caminho_pdf)
    logger.info(f"✓ PDF exportado: '{caminho_pdf}'")

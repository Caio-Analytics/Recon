"""Contrato do HTML no navegador, não apenas como texto gerado.

Os testes são pulados de forma explícita quando a máquina não tiver o Chromium
do Playwright. Na CI ele é instalado no job de interface.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest

from recon.pipeline import DataProfiler
from recon.reporting import exportar_html

playwright_sync = pytest.importorskip("playwright.sync_api")


@contextmanager
def _pagina() -> Iterator[object]:
    try:
        with playwright_sync.sync_playwright() as playwright:
            navegador = playwright.chromium.launch()
            try:
                yield navegador.new_page(viewport={"width": 1280, "height": 900})
            finally:
                navegador.close()
    except Exception as erro:  # navegador pode não estar baixado no computador do analista
        pytest.skip(f"Chromium do Playwright indisponível: {erro}")


def test_html_interativo_navega_filtra_e_ordena(tmp_path: Path) -> None:
    dados = pd.DataFrame({
        "id_venda": range(60),
        "email_contato": [f"cliente{i}@empresa.test" for i in range(60)],
        "valor_venda": [float(i * 10) for i in range(60)],
    })
    relatorio = tmp_path / "perfil.html"
    exportar_html(DataProfiler().processar_dataframe(dados, "vendas"), str(relatorio))

    with _pagina() as pagina:
        pagina.goto(relatorio.as_uri())
        navegacao = pagina.locator(".navegacao a")
        assert navegacao.count() >= 4

        navegacao.filter(has_text="Detalhe por coluna").click()
        pagina.wait_for_timeout(550)
        assert "Detalhe por coluna" in pagina.locator(".navegacao a.ativa").inner_text()

        busca = pagina.locator('.filtros input[type="search"]')
        busca.fill("email_contato")
        assert pagina.locator(".coluna:not(.oculta)").count() == 1
        assert "email_contato" in pagina.locator(".coluna:not(.oculta)").inner_text()

        cabecalho = pagina.locator("table th").first
        cabecalho.click()
        assert "ordenavel" in (cabecalho.get_attribute("class") or "")

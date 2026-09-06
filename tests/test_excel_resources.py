
from __future__ import annotations

from unittest.mock import MagicMock

from recon import ingestion


def test_listar_abas_fecha_leitor_excel(monkeypatch, tmp_path) -> None:
    caminho = tmp_path / "base.xlsx"
    caminho.touch()
    leitor = MagicMock()
    leitor.__enter__.return_value = leitor
    leitor.sheet_names = ["Clientes"]
    monkeypatch.setattr(ingestion.pd, "ExcelFile", lambda *args, **kwargs: leitor)

    assert ingestion.listar_abas(str(caminho)) == ["Clientes"]
    leitor.__exit__.assert_called_once_with(None, None, None)


def test_carregar_arquivo_fecha_leitor_ao_validar_aba(monkeypatch, tmp_path) -> None:
    caminho = tmp_path / "base.xlsx"
    caminho.touch()
    leitor = MagicMock()
    leitor.__enter__.return_value = leitor
    leitor.sheet_names = ["Clientes"]
    monkeypatch.setattr(ingestion.pd, "ExcelFile", lambda *args, **kwargs: leitor)

    try:
        ingestion.carregar_arquivo(str(caminho), aba_excel=2)
    except ingestion.FileFormatError:
        pass
    else:
        raise AssertionError("Era esperado erro para uma aba inexistente.")

    assert leitor.__exit__.call_count == 1

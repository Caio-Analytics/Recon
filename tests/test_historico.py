"""Limiares configuráveis do histórico."""
import pytest

from recon.historico import alertas_da_transicao, carregar_limiares


def _extracao(nome: str, score: float, linhas: int = 100) -> dict:
    return {
        "arquivo": nome, "score": score, "linhas": linhas, "colunas": 3,
        "linhas_total_desconhecido": False,
    }


def test_limiares_personalizados_controlam_alertas(tmp_path):
    arquivo = tmp_path / "limites.yaml"
    arquivo.write_text("score_minimo: 90\nqueda_score_maxima: 2\nvariacao_volume_maxima_pct: 10\n")

    limites = carregar_limiares(str(arquivo))
    alertas = alertas_da_transicao(_extracao("jan.csv", 95), _extracao("fev.csv", 88, 115), limites)

    assert any("abaixo do mínimo" in alerta for alerta in alertas)
    assert any("caiu 7.0" in alerta for alerta in alertas)
    assert any("cresceu 15.0%" in alerta for alerta in alertas)


def test_limiares_rejeitam_chave_desconhecida(tmp_path):
    arquivo = tmp_path / "limites.yaml"
    arquivo.write_text("invente: 10\n")

    with pytest.raises(ValueError, match="desconhecido"):
        carregar_limiares(str(arquivo))

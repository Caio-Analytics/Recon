import json
import math

from data_profiler.reporting import exportar_json, sanear_floats


def test_sanear_floats_converte_nan_para_none():
    resultado = sanear_floats({"skew": float("nan"), "std": 1.5, "valores": [float("inf"), 2.0]})
    assert resultado == {"skew": None, "std": 1.5, "valores": [None, 2.0]}


def test_exportar_json_nunca_gera_token_nan_cru(tmp_path):
    payload = {"colunas": [{"nome": "x", "assimetria": float("nan")}]}
    caminho = tmp_path / "saida.json"

    exportar_json(payload, str(caminho))

    conteudo = caminho.read_text(encoding="utf-8")
    assert "NaN" not in conteudo
    dados = json.loads(conteudo)  # json.loads padrão rejeita NaN cru se não houvesse o saneamento
    assert dados["colunas"][0]["assimetria"] is None

"""Estatísticas descritivas por coluna."""
import math

import numpy as np
import pandas as pd

from recon import config
from recon.statistics import analisar_estatisticas, detectar_mistura_tipos, sugerir_dtype

from .conftest import gerar_cnpjs, gerar_cpfs

# ── Tipagem e características ───────────────────────────────────────────────

def test_coluna_numerica_com_menos_de_3_validos_nao_gera_nan():
    resultado = analisar_estatisticas(pd.Series([5.0, 7.0], name="score"), total_linhas=2)

    extras = resultado["estatisticas_adicionais"]
    assert extras["assimetria"] is None or math.isfinite(extras["assimetria"])
    assert extras["curtose"] is None or math.isfinite(extras["curtose"])


def test_coluna_100_pct_vazia():
    resultado = analisar_estatisticas(pd.Series([None] * 3, name="campo_lixo"), total_linhas=3)

    assert resultado["caracteristica"] == "⚠️ Coluna 100% Vazia"
    assert resultado["nulos_pct"] == 100.0
    assert resultado["tipo_dados"] == config.TIPO_VAZIO


def test_coluna_quase_vazia_nao_e_marcada_como_100_pct_vazia():
    """Regressão: `nulos_pct` arredondado a 4 casas batia exatamente em 100.0
    com um único valor válido em milhões de linhas, e o profiler emitia
    recomendação 🔴 ALTA de remover a coluna 'sem impacto em dados úteis'."""
    n = 3_000_000
    serie = pd.Series([np.nan] * (n - 1) + [42.0], name="quase_vazia")

    resultado = analisar_estatisticas(serie, total_linhas=n)

    assert resultado["nulos_pct"] == 100.0  # o arredondamento continua existindo
    assert resultado["caracteristica"] != "⚠️ Coluna 100% Vazia"
    assert resultado["valores_unicos"] == 1


def test_coluna_chave_primaria_potencial():
    resultado = analisar_estatisticas(pd.Series(range(100), name="id"), total_linhas=100)
    assert "Chave Primária Potencial" in resultado["caracteristica"]


def test_metrica_continua_nao_e_classificada_como_quase_chave():
    """Regressão: salário decimal é quase-único por natureza e virava
    '🔑 Quase-Chave (99.8% únicos — possível dado sujo)', gerando recomendação
    de investigar duplicata numa coluna que nunca seria chave."""
    rng = np.random.default_rng(3)
    serie = pd.Series(np.round(rng.lognormal(8.5, 0.4, 5000), 2), name="salario_bruto")

    resultado = analisar_estatisticas(serie, total_linhas=5000)

    assert resultado["ratio_unicidade"] > config.THRESHOLD_QUASE_CHAVE
    assert "Quase-Chave" not in resultado["caracteristica"]
    assert resultado["caracteristica"] == "📊 Métrica Contínua"


def test_dtype_nullable_int64_classificado_como_numero():
    resultado = analisar_estatisticas(pd.Series([1, 2, 3, None], dtype="Int64"), total_linhas=4)

    assert "Número" in resultado["tipo_dados"]
    assert "media" in resultado["estatisticas_adicionais"]


def test_coef_variacao_overflow_guard():
    serie = pd.Series([1e300, 1e300, 1e300, -1e-300], name="overflow_test")
    coef = analisar_estatisticas(serie, total_linhas=4)["estatisticas_adicionais"]["coef_variacao"]
    assert coef is None or math.isfinite(coef)


def test_mistura_de_tipos_detectada():
    serie = pd.Series(["123"] * 10 + ["texto_livre"] * 10 + ["2024-01-01"] * 10, name="misto")
    assert analisar_estatisticas(serie, 30)["flags"]["mistura_tipos"]["tem_mistura"] is True


def test_detectar_mistura_tipos_opera_apenas_sobre_a_amostra():
    resultado = detectar_mistura_tipos(["1", "2", "abc", "def"])
    assert resultado["tem_mistura"] is True
    assert set(resultado["tipos_detectados"]) == {"numerico", "texto_puro"}


def test_numero_brasileiro_com_milhar_nao_vira_mistura_de_tipos():
    """Regressão real: `1.234.567,89` (milhar com ponto, decimal com vírgula)
    caía em "texto_puro" porque a troca ingênua de vírgula por ponto deixava
    um segundo ponto sobrando. 100% dos valores eram número válido; o recon
    reportava ~11% de mistura e recomendava normalizar um dado que não tinha
    nada de errado."""
    valores = ["155024,500000", "1.234.567,89", "4,0000000000000001E-2", "89025,750000"] * 10
    resultado = detectar_mistura_tipos(valores)
    assert resultado["tem_mistura"] is False


# ── LGPD ────────────────────────────────────────────────────────────────────

def test_cpf_detectado_mesmo_em_coluna_de_chave_sistema():
    resultado = analisar_estatisticas(pd.Series(gerar_cpfs(1) * 20, name="id_cpf"), 20)
    assert resultado["flags"]["detected_pattern"] == "CPF"


def test_cep_nao_detectado_em_coluna_de_chave_sistema():
    serie = pd.Series([str(90000 + i) for i in range(20)], name="id_interno")
    assert analisar_estatisticas(serie, 20)["flags"]["detected_pattern"] != "CEP"


def test_cpf_detectado_quando_armazenado_como_inteiro():
    cpfs = [int(c.replace(".", "").replace("-", "")) for c in gerar_cpfs(30)]
    resultado = analisar_estatisticas(pd.Series(cpfs, name="cpf_colaborador"), 30)

    assert resultado["flags"]["detected_pattern"] == "CPF"
    assert all("*" in v for v in resultado["amostra_representativa"])


def test_cnpj_detectado_quando_armazenado_como_inteiro():
    cnpjs = [int(c.replace(".", "").replace("/", "").replace("-", "")) for c in gerar_cnpjs(30)]
    resultado = analisar_estatisticas(pd.Series(cnpjs, name="cnpj_empresa"), 30)
    assert resultado["flags"]["detected_pattern"] == "CNPJ"


def test_timestamp_epoch_nao_vira_cnpj_falso_positivo():
    """Regressão: 13 dígitos batiam na faixa de CNPJ e um timestamp em
    milissegundos virava 'dado sensível LGPD'."""
    serie = pd.Series([1700000000000 + i * 997 for i in range(200)], name="ts_evento")
    assert analisar_estatisticas(serie, 200)["flags"]["detected_pattern"] == "Nenhum"


def test_id_numerico_generico_nao_vira_cpf_falso_positivo():
    serie = pd.Series(range(100000, 100020), name="id_funcionario")
    assert analisar_estatisticas(serie, 20)["flags"]["detected_pattern"] == "Nenhum"


def test_estatisticas_de_posicao_sao_suprimidas_em_coluna_sensivel():
    """Regressão (vazamento de LGPD): a amostra saía mascarada, mas `min`,
    `max`, `mediana`, o IC95% e os limites de outlier eram CPFs reais
    completos, publicados em claro no JSON e no Markdown."""
    cpfs = [int(c.replace(".", "").replace("-", "")) for c in gerar_cpfs(300)]
    resultado = analisar_estatisticas(pd.Series(cpfs, name="doc"), 300)

    extras = resultado["estatisticas_adicionais"]
    assert resultado["flags"]["detected_pattern"] == "CPF"
    assert resultado["flags"]["stats_suprimidas_lgpd"] is True
    for campo in ("min", "max", "media", "mediana", "outliers_iqr", "testes_hipotese"):
        assert campo not in extras
    assert "estatisticas_suprimidas" in extras

    serializado = str(extras)
    assert not any(str(cpf) in serializado for cpf in cpfs[:20])


def test_valores_lgpd_sensiveis_sao_mascarados_na_amostra_e_no_top5():
    cpfs = gerar_cpfs(30)
    resultado = analisar_estatisticas(pd.Series(cpfs, name="cpf_colaborador"), 30)

    amostra = resultado["amostra_representativa"]
    top5 = [i["valor"] for i in resultado["estatisticas_adicionais"]["distribuicao_top5"]]
    for original in cpfs:
        assert original not in amostra
        assert original not in top5
    assert any("*" in v for v in amostra)


def test_pii_em_texto_livre_e_redigida_na_amostra():
    cpf = gerar_cpfs(1)[0]
    serie = pd.Series([f"Reclamação do cliente CPF {cpf}"] * 5 + [f"Obs {i}" for i in range(25)],
                      name="observacao")

    resultado = analisar_estatisticas(serie, 30)

    assert resultado["qualidade"]["pii_texto_livre"]["tem_pii"] is True
    assert all(cpf not in v for v in resultado["amostra_representativa"])


# ── Qualidade de conteúdo ───────────────────────────────────────────────────

def test_sentinelas_textuais_entram_em_nulos_efetivos():
    """Regressão: coluna 30% preenchida com 'N/A'/'-'/'#N/D' reportava
    `nulos_pct: 0.0`."""
    serie = pd.Series(["SP"] * 300 + ["N/A"] * 80 + ["-"] * 40 + ["#N/D"] * 30 + ["RJ"] * 50,
                      name="uf")

    resultado = analisar_estatisticas(serie, 500)

    assert resultado["nulos_pct"] == 0.0
    assert resultado["qualidade"]["sentinelas"]["tem_sentinela"] is True
    assert resultado["qualidade"]["nulos_efetivos_pct"] == 30.0


def test_inconsistencia_de_grafia_e_sinalizada():
    serie = pd.Series(["SP"] * 200 + ["sp"] * 60 + [" SP"] * 40 + ["S.P."] * 20 + ["RJ"] * 80,
                      name="uf")

    inconsistencia = analisar_estatisticas(serie, 400)["qualidade"]["inconsistencia_normalizacao"]

    assert inconsistencia["tem_inconsistencia"] is True
    assert inconsistencia["valores_unicos_normalizado"] == 2


def test_sentinelas_numericas_detectadas():
    serie = pd.Series([100.0] * 400 + [-1.0] * 60, name="saldo")
    assert analisar_estatisticas(serie, 460)["qualidade"]["sentinelas"]["tem_sentinela"] is True


# ── Datas ───────────────────────────────────────────────────────────────────

def test_perfil_de_datas_detecta_futuro_e_lacuna_de_calendario():
    datas = (
        pd.date_range("2023-01-01", "2023-03-31", freq="D").tolist()
        + pd.date_range("2023-07-01", "2023-08-31", freq="D").tolist()
        + [pd.Timestamp("2099-12-31")] * 3
    )
    resultado = analisar_estatisticas(pd.Series(datas, name="dt_evento"), len(datas))

    extras = resultado["estatisticas_adicionais"]
    assert extras["qtd_datas_futuras"] == 3
    assert extras["qtd_meses_sem_registro"] >= 3  # abril, maio, junho
    assert "2023-04" in extras["meses_sem_registro"]


def test_sentinela_de_data_detectada():
    datas = pd.to_datetime(["1900-01-01"] * 30 + ["2023-05-01"] * 170)
    resultado = analisar_estatisticas(pd.Series(datas, name="dt_admissao"), 200)
    assert resultado["qualidade"]["sentinelas"]["tem_sentinela"] is True


# ── Otimização de dtype ─────────────────────────────────────────────────────

def test_sugere_downcast_de_inteiro():
    resultado = sugerir_dtype(pd.Series(range(100), dtype="int64"), "Número Inteiro", 100, 100)
    assert resultado["dtype_sugerido"] == "int8"
    assert resultado["economia_pct"] > 0.5


def test_sugere_category_para_texto_de_baixa_cardinalidade():
    serie = pd.Series(["SP", "RJ", "MG"] * 1000)
    resultado = sugerir_dtype(serie, "Texto", 3, 3000)
    assert resultado["dtype_sugerido"] == "category"
    assert resultado["economia_mb"] > 0


def test_nao_sugere_category_para_texto_de_alta_cardinalidade():
    serie = pd.Series([f"valor_unico_{i}" for i in range(1000)])
    assert sugerir_dtype(serie, "Texto", 1000, 1000)["dtype_sugerido"] is None


# ── Integração da coluna ────────────────────────────────────────────────────

def test_analisar_estatisticas_inclui_testes_hipotese_para_numerica():
    resultado = analisar_estatisticas(pd.Series(range(50), dtype=float), 50)
    assert "shapiro_wilk" in resultado["estatisticas_adicionais"]["testes_hipotese"]


def test_benford_so_roda_quando_solicitado():
    rng = np.random.default_rng(5)
    serie = pd.Series(rng.lognormal(5, 2, 2000), name="valor_nota")

    sem = analisar_estatisticas(serie, 2000, avaliar_benford=False)
    com = analisar_estatisticas(serie, 2000, avaliar_benford=True)

    assert "benford" not in sem["estatisticas_adicionais"]
    assert "benford" in com["estatisticas_adicionais"]

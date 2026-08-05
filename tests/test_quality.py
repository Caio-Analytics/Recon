import pandas as pd

from data_profiler import config
from data_profiler.quality import _REGRAS_KPI, detectar_dependencias_funcionais, gerar_gap_analysis


def _meta(coluna, qtd_unicos, ratio_unicidade, caracteristica="🏷️ Categórica / Dimensão Curta"):
    return {"Coluna": coluna, "Qtd_Unicos": qtd_unicos, "Ratio_Unicidade": ratio_unicidade, "Caracteristica": caracteristica}


def test_fd_real_e_detectada():
    df = pd.DataFrame({
        "cod_depto": ["D1"] * 5 + ["D2"] * 5,
        "nome_depto": ["Operações"] * 5 + ["TI"] * 5,
    })
    colunas_meta = [_meta("cod_depto", 2, 0.2), _meta("nome_depto", 2, 0.2)]

    fds = detectar_dependencias_funcionais(df, colunas_meta)

    determinantes = {f["determinante"] for f in fds}
    assert "cod_depto" in determinantes


def test_coluna_quase_chave_nao_vira_determinante_trivial():
    df = pd.DataFrame({
        "id_quase_unico": [f"ID{i}" for i in range(100)],
        "outra_coluna": (["X"] * 50 + ["Y"] * 50),
    })
    colunas_meta = [_meta("id_quase_unico", 100, 1.0), _meta("outra_coluna", 2, 0.02)]

    fds = detectar_dependencias_funcionais(df, colunas_meta)

    determinantes = {f["determinante"] for f in fds}
    assert "id_quase_unico" not in determinantes


def test_fd_considera_nulos_no_agrupador():
    df = pd.DataFrame({
        "cod_depto": ["D1", "D1", None, None],
        "nome_depto": ["Operações", "Operações", "TI", "RH"],
    })
    colunas_meta = [_meta("cod_depto", 2, 0.5), _meta("nome_depto", 3, 0.75)]

    fds = detectar_dependencias_funcionais(df, colunas_meta)

    # Com os 2 nulos de cod_depto agrupados juntos, nome_depto varia (TI/RH)
    # dentro desse grupo -> não deve ser reportado como "cod_depto determina nome_depto".
    determinantes_de_nome = [f for f in fds if f["dependente"] == "nome_depto"]
    assert all(f["determinante"] != "cod_depto" for f in determinantes_de_nome)


def test_gap_analysis_kpi_bloqueado_sem_semanticas():
    gaps = gerar_gap_analysis(set())
    assert all(g["status"] == "❌ Bloqueado" for g in gaps)


def test_gap_analysis_kpi_habilitado_com_semanticas_completas():
    gaps = gerar_gap_analysis({"Estrutura Organizacional", "Quantidade / Métrica"})
    gap_hr_001 = next(g for g in gaps if g["kpi_id"] == "KPI_HR_001")
    assert gap_hr_001["status"] == "✅ Habilitado"


def test_regras_kpi_semanticas_existem_na_taxonomia():
    """Toda string de semântica referenciada em _REGRAS_KPI precisa existir
    como chave em config.CATEGORIAS_FORTES ou config.CATEGORIAS_FUZZY — caso
    contrário uma renomeação de categoria quebraria o gap analysis de KPIs
    silenciosamente (sem falha de teste)."""
    todas_categorias = set(config.CATEGORIAS_FORTES) | set(config.CATEGORIAS_FUZZY)
    for regra in _REGRAS_KPI:
        for semantica in regra["semanticas"]:
            assert semantica in todas_categorias, f"{semantica} não existe em nenhuma taxonomia"

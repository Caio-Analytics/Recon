"""Inferência do modelo de dados a partir de um conjunto de tabelas."""
import numpy as np
import pandas as pd
import pytest

from recon import datamodel
from recon.pipeline import DataProfiler


def _tabela(nome: str, df: pd.DataFrame, origem: str = "") -> datamodel.TabelaCarregada:
    payload = DataProfiler().processar_dataframe(df, nome)
    return datamodel.TabelaCarregada(nome=nome, df=df, payload=payload, origem=origem or f"{nome}.csv")


@pytest.fixture(scope="module")
def conjunto_rh():
    """Empregados (dimensão) × Treinamentos (fato) × Cursos (dimensão) — o
    arranjo mais comum de quem recebe extrações soltas de RH."""
    rng = np.random.default_rng(7)
    n_emp, n_tre = 300, 1500

    empregados = pd.DataFrame({
        "matricula": range(50000, 50000 + n_emp),
        "nome_colaborador": [f"Colaborador {i}" for i in range(n_emp)],
        "cd_dpto": rng.choice(["D01", "D02", "D03"], n_emp),
        "diretoria": None,
        "cargo": rng.choice(["Analista", "Gerente"], n_emp),
    })
    empregados["diretoria"] = empregados["cd_dpto"].map(
        {"D01": "Operacoes", "D02": "Tecnologia", "D03": "RH"}
    )
    cursos = pd.DataFrame({
        "cod_curso": [f"C{i:03d}" for i in range(1, 21)],
        "nome_curso": [f"Curso {i}" for i in range(1, 21)],
        "carga_horaria": rng.integers(2, 41, 20),
    })
    treinamentos = pd.DataFrame({
        "id_realizacao": range(1, n_tre + 1),
        "matricula": rng.choice(empregados["matricula"], n_tre),
        "cod_curso": rng.choice(cursos["cod_curso"], n_tre),
        "dt_realizacao": pd.to_datetime("2023-01-01")
        + pd.to_timedelta(rng.integers(0, 500, n_tre), unit="D"),
        "nota_avaliacao": np.round(rng.uniform(5, 10, n_tre), 1),
    })
    return [
        _tabela("empregados", empregados),
        _tabela("treinamentos", treinamentos),
        _tabela("cursos", cursos),
    ]


# ── Relacionamentos ─────────────────────────────────────────────────────────

def test_detecta_as_chaves_estrangeiras_reais(conjunto_rh):
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    pares = {
        (r["tabela_origem"], r["coluna_origem"], r["tabela_destino"], r["coluna_destino"])
        for r in relacoes
    }
    assert ("treinamentos", "matricula", "empregados", "matricula") in pares
    assert ("treinamentos", "cod_curso", "cursos", "cod_curso") in pares


def test_medida_nao_e_confundida_com_chave_estrangeira(conjunto_rh):
    """`carga_horaria` (2 a 40) está inteiramente contida em qualquer `id`
    sequencial que vá até 1.500 — contenção perfeita e relação inexistente."""
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    assert not [r for r in relacoes if r["coluna_origem"] == "carga_horaria"]


def test_chave_como_texto_em_um_arquivo_e_numero_no_outro():
    """Extrações de sistemas diferentes trazem a mesma chave com tipos
    diferentes. A relação precisa ser encontrada mesmo assim — e o cast, avisado."""
    a = pd.DataFrame({"id_item": [f"{i}" for i in range(100, 140)],
                      "descricao": [f"Item {i}" for i in range(40)]})
    b = pd.DataFrame({"cod_item": list(range(100, 140)) * 3,
                      "qtd_vendida": list(range(120))})

    relacoes = datamodel.detectar_relacionamentos([_tabela("itens", a), _tabela("vendas", b)])

    assert relacoes
    relacao = relacoes[0]
    assert relacao["contencao"] == 1.0
    assert relacao["tipos_incompativeis"] is True


def test_orfaos_sao_medidos_por_linha_e_por_valor_distinto():
    """8% de linhas órfãs podem ser 30% dos valores distintos. Medir só por
    valor distinto descartaria a relação inteira; medir só por linha esconderia
    a dispersão do problema."""
    dim = pd.DataFrame({"matricula": range(1000, 1100),
                        "nome": [f"P{i}" for i in range(100)]})
    fato = pd.DataFrame({
        "id": range(1, 501),
        "matricula": list(range(1000, 1100)) * 4 + list(range(90000, 90100)),
        "valor_pago": range(500),
    })

    relacoes = datamodel.detectar_relacionamentos([_tabela("dim", dim), _tabela("fato", fato)])
    relacao = next(r for r in relacoes if r["coluna_origem"] == "matricula")

    assert relacao["pct_orfaos"] == pytest.approx(0.2, abs=0.01)   # 100 de 500 linhas
    assert relacao["contencao"] == pytest.approx(0.5, abs=0.01)    # 100 de 200 distintos


def test_tabelas_sem_relacao_nao_geram_falso_positivo():
    a = pd.DataFrame({"cod_produto": [f"P{i}" for i in range(50)], "preco": range(50)})
    b = pd.DataFrame({"cpf_cliente": [f"{i:011d}" for i in range(900, 950)],
                      "cidade": ["SP"] * 50})
    assert datamodel.detectar_relacionamentos([_tabela("a", a), _tabela("b", b)]) == []


def test_conjunto_de_uma_tabela_nao_tem_relacionamentos(conjunto_rh):
    assert datamodel.detectar_relacionamentos(conjunto_rh[:1]) == []


# ── Papéis ──────────────────────────────────────────────────────────────────

def test_classifica_fato_e_dimensoes(conjunto_rh):
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    perfis = datamodel.classificar_papeis(conjunto_rh, relacoes)

    assert perfis["treinamentos"].papel == "Fato"
    assert perfis["empregados"].papel == "Dimensão"
    assert perfis["cursos"].papel == "Dimensão"


def test_chave_primaria_prefere_identificador_a_nome(conjunto_rh):
    """`nome_colaborador` é formalmente único, mas ninguém usa nome de pessoa
    como chave."""
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    perfis = datamodel.classificar_papeis(conjunto_rh, relacoes)
    assert perfis["empregados"].chaves_primarias == ["matricula"]


def test_tabela_isolada_e_sinalizada():
    a = pd.DataFrame({"id_a": range(60), "valor": range(60)})
    b = pd.DataFrame({"cod_z": [f"Z{i}" for i in range(40)], "texto": ["x"] * 40})
    tabelas = [_tabela("a", a), _tabela("b", b)]

    perfis = datamodel.classificar_papeis(tabelas, [])
    avisos = datamodel.gerar_avisos([], perfis)

    assert any("não se liga" in a["mensagem"] for a in avisos)


# ── Análises sugeridas ──────────────────────────────────────────────────────

def test_sugere_medida_que_mora_na_dimensao(conjunto_rh):
    """A carga horária está na dimensão do curso, não no fato. Cruzar as duas
    é exatamente o que ninguém enxerga olhando uma planilha por vez."""
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    perfis = datamodel.classificar_papeis(conjunto_rh, relacoes)
    analises = datamodel.sugerir_analises(conjunto_rh, relacoes, perfis)

    alvo = [a for a in analises if "carga_horaria" in a["titulo"] and "diretoria" in a["titulo"]]
    assert alvo, [a["titulo"] for a in analises]
    assert set(alvo[0]["tabelas_envolvidas"]) == {"treinamentos", "empregados", "cursos"}


def test_medida_nao_aditiva_usa_media(conjunto_rh):
    """Somar nota não significa nada; a média significa."""
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    perfis = datamodel.classificar_papeis(conjunto_rh, relacoes)
    analises = datamodel.sugerir_analises(conjunto_rh, relacoes, perfis)

    nota = next(a for a in analises if "nota_avaliacao" in a["titulo"])
    assert nota["titulo"].startswith("Média")
    assert ".mean()" in nota["pandas"]

    carga = next(a for a in analises if "carga_horaria" in a["titulo"])
    assert carga["titulo"].startswith("Total")
    assert ".sum()" in carga["pandas"]


def test_atributo_descritivo_vem_antes_do_codigo(conjunto_rh):
    """Entre `cd_dpto` e `diretoria` — mesmo domínio, mesma cardinalidade — o
    segundo é muito mais legível como eixo de análise."""
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    perfis = datamodel.classificar_papeis(conjunto_rh, relacoes)
    analises = datamodel.sugerir_analises(conjunto_rh, relacoes, perfis)

    titulos = [a["titulo"] for a in analises]
    primeiro_diretoria = next(i for i, t in enumerate(titulos) if "diretoria" in t)
    primeiro_codigo = next((i for i, t in enumerate(titulos) if "cd_dpto" in t), 10**6)
    assert primeiro_diretoria < primeiro_codigo


def test_codigo_pandas_gerado_realmente_roda(conjunto_rh):
    """Código gerado que não executa é pior do que nenhum código."""
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    perfis = datamodel.classificar_papeis(conjunto_rh, relacoes)
    analises = datamodel.sugerir_analises(conjunto_rh, relacoes, perfis)

    assert analises
    for analise in analises:
        escopo = {"pd": pd, **{t.nome: t.df for t in conjunto_rh}}
        exec(analise["pandas"], escopo)  # noqa: S102 — o objetivo do teste é executar
        resultado = escopo["resultado"]
        assert isinstance(resultado, pd.DataFrame)
        assert len(resultado) > 0


def test_codigo_sugerido_escapa_aspas_em_nomes_externos():
    pandas = datamodel._codigo_pandas(
        'fato"2026', [], {"tabela": 'fato"2026', "coluna": 'valor"bruto'},
        {"tabela": 'fato"2026', "coluna": 'grupo"nome'}, "sum",
    )
    sql = datamodel._codigo_sql(
        'fato"2026', [], {"tabela": 'fato"2026', "coluna": 'valor"bruto'},
        {"tabela": 'fato"2026', "coluna": 'grupo"nome'}, "sum",
    )
    escopo = {
        datamodel._variavel('fato"2026'): pd.DataFrame({
            'grupo"nome': ["A", "B"], 'valor"bruto': [1, 2],
        }),
    }

    exec(pandas, escopo)  # noqa: S102 — valida o código pandas entregue ao usuário

    assert list(escopo["resultado"].columns) == ['grupo"nome', 'valor"bruto']
    assert '"fato""2026"' in sql
    assert '"grupo""nome"' in sql


def test_sql_gerado_menciona_as_tabelas_e_o_join(conjunto_rh):
    relacoes = datamodel.detectar_relacionamentos(conjunto_rh)
    perfis = datamodel.classificar_papeis(conjunto_rh, relacoes)
    analises = datamodel.sugerir_analises(conjunto_rh, relacoes, perfis)

    carga = next(a for a in analises if "carga_horaria" in a["titulo"])
    assert "LEFT JOIN" in carga["sql"]
    assert "GROUP BY" in carga["sql"]
    assert "treinamentos" in carga["sql"]


# ── Payload completo ────────────────────────────────────────────────────────

def test_analisar_conjunto_monta_payload_completo(conjunto_rh):
    modelo = datamodel.analisar_conjunto(conjunto_rh, "rh")

    assert modelo["metadados_execucao"]["total_tabelas"] == 3
    assert modelo["metadados_execucao"]["total_relacionamentos"] == 2
    assert len(modelo["tabelas"]) == 3
    assert modelo["analises_sugeridas"]
    papeis = {t["nome"]: t["papel"] for t in modelo["tabelas"]}
    assert papeis["treinamentos"] == "Fato"


def test_modelar_conjunto_exige_duas_tabelas(tmp_path):
    caminho = tmp_path / "solo.csv"
    pd.DataFrame({"a": range(40), "b": range(40)}).to_csv(caminho, index=False)

    with pytest.raises(ValueError, match="ao menos 2 tabelas"):
        DataProfiler().modelar_conjunto([str(caminho)], saida_base=str(tmp_path / "m"))


def test_modelar_conjunto_gera_relatorios(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dim = pd.DataFrame({"cod_dep": [f"D{i:02d}" for i in range(20)],
                        "nome_dep": [f"Depto {i}" for i in range(20)]})
    fato = pd.DataFrame({"id_registro": range(200),
                         "cod_dep": [f"D{i % 20:02d}" for i in range(200)],
                         "vl_gasto": range(200)})
    dim.to_csv(tmp_path / "dim.csv", index=False)
    fato.to_csv(tmp_path / "fato.csv", index=False)

    DataProfiler().modelar_conjunto(
        [str(tmp_path / "dim.csv"), str(tmp_path / "fato.csv")],
        saida_base="conj", formatos=["json", "markdown", "html"], perfis_individuais=False,
    )

    assert (tmp_path / "conj_modelo.json").exists()
    assert (tmp_path / "conj_modelo.md").exists()
    assert (tmp_path / "conj_modelo.html").exists()
    conteudo = (tmp_path / "conj_modelo.md").read_text(encoding="utf-8")
    assert "erDiagram" in conteudo
    assert "Análises sugeridas" in conteudo


def test_cada_aba_do_excel_vira_uma_tabela(tmp_path, monkeypatch):
    """Um arquivo de cinco abas é cinco tabelas que podem se relacionar entre
    si — arranjo mais comum de quem trabalha com extração em planilha."""
    monkeypatch.chdir(tmp_path)
    caminho = tmp_path / "conjunto.xlsx"
    dim = pd.DataFrame({"cod_dep": [f"D{i:02d}" for i in range(20)],
                        "nome_dep": [f"Depto {i}" for i in range(20)]})
    fato = pd.DataFrame({"id_registro": range(200),
                         "cod_dep": [f"D{i % 20:02d}" for i in range(200)],
                         "vl_gasto": range(200)})
    with pd.ExcelWriter(caminho) as writer:
        dim.to_excel(writer, sheet_name="Departamentos", index=False)
        fato.to_excel(writer, sheet_name="Gastos", index=False)

    modelo = DataProfiler().modelar_conjunto(
        [str(caminho)], saida_base="abas", formatos=["json"], perfis_individuais=False
    )

    assert modelo["metadados_execucao"]["total_tabelas"] == 2
    assert modelo["metadados_execucao"]["total_relacionamentos"] == 1
    assert all("::" in t["origem"] for t in modelo["tabelas"])

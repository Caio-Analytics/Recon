"""Detecção de layout de planilha feita por gente.

Metade dos testes verifica que a detecção *não* dispara: uma heurística de
layout que se engana num arquivo bem formado é pior que não ter heurística
nenhuma, porque estraga o caso comum para consertar o raro.
"""
import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

from recon import ingestion, layout
from recon.pipeline import DataProfiler


def _planilha_com_preambulo(caminho, com_total=True, n=200):
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatorio"
    ws.append(["RELATORIO DE TREINAMENTOS - 2024"])
    ws.append([])
    ws.append(["Emitido em 14/08/2026"])
    ws.append([])
    ws.append(["Matricula", "Colaborador", "Departamento", "Horas"])
    rng = np.random.default_rng(1)
    for i in range(n):
        ws.append([50000 + i, f"Colaborador {i}",
                   str(rng.choice(["TI", "RH", "Operacoes"])), int(rng.integers(4, 41))])
    if com_total:
        ws.append(["TOTAL", "", "", 4400])
    wb.save(caminho)
    return caminho


# ── Cabeçalho ───────────────────────────────────────────────────────────────

def test_detecta_cabecalho_fora_da_primeira_linha(tmp_path):
    """Sem isso o título vira nome de coluna e o relatório sai bonito e errado."""
    caminho = _planilha_com_preambulo(tmp_path / "rel.xlsx")

    df, _ = ingestion.carregar_arquivo(str(caminho))

    assert list(df.columns) == ["Matricula", "Colaborador", "Departamento", "Horas"]
    assert len(df) == 200
    assert df.attrs["layout"].linha_cabecalho == 4


def test_cabecalho_na_primeira_linha_nao_e_alterado(tmp_path):
    caminho = tmp_path / "limpo.xlsx"
    pd.DataFrame({"id": range(50), "nome": [f"N{i}" for i in range(50)],
                  "valor": range(50)}).to_excel(caminho, index=False)

    df, _ = ingestion.carregar_arquivo(str(caminho))

    assert list(df.columns) == ["id", "nome", "valor"]
    assert df.attrs["layout"].linha_cabecalho == 0
    assert df.attrs["layout"].avisos == []


def test_csv_com_preambulo(tmp_path):
    caminho = tmp_path / "rel.csv"
    linhas = ["Relatorio Mensal", "", "id,nome,valor"]
    linhas += [f"{i},N{i},{i * 10}" for i in range(60)]
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    df, _ = ingestion.carregar_arquivo(str(caminho))

    assert list(df.columns) == ["id", "nome", "valor"]
    assert len(df) == 60


def test_deteccao_pode_ser_desligada(tmp_path):
    caminho = _planilha_com_preambulo(tmp_path / "rel.xlsx")

    df, _ = ingestion.carregar_arquivo(str(caminho), detectar_layout=False)

    assert "Matricula" not in df.columns


def test_linha_do_cabecalho_pode_ser_forcada(tmp_path):
    caminho = _planilha_com_preambulo(tmp_path / "rel.xlsx")

    df, _ = ingestion.carregar_arquivo(str(caminho), linha_cabecalho=4)

    assert list(df.columns) == ["Matricula", "Colaborador", "Departamento", "Horas"]


def test_tabela_sem_dados_abaixo_nao_vira_cabecalho():
    """Uma linha larga de texto no fim do arquivo não é cabeçalho — não há
    dados depois dela."""
    df = pd.DataFrame([["a", "b", "c"], [1, 2, 3], [4, 5, 6], ["x", "y", "z"]])
    indice, _ = layout.detectar_linha_cabecalho(df)
    assert indice == 0


# ── Linha de total ──────────────────────────────────────────────────────────

def test_detecta_total_por_rotulo(tmp_path):
    caminho = _planilha_com_preambulo(tmp_path / "rel.xlsx")

    df, _ = ingestion.carregar_arquivo(str(caminho))

    assert df.attrs["layout"].linhas_rodape == 1
    assert "TOTAL" not in df["Matricula"].astype(str).tolist()


def test_detecta_total_por_soma_sem_rotulo():
    corpo = pd.DataFrame({"item": [f"I{i}" for i in range(10)],
                          "valor": [10.0] * 10})
    com_total = pd.concat(
        [corpo, pd.DataFrame({"item": [None], "valor": [100.0]})], ignore_index=True
    )
    linhas, avisos = layout.detectar_linha_de_total(com_total)
    assert linhas == 1
    assert "soma da coluna" in avisos[0]["mensagem"]


def test_ultima_linha_normal_nao_e_confundida_com_total():
    df = pd.DataFrame({"item": [f"I{i}" for i in range(20)],
                       "valor": list(range(1, 21))})
    assert layout.detectar_linha_de_total(df)[0] == 0


def test_total_removido_restaura_o_tipo_numerico(tmp_path):
    """`Matricula` fica textual enquanto existir um 'TOTAL' no rodapé; sem
    reconverter, a estatística e a semântica seguem degradadas."""
    caminho = _planilha_com_preambulo(tmp_path / "rel.xlsx")

    df, _ = ingestion.carregar_arquivo(str(caminho))

    assert pd.api.types.is_numeric_dtype(df["Matricula"])


# ── Reinferência de tipos ───────────────────────────────────────────────────

@pytest.mark.parametrize("valores,vira_numero", [
    (["1", "2", "3"], True),
    (["1.5", "2.5"], True),
    (["00123", "00456"], False),          # zero à esquerda é código, não número
    (["a", "1"], False),
    (["111.444.777-35", "111.444.777-35"], False),
])
def test_reinferencia_preserva_codigos(valores, vira_numero):
    resultado = layout.reinferir_numericas(pd.DataFrame({"c": valores}))
    assert pd.api.types.is_numeric_dtype(resultado["c"]) is vira_numero


# ── Células mescladas ───────────────────────────────────────────────────────

def test_detecta_celula_mesclada():
    """Mesclagem no Excel guarda o valor só na primeira célula do bloco."""
    coluna = []
    for departamento in ("TI", "RH", "Operacoes", "Financeiro"):
        coluna += [departamento] + [None] * 9
    df = pd.DataFrame({"departamento": coluna, "valor": range(40)})

    avisos = layout.detectar_celulas_mescladas(df)

    assert len(avisos) == 1
    assert "mesclada" in avisos[0]["tipo"].lower()


def test_coluna_com_nulos_normais_nao_e_mesclagem():
    rng = np.random.default_rng(3)
    valores = [None if rng.random() < 0.4 else f"V{rng.integers(0, 20)}" for _ in range(200)]
    valores[0] = "V1"
    df = pd.DataFrame({"c": valores})
    assert layout.detectar_celulas_mescladas(df) == []


def test_coluna_sem_nulos_nao_e_mesclagem():
    df = pd.DataFrame({"c": ["TI", "RH"] * 50})
    assert layout.detectar_celulas_mescladas(df) == []


# ── Blocos múltiplos ────────────────────────────────────────────────────────

def test_detecta_duas_tabelas_na_mesma_aba():
    bloco = pd.DataFrame({"a": range(10), "b": range(10)})
    vazia = pd.DataFrame({"a": [None], "b": [None]})
    df = pd.concat([bloco, vazia, bloco], ignore_index=True)

    avisos = layout.detectar_blocos_multiplos(df)

    assert len(avisos) == 1
    assert avisos[0]["severidade"] == "🔴 ALTA"


def test_tabela_contigua_nao_dispara_aviso_de_blocos():
    df = pd.DataFrame({"a": range(30), "b": range(30)})
    assert layout.detectar_blocos_multiplos(df) == []


# ── Colunas vazias de formatação ────────────────────────────────────────────

def test_remove_colunas_sem_nome_e_sem_valor():
    df = pd.DataFrame({"a": range(5), "Unnamed: 3": [None] * 5, "b": range(5)})
    limpo, removidas = layout.remover_colunas_vazias(df)
    assert removidas == ["Unnamed: 3"]
    assert list(limpo.columns) == ["a", "b"]


def test_coluna_vazia_com_nome_de_verdade_e_preservada():
    """Uma coluna nomeada e 100% vazia é um achado do perfil ('remover: 100%
    nulos'), não sobra de formatação."""
    df = pd.DataFrame({"a": range(5), "observacao": [None] * 5})
    limpo, removidas = layout.remover_colunas_vazias(df)
    assert removidas == []
    assert "observacao" in limpo.columns


# ── Integração com o relatório ──────────────────────────────────────────────

def test_avisos_de_layout_chegam_ao_payload_e_ao_relatorio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho = _planilha_com_preambulo(tmp_path / "rel.xlsx")

    payloads = DataProfiler().processar_arquivo(
        str(caminho), saida_base="s", formatos=["markdown"]
    )

    layout_info = payloads[0]["metadados_execucao"]["layout"]
    assert layout_info["linha_cabecalho"] == 4
    assert layout_info["linhas_rodape_removidas"] == 1
    assert len(layout_info["avisos"]) >= 2

    conteudo = next(tmp_path.glob("s_*.md")).read_text(encoding="utf-8")
    assert "Como o arquivo foi lido" in conteudo
    assert "Cabeçalho fora da primeira linha" in conteudo


def test_planilha_bem_formada_nao_ganha_secao_de_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho = tmp_path / "limpo.csv"
    pd.DataFrame({"id": range(60), "uf": ["SP", "RJ"] * 30}).to_csv(caminho, index=False)

    DataProfiler().processar_arquivo(str(caminho), saida_base="s", formatos=["markdown"])

    conteudo = (tmp_path / "s_limpo.md").read_text(encoding="utf-8")
    assert "Como o arquivo foi lido" not in conteudo


def test_script_de_limpeza_nao_desfaz_a_conversao_de_data(tmp_path, monkeypatch):
    """Regressão: a sugestão de dtype foi calculada sobre a coluna textual, e
    aplicá-la depois do `to_datetime` transformava o datetime recém-criado em
    `category`, desfazendo o passo anterior."""
    monkeypatch.chdir(tmp_path)
    caminho = tmp_path / "datas.csv"
    pd.DataFrame({
        "dt_evento": [f"2023-0{(i % 9) + 1}-15" for i in range(120)],
        "valor": range(120),
    }).to_csv(caminho, index=False)

    DataProfiler().processar_arquivo(
        str(caminho), saida_base="s", formatos=["json"], gerar_limpeza=True
    )

    script = (tmp_path / "s_datas_limpeza.py").read_text(encoding="utf-8")
    # Data ISO agora é convertida já na leitura (o `parse_dates` reproduz o que
    # a ingestão fez), então a conversão pode vir de lá ou de um passo próprio —
    # o que o teste garante é o resultado: o script termina com datetime.
    assert "parse_dates" in script or "to_datetime" in script
    escopo: dict = {}
    exec(compile(script, "limpeza.py", "exec"), escopo)  # noqa: S102
    assert pd.api.types.is_datetime64_any_dtype(escopo["df"]["dt_evento"])

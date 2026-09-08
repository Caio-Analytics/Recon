import pandas as pd
import pytest
from typer.testing import CliRunner

from recon import gui
from recon.cli import app

runner = CliRunner()


def _csv(pasta, nome, **colunas):
    caminho = pasta / nome
    pd.DataFrame(colunas).to_csv(caminho, index=False)
    return str(caminho)


def _acao(chave):
    return next(a for a in gui.ACOES if a.chave == chave)


def test_sem_escolha_salva_ao_lado_do_arquivo_de_entrada(tmp_path):
    entrada = tmp_path / "dados"
    entrada.mkdir()
    arquivo = _csv(entrada, "base.csv", id=[1, 2])

    assert gui.resolver_pasta_saida("", [arquivo]) == entrada.resolve()


def test_escolha_explicita_vence(tmp_path):
    destino = tmp_path / "relatorios"
    assert gui.resolver_pasta_saida(str(destino), ["/qualquer/base.csv"]) == destino


def test_caminho_colado_com_aspas_funciona(tmp_path):
    destino = tmp_path / "saida"
    assert gui.resolver_pasta_saida(f'"{destino}"  ', []) == destino


def test_sem_escolha_e_sem_arquivo_e_erro():
    with pytest.raises(ValueError):
        gui.resolver_pasta_saida("   ", [])


def test_sem_arquivo_pede_para_procurar():
    aviso = gui.validar_selecao(_acao("individual"), [])
    assert aviso is not None and "Procurar" in aviso


def test_lote_com_um_arquivo_so_manda_para_a_aba_certa(tmp_path):
    arquivo = _csv(tmp_path, "base.csv", id=[1, 2])

    aviso = gui.validar_selecao(_acao("lote"), [arquivo])

    assert aviso is not None and "Um arquivo" in aviso


def test_arquivo_que_sumiu_entre_escolher_e_rodar(tmp_path):
    arquivo = _csv(tmp_path, "some.csv", id=[1, 2])
    (tmp_path / "some.csv").unlink()

    aviso = gui.validar_selecao(_acao("individual"), [arquivo])

    assert aviso is not None and "some.csv" in aviso


def test_selecao_valida_nao_impede(tmp_path):
    arquivos = [
        _csv(tmp_path, "a.csv", id=[1, 2]),
        _csv(tmp_path, "b.csv", id=[1, 2]),
    ]
    assert gui.validar_selecao(_acao("lote"), arquivos) is None


def test_planilha_aberta_no_excel_vira_instrucao():
    mensagem = gui.mensagem_amigavel(PermissionError(13, "Permission denied"))
    assert "Excel" in mensagem and "Feche" in mensagem


def test_erro_desconhecido_preserva_o_detalhe():
    mensagem = gui.mensagem_amigavel(ValueError("coluna 'x' duplicada"))
    assert "coluna 'x' duplicada" in mensagem


def test_pasta_lista_so_o_que_o_recon_le(tmp_path):
    _csv(tmp_path, "base.csv", id=[1])
    (tmp_path / "leiame.txt").write_text("nada a ver")
    (tmp_path / "foto.png").write_bytes(b"")

    encontrados = gui.arquivos_suportados(tmp_path)

    assert [p.rsplit("/", 1)[-1] for p in encontrados] == ["base.csv"]


def test_resumo_da_selecao():
    assert "Nenhum" in gui.resumir_selecao([])
    assert gui.resumir_selecao(["/tmp/vendas.csv"]) == "1 arquivo: vendas.csv"
    assert gui.resumir_selecao(["/a.csv", "/b.csv"]) == "2 arquivos escolhidos"


def _base_rh(tmp_path):
    empregados = _csv(
        tmp_path,
        "empregados.csv",
        id_empregado=list(range(1, 61)),
        uf=["SP", "RJ", "MG"] * 20,
        salario=[3000 + i * 10 for i in range(60)],
    )
    treinamentos = _csv(
        tmp_path,
        "treinamentos.csv",
        id_treinamento=list(range(1, 61)),
        id_empregado=[(i % 60) + 1 for i in range(60)],
        horas=[8, 16, 24] * 20,
    )
    return empregados, treinamentos


def test_individual_gera_relatorio_na_pasta_escolhida(tmp_path):
    arquivo = _csv(tmp_path, "vendas.csv", id=list(range(80)), uf=["SP", "RJ"] * 40)
    saida = tmp_path / "out"

    gerados, falhas = gui.executar_analise(_acao("individual"), [arquivo], saida)

    assert not falhas
    assert (saida / "recon_vendas.html").exists()
    assert gerados


def test_lote_gera_o_consolidado(tmp_path):
    empregados, treinamentos = _base_rh(tmp_path)
    saida = tmp_path / "out"

    gerados, falhas = gui.executar_analise(_acao("lote"), [empregados, treinamentos], saida)

    assert not falhas
    assert (saida / "recon_consolidado.html").exists()
    assert any(g.name.endswith("_consolidado.html") for g in gerados)


def test_modelo_gera_o_relatorio_do_conjunto(tmp_path):
    empregados, treinamentos = _base_rh(tmp_path)
    saida = tmp_path / "out"

    gerados, _ = gui.executar_analise(_acao("modelo"), [empregados, treinamentos], saida)

    assert (saida / "recon_modelo.html").exists()
    assert any(g.name.endswith("_modelo.html") for g in gerados)


def test_pasta_de_saida_e_criada_se_nao_existir(tmp_path):
    arquivo = _csv(tmp_path, "base.csv", id=list(range(80)))
    saida = tmp_path / "nao" / "existe" / "ainda"

    gui.executar_analise(_acao("individual"), [arquivo], saida)

    assert saida.is_dir()


def test_lote_reporta_falha_sem_abortar_os_outros(tmp_path):
    empregados, _ = _base_rh(tmp_path)
    quebrado = tmp_path / "quebrado.csv"
    quebrado.write_bytes(b"\x00\x01\x02")
    saida = tmp_path / "out"

    gerados, falhas = gui.executar_analise(_acao("lote"), [empregados, str(quebrado)], saida)

    assert gerados
    assert any("quebrado" in caminho for caminho, _ in falhas)


def test_formatos_escolhidos_chegam_no_pipeline(tmp_path):
    arquivo = _csv(tmp_path, "base.csv", id=list(range(80)), uf=["SP", "RJ"] * 40)
    saida = tmp_path / "out"

    gui.executar_analise(_acao("individual"), [arquivo], saida, formatos=["json", "markdown"])

    assert (saida / "recon_base.json").exists()
    assert (saida / "recon_base.md").exists()
    assert not list(saida.glob("*.html"))


def test_sem_html_o_relatorio_principal_e_o_que_sobrou(tmp_path):
    arquivo = _csv(tmp_path, "base.csv", id=list(range(80)))

    gerados, _ = gui.executar_analise(
        _acao("individual"), [arquivo], tmp_path / "out", formatos=["markdown"]
    )

    assert [g.name for g in gerados] == ["recon_base.md"]


def test_script_de_limpeza_so_sai_quando_pedido(tmp_path):
    arquivo = _csv(tmp_path, "base.csv", id=list(range(80)), uf=["SP", "RJ"] * 40)

    gui.executar_analise(_acao("individual"), [arquivo], tmp_path / "sem")
    gui.executar_analise(_acao("individual"), [arquivo], tmp_path / "com", gerar_limpeza=True)

    assert not list((tmp_path / "sem").glob("*_limpeza.py"))
    assert list((tmp_path / "com").glob("*_limpeza.py"))


@pytest.fixture
def janela(monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        raiz = tk.Tk()
    except tk.TclError:
        pytest.skip("sem ambiente gráfico")
    raiz.destroy()

    for metodo in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(gui.messagebox, metodo, lambda *a, **k: "ok")

    aberta = gui.JanelaRecon()
    yield aberta
    aberta.raiz.destroy()


def _esperar_fim(janela, segundos=180):
    import time

    limite = time.time() + segundos
    while janela.rodando and time.time() < limite:
        janela.raiz.update()
        time.sleep(0.02)
    assert not janela.rodando, "a análise não terminou no tempo esperado"


def test_formato_padrao_e_so_o_html(janela):
    assert janela.formatos_escolhidos() == ["html"]


def test_seletor_de_formato_respeita_a_ordem_da_lista(janela):
    janela.formatos["markdown"].set(True)
    janela.formatos["json"].set(True)

    assert janela.formatos_escolhidos() == ["html", "json", "markdown"]


def test_analisar_sem_formato_nenhum_avisa_e_nao_roda(janela, tmp_path, monkeypatch):
    avisos = []
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda _t, m: avisos.append(m))
    janela.paineis[0]._definir([_csv(tmp_path, "base.csv", id=list(range(80)))])
    janela.formatos["html"].set(False)

    janela._analisar()

    assert not janela.rodando
    assert avisos and "formato" in avisos[0].lower()
    assert not list(tmp_path.glob("recon*"))


def test_botao_so_libera_depois_de_escolher_arquivo(janela, tmp_path):
    assert str(janela.botao["state"]) == "disabled"

    janela.paineis[0]._definir([_csv(tmp_path, "base.csv", id=list(range(80)))])
    janela.raiz.update()

    assert str(janela.botao["state"]) == "normal"
    assert "base.csv" in janela.status["text"]


def test_secao_de_ajuda_nao_oferece_botao(janela):
    janela.selecionar(len(gui.ACOES))
    janela.raiz.update()

    assert str(janela.botao["state"]) == "disabled"


def test_navegacao_marca_so_o_item_ativo(janela):
    janela.selecionar(1)
    janela.raiz.update()

    assert [item.selecionado for item in janela.itens] == [False, True, False, False]


def test_trocar_de_secao_preserva_a_selecao_de_arquivos(janela, tmp_path):
    arquivos = [_csv(tmp_path, f"b{i}.csv", id=[1, 2]) for i in range(3)]
    janela.selecionar(1)
    janela.paineis[1]._definir(arquivos)

    janela.selecionar(2)
    janela.selecionar(1)
    janela.raiz.update()

    assert janela.paineis[1].arquivos == arquivos
    assert str(janela.botao["state"]) == "normal"


def test_analise_roda_sem_congelar_a_janela(janela, tmp_path):
    import time

    arquivo = _csv(tmp_path, "vendas.csv", id=list(range(400)), uf=["SP", "RJ"] * 200)
    janela.paineis[0]._definir([arquivo])
    janela.saida_escolhida.set(str(tmp_path / "out"))
    janela.raiz.update()

    inicio = time.perf_counter()
    janela._analisar()
    devolveu_em = time.perf_counter() - inicio

    assert devolveu_em < 1.0, "o clique bloqueou a interface"
    assert janela.rodando
    assert str(janela.botao["state"]) == "disabled"
    janela.raiz.update()

    _esperar_fim(janela)

    assert (tmp_path / "out" / "recon_vendas.html").exists()
    assert str(janela.botao["state"]) == "normal"
    assert str(janela.botao_pasta["state"]) == "normal"
    assert janela.ultima_saida == tmp_path / "out"
    assert "recon_vendas.html" in janela.status["text"]


def test_o_log_do_pipeline_aparece_na_area_de_mensagens(janela, tmp_path):
    janela.paineis[0]._definir([_csv(tmp_path, "base.csv", id=list(range(80)))])
    janela._analisar()
    _esperar_fim(janela)

    mensagens = janela.log.get("1.0", "end")

    assert "profiling" in mensagens.lower()
    assert "HTML exportado" in mensagens


def test_erro_no_meio_da_analise_nao_deixa_a_janela_travada(janela, tmp_path):
    quebrado = tmp_path / "quebrado.csv"
    quebrado.write_bytes(b"\x00\x01\x02")
    janela.paineis[0]._definir([str(quebrado)])

    janela._analisar()
    _esperar_fim(janela, segundos=60)

    assert str(janela.botao["state"]) == "normal"
    assert "tente de novo" in janela.status["text"]


def test_janela_cabe_na_tela(janela):
    janela.raiz.update_idletasks()
    largura, altura = janela.raiz.winfo_width(), janela.raiz.winfo_height()

    assert altura <= janela.raiz.winfo_screenheight() - 80
    assert largura <= janela.raiz.winfo_screenwidth() - 50


@pytest.mark.parametrize("altura", [960, 768, 700, 620])
def test_o_botao_continua_alcancavel_em_tela_baixa(janela, altura):
    janela.raiz.geometry(f"780x{altura}")
    janela.raiz.update()
    janela.raiz.update_idletasks()

    topo_da_janela = janela.raiz.winfo_rooty()
    for nome, widget in (
        ("botão", janela.botao),
        ("barra", janela.barra),
        ("status", janela.status),
        ("mensagens", janela.log),
    ):
        base = widget.winfo_rooty() - topo_da_janela + widget.winfo_height()
        assert widget.winfo_ismapped(), f"{nome} sumiu da janela em {altura}px"
        assert base <= altura, f"{nome} ficou {base - altura}px fora da janela em {altura}px"


def test_comando_janela_existe():
    resultado = runner.invoke(app, ["janela", "--help"])

    assert resultado.exit_code == 0
    assert "sem terminal" in resultado.output

"""Comandos de terminal."""
import random

import pandas as pd
from typer.testing import CliRunner

from recon import __version__
from recon.cli import app

runner = CliRunner()


def _csv(tmp_path, nome="dados.csv", n=30):
    caminho = tmp_path / nome
    pd.DataFrame({"id": range(n), "valor": range(n)}).to_csv(caminho, index=False)
    return caminho


def test_vocabularios_estao_disponiveis_em_todos_os_fluxos_de_multiplos_arquivos():
    """O vocabulário do negócio não pode desaparecer ao mudar de comando."""
    for comando in ("lote", "modelar", "pasta", "historico"):
        resultado = runner.invoke(app, [comando, "--help"])
        assert resultado.exit_code == 0
        assert "--vocabularios" in resultado.output


def test_historico_compara_extracoes_e_gera_relatorios(tmp_path, monkeypatch):
    """O histórico preserva a ordem informada e aponta mudança estrutural."""
    import json

    monkeypatch.chdir(tmp_path)
    primeiro = tmp_path / "janeiro.csv"
    segundo = tmp_path / "fevereiro.csv"
    pd.DataFrame({"id": range(10), "valor": range(10)}).to_csv(primeiro, index=False)
    pd.DataFrame({"id": range(10), "valor": range(10), "canal": ["site"] * 10}).to_csv(
        segundo, index=False
    )

    resultado = runner.invoke(
        app,
        [
            "historico", str(primeiro), str(segundo), "--saida-base", "evolucao",
            "--formatos", "json,markdown,html",
        ],
    )

    assert resultado.exit_code == 0
    payload = json.loads((tmp_path / "evolucao_historico.json").read_text(encoding="utf-8"))
    assert [item["arquivo"] for item in payload["extracoes"]] == ["janeiro.csv", "fevereiro.csv"]
    assert any("estrutura mudou" in alerta.lower() for alerta in payload["alertas"])
    assert (tmp_path / "evolucao_historico.md").exists()
    assert (tmp_path / "evolucao_historico.html").exists()


def test_perfilar_gera_json_e_html_por_padrao(tmp_path, monkeypatch):
    """O padrão é HTML: um `.html` clicado abre renderizado no navegador de
    qualquer máquina, enquanto um `.md` abre no bloco de notas mostrando a
    marcação crua para quem não tem visualizador."""
    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(app, ["perfilar", str(_csv(tmp_path)), "--saida-base", "saida"])

    assert resultado.exit_code == 0
    assert (tmp_path / "saida_dados.json").exists()
    assert (tmp_path / "saida_dados.html").exists()
    assert not (tmp_path / "saida_dados.md").exists()


def test_markdown_continua_disponivel_por_opcao(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(
        app, ["perfilar", str(_csv(tmp_path)), "--saida-base", "m", "--formatos", "json,markdown"]
    )

    assert resultado.exit_code == 0
    assert (tmp_path / "m_dados.md").exists()
    assert not (tmp_path / "m_dados.html").exists()


def test_perfilar_com_formatos_customizados(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(
        app, ["perfilar", str(_csv(tmp_path)), "--saida-base", "s", "--formatos", "html,json"]
    )

    assert resultado.exit_code == 0
    assert (tmp_path / "s_dados.html").exists()
    assert not (tmp_path / "s_dados.md").exists()


def test_formato_invalido_e_rejeitado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(
        app, ["perfilar", str(_csv(tmp_path)), "--formatos", "pdf"]
    )
    assert resultado.exit_code != 0


def test_limite_amostra_e_respeitado(tmp_path, monkeypatch):
    """Regressão: `limite_amostra` era a decisão mais importante de custo ×
    precisão da ferramenta e só existia na API Python."""
    import json

    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(
        app, ["perfilar", str(_csv(tmp_path, n=500)), "--saida-base", "s", "--limite-amostra", "50"]
    )

    assert resultado.exit_code == 0
    meta = json.loads((tmp_path / "s_dados.json").read_text(encoding="utf-8"))["metadados_execucao"]
    assert meta["linhas_analisadas"] == 50
    assert meta["amostragem_aplicada"] is True


def test_json_compacto_reduz_o_arquivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caminho = _csv(tmp_path, n=100)
    runner.invoke(app, ["perfilar", str(caminho), "--saida-base", "normal"])
    runner.invoke(app, ["perfilar", str(caminho), "--saida-base", "compacto", "--json-compacto"])

    assert (tmp_path / "compacto_dados.json").stat().st_size < \
           (tmp_path / "normal_dados.json").stat().st_size


def test_kpis_customizados_via_yaml(tmp_path, monkeypatch):
    import json

    monkeypatch.chdir(tmp_path)
    yaml_kpis = tmp_path / "kpis.yaml"
    yaml_kpis.write_text(
        "kpis:\n  - id: MEU_KPI\n    nome: Teste\n    semanticas: [Valor Financeiro]\n",
        encoding="utf-8",
    )

    resultado = runner.invoke(
        app, ["perfilar", str(_csv(tmp_path)), "--saida-base", "s", "--kpis", str(yaml_kpis)]
    )

    assert resultado.exit_code == 0
    payload = json.loads((tmp_path / "s_dados.json").read_text(encoding="utf-8"))
    assert [g["kpi_id"] for g in payload["gap_analysis_kpis"]] == ["MEU_KPI"]


def test_aba_em_csv_gera_aviso(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(
        app, ["perfilar", str(_csv(tmp_path)), "--saida-base", "s", "--aba", "2"]
    )
    assert resultado.exit_code == 0
    assert "ignorados" in resultado.output


def test_comando_versao():
    resultado = runner.invoke(app, ["versao"])
    assert resultado.exit_code == 0
    assert __version__ in resultado.output


def test_perfilar_arquivo_inexistente_retorna_codigo_erro(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["perfilar", "nao_existe.csv"]).exit_code != 0


def test_lote_processa_varios_arquivos_mesmo_com_um_falhando(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pd.DataFrame({"a": range(10)}).to_csv(tmp_path / "bom.csv", index=False)
    (tmp_path / "vazio.csv").write_text("", encoding="utf-8")

    runner.invoke(app, ["lote", str(tmp_path / "bom.csv"), str(tmp_path / "vazio.csv"),
                        "--saida-base", "lote_saida"])

    assert (tmp_path / "lote_saida_bom.json").exists()


def test_lote_continua_apos_falha_mesmo_com_arquivo_ruim_primeiro(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "vazio.csv").write_text("", encoding="utf-8")
    pd.DataFrame({"a": range(10)}).to_csv(tmp_path / "bom.csv", index=False)

    runner.invoke(app, ["lote", str(tmp_path / "vazio.csv"), str(tmp_path / "bom.csv"),
                        "--saida-base", "lote_saida2"])

    assert (tmp_path / "lote_saida2_bom.json").exists()
    assert not (tmp_path / "lote_saida2_vazio.json").exists()


def test_lote_continua_apos_falha_de_encoding(tmp_path, monkeypatch):
    """Ambas as exceções tipadas de ingestão compartilham a base
    IngestionError, capturada pela CLI — um arquivo binário não aborta o lote."""
    monkeypatch.chdir(tmp_path)
    ruim = tmp_path / "binario.csv"
    rng = random.Random(1)
    ruim.write_bytes(bytes(rng.randint(0, 255) for _ in range(2000)))
    pd.DataFrame({"a": range(10)}).to_csv(tmp_path / "bom.csv", index=False)

    runner.invoke(app, ["lote", str(ruim), str(tmp_path / "bom.csv"), "--saida-base", "lote3"])

    assert (tmp_path / "lote3_bom.json").exists()
    assert not (tmp_path / "lote3_binario.json").exists()



def _conjunto(tmp_path):
    dim = pd.DataFrame({"cod_dep": [f"D{i:02d}" for i in range(20)],
                        "nome_dep": [f"Depto {i}" for i in range(20)]})
    fato = pd.DataFrame({"id_registro": range(200),
                         "cod_dep": [f"D{i % 20:02d}" for i in range(200)],
                         "vl_gasto": range(200)})
    dim.to_csv(tmp_path / "dim.csv", index=False)
    fato.to_csv(tmp_path / "fato.csv", index=False)
    return str(tmp_path / "dim.csv"), str(tmp_path / "fato.csv")


def test_modelar_gera_relatorio_do_conjunto(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dim, fato = _conjunto(tmp_path)

    resultado = runner.invoke(
        app, ["modelar", dim, fato, "--saida-base", "m", "--sem-perfis", "--formatos", "markdown"]
    )

    assert resultado.exit_code == 0
    assert (tmp_path / "m_modelo.md").exists()
    assert not (tmp_path / "m_dim.md").exists()


def test_modelar_com_perfis_individuais(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dim, fato = _conjunto(tmp_path)

    runner.invoke(app, ["modelar", dim, fato, "--saida-base", "p", "--formatos", "markdown"])

    assert (tmp_path / "p_modelo.md").exists()
    assert (tmp_path / "p_dim.md").exists()
    assert (tmp_path / "p_fato.md").exists()


def test_modelar_com_uma_tabela_so_falha_com_orientacao(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dim, _ = _conjunto(tmp_path)

    resultado = runner.invoke(app, ["modelar", dim, "--saida-base", "u"])

    assert resultado.exit_code != 0
    assert "perfilar" in resultado.output


def test_perfilar_avisa_sobre_abas_ignoradas(tmp_path, monkeypatch):
    """Perfilar em silêncio só a primeira aba de um arquivo com várias é a
    forma mais fácil de alguém concluir coisa errada sobre os dados."""
    monkeypatch.chdir(tmp_path)
    caminho = tmp_path / "varias.xlsx"
    with pd.ExcelWriter(caminho) as writer:
        for nome in ("Um", "Dois", "Tres"):
            pd.DataFrame({"a": range(30), "b": range(30)}).to_excel(
                writer, sheet_name=nome, index=False
            )

    resultado = runner.invoke(app, ["perfilar", str(caminho), "--saida-base", "s"])

    assert resultado.exit_code == 0
    assert "3 abas" in resultado.output
    assert "--todas-abas" in resultado.output


def test_python_dash_m_recon_funciona_sem_o_script_no_path():
    """`python -m recon` precisa funcionar mesmo quando o script `recon` não
    está no PATH — é o caminho documentado para instalação `--user` em
    máquina corporativa sem admin, onde a pasta de scripts do usuário nem
    sempre está no PATH."""
    import subprocess
    import sys

    saida = subprocess.run(
        [sys.executable, "-m", "recon", "versao"],
        capture_output=True, text=True, timeout=30,
    )
    assert saida.returncode == 0
    assert "Recon" in saida.stdout

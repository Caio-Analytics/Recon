"""Testes de validação de documento, mascaramento e detecção de sujeira."""
import pandas as pd

from recon import patterns

from .conftest import gerar_cnpjs, gerar_cpfs

# ── Validação por dígito verificador ────────────────────────────────────────

def test_validar_cpf_aceita_valido_e_rejeita_invalido():
    assert patterns.validar_cpf("111.444.777-35") is True
    assert patterns.validar_cpf("11144477735") is True
    assert patterns.validar_cpf("123.456.789-00") is False
    assert patterns.validar_cpf("111.111.111-11") is False  # sequência repetida
    assert patterns.validar_cpf("123") is False


def test_validar_cpf_tolera_zero_a_esquerda_perdido():
    """CPF que virou int64 na origem perde o zero à esquerda e chega com 10
    dígitos — precisa validar mesmo assim."""
    completo = gerar_cpfs(1, inicio=12345678)[0].replace(".", "").replace("-", "")
    assert completo.startswith("0")
    assert patterns.validar_cpf(completo.lstrip("0")) is True


def test_validar_cnpj_aceita_valido_e_rejeita_invalido():
    cnpj = gerar_cnpjs(1)[0]
    assert patterns.validar_cnpj(cnpj) is True
    assert patterns.validar_cnpj("12.345.678/0001-00") is False
    assert patterns.validar_cnpj("11.111.111/1111-11") is False


def test_epoch_em_milissegundos_nao_e_confundido_com_cnpj():
    """Regressão: a heurística por comprimento de dígito classificava um
    timestamp epoch em ms (13 dígitos) como CNPJ, e a coluna inteira virava
    'dado sensível' com recomendação de mascarar."""
    epoch_ms = [str(1700000000000 + i) for i in range(200)]
    assert patterns.detectar_padrao_numerico(epoch_ms) == "Nenhum"


def test_id_sequencial_de_dez_digitos_nao_e_confundido_com_cpf():
    ids = [str(1000000000 + i) for i in range(200)]
    assert patterns.detectar_padrao_numerico(ids) == "Nenhum"


def test_cpf_valido_como_inteiro_e_detectado():
    cpfs = [c.replace(".", "").replace("-", "") for c in gerar_cpfs(200)]
    assert patterns.detectar_padrao_numerico(cpfs) == "CPF"


def test_texto_com_formato_de_cpf_mas_dv_invalido_nao_e_cpf():
    """Casar o formato não basta: a máscara de CPF é indistinguível de
    qualquer outro número de 11 dígitos pontuado."""
    falsos = [f"{i:03d}.456.789-00" for i in range(200)]
    assert patterns.detectar_padrao_texto(falsos) != "CPF"


# ── Mascaramento ────────────────────────────────────────────────────────────

def test_mascarar_email_preserva_dominio_multinivel():
    """Regressão: a regex de mascaramento aceitava só dois rótulos de domínio,
    então `@empresa.com.br` — o caso comum no Brasil — caía no fallback
    '***MASCARADO***' e perdia o formato."""
    assert patterns.mascarar_valor_sensivel("ana@empresa.com.br", "E-mail") == "a***@empresa.com.br"
    assert patterns.mascarar_valor_sensivel("ana@mail.corp.co.uk", "E-mail") == "a***@mail.corp.co.uk"
    assert patterns.mascarar_valor_sensivel("ana@empresa.com", "E-mail") == "a***@empresa.com"


def test_mascarar_cpf_preserva_pontuacao_e_esconde_o_resto():
    mascarado = patterns.mascarar_valor_sensivel("111.444.777-35", "CPF")
    assert mascarado.startswith("111")
    assert "444" not in mascarado
    assert mascarado.count(".") == 2 and "-" in mascarado


def test_mascarar_uuid_mantem_apenas_o_primeiro_bloco():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    mascarado = patterns.mascarar_valor_sensivel(uuid, "UUID")
    assert mascarado.startswith("550e8400-")
    assert "e29b" not in mascarado


# ── Sentinelas ──────────────────────────────────────────────────────────────

def test_sentinelas_texto_detectadas():
    serie = pd.Series(["SP"] * 300 + ["N/A"] * 80 + ["-"] * 40 + ["#N/D"] * 30 + ["RJ"] * 50)
    resultado = patterns.detectar_sentinelas_texto(serie.value_counts(), len(serie))

    assert resultado["tem_sentinela"] is True
    assert resultado["qtd_total"] == 150
    assert {v["valor"] for v in resultado["valores"]} == {"N/A", "-", "#N/D"}


def test_sentinela_textual_rara_e_ignorada():
    serie = pd.Series(["SP"] * 999 + ["N/A"])
    resultado = patterns.detectar_sentinelas_texto(serie.value_counts(), len(serie))
    assert resultado["tem_sentinela"] is False


def test_sentinelas_numericas_so_valem_quando_sao_extremo():
    com_sentinela = pd.Series([100.0] * 400 + [-1.0] * 60)
    assert patterns.detectar_sentinelas_numericas(com_sentinela, 460)["tem_sentinela"] is True

    # -1 legítimo, no meio da faixa observada (saldo pode ser negativo)
    legitimo = pd.Series([-5.0] * 50 + [-1.0] * 60 + [100.0] * 400)
    assert patterns.detectar_sentinelas_numericas(legitimo, 510)["tem_sentinela"] is False


def test_sentinelas_de_data_detectadas():
    serie = pd.Series(pd.to_datetime(["1900-01-01"] * 30 + ["2023-05-01"] * 170))
    resultado = patterns.detectar_sentinelas_data(serie, len(serie))
    assert resultado["tem_sentinela"] is True
    assert resultado["valores"][0]["valor"] == "1900-01-01"


# ── Inconsistência de grafia ────────────────────────────────────────────────

def test_inconsistencia_de_grafia_detectada():
    serie = pd.Series(["SP"] * 200 + ["sp"] * 60 + [" SP"] * 40 + ["S.P."] * 20 + ["RJ"] * 80)
    resultado = patterns.detectar_inconsistencia_normalizacao(serie.value_counts())

    assert resultado["tem_inconsistencia"] is True
    assert resultado["valores_unicos_atual"] == 5
    assert resultado["valores_unicos_normalizado"] == 2
    assert set(resultado["exemplos"][0]["variantes"]) == {"SP", "sp", " SP", "S.P."}


def test_valores_realmente_distintos_nao_disparam_inconsistencia():
    serie = pd.Series(["SP"] * 100 + ["RJ"] * 100 + ["MG"] * 100)
    assert patterns.detectar_inconsistencia_normalizacao(serie.value_counts())["tem_inconsistencia"] is False


def test_inconsistencia_pega_acentuacao_divergente():
    serie = pd.Series(["Operações"] * 50 + ["Operacoes"] * 30)
    resultado = patterns.detectar_inconsistencia_normalizacao(serie.value_counts())
    assert resultado["tem_inconsistencia"] is True


# ── Mojibake ────────────────────────────────────────────────────────────────

def test_mojibake_detectado():
    amostra = ["ObservaÃ§Ã£o do cliente"] * 5 + ["texto normal"] * 5
    resultado = patterns.detectar_mojibake(amostra)
    assert resultado["tem_mojibake"] is True
    assert resultado["pct_amostra"] == 0.5


def test_texto_acentuado_correto_nao_e_mojibake():
    assert patterns.detectar_mojibake(["Observação", "Operações", "José"])["tem_mojibake"] is False


# ── PII em texto livre ──────────────────────────────────────────────────────

def test_pii_dentro_de_texto_livre_detectada():
    cpf = gerar_cpfs(1)[0]
    amostra = [f"Cliente reclamou, CPF {cpf}", "sem dado pessoal", "contato ana@x.com.br"]
    resultado = patterns.detectar_pii_em_texto_livre(amostra)

    assert resultado["tem_pii"] is True
    assert set(resultado["tipos"]) >= {"CPF", "E-mail"}


def test_redigir_pii_remove_o_documento_do_texto():
    cpf = gerar_cpfs(1)[0]
    redigido = patterns.redigir_pii_em_texto(f"Contato: {cpf} / ana@x.com")
    assert cpf not in redigido
    assert "ana@x.com" not in redigido
    assert "REDIGIDO" in redigido


def test_texto_sem_pii_nao_dispara():
    assert patterns.detectar_pii_em_texto_livre(["reclamação genérica", "ok"])["tem_pii"] is False


# ── Benford ─────────────────────────────────────────────────────────────────

def test_benford_aderente_para_distribuicao_lognormal():
    import numpy as np
    rng = np.random.default_rng(7)
    serie = pd.Series(rng.lognormal(5, 2, 5000))
    resultado = patterns.distribuicao_benford(serie)
    assert resultado is not None
    assert resultado["aderente"] is True


def test_benford_nao_aderente_para_valores_de_faixa_estreita():
    serie = pd.Series([500.0 + i * 0.01 for i in range(1000)])
    resultado = patterns.distribuicao_benford(serie)
    assert resultado is not None
    assert resultado["aderente"] is False


def test_benford_exige_amostra_minima():
    assert patterns.distribuicao_benford(pd.Series([1.0, 2.0, 3.0])) is None


# ── Documento com formato válido e DV inválido ──────────────────────────────

def test_documento_com_formato_certo_e_dv_errado_e_sinalizado():
    """Com a validação por DV, uma coluna de CPF corrompido deixa de ser
    reportada como CPF — esse silêncio esconderia campo truncado ou dígito
    perdido em conversão numérica."""
    falsos = [f"{i:03d}.456.789-00" for i in range(200)]

    assert patterns.detectar_padrao_texto(falsos) != "CPF"
    resultado = patterns.detectar_documento_invalido(falsos)
    assert resultado["tem_documento_invalido"] is True
    assert resultado["tipo"] == "CPF"
    assert resultado["pct_valido"] < 0.2


def test_documento_valido_nao_e_sinalizado_como_invalido():
    assert patterns.detectar_documento_invalido(gerar_cpfs(200))["tem_documento_invalido"] is False


def test_coluna_toda_de_documentos_nao_vira_pii_em_texto_livre():
    """Regressão: uma coluna que é toda de CPF já é tratada pela detecção de
    padrão estruturado (com mascaramento próprio). Reportá-la também como
    'PII em texto livre' é rotulagem errada e recomendação duplicada."""
    assert patterns.detectar_pii_em_texto_livre(gerar_cpfs(50))["tem_pii"] is False


def test_pii_embutida_em_frase_continua_sendo_detectada():
    cpf = gerar_cpfs(1)[0]
    amostra = [f"Cliente reclamou, CPF {cpf}"] * 5
    assert patterns.detectar_pii_em_texto_livre(amostra)["tem_pii"] is True


def test_matricula_alfanumerica_nao_vira_telefone():
    """Regressão real: a regex de telefone não exigia fronteira no início,
    então casava um trecho de dígitos embutido dentro de um código
    alfanumérico como `CD9988776655`. Telefone não tem letra ao lado."""
    matriculas = ["AB000123456", "CD9988776655", "AB772104537", "EF14290712"] * 5
    assert patterns.detectar_pii_em_texto_livre(matriculas)["tem_pii"] is False


def test_coluna_de_codigo_sem_espaco_nao_e_texto_livre():
    """Texto livre tem espaço; coluna de código não. Rodar a busca de PII
    embutida num código só produz falso positivo."""
    codigos = [f"AB{i:08d}CD" for i in range(40)]
    assert patterns.detectar_pii_em_texto_livre(codigos)["tem_pii"] is False


def test_telefone_em_frase_continua_sendo_detectado():
    frases = ["Cliente ligou do 11 99999-8888 ontem", "retornar no (21) 98888-7777"] * 10
    assert patterns.detectar_pii_em_texto_livre(frases)["tem_pii"] is True


def test_nome_de_pessoa_e_mascarado_preservando_a_forma():
    """Nome completo é dado pessoal sob a LGPD e não casa com nenhum padrão
    estruturado — ia para o relatório em claro."""
    mascarado = patterns.mascarar_nome_pessoa("MARIANA OLIVEIRA DOS SANTOS")
    assert mascarado == "M****** O******* D** S*****"
    assert "MARIANA" not in mascarado

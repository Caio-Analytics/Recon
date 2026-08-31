"""Padrões estruturados, validação de documentos, mascaramento LGPD e
detecção de sujeira de conteúdo (sentinelas, mojibake, inconsistência de
normalização).

Separado de `statistics` porque é lógica de conteúdo de valor — nada aqui
depende de agregação estatística, e vários itens (sentinela, mojibake) são
consumidos direto pelas recomendações de ETL.
"""
import re
from typing import Any

import pandas as pd
from unidecode import unidecode

from . import config

_RE_MOJIBAKE = re.compile(config.PADRAO_MOJIBAKE)
_RE_SO_DIGITOS = re.compile(r"\D")
_RE_NAO_ALFANUM = re.compile(r"[^0-9a-z]")
_RE_NUMERICO_INICIO = re.compile(r"^-?\d")


def eh_numerico_br(valor: str) -> bool:
    """Reconhece número no formato brasileiro: vírgula decimal, ponto como
    separador de milhar quando os dois aparecem juntos.

    Trocar vírgula por ponto sem tirar o ponto de milhar antes rejeitava
    `1.234.567,89` — sobrava um segundo ponto e o valor caía em "texto" por
    engano. Notação científica com vírgula (`4,0000000000000001E-2`) tem o
    mesmo problema e o mesmo conserto: normalizar para o formato que `float`
    entende antes de tentar converter.
    """
    texto = str(valor).strip()
    if not texto or not _RE_NUMERICO_INICIO.match(texto):
        return False
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        float(texto)
    except ValueError:
        return False
    return True


# ── Validação por dígito verificador ────────────────────────────────────────

def _digitos(valor: str) -> str:
    return _RE_SO_DIGITOS.sub("", str(valor))


def validar_cpf(valor: str) -> bool:
    """Valida os dois dígitos verificadores do CPF.

    Aceita valor com ou sem pontuação e com zeros à esquerda perdidos (comum
    quando a coluna virou int64 na origem) — 10 dígitos são completados para
    11. Sequências de dígito repetido (111.111.111-11) são rejeitadas: são
    formalmente válidas na conta, mas na prática só aparecem como preenchimento
    de teste.
    """
    d = _digitos(valor)
    if len(d) in (9, 10):
        d = d.zfill(11)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != int(d[tamanho]):
            return False
    return True


def validar_cnpj(valor: str) -> bool:
    """Valida os dois dígitos verificadores do CNPJ (mesma tolerância a zeros
    à esquerda perdidos que `validar_cpf`)."""
    d = _digitos(valor)
    if len(d) in (12, 13):
        d = d.zfill(14)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6] + pesos_1
    for pesos, posicao in ((pesos_1, 12), (pesos_2, 13)):
        soma = sum(int(d[i]) * p for i, p in enumerate(pesos))
        resto = soma % 11
        esperado = 0 if resto < 2 else 11 - resto
        if esperado != int(d[posicao]):
            return False
    return True


_VALIDADORES = {"CPF": validar_cpf, "CNPJ": validar_cnpj}


def _fracao_valida(valores: list[str], padrao: str) -> float:
    validador = _VALIDADORES.get(padrao)
    if validador is None or not valores:
        return 1.0
    return sum(1 for v in valores if validador(v)) / len(valores)


# ── Detecção de padrão estruturado ──────────────────────────────────────────

def detectar_padrao_texto(amostra_str: list[str], eh_chave_sistema: bool = False) -> str:
    """Identifica o padrão estruturado dominante numa amostra de strings.

    Padrões com dígito verificador (CPF/CNPJ) só são aceitos se a maioria da
    amostra também validar — casar o formato não basta, porque a máscara de
    CPF é indistinguível de qualquer outro número de 11 dígitos pontuado.
    """
    if not amostra_str:
        return "Nenhum"
    for nome, regex in config.PADROES_ESTRUTURADOS.items():
        if eh_chave_sistema and nome in ("CEP", "Telefone"):
            continue
        casados = [v for v in amostra_str if re.match(regex, v)]
        if (len(casados) / len(amostra_str)) < config.THRESHOLD_PADRAO_ESTRUTURADO:
            continue
        if (nome in config.PADROES_COM_VALIDACAO
                and _fracao_valida(casados, nome) < config.THRESHOLD_PADRAO_ESTRUTURADO):
            continue
        return nome
    return "Nenhum"


def detectar_documento_invalido(amostra_str: list[str]) -> dict[str, Any]:
    """Detecta coluna que tem cara de CPF/CNPJ mas cujos dígitos
    verificadores não fecham.

    Consequência direta da validação por DV: quando o formato bate e a conta
    não, o padrão deixa de ser reportado — e esse silêncio esconde um achado
    valioso. Documento com DV inválido em massa é sintoma de campo truncado,
    dígito perdido em conversão numérica ou preenchimento fictício.
    """
    if not amostra_str:
        return {"tem_documento_invalido": False}

    for nome in config.PADROES_COM_VALIDACAO:
        regex = config.PADROES_ESTRUTURADOS[nome]
        casados = [v for v in amostra_str if re.match(regex, v)]
        if (len(casados) / len(amostra_str)) < config.THRESHOLD_PADRAO_ESTRUTURADO:
            continue
        fracao_valida = _fracao_valida(casados, nome)
        if fracao_valida >= config.THRESHOLD_PADRAO_ESTRUTURADO:
            continue
        return {
            "tem_documento_invalido": True,
            "tipo": nome,
            "pct_formato": round(len(casados) / len(amostra_str), 4),
            "pct_valido": round(fracao_valida, 4),
        }
    return {"tem_documento_invalido": False}


def detectar_padrao_numerico(amostra_int_str: list[str]) -> str:
    """Identifica CPF/CNPJ guardado como inteiro (sem pontuação e possivelmente
    sem os zeros à esquerda).

    Diferente da versão por comprimento de dígito, exige o dígito verificador:
    sem isso um timestamp epoch em milissegundos (13 dígitos) é classificado
    como CNPJ e a coluna inteira vira "dado sensível".
    """
    if not amostra_int_str:
        return "Nenhum"
    total = len(amostra_int_str)
    for nome, faixa in (("CNPJ", (12, 13, 14)), ("CPF", (9, 10, 11))):
        candidatos = [v for v in amostra_int_str if len(v) in faixa]
        if (len(candidatos) / total) < config.THRESHOLD_PADRAO_ESTRUTURADO:
            continue
        if _fracao_valida(candidatos, nome) >= config.THRESHOLD_PADRAO_ESTRUTURADO:
            return nome
    return "Nenhum"


# ── Mascaramento LGPD ───────────────────────────────────────────────────────

_RE_EMAIL_MASCARA = re.compile(r"^([\w.+\-]+)@([\w\-]+(?:\.[\w\-]+)+)$")


def mascarar_valor_sensivel(valor: str, padrao_estruturado: str) -> str:
    """Mascara um valor de coluna sinalizada como sensível LGPD
    (CPF/CNPJ/CEP/E-mail/Telefone/UUID), preservando o formato o suficiente
    para o leitor reconhecer o padrão sem expor o dado real."""
    if padrao_estruturado == "E-mail":
        m = _RE_EMAIL_MASCARA.match(valor)
        if not m:
            return "***MASCARADO***"
        local, dominio = m.groups()
        visivel = local[0] if local else ""
        return f"{visivel}{'*' * max(len(local) - 1, 3)}@{dominio}"

    if padrao_estruturado == "UUID":
        partes = valor.split("-")
        if len(partes) != 5:
            return "***MASCARADO***"
        return "-".join([partes[0]] + ["*" * len(p) for p in partes[1:]])

    if padrao_estruturado not in config.PADROES_ESTRUTURADOS:
        return "***MASCARADO***"

    # CPF/CNPJ/CEP/Telefone: mantém os N primeiros caracteres alfanuméricos
    # visíveis e mascara o restante, preservando pontuação/espaços — dá pra
    # reconhecer o formato sem reconstruir o valor original.
    qtd_visivel = 3 if padrao_estruturado == "CPF" else 2
    resultado = []
    vistos = 0
    for ch in valor:
        if ch.isalnum():
            if vistos < qtd_visivel:
                resultado.append(ch)
                vistos += 1
            else:
                resultado.append("*")
        else:
            resultado.append(ch)
    return "".join(resultado)


def eh_sensivel(padrao_estruturado: str) -> bool:
    return padrao_estruturado != "Nenhum"


def mascarar_nome_pessoa(valor: str) -> str:
    """Mascara nome de pessoa preservando a forma do valor.

    Nome completo é dado pessoal sob a LGPD, mas não tem padrão estruturado que
    o detector de documento reconheça — `FULL_NAME` saía no relatório com os
    nomes em claro e marcada como "Dado_Sensivel_LGPD: Nenhum". A inicial e a
    contagem de palavras bastam para quem está perfilando (dá para ver que são
    cinco tokens, com preposição no meio) e não identificam ninguém.
    """
    return _RE_PALAVRA.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), valor)


# ── Sentinelas (nulos disfarçados) ──────────────────────────────────────────

def _normalizar_para_comparacao(valor: str) -> str:
    return unidecode(str(valor)).strip().lower()


def detectar_sentinelas_texto(contagens: pd.Series, n_validos: int) -> dict[str, Any]:
    """Procura valores que representam ausência de dado mas não são nulos
    (`N/A`, `-`, `#N/D`, `NAO INFORMADO`).

    Recebe o `value_counts` já calculado para não varrer a coluna de novo.
    """
    if n_validos <= 0 or contagens.empty:
        return {"tem_sentinela": False}

    achados: list[dict[str, Any]] = []
    for valor, qtd in contagens.items():
        if _normalizar_para_comparacao(str(valor)) not in config.SENTINELAS_TEXTO:
            continue
        pct = float(qtd) / n_validos
        if pct >= config.THRESHOLD_SENTINELA_MIN_PCT:
            achados.append({"valor": str(valor), "qtd": int(qtd), "pct": round(pct, 4)})

    if not achados:
        return {"tem_sentinela": False}
    total = sum(a["qtd"] for a in achados)
    return {
        "tem_sentinela": True,
        "valores": sorted(achados, key=lambda a: -a["qtd"]),
        "qtd_total": total,
        "pct_total": round(total / n_validos, 4),
    }


def detectar_sentinelas_numericas(serie: pd.Series, n_validos: int) -> dict[str, Any]:
    """Procura códigos de ausência numéricos (-1, 999999).

    Um candidato só conta se for extremo da distribuição — um `-1` no meio da
    faixa de valores observados é dado legítimo, não sentinela.
    """
    if n_validos <= 0 or serie.empty:
        return {"tem_sentinela": False}

    minimo, maximo = float(serie.min()), float(serie.max())
    achados: list[dict[str, Any]] = []
    for candidato in config.SENTINELAS_NUMERICAS:
        if candidato not in (minimo, maximo):
            continue
        qtd = int((serie == candidato).sum())
        if qtd == 0:
            continue
        pct = qtd / n_validos
        if pct >= config.THRESHOLD_SENTINELA_MIN_PCT:
            achados.append({"valor": candidato, "qtd": qtd, "pct": round(pct, 4)})

    if not achados:
        return {"tem_sentinela": False}
    total = sum(a["qtd"] for a in achados)
    return {
        "tem_sentinela": True,
        "valores": sorted(achados, key=lambda a: -a["qtd"]),
        "qtd_total": total,
        "pct_total": round(total / n_validos, 4),
    }


def detectar_sentinelas_data(serie: pd.Series, n_validos: int) -> dict[str, Any]:
    """Procura datas usadas como marcador de ausência (1900-01-01, 9999-12-31,
    epoch do Excel)."""
    if n_validos <= 0 or serie.empty:
        return {"tem_sentinela": False}
    achados: list[dict[str, Any]] = []
    normalizada = serie.dt.normalize()
    for texto in config.SENTINELAS_DATA:
        alvo = pd.Timestamp(texto)
        qtd = int((normalizada == alvo).sum())
        if qtd == 0:
            continue
        pct = qtd / n_validos
        if pct >= config.THRESHOLD_SENTINELA_MIN_PCT:
            achados.append({"valor": texto, "qtd": qtd, "pct": round(pct, 4)})
    if not achados:
        return {"tem_sentinela": False}
    total = sum(a["qtd"] for a in achados)
    return {
        "tem_sentinela": True,
        "valores": sorted(achados, key=lambda a: -a["qtd"]),
        "qtd_total": total,
        "pct_total": round(total / n_validos, 4),
    }


# ── Inconsistência de normalização ──────────────────────────────────────────

def _chave_canonica(valor: str) -> str:
    """Chave que agrupa grafias diferentes do mesmo valor.

    Remover pontuação cega funciona para texto (`S.P.` e `SP` são a mesma
    sigla) e quebra para número: `145` e `14,5` viram a mesma sequência de
    dígitos se a vírgula some, mas são dois números diferentes, não duas
    grafias do mesmo. Valor numérico usa o próprio número como chave.
    """
    texto = str(valor)
    if eh_numerico_br(texto):
        normalizado = texto.strip()
        sinal = ""
        if normalizado.startswith("-"):
            sinal, normalizado = "-", normalizado[1:]
        if "," in normalizado:
            normalizado = normalizado.replace(".", "").replace(",", ".")
        return sinal + repr(float(normalizado))
    return _RE_NAO_ALFANUM.sub("", unidecode(texto).lower())


def detectar_inconsistencia_normalizacao(
    contagens: pd.Series, max_exemplos: int = 3
) -> dict[str, Any]:
    """Detecta valores que são o mesmo dado escrito de formas diferentes
    (`SP`, `sp`, ` SP`, `S.P.`).

    Colapsa por chave canônica (sem acento, sem pontuação, minúscula) e
    reporta os grupos que reúnem mais de uma grafia. É o defeito mais comum de
    planilha corporativa e hoje inflava a cardinalidade sem nenhum alerta.
    """
    if contagens.empty or len(contagens) < 2:
        return {"tem_inconsistencia": False}

    grupos: dict[str, list[tuple[str, int]]] = {}
    for valor, qtd in contagens.items():
        chave = _chave_canonica(str(valor))
        if not chave:
            continue
        grupos.setdefault(chave, []).append((str(valor), int(qtd)))

    colapsaveis = [g for g in grupos.values() if len(g) > 1]
    if not colapsaveis:
        return {"tem_inconsistencia": False}

    colapsaveis.sort(key=lambda g: -sum(q for _, q in g))
    exemplos = [
        {"variantes": [v for v, _ in sorted(g, key=lambda x: -x[1])], "qtd_total": sum(q for _, q in g)}
        for g in colapsaveis[:max_exemplos]
    ]
    unicos_atual = int(len(contagens))
    unicos_normalizado = int(len(grupos))
    return {
        "tem_inconsistencia": True,
        "valores_unicos_atual": unicos_atual,
        "valores_unicos_normalizado": unicos_normalizado,
        "grupos_afetados": len(colapsaveis),
        "exemplos": exemplos,
    }


# ── Mojibake ────────────────────────────────────────────────────────────────

def detectar_mojibake(amostra_str: list[str], max_exemplos: int = 3) -> dict[str, Any]:
    """Detecta texto UTF-8 lido com o encoding errado (`ção` → `Ã§Ã£o`).

    Sinaliza problema na origem/ingestão, não no dado — por isso vira
    recomendação de Bronze (reprocessar a carga), não de limpeza.
    """
    if not amostra_str:
        return {"tem_mojibake": False}
    afetados = [v for v in amostra_str if _RE_MOJIBAKE.search(v)]
    if not afetados:
        return {"tem_mojibake": False}
    return {
        "tem_mojibake": True,
        "pct_amostra": round(len(afetados) / len(amostra_str), 4),
        "exemplos": afetados[:max_exemplos],
    }


# ── PII em texto livre ──────────────────────────────────────────────────────

_RE_PII_LIVRE: dict[str, re.Pattern] = {
    "CPF": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "CNPJ": re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    "E-mail": re.compile(r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b"),
    # `(?<!\w)` no início e `(?!\w)` no fim impedem o casamento no meio de
    # um código alfanumérico: sem eles, uma matrícula como `CD9988776655`
    # casava pelo trecho de dígitos. Telefone não tem letra ao lado.
    "Telefone": re.compile(r"(?<!\w)\(?\d{2}\)?\s?9?\d{4}[\s\-]?\d{4}(?!\w)"),
}


def detectar_pii_em_texto_livre(amostra_str: list[str]) -> dict[str, Any]:
    """Procura CPF/CNPJ/e-mail/telefone dentro de coluna de texto livre.

    A detecção de padrão estruturado exige que o valor inteiro seja o
    documento; um CPF citado no meio de uma observação escapa dela — e é
    justamente onde PII costuma vazar sem ninguém perceber.

    Só conta como PII embutida o que não ocupa o valor inteiro. Sem essa
    distinção, uma coluna que é toda de documentos (a que a detecção de padrão
    estruturado já trata, com mascaramento próprio) seria reportada aqui de
    novo, com a rotulagem errada de "texto livre".
    """
    if not amostra_str:
        return {"tem_pii": False}

    # Texto livre tem espaço. Uma coluna de código (`CD9988776655`) não é
    # texto livre, e rodar a busca nela só produz falso positivo — foi assim
    # que uma matrícula virou "telefone embutido".
    com_espaco = sum(1 for v in amostra_str if " " in str(v).strip())
    if com_espaco / len(amostra_str) < _FRACAO_MINIMA_TEXTO_LIVRE:
        return {"tem_pii": False}

    total = len(amostra_str)
    achados: dict[str, dict[str, Any]] = {}
    for nome, regex in _RE_PII_LIVRE.items():
        ocorrencias = [
            (v, m) for v in amostra_str
            if (m := regex.search(v)) is not None and m.group(0) != v.strip()
        ]
        if nome in config.PADROES_COM_VALIDACAO:
            ocorrencias = [(v, m) for v, m in ocorrencias if _VALIDADORES[nome](m.group(0))]
        casados = [v for v, _ in ocorrencias]
        if not casados:
            continue
        achados[nome] = {"qtd_amostra": len(casados), "pct_amostra": round(len(casados) / total, 4)}
    if not achados:
        return {"tem_pii": False}
    return {"tem_pii": True, "tipos": achados}


def redigir_pii_em_texto(valor: str) -> str:
    """Substitui ocorrências de PII dentro de um texto livre por um marcador,
    para que a amostra do relatório possa ser exibida sem expor o dado."""
    texto = str(valor)
    for nome, regex in _RE_PII_LIVRE.items():
        texto = regex.sub(f"[{nome} REDIGIDO]", texto)
    return texto


# ── Formato por "shape" ─────────────────────────────────────────────────────

_TRADUCAO_SHAPE = str.maketrans({
    **{chr(c): "9" for c in range(ord("0"), ord("9") + 1)},
    **{chr(c): "A" for c in range(ord("A"), ord("Z") + 1)},
    **{chr(c): "a" for c in range(ord("a"), ord("z") + 1)},
})
_MAX_COMPRIMENTO_SHAPE = 40


def _shape(valor: str) -> str:
    """Colapsa um valor no seu formato: `AB-1234` vira `AA-9999`."""
    return unidecode(str(valor))[:_MAX_COMPRIMENTO_SHAPE].translate(_TRADUCAO_SHAPE)


def inferir_formato(amostra_str: list[str], cobertura_minima: float = 0.8) -> dict[str, Any]:
    """Descobre o formato dominante de uma coluna de código e quem foge dele.

    Generaliza a detecção de padrão estruturado para códigos que não são
    CPF/CNPJ: matrícula, código de produto, placa, número de contrato. O
    achado principal é a lista de exceções, não o formato dominante em si —
    "98% dos códigos são `AA999999` e estes 2% não são" é um achado de
    limpeza direto, e hoje esses 2% passariam despercebidos no meio da
    coluna.
    """
    if len(amostra_str) < 20:
        return {"tem_formato": False}

    formas: dict[str, list[str]] = {}
    for valor in amostra_str:
        texto = str(valor).strip()
        if not texto:
            continue
        formas.setdefault(_shape(texto), []).append(texto)
    if not formas:
        return {"tem_formato": False}

    total = sum(len(v) for v in formas.values())
    dominante, exemplos_dominante = max(formas.items(), key=lambda kv: len(kv[1]))
    cobertura = len(exemplos_dominante) / total
    # Formato só é formato se houver repetição real de estrutura. Texto livre
    # gera uma forma diferente por valor e cai fora aqui.
    if cobertura < cobertura_minima:
        return {"tem_formato": False}

    fora = [
        {"valor": v, "formato": forma}
        for forma, valores in formas.items() if forma != dominante
        for v in valores[:2]
    ]
    return {
        "tem_formato": True,
        "formato_dominante": dominante,
        "cobertura": round(cobertura, 4),
        "qtd_formatos_distintos": len(formas),
        "exemplo_conforme": exemplos_dominante[0],
        "qtd_fora_do_padrao": total - len(exemplos_dominante),
        "exemplos_fora_do_padrao": fora[:5],
    }


# ── Lei de Benford ──────────────────────────────────────────────────────────

# Fração mínima de valores com espaço para a coluna ser tratada como texto
# livre na busca de PII embutida.
_FRACAO_MINIMA_TEXTO_LIVRE = 0.5

_RE_PALAVRA = re.compile(r"\w+", re.UNICODE)

_BENFORD_ESPERADO = [0.301, 0.176, 0.125, 0.097, 0.079, 0.067, 0.058, 0.051, 0.046]


def distribuicao_benford(serie: pd.Series) -> dict[str, Any] | None:
    """Compara a distribuição do primeiro dígito com a esperada pela Lei de
    Benford. Desvio forte em coluna financeira costuma indicar valor
    arredondado/manual, faixa truncada ou dado sintético. Não confirma
    fraude sozinho — é um ponteiro para investigar a origem do dado.
    """
    positivos = serie[serie > 0]
    if len(positivos) < 100:
        return None
    primeiros = (
        positivos.abs().astype(str).str.replace(r"[^1-9]", "", regex=True).str[:1]
    )
    primeiros = primeiros[primeiros != ""]
    if len(primeiros) < 100:
        return None
    observado = primeiros.value_counts(normalize=True)
    n = len(primeiros)
    frequencias = []
    desvio_max = 0.0
    for i, esperado in enumerate(_BENFORD_ESPERADO, start=1):
        obs = float(observado.get(str(i), 0.0))
        frequencias.append({"digito": i, "observado": round(obs, 4), "esperado": esperado})
        desvio_max = max(desvio_max, abs(obs - esperado))
    return {
        "aplicavel": True,
        "n": int(n),
        "desvio_maximo_absoluto": round(desvio_max, 4),
        "aderente": bool(desvio_max < 0.05),
        "frequencias": frequencias,
    }

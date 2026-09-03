"""Detectores de evidência semântica.

Cada detector olha para uma fonte diferente e emite `Evidencia`. Nenhum
decide sozinho — quem decide é o combinador em `evidence`. Isso é o que
permite o caso difícil: um nome opaco (`f27`, `cd_dpto_lot`) que o dicionário
não conhece pode ser resolvido pelo conteúdo, pela abreviatura reconstruída ou
pelo contexto das colunas vizinhas.
"""
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz.distance import JaroWinkler

from .. import config
from .contexto import contexto_atual
from .evidence import EIXO_DOMINIO, EIXO_PAPEL, Evidencia
from .tokens import expandir_abreviatura, normalizar, tokens_expandidos

# Papéis que definem sozinhos o tratamento de ETL da coluna: se a coluna é uma
# chave ou uma data, isso importa mais para o pipeline do que o assunto dela.
PAPEIS_ESTRUTURAIS = frozenset({
    config.SEMANTICA_CHAVE_ID,
    config.SEMANTICA_DATA_CALENDARIO,
    "Valor Financeiro",
    "Quantidade / Métrica",
    "Contato / Rede",
    "Status / Indicador / Flag",
    "Resultado de Avaliação",
})

_MAPA_PADRAO_SEMANTICA: dict[str, tuple[str, str]] = {
    "CPF":      (config.SEMANTICA_CHAVE_ID,   EIXO_PAPEL),
    "CNPJ":     (config.SEMANTICA_CHAVE_ID,   EIXO_PAPEL),
    "UUID":     (config.SEMANTICA_CHAVE_ID,   EIXO_PAPEL),
    "E-mail":   ("Contato / Rede",            EIXO_PAPEL),
    "Telefone": ("Contato / Rede",            EIXO_PAPEL),
    "CEP":      ("Localização Geográfica",    EIXO_DOMINIO),
}

def reconstruir_indice_tokens_fortes() -> None:
    """Compatibilidade com a API antiga; o índice agora pertence ao contexto."""

_DECAIMENTO_POSICIONAL = 0.03

# Prefixo que cobre mais que isto da palavra-alvo continua sendo evidência
# cheia; abaixo disso vira palpite proporcional ao que cobre. 0,7 é o piso —
# `forma` cobre 0,625 de `formacao` e ainda assim é uma palavra comum demais
# para valer como evidência plena de "Curso / Treinamento".
_COBERTURA_MINIMA_PREFIXO = 0.7


@dataclass
class PerfilConteudo:
    """O que os detectores de conteúdo precisam saber sobre a coluna.

    É um recorte do que `statistics` já calculou — nada aqui é recomputado.
    """
    tipo_dados: str = ""
    valores_distintos: list[str] = field(default_factory=list)
    n_unicos: int = 0
    ratio_unicidade: float = 0.0
    str_len_media: float | None = None
    comprimento_fixo: bool = False
    assimetria: float | None = None
    minimo: float | None = None
    monotonica_crescente: bool = False
    casas_decimais_fixas: int | None = None


def _peso_posicional(indice: int) -> float:
    return max(1.0 - _DECAIMENTO_POSICIONAL * indice, 0.5)


# ── 1. Conteúdo: padrão estruturado ─────────────────────────────────────────

def por_padrao_conteudo(detectado_padrao: str) -> list[Evidencia]:
    """CPF/CNPJ/e-mail validados no conteúdo. É a evidência mais forte que
    existe: uma coluna chamada `campo1` que só contém CPF é um identificador,
    independentemente de como alguém a batizou."""
    entrada = _MAPA_PADRAO_SEMANTICA.get(detectado_padrao)
    if entrada is None:
        return []
    categoria, eixo = entrada
    return [Evidencia(categoria, eixo, 0.98, f"conteúdo validado como {detectado_padrao}")]


# ── 2. Conteúdo: gazetteer de valores ───────────────────────────────────────

def por_gazetteer(perfil: PerfilConteudo) -> list[Evidencia]:
    """Compara os valores da coluna com conjuntos fechados conhecidos.

    É o detector que resolve o nome ilegível: `f27` cujos valores são as 27
    siglas de UF é uma coluna de localização, e nenhuma análise do nome
    chegaria lá.
    """
    if not perfil.valores_distintos or perfil.n_unicos <= 0:
        return []

    normalizados = [normalizar(v) for v in perfil.valores_distintos]
    normalizados = [v for v in normalizados if v]
    if not normalizados:
        return []

    achados: list[Evidencia] = []
    for gazetteer in contexto_atual().gazetteers:
        if perfil.n_unicos > gazetteer["max_distintos"]:
            continue
        contidos = sum(1 for v in normalizados if v in gazetteer["valores"])
        cobertura = contidos / len(normalizados)
        if cobertura < gazetteer["cobertura_minima"]:
            continue
        achados.append(Evidencia(
            gazetteer["categoria"], gazetteer["eixo"],
            round(gazetteer["peso"] * cobertura, 4),
            f"valores correspondem a {gazetteer['nome']} ({cobertura:.0%} da coluna)",
        ))
    return achados


def _qualificador_de_borda(token: str, posicao: str) -> Evidencia | None:
    """Evidência de papel vinda do token na borda do nome da coluna.

    A expansão da abreviatura conta: `vl_saque` só é reconhecido como valor
    financeiro porque `vl` vira `valor`. Quando a expansão é ambígua, a posição
    resolve — `des` em `REFUND_TYPE_DES` pode ser `desc`, `despesa` ou
    `demissao`, e na ponta do nome só `desc` faz sentido como qualificador.
    """
    candidatos: list[tuple[str, float]] = [(token, 1.0)]
    expansoes = expandir_abreviatura(token)
    qualificadoras = [e for e in expansoes if e[0] in config.TOKENS_QUALIFICADORES]
    if len(expansoes) == 1:
        candidatos.append(expansoes[0])
    elif len(qualificadoras) == 1:
        candidatos.append(qualificadoras[0])

    for palavra, confianca in candidatos:
        if palavra not in config.TOKENS_QUALIFICADORES:
            continue
        categorias = contexto_atual().indice_tokens_fortes.get(palavra, ())
        if len(categorias) != 1:
            continue
        origem = (
            f"qualificador {posicao} '{palavra}'" if palavra == token
            else f"qualificador {posicao} '{token}' → '{palavra}'"
        )
        return Evidencia(categorias[0], EIXO_PAPEL, round(0.9 * confianca, 4), origem)
    return None


# ── 3. Nome: token forte (com abreviaturas expandidas) ──────────────────────

def por_token_forte(tokens: list[str]) -> list[Evidencia]:
    """Casa os tokens do nome — e as expansões das abreviaturas — contra o
    dicionário curado.

    A regra do qualificador posicional continua valendo: o token na borda do
    nome define o papel. As duas convenções que aparecem em sistema corporativo
    põem o qualificador em pontas opostas — `id_funcionario`, `dt_movimento`,
    `nome_departamento` no português; `EMPLOYEE_ID`, `SUPPLIER_CONTACT_CODE`,
    `DEPARTMENT_NAME` no inglês. Olhar só o primeiro token classificava
    `SUPPLIER_CONTACT_CODE` como valor financeiro, e alguém acabaria somando um
    centro de custo.
    """
    if not tokens:
        return []

    evidencias: list[Evidencia] = []

    bordas = [(tokens[0], "inicial")]
    if len(tokens) > 1:
        bordas.append((tokens[-1], "final"))
    for token, posicao in bordas:
        evidencia = _qualificador_de_borda(token, posicao)
        if evidencia is not None:
            evidencias.append(evidencia)

    for indice, (palavra, confianca_expansao, original) in enumerate(tokens_expandidos(tokens)):
        for categoria in contexto_atual().indice_tokens_fortes.get(palavra, ()):
            peso_token = (
                config.PESO_TOKEN_QUALIFICADOR
                if palavra in config.TOKENS_QUALIFICADORES
                else config.PESO_TOKEN_ENTIDADE
            )
            peso = 0.85 * peso_token * confianca_expansao * _peso_posicional(indice)
            origem = (
                f"token '{palavra}'" if palavra == original
                else f"abreviatura '{original}' → '{palavra}'"
            )
            evidencias.append(Evidencia(categoria, EIXO_PAPEL, round(peso, 4), origem))

    return evidencias


def _fator_truncagem(candidato: str, palavra: str) -> float:
    """Desconto para o match fuzzy que é só um prefixo da palavra-alvo.

    Jaro-Winkler bonifica prefixo comum de propósito, então `work` casa com
    `workshop` a 0,9 — foi assim que `WORK_EMAIL_ADDRESS` ganhou o domínio
    "Curso / Treinamento". Quando o candidato é prefixo estrito e cobre pouco
    da palavra, a evidência vale o que ela cobre, exatamente como já acontece
    na reconstrução de abreviatura por subsequência.
    """
    if len(candidato) >= len(palavra) or not palavra.startswith(candidato):
        return 1.0
    cobertura = len(candidato) / len(palavra)
    return 1.0 if cobertura > _COBERTURA_MINIMA_PREFIXO else cobertura


# ── 4. Nome: fuzzy contra as categorias de domínio ──────────────────────────

def por_fuzzy(nome_limpo: str, tokens: list[str]) -> list[Evidencia]:
    """Jaro-Winkler contra as palavras-chave de domínio.

    Roda sempre, inclusive quando um papel forte já foi encontrado: `nome` e
    `cod` prefixam metade das colunas de um sistema corporativo, e condicionar
    o fuzzy à ausência de token forte tornava as categorias de domínio
    inalcançáveis.
    """
    melhores: dict[str, tuple[float, str]] = {}

    # Token que já é palavra conhecida com papel definido não entra no fuzzy de
    # domínio: a semelhança que sobra é homógrafo, não evidência. `time` é
    # "equipe" em português e está no vocabulário de estrutura organizacional —
    # por isso `RECORD_UPDATE_TIME` ganhava domínio "Estrutura Organizacional"
    # tendo papel de data com 0,96 de confiança vindo do mesmo token.
    candidatos_nome = [(nome_limpo, 1.0, nome_limpo)] + [
        c for c in tokens_expandidos(tokens)
        if not (c[0] == c[2] and c[0] in contexto_atual().indice_tokens_fortes)
    ]
    for categoria, palavras_chave in contexto_atual().categorias_fuzzy.items():
        for palavra in palavras_chave:
            palavra_norm = normalizar(palavra)
            threshold = (
                config.THRESHOLD_FUZZY_CURTO if len(palavra_norm) <= 3
                else config.THRESHOLD_FUZZY_PADRAO
            )
            for indice, (candidato, confianca, original) in enumerate(candidatos_nome):
                candidato_norm = normalizar(candidato)
                similaridade = JaroWinkler.similarity(candidato_norm, palavra_norm)
                if similaridade < threshold:
                    continue
                similaridade *= _fator_truncagem(candidato_norm, palavra_norm)
                # Token que já é qualificador estrutural (`categoria`, `tipo`,
                # `status`) pesa menos como evidência de domínio, do mesmo jeito
                # que já pesa menos como evidência de papel: é genérico demais
                # para decidir sozinho. Sem isso, `CATEGORIA_PRODUTO` empatava
                # "Cargo / Função" (de `categoria`) com "Produto / Item" (de
                # `produto`) e o desempate virava sorte de posição.
                peso_qualificador = (
                    config.PESO_TOKEN_QUALIFICADOR if original in config.TOKENS_QUALIFICADORES
                    else 1.0
                )
                peso = (
                    0.8 * similaridade * confianca * peso_qualificador
                    * _peso_posicional(max(indice - 1, 0))
                )
                atual = melhores.get(categoria)
                if atual is None or peso > atual[0]:
                    origem = (
                        f"nome parecido com '{palavra}'" if candidato == original
                        else f"abreviatura '{original}' → '{candidato}' ~ '{palavra}'"
                    )
                    melhores[categoria] = (peso, origem)

    return [
        Evidencia(categoria, EIXO_DOMINIO, round(peso, 4), origem)
        for categoria, (peso, origem) in melhores.items()
    ]


# ── 5. Conteúdo: assinatura estrutural ──────────────────────────────────────

def por_assinatura_estrutural(perfil: PerfilConteudo) -> list[Evidencia]:
    """Deduz o papel pela forma dos dados, não pelo nome.

    Pistas fracas de propósito: sozinhas não decidem nada, mas somadas a um
    nome ambíguo costumam ser o que desempata.
    """
    evidencias: list[Evidencia] = []
    tipo = perfil.tipo_dados

    if tipo == "Booleano":
        evidencias.append(Evidencia(
            "Status / Indicador / Flag", EIXO_PAPEL, 0.7, "coluna booleana"
        ))

    if tipo == "Número Inteiro" and perfil.monotonica_crescente and perfil.ratio_unicidade >= 0.99:
        evidencias.append(Evidencia(
            config.SEMANTICA_CHAVE_ID, EIXO_PAPEL, 0.6,
            "inteiro único e crescente (cara de chave sequencial)",
        ))

    if (tipo == "Número Decimal" and perfil.casas_decimais_fixas == 2
            and perfil.minimo is not None and perfil.minimo >= 0
            and perfil.assimetria is not None and perfil.assimetria > 0.5):
        evidencias.append(Evidencia(
            "Valor Financeiro", EIXO_PAPEL, 0.45,
            "decimal de 2 casas, não negativo e assimétrico à direita (perfil monetário)",
        ))

    if tipo.startswith("Texto") and perfil.str_len_media is not None:
        if perfil.str_len_media > 40 and perfil.ratio_unicidade > 0.5:
            evidencias.append(Evidencia(
                "Texto Descritivo Livre", EIXO_PAPEL, 0.55,
                f"texto longo (média de {perfil.str_len_media:.0f} caracteres) e pouco repetido",
            ))
        elif perfil.comprimento_fixo and perfil.ratio_unicidade > 0.9:
            evidencias.append(Evidencia(
                config.SEMANTICA_CHAVE_ID, EIXO_PAPEL, 0.5,
                "texto de comprimento fixo e quase único (cara de código)",
            ))

    return evidencias


# ── 6. Contexto da tabela ───────────────────────────────────────────────────

def por_contexto_da_tabela(
    tokens: list[str], dominios_da_tabela: dict[str, float]
) -> list[Evidencia]:
    """Desempata abreviaturas ambíguas usando o assunto da tabela.

    `dep` pode ser departamento, dependente ou depósito. Sozinho é insolúvel —
    nenhum modelo acerta olhando só a coluna. Mas se as outras colunas da
    tabela já estabeleceram "Estrutura Organizacional" com confiança, a
    expansão `departamento` passa a ser a leitura provável.
    """
    if not dominios_da_tabela:
        return []

    evidencias: list[Evidencia] = []
    vistos: set[str] = set()
    for palavra, confianca, original in tokens_expandidos(tokens):
        if palavra == original or confianca >= 0.85:
            continue  # expansão única já é forte o bastante sem contexto
        for categoria in contexto_atual().indice_tokens_fortes.get(palavra, ()):
            chave = f"{categoria}|{palavra}"
            if chave in vistos or categoria not in dominios_da_tabela:
                continue
            vistos.add(chave)
            evidencias.append(Evidencia(
                categoria, EIXO_PAPEL,
                round(0.4 * dominios_da_tabela[categoria], 4),
                f"contexto da tabela favorece '{original}' → '{palavra}'",
            ))
        for categoria, forca in dominios_da_tabela.items():
            if categoria not in contexto_atual().categorias_fuzzy:
                continue
            if palavra in contexto_atual().categorias_fuzzy[categoria]:
                chave = f"{categoria}|{palavra}"
                if chave in vistos:
                    continue
                vistos.add(chave)
                evidencias.append(Evidencia(
                    categoria, EIXO_DOMINIO, round(0.4 * forca, 4),
                    f"contexto da tabela favorece '{original}' → '{palavra}'",
                ))
    return evidencias


def perfil_de_registro(stats: dict[str, Any], amostra: list[str]) -> PerfilConteudo:
    """Monta o `PerfilConteudo` a partir do que `statistics` já apurou."""
    extras = stats.get("estatisticas_adicionais", {})
    return PerfilConteudo(
        tipo_dados=stats.get("tipo_dados", ""),
        valores_distintos=amostra,
        n_unicos=int(stats.get("valores_unicos", 0)),
        ratio_unicidade=float(stats.get("ratio_unicidade", 0.0)),
        str_len_media=extras.get("str_len_media"),
        comprimento_fixo=bool(extras.get("comprimento_fixo", False)),
        assimetria=extras.get("assimetria"),
        minimo=extras.get("min"),
        monotonica_crescente=bool(stats.get("monotonica_crescente", False)),
        casas_decimais_fixas=stats.get("casas_decimais_fixas"),
    )

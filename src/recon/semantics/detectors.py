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
from .evidence import EIXO_DOMINIO, EIXO_PAPEL, Evidencia
from .tokens import expandir_abreviatura, normalizar, tokens_expandidos
from .vocabulary import GAZETTEERS

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

# Índice invertido token -> categorias fortes que o contêm.
_INDICE_TOKEN_FORTE: dict[str, list[str]] = {}
for _categoria, _palavras in config.CATEGORIAS_FORTES.items():
    for _palavra in _palavras:
        _INDICE_TOKEN_FORTE.setdefault(_palavra, []).append(_categoria)

_DECAIMENTO_POSICIONAL = 0.03


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
    for gazetteer in GAZETTEERS:
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


# ── 3. Nome: token forte (com abreviaturas expandidas) ──────────────────────

def por_token_forte(tokens: list[str]) -> list[Evidencia]:
    """Casa os tokens do nome — e as expansões das abreviaturas — contra o
    dicionário curado.

    A regra do qualificador posicional continua valendo: quando o primeiro
    token é um qualificador conhecido (`id`, `cod`, `dt`, `nome`), ele define o
    papel. É a convenção `<papel>_<entidade>` do português, e é o que faz
    `id_funcionario` ser um identificador em vez de um nome de pessoa.
    """
    if not tokens:
        return []

    evidencias: list[Evidencia] = []

    # O primeiro token conta, e a sua expansão também: `vl_saque` só é
    # reconhecido como valor financeiro porque `vl` expande para `valor`.
    primeiro = tokens[0]
    candidatos_primeiro = [(primeiro, 1.0)]
    expansoes_primeiro = expandir_abreviatura(primeiro)
    if len(expansoes_primeiro) == 1:
        candidatos_primeiro.append(expansoes_primeiro[0])

    for palavra, confianca in candidatos_primeiro:
        if palavra not in config.TOKENS_QUALIFICADORES or palavra not in _INDICE_TOKEN_FORTE:
            continue
        categorias = _INDICE_TOKEN_FORTE[palavra]
        if len(categorias) != 1:
            continue
        origem = (
            f"qualificador posicional '{palavra}'" if palavra == primeiro
            else f"qualificador posicional '{primeiro}' → '{palavra}'"
        )
        evidencias.append(Evidencia(categorias[0], EIXO_PAPEL, round(0.9 * confianca, 4), origem))
        break

    for indice, (palavra, confianca_expansao, original) in enumerate(tokens_expandidos(tokens)):
        for categoria in _INDICE_TOKEN_FORTE.get(palavra, ()):
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


# ── 4. Nome: fuzzy contra as categorias de domínio ──────────────────────────

def por_fuzzy(nome_limpo: str, tokens: list[str]) -> list[Evidencia]:
    """Jaro-Winkler contra as palavras-chave de domínio.

    Roda sempre, inclusive quando um papel forte já foi encontrado: `nome` e
    `cod` prefixam metade das colunas de um sistema corporativo, e condicionar
    o fuzzy à ausência de token forte tornava as categorias de domínio
    inalcançáveis.
    """
    melhores: dict[str, tuple[float, str]] = {}

    candidatos_nome = [(nome_limpo, 1.0, nome_limpo)] + tokens_expandidos(tokens)
    for categoria, palavras_chave in config.CATEGORIAS_FUZZY.items():
        for palavra in palavras_chave:
            palavra_norm = normalizar(palavra)
            threshold = (
                config.THRESHOLD_FUZZY_CURTO if len(palavra_norm) <= 3
                else config.THRESHOLD_FUZZY_PADRAO
            )
            for indice, (candidato, confianca, original) in enumerate(candidatos_nome):
                similaridade = JaroWinkler.similarity(normalizar(candidato), palavra_norm)
                if similaridade < threshold:
                    continue
                peso = 0.8 * similaridade * confianca * _peso_posicional(max(indice - 1, 0))
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
    """Deduz o papel pela *forma* dos dados, não pelo nome.

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
        for categoria in _INDICE_TOKEN_FORTE.get(palavra, ()):
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
            if categoria not in config.CATEGORIAS_FUZZY:
                continue
            if palavra in config.CATEGORIAS_FUZZY[categoria]:
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

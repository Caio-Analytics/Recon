from dataclasses import dataclass, field
from typing import Any

from rapidfuzz.distance import JaroWinkler

from .. import config
from .evidence import EIXO_DOMINIO, EIXO_PAPEL, Evidencia
from .tokens import expandir_abreviatura, normalizar, tokens_expandidos
from .vocabulary import GAZETTEERS



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


_INDICE_TOKEN_FORTE: dict[str, list[str]] = {}
for _categoria, _palavras in config.CATEGORIAS_FORTES.items():
    for _palavra in _palavras:
        _INDICE_TOKEN_FORTE.setdefault(_palavra, []).append(_categoria)

_DECAIMENTO_POSICIONAL = 0.03



_COBERTURA_MINIMA_PREFIXO = 0.6


@dataclass
class PerfilConteudo:
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




def por_padrao_conteudo(detectado_padrao: str) -> list[Evidencia]:
    entrada = _MAPA_PADRAO_SEMANTICA.get(detectado_padrao)
    if entrada is None:
        return []
    categoria, eixo = entrada
    return [Evidencia(categoria, eixo, 0.98, f"conteúdo validado como {detectado_padrao}")]




def por_gazetteer(perfil: PerfilConteudo) -> list[Evidencia]:
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


def _qualificador_de_borda(token: str, posicao: str) -> Evidencia | None:
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
        categorias = _INDICE_TOKEN_FORTE.get(palavra, ())
        if len(categorias) != 1:
            continue
        origem = (
            f"qualificador {posicao} '{palavra}'" if palavra == token
            else f"qualificador {posicao} '{token}' → '{palavra}'"
        )
        return Evidencia(categorias[0], EIXO_PAPEL, round(0.9 * confianca, 4), origem)
    return None




def por_token_forte(tokens: list[str]) -> list[Evidencia]:
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


def _fator_truncagem(candidato: str, palavra: str) -> float:
    if len(candidato) >= len(palavra) or not palavra.startswith(candidato):
        return 1.0
    cobertura = len(candidato) / len(palavra)
    return 1.0 if cobertura > _COBERTURA_MINIMA_PREFIXO else cobertura




def por_fuzzy(nome_limpo: str, tokens: list[str]) -> list[Evidencia]:
    melhores: dict[str, tuple[float, str]] = {}

    
    
    
    
    
    candidatos_nome = [(nome_limpo, 1.0, nome_limpo)] + [
        c for c in tokens_expandidos(tokens)
        if not (c[0] == c[2] and c[0] in _INDICE_TOKEN_FORTE)
    ]
    for categoria, palavras_chave in config.CATEGORIAS_FUZZY.items():
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




def por_assinatura_estrutural(perfil: PerfilConteudo) -> list[Evidencia]:
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




def por_contexto_da_tabela(
    tokens: list[str], dominios_da_tabela: dict[str, float]
) -> list[Evidencia]:
    if not dominios_da_tabela:
        return []

    evidencias: list[Evidencia] = []
    vistos: set[str] = set()
    for palavra, confianca, original in tokens_expandidos(tokens):
        if palavra == original or confianca >= 0.85:
            continue  
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

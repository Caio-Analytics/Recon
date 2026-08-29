"""Normalização, tokenização e expansão de abreviaturas de nomes de coluna."""
import re
from functools import lru_cache

from unidecode import unidecode

from .. import config
from .vocabulary import ABREVIATURAS

_RE_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_RE_SEPARADORES = re.compile(r"[_\s\-\.]+")
_RE_LETRA_NUMERO = re.compile(r"([a-z])(\d)")

# Comprimento máximo da expansão em relação à abreviatura. `dp` expandindo para
# uma palavra de 20 letras não é abreviatura, é coincidência de subsequência.
_RAZAO_MAX_EXPANSAO = 4.0
_MIN_LEN_ABREVIATURA = 2
# Abaixo disso, só o dicionário curado expande (`nm`, `sg`, `dt`...). Palpite
# por subsequência com 2 letras casa contra quase qualquer palavra do
# vocabulário — `ue` ⊂ `user` não quer dizer nada.
_MIN_LEN_ABREVIATURA_ESPECULATIVA = 3


def normalizar(texto: str) -> str:
    return unidecode(str(texto)).lower().strip()


def tokenizar(nome_col: str) -> list[str]:
    """Quebra o nome da coluna em tokens normalizados.

    Separa camelCase, separadores explícitos e a fronteira letra→número
    (`col1` → `col`, `1`), que é comum em nome gerado por sistema.
    """
    nome = _RE_CAMEL.sub(r"\1_\2", str(nome_col))
    nome = normalizar(nome)
    nome = _RE_LETRA_NUMERO.sub(r"\1_\2", nome)
    return [p for p in _RE_SEPARADORES.split(nome) if p]


@lru_cache(maxsize=1)
def _vocabulario_expansao() -> tuple[str, ...]:
    """Todas as palavras que valem como alvo de expansão: as palavras-chave da
    taxonomia mais as expansões conhecidas do dicionário de abreviaturas."""
    palavras: set[str] = set()
    for grupo in (config.CATEGORIAS_FORTES, config.CATEGORIAS_FUZZY):
        for lista in grupo.values():
            palavras.update(lista)
    for expansoes in ABREVIATURAS.values():
        palavras.update(expansoes)
    return tuple(sorted(palavras))


def _e_subsequencia(abreviatura: str, palavra: str) -> bool:
    """`dpto` é subsequência de `departamento` (d-e-p-a-r-t-a-m-e-n-t-o).

    Abreviatura corporativa é quase sempre a palavra com letras removidas na
    ordem — não uma troca de letras. Distância de edição erra esse caso;
    subsequência acerta.
    """
    iterador = iter(palavra)
    return all(letra in iterador for letra in abreviatura)


@lru_cache(maxsize=4096)
def expandir_abreviatura(token: str) -> tuple[tuple[str, float], ...]:
    """Devolve as expansões possíveis de um token, com a confiança de cada uma.

    Duas fontes, nessa ordem: o dicionário curado (alta confiança, e é onde
    moram as abreviaturas ambíguas como `dep`) e a reconstrução por
    subsequência (confiança proporcional a quanto da palavra a abreviatura
    preserva).

    Retorna tupla de tuplas para poder ser cacheada.
    """
    if len(token) < _MIN_LEN_ABREVIATURA or not token.isalpha():
        return ()

    # Token que já é uma palavra conhecida do vocabulário não é abreviatura de
    # nada. Sem esta guarda, `name` — que está na taxonomia como nome de
    # pessoa — era expandido para `nascimento` (do qual é subsequência:
    # n-a-s-c-i-M-E-n-t-o) e a coluna `FULL_NAME` virava "Data / Calendário".
    # Um palpite não pode competir com a evidência literal do mesmo token.
    if token in _vocabulario_expansao():
        return ()

    curadas = ABREVIATURAS.get(token)
    if curadas:
        # Quando há várias expansões, nenhuma é certa — a confiança cai e o
        # desempate fica por conta do contexto da tabela.
        confianca = 0.85 if len(curadas) == 1 else 0.55
        return tuple((palavra, confianca) for palavra in curadas)

    # Token de 2 letras casa por subsequência com quase qualquer palavra
    # longa o suficiente — `ue` ⊂ `user`, sem nenhuma relação real entre os
    # dois. Abaixo desse tamanho só o dicionário curado (checado acima) vale;
    # o palpite por subsequência precisa de pelo menos 3 letras pra a posição
    # relativa das letras significar alguma coisa.
    if len(token) < _MIN_LEN_ABREVIATURA_ESPECULATIVA:
        return ()

    candidatos: list[tuple[str, float]] = []
    for palavra in _vocabulario_expansao():
        if palavra == token or len(palavra) <= len(token):
            continue
        if len(palavra) > len(token) * _RAZAO_MAX_EXPANSAO:
            continue
        if palavra[0] != token[0]:
            continue
        if not _e_subsequencia(token, palavra):
            continue
        # Quanto mais da palavra a abreviatura preserva, mais confiável.
        cobertura = len(token) / len(palavra)
        candidatos.append((palavra, round(0.35 + 0.35 * cobertura, 4)))

    candidatos.sort(key=lambda c: -c[1])
    return tuple(candidatos[:3])


def tokens_expandidos(tokens: list[str]) -> list[tuple[str, float, str]]:
    """Expande cada token, mantendo o original como candidato de peso máximo.

    Devolve `(palavra, confianca, token_original)` — o token original vai
    junto para a origem do achado poder dizer de onde a palavra veio.
    """
    resultado: list[tuple[str, float, str]] = []
    for token in tokens:
        resultado.append((token, 1.0, token))
        for palavra, confianca in expandir_abreviatura(token):
            if palavra != token:
                resultado.append((palavra, confianca, token))
    return resultado

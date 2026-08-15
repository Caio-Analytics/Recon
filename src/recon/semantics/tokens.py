import re
from functools import lru_cache

from unidecode import unidecode

from .. import config
from .vocabulary import ABREVIATURAS

_RE_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_RE_SEPARADORES = re.compile(r"[_\s\-\.]+")
_RE_LETRA_NUMERO = re.compile(r"([a-z])(\d)")



_RAZAO_MAX_EXPANSAO = 4.0
_MIN_LEN_ABREVIATURA = 2


def normalizar(texto: str) -> str:
    return unidecode(str(texto)).lower().strip()


def tokenizar(nome_col: str) -> list[str]:
    nome = _RE_CAMEL.sub(r"\1_\2", str(nome_col))
    nome = normalizar(nome)
    nome = _RE_LETRA_NUMERO.sub(r"\1_\2", nome)
    return [p for p in _RE_SEPARADORES.split(nome) if p]


@lru_cache(maxsize=1)
def _vocabulario_expansao() -> tuple[str, ...]:
    palavras: set[str] = set()
    for grupo in (config.CATEGORIAS_FORTES, config.CATEGORIAS_FUZZY):
        for lista in grupo.values():
            palavras.update(lista)
    for expansoes in ABREVIATURAS.values():
        palavras.update(expansoes)
    return tuple(sorted(palavras))


def _e_subsequencia(abreviatura: str, palavra: str) -> bool:
    iterador = iter(palavra)
    return all(letra in iterador for letra in abreviatura)


@lru_cache(maxsize=4096)
def expandir_abreviatura(token: str) -> tuple[tuple[str, float], ...]:
    if len(token) < _MIN_LEN_ABREVIATURA or not token.isalpha():
        return ()

    
    
    
    
    
    if token in _vocabulario_expansao():
        return ()

    curadas = ABREVIATURAS.get(token)
    if curadas:
        
        
        confianca = 0.85 if len(curadas) == 1 else 0.55
        return tuple((palavra, confianca) for palavra in curadas)

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
        
        cobertura = len(token) / len(palavra)
        candidatos.append((palavra, round(0.35 + 0.35 * cobertura, 4)))

    candidatos.sort(key=lambda c: -c[1])
    return tuple(candidatos[:3])


def tokens_expandidos(tokens: list[str]) -> list[tuple[str, float, str]]:
    resultado: list[tuple[str, float, str]] = []
    for token in tokens:
        resultado.append((token, 1.0, token))
        for palavra, confianca in expandir_abreviatura(token):
            if palavra != token:
                resultado.append((palavra, confianca, token))
    return resultado

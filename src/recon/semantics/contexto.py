"""Contexto semântico imutável e isolado por execução.

Vocabulários YAML são configuração da análise atual, não estado do processo.
Usar ``ContextVar`` permite que duas análises concorrentes — por exemplo, duas
threads da GUI — usem dicionários diferentes sem alterar o resultado uma da
outra.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .. import config
from .vocabulary import ABREVIATURAS, GAZETTEERS


@dataclass(frozen=True)
class ContextoSemantico:
    categorias_fortes: Mapping[str, tuple[str, ...]]
    categorias_fuzzy: Mapping[str, tuple[str, ...]]
    gazetteers: tuple[Mapping[str, Any], ...]
    indice_tokens_fortes: Mapping[str, tuple[str, ...]]
    palavras_para_abreviatura: tuple[str, ...]
    correcoes_colunas: Mapping[str, str]


def criar_contexto(
    categorias_fortes: Mapping[str, tuple[str, ...]] | None = None,
    categorias_fuzzy: Mapping[str, tuple[str, ...]] | None = None,
    gazetteers: tuple[Mapping[str, Any], ...] | None = None,
    correcoes_colunas: Mapping[str, str] | None = None,
) -> ContextoSemantico:
    """Cria um contexto congelado a partir do núcleo e de extensões locais."""
    fortes = categorias_fortes or {
        categoria: tuple(termos) for categoria, termos in config.CATEGORIAS_FORTES.items()
    }
    fuzzy = categorias_fuzzy or {
        categoria: tuple(termos) for categoria, termos in config.CATEGORIAS_FUZZY.items()
    }
    fontes_gazetteer = gazetteers or tuple(GAZETTEERS)
    indice: dict[str, list[str]] = {}
    for categoria, termos in fortes.items():
        for termo in termos:
            indice.setdefault(termo, []).append(categoria)
    palavras = {palavra for termos in fortes.values() for palavra in termos}
    palavras.update(palavra for termos in fuzzy.values() for palavra in termos)
    palavras.update(palavra for expansoes in ABREVIATURAS.values() for palavra in expansoes)
    return ContextoSemantico(
        categorias_fortes=MappingProxyType(dict(fortes)),
        categorias_fuzzy=MappingProxyType(dict(fuzzy)),
        gazetteers=tuple(MappingProxyType({**item, "valores": frozenset(item["valores"])}) for item in fontes_gazetteer),
        indice_tokens_fortes=MappingProxyType({chave: tuple(valor) for chave, valor in indice.items()}),
        palavras_para_abreviatura=tuple(sorted(palavras)),
        correcoes_colunas=MappingProxyType(dict(correcoes_colunas or {})),
    )


_CONTEXTO_PADRAO = criar_contexto()
_CONTEXTO_ATUAL: ContextVar[ContextoSemantico] = ContextVar(
    "recon_contexto_semantico", default=_CONTEXTO_PADRAO
)


def contexto_atual() -> ContextoSemantico:
    return _CONTEXTO_ATUAL.get()


def definir_contexto(contexto: ContextoSemantico):
    """Ativa contexto e devolve token para restauração por quem chamou."""
    return _CONTEXTO_ATUAL.set(contexto)


def restaurar_contexto(token: object) -> None:
    _CONTEXTO_ATUAL.reset(token)  # type: ignore[arg-type]

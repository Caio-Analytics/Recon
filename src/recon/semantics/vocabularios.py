"""Extensão opcional do vocabulário semântico por arquivos YAML locais."""
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml

from .contexto import (
    ContextoSemantico,
    contexto_atual,
    criar_contexto,
    definir_contexto,
    restaurar_contexto,
)


@contextmanager
def vocabulario_temporario(caminhos: str | None) -> Iterator[None]:
    """Aplica vocabulários apenas durante uma execução do profiler.

    O contexto fica em ``ContextVar``: uma análise concorrente não enxerga o
    YAML de outra, nem durante nem depois da execução.
    """
    if not caminhos:
        yield
        return

    token = definir_contexto(carregar_vocabularios(caminhos, contexto_atual()))
    try:
        yield
    finally:
        restaurar_contexto(token)


def carregar_vocabularios(
    caminhos: str | None, base: ContextoSemantico | None = None
) -> ContextoSemantico:
    """Acrescenta vocabulários de domínio sem substituir o núcleo do Recon.

    Cada arquivo aceita ``categorias_fortes``, ``categorias_fuzzy`` e
    ``gazetteers``. O formato é deliberadamente simples para uma equipe poder
    versionar seus próprios termos junto da base, sem editar o código-fonte.
    """
    contexto = base or contexto_atual()
    fortes = {categoria: tuple(termos) for categoria, termos in contexto.categorias_fortes.items()}
    fuzzy = {categoria: tuple(termos) for categoria, termos in contexto.categorias_fuzzy.items()}
    gazetteers: list[dict[str, object]] = [
        {**item, "valores": set(item["valores"])} for item in contexto.gazetteers
    ]
    if not caminhos:
        return criar_contexto(fortes, fuzzy, tuple(gazetteers))
    for caminho in (Path(p.strip()) for p in caminhos.split(",") if p.strip()):
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            raise ValueError(f"Vocabulário '{caminho}' precisa ser um objeto YAML.")
        for chave, destino in (
            ("categorias_fortes", fortes),
            ("categorias_fuzzy", fuzzy),
        ):
            secoes = dados.get(chave, {})
            if not isinstance(secoes, dict):
                raise ValueError(f"'{chave}' em '{caminho}' precisa mapear categoria para termos.")
            for categoria, termos in secoes.items():
                if not isinstance(termos, list) or not all(isinstance(t, str) for t in termos):
                    raise ValueError(f"Termos de '{categoria}' em '{caminho}' precisam ser uma lista de texto.")
                destino[str(categoria)] = tuple(destino.get(str(categoria), ()) + tuple(termos))
        extras = dados.get("gazetteers", [])
        if not isinstance(extras, list):
            raise ValueError(f"'gazetteers' em '{caminho}' precisa ser uma lista.")
        for item in extras:
            if not isinstance(item, dict) or not {"nome", "valores", "categoria", "eixo"} <= item.keys():
                raise ValueError(f"Gazetteer inválido em '{caminho}'.")
            valores = item["valores"]
            if not isinstance(valores, list) or not all(isinstance(v, str) for v in valores):
                raise ValueError(f"Valores do gazetteer '{item.get('nome')}' precisam ser texto.")
            gazetteers.append({
                "nome": str(item["nome"]), "valores": set(valores),
                "categoria": str(item["categoria"]), "eixo": str(item["eixo"]),
                "cobertura_minima": float(item.get("cobertura_minima", 0.8)),
                "peso": float(item.get("peso", 0.8)),
                "max_distintos": int(item.get("max_distintos", 100)),
            })
    return criar_contexto(fortes, fuzzy, tuple(gazetteers))

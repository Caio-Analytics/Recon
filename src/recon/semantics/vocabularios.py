"""Extensão opcional do vocabulário semântico por arquivos YAML locais."""
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml

from .. import config
from .vocabulary import GAZETTEERS


@contextmanager
def vocabulario_temporario(caminhos: str | None) -> Iterator[None]:
    """Aplica vocabulários apenas durante uma execução do profiler.

    Os detectores legados leem o vocabulário por estruturas de módulo. Guardar
    e restaurar essas estruturas impede que um YAML escolhido numa análise da
    GUI altere silenciosamente a análise seguinte.
    """
    if not caminhos:
        yield
        return

    fortes = {categoria: list(termos) for categoria, termos in config.CATEGORIAS_FORTES.items()}
    fuzzy = {categoria: list(termos) for categoria, termos in config.CATEGORIAS_FUZZY.items()}
    gazetteers = [
        {**item, "valores": set(item["valores"])}
        for item in GAZETTEERS
    ]
    try:
        carregar_vocabularios(caminhos)
        yield
    finally:
        config.CATEGORIAS_FORTES.clear()
        config.CATEGORIAS_FORTES.update(fortes)
        config.CATEGORIAS_FUZZY.clear()
        config.CATEGORIAS_FUZZY.update(fuzzy)
        GAZETTEERS[:] = gazetteers
        from .detectors import reconstruir_indice_tokens_fortes

        reconstruir_indice_tokens_fortes()


def carregar_vocabularios(caminhos: str | None) -> None:
    """Acrescenta vocabulários de domínio sem substituir o núcleo do Recon.

    Cada arquivo aceita ``categorias_fortes``, ``categorias_fuzzy`` e
    ``gazetteers``. O formato é deliberadamente simples para uma equipe poder
    versionar seus próprios termos junto da base, sem editar o código-fonte.
    """
    if not caminhos:
        return
    for caminho in (Path(p.strip()) for p in caminhos.split(",") if p.strip()):
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            raise ValueError(f"Vocabulário '{caminho}' precisa ser um objeto YAML.")
        for chave, destino in (
            ("categorias_fortes", config.CATEGORIAS_FORTES),
            ("categorias_fuzzy", config.CATEGORIAS_FUZZY),
        ):
            secoes = dados.get(chave, {})
            if not isinstance(secoes, dict):
                raise ValueError(f"'{chave}' em '{caminho}' precisa mapear categoria para termos.")
            for categoria, termos in secoes.items():
                if not isinstance(termos, list) or not all(isinstance(t, str) for t in termos):
                    raise ValueError(f"Termos de '{categoria}' em '{caminho}' precisam ser uma lista de texto.")
                destino.setdefault(str(categoria), []).extend(termos)
        extras = dados.get("gazetteers", [])
        if not isinstance(extras, list):
            raise ValueError(f"'gazetteers' em '{caminho}' precisa ser uma lista.")
        for item in extras:
            if not isinstance(item, dict) or not {"nome", "valores", "categoria", "eixo"} <= item.keys():
                raise ValueError(f"Gazetteer inválido em '{caminho}'.")
            valores = item["valores"]
            if not isinstance(valores, list) or not all(isinstance(v, str) for v in valores):
                raise ValueError(f"Valores do gazetteer '{item.get('nome')}' precisam ser texto.")
            GAZETTEERS.append({
                "nome": str(item["nome"]), "valores": set(valores),
                "categoria": str(item["categoria"]), "eixo": str(item["eixo"]),
                "cobertura_minima": float(item.get("cobertura_minima", 0.8)),
                "peso": float(item.get("peso", 0.8)),
                "max_distintos": int(item.get("max_distintos", 100)),
            })
    # O detector mantém um índice para a inferência ficar barata; como os
    # dicionários foram estendidos em memória, ele precisa ser recomposto.
    from .detectors import reconstruir_indice_tokens_fortes
    reconstruir_indice_tokens_fortes()

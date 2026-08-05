"""Inferência semântica de nomes de coluna: match forte por token + fuzzy (rapidfuzz)."""
import re
from typing import Any, Dict, List, Optional

from rapidfuzz.distance import JaroWinkler
from unidecode import unidecode

from . import config


def normalizar(texto: str) -> str:
    return unidecode(str(texto)).lower().strip()


def tokenizar(nome_col: str) -> List[str]:
    nome = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(nome_col))
    nome = normalizar(nome)
    return [p for p in re.split(r"[_\s\-\.]+", nome) if p]


_MAPA_PADRAO_SEMANTICA = {
    "CPF":      ("Chave Identificadora (ID)", "Inferred by Content — CPF"),
    "CNPJ":     ("Chave Identificadora (ID)", "Inferred by Content — CNPJ"),
    "UUID":     ("Chave Identificadora (ID)", "Inferred by Content — UUID"),
    "E-mail":   ("Contato / Rede",            "Inferred by Content — E-mail"),
    "Telefone": ("Contato / Rede",            "Inferred by Content — Telefone"),
    "CEP":      ("Localização Geográfica",    "Inferred by Content — CEP"),
}


def inferir_semantica(nome_col: str, detectado_padrao: str = "Nenhum") -> Dict[str, Any]:
    if detectado_padrao in _MAPA_PADRAO_SEMANTICA:
        sem, origem = _MAPA_PADRAO_SEMANTICA[detectado_padrao]
        return {"semantica": sem, "confianca_score": 1.0, "origem": origem}

    tokens = tokenizar(nome_col)
    tokens_set = set(tokens)

    melhor_forte: Optional[str] = None
    max_tokens_forte = 0
    for categoria, palavras in config.CATEGORIAS_FORTES.items():
        intersecao = tokens_set & set(palavras)
        if intersecao and len(intersecao) >= max_tokens_forte:
            max_len_atual = max(len(w) for w in intersecao)
            max_len_melhor = (
                max(len(w) for w in (tokens_set & set(config.CATEGORIAS_FORTES[melhor_forte])))
                if melhor_forte else 0
            )
            if len(intersecao) > max_tokens_forte or max_len_atual > max_len_melhor:
                max_tokens_forte = len(intersecao)
                melhor_forte = categoria

    if melhor_forte:
        palavras_match = tokens_set & set(config.CATEGORIAS_FORTES[melhor_forte])
        max_len = max(len(w) for w in palavras_match)
        if max_tokens_forte > 1:
            score = 1.0
        elif max_len > 5:
            score = 0.95
        else:
            score = 0.90
        return {
            "semantica": melhor_forte,
            "confianca_score": score,
            "origem": f"Strong Token Match ({', '.join(palavras_match)})",
        }

    nome_limpo = normalizar(nome_col)
    melhor_score = 0.0
    categoria_vencedora = config.SEMANTICA_GENERICA
    palavra_vencedora = ""

    for categoria, palavras_chave in config.CATEGORIAS_FUZZY.items():
        for palavra in palavras_chave:
            palavra_norm = normalizar(palavra)
            threshold = (
                config.THRESHOLD_FUZZY_CURTO if len(palavra_norm) <= 3
                else config.THRESHOLD_FUZZY_PADRAO
            )
            score_full = JaroWinkler.similarity(nome_limpo, palavra_norm)
            scores_tokens = [
                JaroWinkler.similarity(normalizar(t), palavra_norm) for t in tokens
            ]
            score_final = max([score_full] + scores_tokens)

            if score_final >= threshold and score_final > melhor_score:
                melhor_score = score_final
                categoria_vencedora = categoria
                palavra_vencedora = palavra

    return {
        "semantica": categoria_vencedora,
        "confianca_score": round(melhor_score, 4),
        "origem": f"Fuzzy Match ({palavra_vencedora})" if palavra_vencedora else "Unmatched",
    }

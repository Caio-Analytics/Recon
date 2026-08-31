"""Contrato de dados: congelar o que a base é hoje e reconferir depois.

O Recon já descobre que `dt_admissao <= dt_desligamento`, que `matricula` é
única e sem nulo, e que `uf` só assume 27 valores. Enquanto isso vive apenas
no relatório, vale só para o dia em que foi gerado.

O contrato transforma esses achados num arquivo YAML pequeno, legível e
editável, e `conferir_contrato` roda a mesma verificação na extração do mês
seguinte — uma checagem recorrente sem servidor, sem banco e sem agendador.

O arquivo é feito para ser editado à mão: o que o Recon inferiu é ponto de
partida, não regra fixa. Apagar uma entrada é a forma de dizer que aquilo
pode variar entre extrações.
"""
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from . import __version__

VERSAO_CONTRATO = 1

# Cardinalidade máxima para congelar a lista de valores permitidos. Acima
# disso deixa de ser um domínio fechado e vira conteúdo — a lista viraria um
# arquivo de milhares de linhas que ninguém revisa.
MAX_VALORES_DOMINIO = 40
# Folga sobre o percentual de nulos observado. Sem ela, qualquer oscilação
# normal da extração viraria violação.
FOLGA_NULOS_PP = 5.0
FOLGA_LINHAS = 0.5


def gerar_contrato(payload: dict[str, Any]) -> dict[str, Any]:
    """Extrai do perfil o que deve continuar valendo nas próximas versões."""
    meta = payload["metadados_execucao"]
    colunas: list[dict[str, Any]] = []

    for coluna in payload["colunas"]:
        registro: dict[str, Any] = {
            "nome": coluna["Coluna"],
            "tipo": coluna["Tipo_Inferred"],
            "obrigatoria": bool(coluna["Qtd_Nulos"] == 0),
            "max_pct_nulos": round(min(100.0, float(coluna["Pct_Nulos"]) + FOLGA_NULOS_PP), 2),
        }
        if float(coluna.get("Ratio_Unicidade", 0)) >= 0.999:
            registro["unica"] = True

        extras = coluna.get("Stats_Extra") or {}
        if "min" in extras and "max" in extras:
            registro["min"] = extras["min"]
            registro["max"] = extras["max"]

        # Domínio fechado só vale a pena para categoria pequena, e nunca para
        # dado pessoal — a lista de valores permitidos seria a própria base.
        if (
            coluna.get("Dado_Sensivel_LGPD", "Nenhum") == "Nenhum"
            and 1 < int(coluna.get("Qtd_Unicos", 0)) <= MAX_VALORES_DOMINIO
            and coluna["Tipo_Inferred"].startswith("Texto")
        ):
            valores = [str(v) for v in (coluna.get("Amostra_Valores") or "").split(", ") if v]
            if 0 < len(valores) <= MAX_VALORES_DOMINIO:
                registro["valores_permitidos"] = sorted(set(valores))
        colunas.append(registro)

    regras = [
        {"tipo": r["tipo"], "regra": r["regra"]}
        for r in payload.get("regras_negocio", [])
        if r.get("qtd_violacoes", 1) == 0
    ]

    return {
        "versao_contrato": VERSAO_CONTRATO,
        "tabela": meta["tabela"],
        "gerado_em": datetime.now(UTC).isoformat(),
        "gerado_por": f"Recon {__version__}",
        "linhas_minimas": int(meta["linhas_originais"] * FOLGA_LINHAS),
        "colunas": colunas,
        "regras_negocio": regras,
        "_leia_me": (
            "Editar este arquivo é esperado: o Recon propõe, você decide. Apagar uma "
            "entrada é dizer que aquilo pode variar entre extrações."
        ),
    }


def salvar_contrato(contrato: dict[str, Any], caminho: str) -> None:
    texto = yaml.safe_dump(contrato, allow_unicode=True, sort_keys=False, width=100)
    Path(caminho).write_text(texto, encoding="utf-8")
    logger.info(f"✓ Contrato salvo: '{caminho}' ({len(contrato['colunas'])} colunas)")


def carregar_contrato(caminho: str) -> dict[str, Any]:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or "colunas" not in dados:
        raise ValueError(
            f"'{caminho}' não parece um contrato do Recon (falta a lista 'colunas')."
        )
    return dados


def _violacao(severidade: str, tipo: str, coluna: str, mensagem: str) -> dict[str, Any]:
    return {"severidade": severidade, "tipo": tipo, "coluna": coluna, "mensagem": mensagem}


def conferir_contrato(payload: dict[str, Any], contrato: dict[str, Any]) -> dict[str, Any]:
    """Confere um perfil novo contra o contrato e lista o que saiu da linha."""
    meta = payload["metadados_execucao"]
    por_nome = {c["Coluna"]: c for c in payload["colunas"]}
    violacoes: list[dict[str, Any]] = []

    esperadas = {c["nome"] for c in contrato["colunas"]}
    faltando = sorted(esperadas - set(por_nome))
    novas = sorted(set(por_nome) - esperadas)
    for nome in faltando:
        violacoes.append(_violacao(
            "🔴 ALTA", "Coluna ausente", nome,
            f"A coluna '{nome}' está no contrato e não veio nesta extração.",
        ))
    for nome in novas:
        violacoes.append(_violacao(
            "🟢 INFO", "Coluna nova", nome,
            f"A coluna '{nome}' não está no contrato — nova na origem, ou renomeada.",
        ))

    linhas_minimas = int(contrato.get("linhas_minimas") or 0)
    if linhas_minimas and meta["linhas_originais"] < linhas_minimas:
        violacoes.append(_violacao(
            "🔴 ALTA", "Volume abaixo do mínimo", "(tabela)",
            f"{meta['linhas_originais']:,} linhas, abaixo do mínimo de {linhas_minimas:,} "
            "registrado no contrato. Extração truncada é a causa mais comum.",
        ))

    for esperada in contrato["colunas"]:
        atual = por_nome.get(esperada["nome"])
        if atual is None:
            continue
        nome = esperada["nome"]

        if esperada.get("tipo") and atual["Tipo_Inferred"] != esperada["tipo"]:
            violacoes.append(_violacao(
                "🔴 ALTA", "Tipo mudou", nome,
                f"'{nome}' era {esperada['tipo']} e agora é {atual['Tipo_Inferred']}. "
                "Cast implícito quebra join e comparação.",
            ))

        pct_nulos = float(atual["Pct_Nulos"])
        if esperada.get("obrigatoria") and atual["Qtd_Nulos"] > 0:
            violacoes.append(_violacao(
                "🔴 ALTA", "Coluna obrigatória com nulo", nome,
                f"'{nome}' não podia ter nulo e veio com {atual['Qtd_Nulos']:,} "
                f"({pct_nulos:.1f}%).",
            ))
        elif pct_nulos > float(esperada.get("max_pct_nulos", 100.0)):
            violacoes.append(_violacao(
                "🟡 MÉDIA", "Mais nulos que o previsto", nome,
                f"'{nome}' está com {pct_nulos:.1f}% de nulos; o contrato admite até "
                f"{esperada['max_pct_nulos']:.1f}%.",
            ))

        if esperada.get("unica") and float(atual.get("Ratio_Unicidade", 0)) < 0.999:
            violacoes.append(_violacao(
                "🔴 ALTA", "Chave duplicada", nome,
                f"'{nome}' era única e agora repete valores "
                f"({atual['Qtd_Unicos']:,} distintos em {meta['linhas_analisadas']:,} linhas).",
            ))

        permitidos = esperada.get("valores_permitidos")
        if permitidos:
            atuais = {v for v in (atual.get("Amostra_Valores") or "").split(", ") if v}
            fora = sorted(atuais - set(permitidos))
            if fora:
                violacoes.append(_violacao(
                    "🟡 MÉDIA", "Valor fora do domínio", nome,
                    f"'{nome}' trouxe valor(es) que não constam do contrato: "
                    f"{', '.join(fora[:5])}.",
                ))

    regras_atuais = {r["regra"]: r for r in payload.get("regras_negocio", [])}
    for regra in contrato.get("regras_negocio", []):
        atual_regra = regras_atuais.get(regra["regra"])
        if atual_regra is None:
            violacoes.append(_violacao(
                "🟡 MÉDIA", "Regra não confirmada", "(tabela)",
                f"A regra {regra['regra']} valia no contrato e não foi observada nesta "
                "extração — pode ter deixado de valer, ou as colunas mudaram.",
            ))
        elif atual_regra.get("qtd_violacoes", 0) > 0:
            violacoes.append(_violacao(
                "🔴 ALTA", "Regra violada", "(tabela)",
                f"{regra['regra']} falha em {atual_regra['qtd_violacoes']:,} linha(s).",
            ))

    graves = sum(1 for v in violacoes if v["severidade"].endswith("ALTA"))
    return {
        "tabela": meta["tabela"],
        "contrato_de": contrato.get("tabela"),
        "gerado_em": datetime.now(UTC).isoformat(),
        "aprovado": graves == 0,
        "qtd_violacoes": len(violacoes),
        "qtd_graves": graves,
        "violacoes": violacoes,
        "resumo": (
            "Nenhuma violação: a extração está de acordo com o contrato."
            if not violacoes else
            f"{len(violacoes)} violação(ões), {graves} grave(s)."
        ),
    }

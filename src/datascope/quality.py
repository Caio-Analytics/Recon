"""Transformação de achados em recomendações de ETL, gap analysis de KPI e
score de qualidade da tabela.

Este módulo não analisa dados: ele recebe o que `statistics` e
`relationships` apuraram e decide o que dizer ao usuário e com que
prioridade.
"""
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from loguru import logger

from . import config

# ── Prioridades ─────────────────────────────────────────────────────────────
# Rank explícito: a ordenação do relatório dependia do codepoint do emoji
# ("🔴" < "🟡" < "🟢" por acidente do Unicode) e quebraria em silêncio ao
# renomear qualquer prioridade.
PRIORIDADE_ALTA = "🔴 ALTA"
PRIORIDADE_MEDIA = "🟡 MÉDIA"
PRIORIDADE_BAIXA = "🟢 BAIXA"
PRIORIDADE_INFO = "🟢 INFO"

RANK_PRIORIDADE: dict[str, int] = {
    PRIORIDADE_ALTA: 0,
    PRIORIDADE_MEDIA: 1,
    PRIORIDADE_BAIXA: 2,
    PRIORIDADE_INFO: 3,
}


def ordenar_por_prioridade(recomendacoes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        recomendacoes,
        key=lambda r: (RANK_PRIORIDADE.get(r.get("Prioridade", ""), 9), str(r.get("Coluna", ""))),
    )


# ── Regras de KPI ───────────────────────────────────────────────────────────

def carregar_regras_kpi(caminho: str | None = None) -> list[dict[str, Any]]:
    """Carrega as regras de gap analysis, do YAML informado ou do padrão.

    As regras embutidas são de RH. Num arquivo de outro domínio elas viram
    ruído — daí a possibilidade de trocar por um YAML com a mesma estrutura:
    uma lista de `{id, nome, semanticas}`.
    """
    if not caminho:
        return config.REGRAS_KPI_PADRAO

    import yaml  # dependência opcional no caminho quente; só carrega se usado

    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))
    if isinstance(dados, dict):
        dados = dados.get("kpis", [])
    if not isinstance(dados, list) or not dados:
        raise ValueError(f"Arquivo de KPIs '{caminho}' não contém uma lista de regras.")

    regras: list[dict[str, Any]] = []
    for i, item in enumerate(dados):
        if not isinstance(item, dict) or "semanticas" not in item:
            raise ValueError(f"Regra {i} de '{caminho}' precisa ter ao menos o campo 'semanticas'.")
        regras.append({
            "id": str(item.get("id", f"KPI_{i + 1:03d}")),
            "nome": str(item.get("nome", item.get("id", f"KPI {i + 1}"))),
            "semanticas": [str(s) for s in item["semanticas"]],
        })
    logger.info(f"Regras de KPI carregadas de '{caminho}': {len(regras)} regra(s)")
    return regras


def gerar_gap_analysis(
    semanticas_presentes: set[str], regras: Sequence[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    gaps = []
    for regra in (regras if regras is not None else config.REGRAS_KPI_PADRAO):
        exigidas = set(regra["semanticas"])
        presentes = exigidas & semanticas_presentes
        ausentes = exigidas - semanticas_presentes
        cobertura = len(presentes) / len(exigidas) if exigidas else 0.0

        if cobertura == 1.0:
            status = "✅ Habilitado"
        elif cobertura > 0:
            status = "⚠️ Parcialmente Habilitado"
        else:
            status = "❌ Bloqueado"

        gaps.append({
            "kpi_id": regra["id"],
            "kpi_nome": regra["nome"],
            "status": status,
            "cobertura_pct": f"{cobertura:.0%}",
            "semanticas_presentes": sorted(presentes),
            "semanticas_ausentes": sorted(ausentes),
            "recomendacao": (
                f"Inclua colunas com semântica: {', '.join(sorted(ausentes))}"
                if ausentes else "Tabela possui todos os requisitos para este KPI."
            ),
        })
    return gaps


# ── Recomendações por coluna ────────────────────────────────────────────────

def _base(nome_tabela: str, coluna: str, prioridade: str, camada: str, acao: str,
          linhas: int, pct: float | None = None) -> dict[str, Any]:
    rec = {
        "Tabela": nome_tabela, "Coluna": coluna, "Prioridade": prioridade,
        "Camada": camada, "Acao": acao, "Linhas_Afetadas": linhas,
    }
    if pct is not None:
        rec["Pct_Impacto"] = f"{pct:.1f}%"
    return rec


def gerar_recomendacoes_etl(
    nome_tabela: str,
    coluna: str,
    stats: dict[str, Any],
    padrao_estruturado: str,
    linhas_analisadas: int,
) -> list[dict[str, Any]]:
    recomendacoes: list[dict[str, Any]] = []
    n_validos = linhas_analisadas - stats["nulos_qtd"]
    pct_validos = (n_validos / linhas_analisadas * 100) if linhas_analisadas > 0 else 0.0
    caracteristica = stats["caracteristica"]
    flags = stats["flags"]
    qualidade = stats.get("qualidade", {})
    extras = stats.get("estatisticas_adicionais", {})
    sensivel = padrao_estruturado != "Nenhum"

    if "Vazia" in caracteristica:
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Bronze",
            f"Remover '{coluna}': 100% nulos. Zero impacto em dados úteis.", 0,
        ))

    if flags["is_date_as_text"]:
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Bronze",
            f"Converter '{coluna}' para Date/Datetime. Viabiliza filtros e JOINs temporais.",
            n_validos, pct_validos,
        ))

    if sensivel:
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Silver",
            f"LGPD: Mascarar/Hashear '{coluna}' ({padrao_estruturado}). "
            f"Protege {n_validos:,} registros ({pct_validos:.1f}%).",
            n_validos, pct_validos,
        ))

    pii = qualidade.get("pii_texto_livre", {})
    if pii.get("tem_pii"):
        tipos = ", ".join(sorted(pii.get("tipos", {})))
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Silver",
            f"LGPD: '{coluna}' é texto livre com PII embutida ({tipos}). "
            "Aplicar redação/anonimização antes de expor a coluna.",
            n_validos, pct_validos,
        ))

    sentinelas = qualidade.get("sentinelas", {})
    if sentinelas.get("tem_sentinela"):
        exemplos = ", ".join(f"'{v['valor']}'" for v in sentinelas["valores"][:3])
        qtd = sentinelas["qtd_total"]
        pct_sentinela = sentinelas["pct_total"] * 100
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Bronze",
            f"'{coluna}' usa {exemplos} como marcador de ausência em {qtd:,} registros "
            f"({pct_sentinela:.1f}%). Converter para NULL — hoje entram como valor válido e "
            "distorcem contagens e médias.",
            qtd, pct_sentinela,
        ))

    if qualidade.get("mojibake", {}).get("tem_mojibake"):
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Bronze",
            f"'{coluna}' tem caracteres corrompidos por encoding (ex.: "
            f"{qualidade['mojibake']['exemplos'][0][:40]!r}). Reprocessar a carga com o "
            "encoding correto — corrigir no destino não recupera o caractere original.",
            n_validos, pct_validos,
        ))

    documento = qualidade.get("documento_invalido", {})
    if documento.get("tem_documento_invalido"):
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Bronze",
            f"'{coluna}' tem formato de {documento['tipo']} em "
            f"{documento['pct_formato']:.0%} dos valores, mas só "
            f"{documento['pct_valido']:.0%} passam no dígito verificador. "
            "Indica campo truncado, dígito perdido em conversão numérica ou "
            "preenchimento fictício — validar na origem antes de usar como chave.",
            n_validos, pct_validos,
        ))

    inconsistencia = qualidade.get("inconsistencia_normalizacao", {})
    if inconsistencia.get("tem_inconsistencia"):
        exemplo = inconsistencia["exemplos"][0]["variantes"]
        atual = inconsistencia["valores_unicos_atual"]
        normalizado = inconsistencia["valores_unicos_normalizado"]
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_MEDIA, "Silver",
            f"'{coluna}' tem o mesmo valor escrito de formas diferentes "
            f"(ex.: {' / '.join(repr(v) for v in exemplo[:4])}). Padronizar reduz a "
            f"cardinalidade de {atual} para {normalizado} — sem isso qualquer GROUP BY "
            "divide o mesmo grupo em vários.",
            n_validos, pct_validos,
        ))

    # Chave primária só faz sentido em coluna que não é dado pessoal. Promover
    # CPF ou e-mail a PK contradiz a recomendação de mascarar a mesma coluna.
    if "Chave Primária Potencial" in caracteristica:
        if sensivel:
            recomendacoes.append(_base(
                nome_tabela, coluna, PRIORIDADE_MEDIA, "Silver",
                f"'{coluna}' é única e serviria como chave natural, mas é dado pessoal "
                f"({padrao_estruturado}). Gerar uma surrogate key e manter "
                f"'{coluna}' apenas hasheada.",
                n_validos, pct_validos,
            ))
        else:
            recomendacoes.append(_base(
                nome_tabela, coluna, PRIORIDADE_MEDIA, "Silver",
                f"Promover '{coluna}' como PK. {stats['valores_unicos']:,} valores únicos "
                "garantem integridade.",
                n_validos, pct_validos,
            ))

    if "Quase-Chave" in caracteristica:
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_MEDIA, "Bronze",
            f"'{coluna}' tem {stats['ratio_unicidade']:.1%} de unicidade — verificar "
            "duplicatas ou dados sujos antes de usar como chave.",
            n_validos, pct_validos,
        ))

    if "Quasi-Constante" in caracteristica:
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_MEDIA, "Silver",
            f"'{coluna}' é quasi-constante. Avaliar remoção ou tratamento como constante "
            "no pipeline.",
            n_validos, pct_validos,
        ))

    if flags["mistura_tipos"].get("tem_mistura"):
        tipos = flags["mistura_tipos"].get("tipos_detectados", [])
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_ALTA, "Bronze",
            f"'{coluna}' contém mistura de tipos: {tipos}. Normalizar antes de qualquer "
            "transformação.",
            n_validos, pct_validos,
        ))

    outliers_info = extras.get("outliers_iqr", {})
    n_out = outliers_info.get("qtd_outliers_total", 0)
    if n_out > 0 and linhas_analisadas > 0:
        pct_out = round(n_out / linhas_analisadas * 100, 1)
        if pct_out > 1.0:
            recomendacoes.append(_base(
                nome_tabela, coluna, PRIORIDADE_MEDIA, "Silver",
                f"'{coluna}' tem {n_out:,} outliers ({pct_out:.1f}%, método "
                f"{outliers_info.get('metodo', 'IQR')}). Intervalo esperado: "
                f"[{outliers_info['limite_inferior']}, {outliers_info['limite_superior']}].",
                n_out, pct_out,
            ))

    if extras.get("qtd_datas_futuras", 0) > 0:
        qtd = extras["qtd_datas_futuras"]
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_MEDIA, "Bronze",
            f"'{coluna}' tem {qtd:,} data(s) no futuro (máx.: {extras.get('max_data')}). "
            "Normalmente erro de digitação de ano ou valor default.",
            qtd, qtd / linhas_analisadas * 100 if linhas_analisadas else 0.0,
        ))

    if extras.get("qtd_meses_sem_registro", 0) > 0:
        faltantes = extras["meses_sem_registro"]
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_MEDIA, "Bronze",
            f"'{coluna}' tem {extras['qtd_meses_sem_registro']} mês(es) sem nenhum registro "
            f"dentro do intervalo coberto (ex.: {', '.join(faltantes[:4])}). "
            "Verificar se houve falha de carga.",
            0,
        ))

    benford = extras.get("benford")
    if benford and not benford.get("aderente"):
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_BAIXA, "Silver",
            f"'{coluna}' desvia da Lei de Benford (desvio máx. "
            f"{benford['desvio_maximo_absoluto']:.1%}). Comum em valor arredondado, faixa "
            "truncada ou dado sintético — vale conferir a origem.",
            benford["n"],
        ))

    otimizacao = stats.get("otimizacao", {})
    if otimizacao.get("dtype_sugerido") and otimizacao.get("economia_pct", 0) >= 0.3:
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_BAIXA, "Silver",
            f"Converter '{coluna}' de {otimizacao['dtype_atual']} para "
            f"{otimizacao['dtype_sugerido']}: economiza {otimizacao['economia_mb']:.2f} MB "
            f"({otimizacao['economia_pct']:.0%}) sem perda de informação.",
            n_validos,
        ))

    return recomendacoes


# ── Recomendações no nível da tabela ────────────────────────────────────────

def gerar_recomendacoes_tabela(
    nome_tabela: str,
    duplicatas: dict[str, Any],
    redundantes: list[dict[str, Any]],
    chaves_compostas: list[dict[str, Any]],
    linhas_analisadas: int,
) -> list[dict[str, Any]]:
    recomendacoes: list[dict[str, Any]] = []

    qtd_dup = duplicatas.get("qtd_linhas_duplicadas", 0)
    if qtd_dup > 0:
        pct = duplicatas.get("pct_linhas_duplicadas", 0.0) * 100
        recomendacoes.append(_base(
            nome_tabela, "(tabela)", PRIORIDADE_ALTA, "Bronze",
            f"{qtd_dup:,} linha(s) integralmente duplicada(s) ({pct:.1f}%). Deduplicar na "
            "Bronze — qualquer contagem ou soma feita sobre esta tabela está inflada.",
            qtd_dup, pct,
        ))

    for red in redundantes:
        recomendacoes.append(_base(
            nome_tabela, red["coluna_redundante"], PRIORIDADE_MEDIA, "Silver",
            f"'{red['coluna_redundante']}' é idêntica a '{red['coluna']}'. Remover uma das "
            "duas elimina ambiguidade e reduz o volume.",
            linhas_analisadas,
        ))

    for chave in chaves_compostas:
        colunas = " + ".join(f"'{c}'" for c in chave["colunas"])
        recomendacoes.append(_base(
            nome_tabela, "(tabela)", PRIORIDADE_MEDIA, "Silver",
            f"Nenhuma coluna é única sozinha, mas {colunas} identificam a linha. "
            "Usar como chave primária composta.",
            linhas_analisadas,
        ))

    return recomendacoes


# ── Score de qualidade ──────────────────────────────────────────────────────

def _nota(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "E"


def calcular_score_qualidade(
    colunas: list[dict[str, Any]],
    duplicatas: dict[str, Any],
    redundantes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Consolida os defeitos encontrados num score 0-100.

    Cada dimensão penaliza proporcionalmente à sua abrangência (fração de
    colunas afetadas, ou fração de linhas no caso das duplicatas), limitada
    pelo peso configurado. O objetivo não é precisão — é dar uma leitura de
    uma linha e uma lista ordenada do que mais pesa.
    """
    total = len(colunas)
    if total == 0:
        return {"score": 0.0, "nota": "E", "penalidades": []}

    pesos = config.PESOS_SCORE_QUALIDADE

    def fracao(predicado) -> float:
        return sum(1 for c in colunas if predicado(c)) / total

    # As dimensões precisam ser disjuntas: usar `nulos_efetivos_pct` aqui
    # contaria a sentinela duas vezes (uma como nulo, outra na dimensão
    # própria) e deixaria o score pessimista em toda tabela com "N/A".
    media_nulos = sum(c.get("Pct_Nulos", 0.0) for c in colunas) / total / 100

    def tem_algum_defeito(c: dict[str, Any]) -> bool:
        qual = c.get("Qualidade", {})
        alertas = c.get("Alertas", {})
        return bool(
            c.get("Pct_Nulos", 0.0) > 0
            or qual.get("sentinelas", {}).get("tem_sentinela")
            or qual.get("inconsistencia_normalizacao", {}).get("tem_inconsistencia")
            or qual.get("mojibake", {}).get("tem_mojibake")
            or qual.get("documento_invalido", {}).get("tem_documento_invalido")
            or qual.get("pii_texto_livre", {}).get("tem_pii")
            or alertas.get("mistura_tipos", {}).get("tem_mistura")
            or alertas.get("data_como_texto")
            or "Vazia" in c.get("Caracteristica", "")
        )

    dimensoes = [
        ("Colunas com algum defeito", fracao(tem_algum_defeito),
         pesos["colunas_com_defeito"]),
        ("Nulos reais", media_nulos, pesos["nulos"]),
        ("Documento com dígito inválido",
         fracao(lambda c: c.get("Qualidade", {}).get("documento_invalido", {})
                .get("tem_documento_invalido")),
         pesos["documento_invalido"]),
        ("Encoding corrompido",
         fracao(lambda c: c.get("Qualidade", {}).get("mojibake", {}).get("tem_mojibake")),
         pesos["mojibake"]),
        ("Sentinelas / nulos disfarçados",
         fracao(lambda c: c.get("Qualidade", {}).get("sentinelas", {}).get("tem_sentinela")),
         pesos["sentinelas"]),
        ("Colunas 100% vazias",
         fracao(lambda c: "Vazia" in c.get("Caracteristica", "")), pesos["colunas_vazias"]),
        ("Mistura de tipos",
         fracao(lambda c: c.get("Alertas", {}).get("mistura_tipos", {}).get("tem_mistura")),
         pesos["mistura_tipos"]),
        ("Inconsistência de grafia",
         fracao(lambda c: c.get("Qualidade", {}).get("inconsistencia_normalizacao", {})
                .get("tem_inconsistencia")),
         pesos["inconsistencia_texto"]),
        ("Linhas duplicadas",
         float(duplicatas.get("pct_linhas_duplicadas", 0.0)), pesos["duplicatas"]),
        ("Data armazenada como texto",
         fracao(lambda c: c.get("Alertas", {}).get("data_como_texto")), pesos["data_como_texto"]),
        ("Colunas redundantes",
         min(len(redundantes) / total, 1.0), pesos["colunas_redundantes"]),
        ("PII em texto livre",
         fracao(lambda c: c.get("Qualidade", {}).get("pii_texto_livre", {}).get("tem_pii")),
         pesos["lgpd_exposto"]),
    ]

    penalidades: list[dict[str, Any]] = []
    desconto_total = 0.0
    for nome, intensidade, peso in dimensoes:
        penalidade = min(max(float(intensidade), 0.0), 1.0) * peso
        desconto_total += penalidade
        if penalidade > 0:
            penalidades.append({
                "dimensao": nome,
                "intensidade": round(float(intensidade), 4),
                "pontos_perdidos": round(penalidade, 2),
            })

    penalidades.sort(key=lambda p: -float(p["pontos_perdidos"]))
    score = max(0.0, 100.0 - desconto_total)
    return {"score": round(score, 1), "nota": _nota(score), "penalidades": penalidades}

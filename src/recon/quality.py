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

    formato = qualidade.get("formato", {})
    if formato.get("tem_formato") and formato.get("qtd_fora_do_padrao"):
        fora = ", ".join(
            f"{ex['valor']!r}" for ex in formato.get("exemplos_fora_do_padrao", [])[:3]
        )
        recomendacoes.append(_base(
            nome_tabela, coluna, PRIORIDADE_MEDIA, "Bronze",
            f"'{coluna}' segue o formato {formato['formato_dominante']} em "
            f"{formato['cobertura']:.0%} dos valores (ex.: {formato['exemplo_conforme']!r}), "
            f"mas {formato['qtd_fora_do_padrao']} valor(es) fogem dele: {fora}. "
            "Em código de cadastro isso costuma ser digitação manual, campo truncado ou "
            "registro de outro sistema — conferir antes de usar como chave.",
            int(formato["qtd_fora_do_padrao"]),
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

    return recomendacoes


# ── Recomendações no nível da tabela ────────────────────────────────────────

def gerar_recomendacoes_tabela(
    nome_tabela: str,
    duplicatas: dict[str, Any],
    redundantes: list[dict[str, Any]],
    chaves_compostas: list[dict[str, Any]],
    linhas_analisadas: int,
    colunas: list[dict[str, Any]] | None = None,
    duplicatas_aproximadas: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    recomendacoes: list[dict[str, Any]] = []

    # Sugestão de dtype é por coluna, mas como recomendação individual afogava
    # a lista: numa tabela de 70 colunas eram 68 linhas de "converter para
    # category" contra 22 achados que importavam. Vira uma linha só, com o
    # ganho somado e as colunas listadas.
    otimizaveis = [
        (c["Coluna"], c["Otimizacao"]) for c in (colunas or [])
        if (c.get("Otimizacao") or {}).get("dtype_sugerido")
        and c["Otimizacao"].get("economia_pct", 0) >= 0.3
    ]
    if otimizaveis:
        economia = sum(o.get("economia_mb", 0.0) for _, o in otimizaveis)
        exemplos = ", ".join(
            f"{nome} → {o['dtype_sugerido']}" for nome, o in otimizaveis[:4]
        )
        resto = f" (+{len(otimizaveis) - 4})" if len(otimizaveis) > 4 else ""
        recomendacoes.append(_base(
            nome_tabela, "(tabela)", PRIORIDADE_BAIXA, "Silver",
            f"Otimizar o dtype de {len(otimizaveis)} coluna(s) economiza "
            f"{economia:.1f} MB em memória: {exemplos}{resto}. "
            "O script de limpeza gerado já aplica todas.",
            linhas_analisadas,
        ))

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
        # Idêntica e quase idêntica pedem ações opostas. A primeira é uma coluna
        # sobrando: apaga-se uma das duas. A segunda é o mesmo campo vindo de
        # dois sistemas, e as linhas divergentes são o achado — mandar remover
        # uma delas joga fora exatamente a informação que justificou o alerta.
        if red.get("tipo") == "quase idêntica":
            recomendacoes.append(_base(
                nome_tabela, red["coluna_redundante"], PRIORIDADE_ALTA, "Silver",
                f"'{red['coluna_redundante']}' concorda com '{red['coluna']}' em "
                f"{red['concordancia']:.1%} das {red.get('linhas_comparadas', 0):,} linhas "
                f"comparáveis, e diverge em {red.get('linhas_divergentes', 0):,}. "
                "Provável mesmo campo vindo de duas origens: reconciliar as divergências e "
                "eleger a fonte de verdade — não remover antes de decidir qual vale.",
                red.get("linhas_divergentes", 0),
            ))
            continue
        recomendacoes.append(_base(
            nome_tabela, red["coluna_redundante"], PRIORIDADE_MEDIA, "Silver",
            f"'{red['coluna_redundante']}' é idêntica a '{red['coluna']}'. Remover uma das "
            "duas elimina ambiguidade e reduz o volume.",
            linhas_analisadas,
        ))

    for aproximada in duplicatas_aproximadas or []:
        exemplo = aproximada["exemplos"][0]["variantes"] if aproximada["exemplos"] else []
        recomendacoes.append(_base(
            nome_tabela, aproximada["coluna"], PRIORIDADE_ALTA, "Silver",
            f"{aproximada['qtd_grupos']} grupo(s) de valores diferentes em "
            f"'{aproximada['coluna']}' apontam para o mesmo registro"
            + (f" (ex.: {' / '.join(exemplo[:3])})" if exemplo else "")
            + f", somando {aproximada['linhas_afetadas']:,} linhas. Deduplicar por chave "
            "canônica antes de contar pessoas — a comparação exata não pega esses casos.",
            aproximada["linhas_afetadas"],
        ))

    for chave in chaves_compostas:
        rotulo = " + ".join(f"'{c}'" for c in chave["colunas"])
        recomendacoes.append(_base(
            nome_tabela, "(tabela)", PRIORIDADE_MEDIA, "Silver",
            f"Nenhuma coluna é única sozinha, mas {rotulo} identificam a linha. "
            "Usar como chave primária composta.",
            linhas_analisadas,
        ))

    return recomendacoes


# ── Risco LGPD ──────────────────────────────────────────────────────────────

# Quanto cada tipo de dado pessoal pesa na exposição da tabela. CPF identifica
# uma pessoa sozinho; CEP e telefone precisam de companhia.
_PESO_EXPOSICAO: dict[str, float] = {
    "CPF": 1.0, "Nome de pessoa": 0.9, "E-mail": 0.8, "CNPJ": 0.4,
    "Telefone": 0.7, "CEP": 0.5, "UUID": 0.2,
}
_PESO_EXPOSICAO_PADRAO = 0.6


def calcular_risco_lgpd(colunas: list[dict[str, Any]]) -> dict[str, Any]:
    """Exposição de dado pessoal, num número separado da qualidade.

    Misturar as duas coisas num score só respondia mal às duas perguntas: uma
    base impecável cheia de CPF tirava nota baixa como se estivesse suja, e uma
    base suja sem dado pessoal parecia tão arriscada quanto. Aqui a pergunta é
    outra — *o que vaza se este arquivo for para o lugar errado?*
    """
    sensiveis = [
        {"coluna": c["Coluna"], "tipo": c["Dado_Sensivel_LGPD"]}
        for c in colunas if c.get("Dado_Sensivel_LGPD", "Nenhum") != "Nenhum"
    ]
    embutidas = [
        {"coluna": c["Coluna"],
         "tipo": ", ".join(sorted(c.get("Qualidade", {}).get("pii_texto_livre", {}).get("tipos", {})))}
        for c in colunas
        if c.get("Qualidade", {}).get("pii_texto_livre", {}).get("tem_pii")
    ]
    if not sensiveis and not embutidas:
        return {
            "nivel": "🟢 Sem dado pessoal identificado",
            "exposicao": 0.0,
            "colunas_sensiveis": [],
            "pii_em_texto_livre": [],
            "recomendacao": "Nada a mascarar: nenhuma coluna com dado pessoal reconhecido.",
        }

    exposicao = max(
        [_PESO_EXPOSICAO.get(s["tipo"], _PESO_EXPOSICAO_PADRAO) for s in sensiveis]
        + [1.0 for _ in embutidas],  # PII solta em texto livre é o pior caso
        default=0.0,
    )
    # Várias colunas sensíveis juntas aumentam a exposição: nome + CPF + e-mail
    # identifica muito mais do que qualquer um deles sozinho.
    exposicao = min(1.0, exposicao + 0.05 * max(len(sensiveis) + len(embutidas) - 1, 0))
    nivel = (
        "🔴 Alta" if exposicao >= 0.8 else "🟡 Média" if exposicao >= 0.5 else "🟢 Baixa"
    )
    return {
        "nivel": nivel,
        "exposicao": round(exposicao, 3),
        "colunas_sensiveis": sensiveis,
        "pii_em_texto_livre": embutidas,
        "recomendacao": (
            f"{len(sensiveis) + len(embutidas)} coluna(s) com dado pessoal. Mascarar ou "
            "hashear antes de compartilhar o arquivo, e restringir quem acessa a camada "
            "que guarda o valor original."
        ),
    }


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


def dano_da_coluna(coluna: dict[str, Any]) -> tuple[float, list[str]]:
    """Quanto uma coluna está comprometida, de 0 a 1, e por quê.

    Os danos somam e saturam em 1: uma coluna com mojibake *e* sentinela está
    mais comprometida que uma com só um dos dois, mas nenhuma passa de
    inutilizável.
    """
    qual = coluna.get("Qualidade", {})
    alertas = coluna.get("Alertas", {})
    dano = config.DANO_POR_DEFEITO
    achados: list[tuple[float, str]] = []

    if "Vazia" in coluna.get("Caracteristica", ""):
        return 1.0, ["coluna 100% vazia"]

    pct_nulos = float(coluna.get("Pct_Nulos", 0.0)) / 100
    if pct_nulos > 0:
        achados.append((pct_nulos * config.DANO_MAXIMO_NULOS, f"{pct_nulos:.0%} de nulos"))
    if qual.get("mojibake", {}).get("tem_mojibake"):
        achados.append((dano["mojibake"], "encoding corrompido"))
    if qual.get("documento_invalido", {}).get("tem_documento_invalido"):
        achados.append((dano["documento_invalido"], "documento com dígito inválido"))
    if alertas.get("mistura_tipos", {}).get("tem_mistura"):
        achados.append((dano["mistura_tipos"], "mistura de tipos"))
    if qual.get("sentinelas", {}).get("tem_sentinela"):
        achados.append((dano["sentinela"], "nulos disfarçados"))
    if qual.get("pii_texto_livre", {}).get("tem_pii"):
        achados.append((dano["pii_texto_livre"], "PII em texto livre"))
    if qual.get("inconsistencia_normalizacao", {}).get("tem_inconsistencia"):
        achados.append((dano["inconsistencia_texto"], "grafias divergentes"))
    if alertas.get("data_como_texto"):
        achados.append((dano["data_como_texto"], "data como texto"))
    # Dado pessoal estruturado *não* entra aqui. Uma base de RH limpa perdia
    # nota por ter CPF — que é o dado dela. Exposição é risco, não defeito, e
    # agora tem número próprio em `calcular_risco_lgpd`.

    total = min(1.0, sum(peso for peso, _ in achados))
    motivos = [motivo for _, motivo in sorted(achados, key=lambda a: -a[0])]
    return total, motivos


def calcular_score_qualidade(
    colunas: list[dict[str, Any]],
    duplicatas: dict[str, Any],
    redundantes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Consolida os defeitos num score 0-100.

    É a média do dano por coluna, não a soma de frações do total de colunas. A
    diferença importa: dividir cada dimensão pelo número de colunas fazia o
    score encolher conforme a tabela crescia — uma base de 70 colunas com 22
    problemas de alta prioridade tirava a mesma nota de uma base limpa, porque
    cada defeito isolado respondia por menos de 1% do total.

    Assim o score é invariante ao tamanho da tabela: 30% das colunas
    comprometidas custam o mesmo em 10 ou em 200 colunas.
    """
    total = len(colunas)
    if total == 0:
        return {"score": 0.0, "nota": "E", "colunas_criticas": [], "penalidades": []}

    danos = [(c["Coluna"], *dano_da_coluna(c)) for c in colunas]
    dano_colunas = sum(d for _, d, _ in danos) / total

    pct_duplicadas = float(duplicatas.get("pct_linhas_duplicadas", 0.0))
    # Só coluna *idêntica* é redundância. A quase idêntica é divergência entre
    # origens — problema real, mas de outra natureza, e contá-la aqui derrubava
    # a nota de uma tabela cujo defeito é reconciliação, não duplicação.
    exatas = [r for r in redundantes if r.get("tipo") != "quase idêntica"]
    fracao_redundante = min(len(exatas) / total, 1.0)
    dano_tabela = min(1.0, pct_duplicadas + fracao_redundante * 0.5)

    dano_total = min(
        1.0,
        config.PESO_DANO_COLUNAS * dano_colunas + config.PESO_DANO_TABELA * dano_tabela,
    )
    score = max(0.0, 100.0 * (1.0 - dano_total))

    criticas = sorted(
        ({"coluna": nome, "dano": round(d, 3), "motivos": motivos}
         for nome, d, motivos in danos if d > 0),
        key=lambda c: -c["dano"],
    )

    penalidades: list[dict[str, Any]] = [{
        "dimensao": "Colunas comprometidas",
        "intensidade": round(dano_colunas, 4),
        "pontos_perdidos": round(100 * config.PESO_DANO_COLUNAS * dano_colunas, 2),
    }]
    if dano_tabela > 0:
        penalidades.append({
            "dimensao": "Duplicatas e colunas redundantes",
            "intensidade": round(dano_tabela, 4),
            "pontos_perdidos": round(100 * config.PESO_DANO_TABELA * dano_tabela, 2),
        })

    return {
        "score": round(score, 1),
        "nota": _nota(score),
        "colunas_comprometidas": len(criticas),
        "colunas_criticas": criticas[:10],
        "penalidades": penalidades,
    }

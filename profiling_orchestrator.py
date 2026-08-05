"""
profiling_orchestrator.py — v2.1
─────────────────────────────────
Orquestrador do pipeline de profiling de CSV/XLSX.

Uso:
    python profiling_orchestrator.py arquivo.csv
    python profiling_orchestrator.py arquivo.xlsx
"""

import sys
import os
import csv
import json
import chardet
import pandas as pd
from tqdm import tqdm
from semantic_engine import analisar_contexto
from statistical_profiler import analisar_matematica


# ─────────────────────────────────────────────────────────────
# DETECÇÃO DE ARQUIVO
# ─────────────────────────────────────────────────────────────

def cheirar_arquivo(caminho_arquivo: str) -> tuple:
    with open(caminho_arquivo, "rb") as f:
        amostra_bytes = f.read(50000)

    detectado = chardet.detect(amostra_bytes)["encoding"]
    encoding_detectado = detectado if detectado else "utf-8"

    # ASCII é subconjunto de UTF-8 — elevar para evitar problemas com acentos
    if encoding_detectado.lower() == "ascii":
        encoding_detectado = "utf-8"

    try:
        amostra_str = amostra_bytes.decode(encoding_detectado, errors="ignore")
        sniffer = csv.Sniffer()
        delimitador = sniffer.sniff(amostra_str).delimiter
    except Exception:
        delimitador = ","

    return encoding_detectado, delimitador


# ─────────────────────────────────────────────────────────────
# GERADOR DE RECOMENDAÇÕES ETL
# ─────────────────────────────────────────────────────────────

def _gerar_recomendacoes_etl(lista_insights: list) -> list:
    """
    Produz uma lista de ações concretas para o Power Query / Dataflow
    baseada nos resultados do profiling. Ordenadas por prioridade.
    """
    recomendacoes = []

    # PRIORIDADE 1 — Remover lixo
    vazias = [i["coluna"] for i in lista_insights if "Vazia" in i["caract"]]
    if vazias:
        recomendacoes.append({
            "prioridade": "🔴 ALTA — Limpeza obrigatória",
            "acao": f"Remover colunas 100% vazias no Power Query (Bronze): {vazias}",
            "camada": "Bronze"
        })

    # PRIORIDADE 1 — Tipagem de datas erradas
    datas_texto = [i["coluna"] for i in lista_insights if i.get("flag_data_como_texto")]
    if datas_texto:
        recomendacoes.append({
            "prioridade": "🔴 ALTA — Tipagem incorreta",
            "acao": (
                f"Converter para tipo Date no Power Query (Bronze): {datas_texto}. "
                "Sem essa tipagem, joins com Tabela Calendário falharão silenciosamente."
            ),
            "camada": "Bronze"
        })

    # PRIORIDADE 1 — Dados sensíveis
    sensiveis = [
        f"{i['coluna']} ({i['flag_padrao_estruturado']})"
        for i in lista_insights if i.get("flag_padrao_estruturado")
    ]
    if sensiveis:
        recomendacoes.append({
            "prioridade": "🔴 ALTA — Privacidade / LGPD",
            "acao": (
                f"Colunas com dados pessoais identificados: {sensiveis}. "
                "Avaliar mascaramento (ex: mostrar apenas últimos 4 dígitos de CPF) "
                "antes de publicar no relatório."
            ),
            "camada": "Bronze ou Silver"
        })

    # PRIORIDADE 2 — Chaves potenciais para join
    chaves = [i["coluna"] for i in lista_insights if "Chave Primária" in i["caract"]]
    if chaves:
        recomendacoes.append({
            "prioridade": "🟡 MÉDIA — Modelagem",
            "acao": (
                f"Colunas candidatas a chave primária: {chaves}. "
                "Usar como campo de relacionamento no modelo do Power BI "
                "ou como argumento de DISTINCTCOUNT em DAX."
            ),
            "camada": "Silver"
        })

    # PRIORIDADE 2 — Categóricas com poucos valores → flags
    categoricas = [i for i in lista_insights if "Categórica" in i["caract"]]
    for c in categoricas:
        n = c["n_unicos"]
        if n == 2:
            recomendacoes.append({
                "prioridade": "🟡 MÉDIA — Enriquecimento",
                "acao": (
                    f"Coluna '{c['coluna']}' tem apenas 2 valores únicos "
                    f"({', '.join(str(v) for v in c['valores_amostra'][:2])}). "
                    "Candidata a conversão para flag booleana (0/1) na camada Silver, "
                    "o que melhora performance em filtros DAX."
                ),
                "camada": "Silver"
            })
        else:
            recomendacoes.append({
                "prioridade": "🟡 MÉDIA — Enriquecimento",
                "acao": (
                    f"Coluna '{c['coluna']}' tem {n} valores distintos — "
                    "candidata a tabela de dimensão ou segmentação de filtro no BI."
                ),
                "camada": "Silver"
            })

    # PRIORIDADE 3 — Valor constante (inútil para análise)
    constantes = [i["coluna"] for i in lista_insights if "Constante" in i["caract"]]
    if constantes:
        recomendacoes.append({
            "prioridade": "🟢 BAIXA — Otimização",
            "acao": (
                f"Colunas com valor único constante: {constantes}. "
                "Avaliar remoção para reduzir peso do modelo."
            ),
            "camada": "Bronze"
        })

    return recomendacoes


# ─────────────────────────────────────────────────────────────
# ORQUESTRADOR PRINCIPAL
# ─────────────────────────────────────────────────────────────

def orquestrar(caminho_arquivo: str):
    print(f"\n{'='*55}")
    print("  Profiler de Alta Precisão v2.1 — Amostra cap 100k")
    print(f"{'='*55}")

    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    encoding = "N/A"
    delimitador = "N/A"

    # ── Leitura ──────────────────────────────────────────────
    try:
        if extensao in (".xlsx", ".xls"):
            xl = pd.ExcelFile(caminho_arquivo)
            if len(xl.sheet_names) > 1:
                print(
                    f"[Aviso] O arquivo tem {len(xl.sheet_names)} abas: "
                    f"{xl.sheet_names}. Lendo apenas a primeira: '{xl.sheet_names[0]}'."
                )
            df = xl.parse(xl.sheet_names[0])
        else:
            encoding, delimitador = cheirar_arquivo(caminho_arquivo)
            print(f"[Core] CSV | Encoding: {encoding} | Delimitador: '{delimitador}'")
            try:
                df = pd.read_csv(
                    caminho_arquivo,
                    sep=delimitador,
                    encoding=encoding,
                    engine="python",
                    on_bad_lines="warn",
                )
            except UnicodeDecodeError:
                fallback = "latin1" if encoding.lower() == "utf-8" else "utf-8"
                encoding = fallback
                df = pd.read_csv(
                    caminho_arquivo,
                    sep=delimitador,
                    encoding=encoding,
                    engine="python",
                    on_bad_lines="warn",
                )
    except Exception as e:
        print(f"\n[Erro Fatal] Falha na leitura:\n{e}")
        return

    # ── Amostragem: 50% do arquivo, com teto absoluto de 100.000 linhas ──
    LIMITE_AMOSTRA = 100_000
    total_linhas_real = len(df)
    tamanho_amostra = min(LIMITE_AMOSTRA, max(1, int(total_linhas_real * 0.50)))
    df_amostra = df.sample(n=tamanho_amostra, random_state=42)

    total_linhas = len(df_amostra)
    total_colunas = len(df_amostra.columns)

    pct_real = round((total_linhas / total_linhas_real) * 100, 1)
    cap_ativo = " [LIMITE 100k ATIVO]" if tamanho_amostra == LIMITE_AMOSTRA else ""
    print(
        f"[Core] Analisando {total_linhas:,} linhas "
        f"({pct_real}% de {total_linhas_real:,}){cap_ativo} | {total_colunas} colunas"
    )

    # ── Estrutura de saída ───────────────────────────────────
    json_output = {
        "metadados": {
            "arquivo": os.path.basename(caminho_arquivo),
            "linhas_totais": total_linhas_real,
            "linhas_analisadas_amostra": total_linhas,
            "colunas": total_colunas,
            "encoding": encoding,
            "delimitador": delimitador,
        },
        "colunas": [],
        "insights_estrategicos": [],
        "recomendacoes_etl": [],
    }

    lista_insights = []

    # ── Análise por coluna ───────────────────────────────────
    for coluna in tqdm(df_amostra.columns, desc="Processando", unit="col"):
        serie = df_amostra[coluna]
        math = analisar_matematica(serie, total_linhas)
        sem = analisar_contexto(coluna)

        lista_insights.append({
            "coluna": coluna,
            "caract": math["caracteristica"],
            "semantica": sem["semantica"],
            "nulos": math["pct_nulos"],
            "n_unicos": math["n_unicos"],
            "valores_amostra": math["valores_amostra"],
            "flag_data_como_texto": math["flag_data_como_texto"],
            "flag_padrao_estruturado": math["flag_padrao_estruturado"],
        })

        json_output["colunas"].append({
            "nome_coluna": coluna,
            "tipo_dado": math["tipo_dados"],
            "semantica_ia": sem["semantica"],
            "confianca_semantica": sem["confianca"],
            "percentual_nulos": math["pct_nulos"],
            "valores_unicos": math["n_unicos"],
            "caracteristica": math["caracteristica"],
            "valores_encontrados": math["valores_amostra"] if math["valores_amostra"] else "Não Elegível",
            "nota_amostragem": math.get("nota_amostra", "Não Elegível"),
            "alertas": {
                "data_como_texto": math["flag_data_como_texto"],
                "dado_sensivel": math["flag_padrao_estruturado"] if math["flag_padrao_estruturado"] else False,
            },
        })

    # ── Insights estratégicos ─────────────────────────────────
    categoricas = [i for i in lista_insights if "Categórica" in i["caract"]]
    for c in categoricas:
        exemplos = ", ".join(str(v) for v in c["valores_amostra"][:10])
        insight = (
            f"A coluna '{c['coluna']}' possui {c['n_unicos']} valores distintos "
            f"({exemplos}). "
            "Identificado como status/categoria — alto potencial para filtros e flags no BI."
        )
        json_output["insights_estrategicos"].append(insight)

    chaves = [i["coluna"] for i in lista_insights if "Chave Primária" in i["caract"]]
    if chaves:
        json_output["insights_estrategicos"].append(
            f"Coluna(s) {chaves} com identificadores 100% únicos na amostra. "
            "Candidatas a chave primária ou campo de DISTINCTCOUNT no DAX."
        )

    vazias = [i["coluna"] for i in lista_insights if "Vazia" in i["caract"]]
    if vazias:
        json_output["insights_estrategicos"].append(
            f"Colunas completamente vazias detectadas: {vazias}. "
            "Remover no Power Query (Bronze) para reduzir peso do modelo."
        )

    datas_texto = [i["coluna"] for i in lista_insights if i.get("flag_data_como_texto")]
    if datas_texto:
        json_output["insights_estrategicos"].append(
            f"⚠️ Colunas que parecem datas mas estão tipadas como Texto: {datas_texto}. "
            "Sem conversão explícita na camada Bronze, o join com Tabela Calendário falhará."
        )

    for i in lista_insights:
        if i.get("flag_padrao_estruturado"):
            json_output["insights_estrategicos"].append(
                f"🔐 Coluna '{i['coluna']}' parece conter {i['flag_padrao_estruturado']}. "
                "Avaliar mascaramento antes da publicação (LGPD)."
            )

    # ── Recomendações ETL ─────────────────────────────────────
    json_output["recomendacoes_etl"] = _gerar_recomendacoes_etl(lista_insights)

    # ── Salvar JSON ───────────────────────────────────────────
    nome_base = os.path.splitext(os.path.basename(caminho_arquivo))[0]
    nome_saida = f"analise_IA_{nome_base}.json"

    with open(nome_saida, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=4)

    print(f"\n[✓] Payload gerado: {nome_saida}")
    print("→  Cole o conteúdo do JSON no Gem de ETL/BI para análise completa.")

    # Resumo no terminal
    print(f"\n{'─'*55}")
    print("  RESUMO")
    print(f"{'─'*55}")
    alertas = [i for i in lista_insights if i.get("flag_data_como_texto") or i.get("flag_padrao_estruturado")]
    print(f"  Colunas analisadas : {total_colunas}")
    print(f"  Categóricas        : {len(categoricas)}")
    print(f"  Chaves únicas      : {len(chaves)}")
    print(f"  Colunas vazias     : {len(vazias)}")
    print(f"  Alertas de tipo    : {len(alertas)}")
    print(f"  Recomendações ETL  : {len(json_output['recomendacoes_etl'])}")
    print(f"{'─'*55}\n")


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python profiling_orchestrator.py <arquivo.csv|xlsx>")
    else:
        orquestrar(sys.argv[1])
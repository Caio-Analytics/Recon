"""Detecção do layout real de uma planilha feita por gente.

Arquivo exportado de sistema tem os dados começando na linha 1. Planilha
montada por uma pessoa tem título, data de emissão, linha em branco, o
cabeçalho lá pela quinta linha, e um "TOTAL" no rodapé.

Sem tratar isso, o pandas adota o título como nome de coluna, toda a tipagem
vai por água abaixo e o relatório sai *bonito e errado* — que é o pior
resultado possível, porque nada nele indica que está errado.

Todas as heurísticas aqui são conservadoras: na dúvida, devolvem o
comportamento padrão (cabeçalho na primeira linha) em vez de arriscar um
palpite. Cada desvio do padrão vira um aviso explícito no relatório.
"""
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# Uma linha só é candidata a cabeçalho se preencher pelo menos esta fração da
# largura típica do bloco de dados.
_FRACAO_LARGURA_CABECALHO = 0.8
# E se a maior parte das suas células for texto — cabeçalho é rótulo, não dado.
_FRACAO_TEXTO_CABECALHO = 0.6
# Linhas do topo inspecionadas em busca do cabeçalho. Preâmbulo maior que isso
# não é preâmbulo, é outra coisa.
_MAX_LINHAS_PREAMBULO = 30
_MAX_CARDINALIDADE_MESCLA = 50
_TOLERANCIA_TOTAL = 0.01
_ROTULOS_TOTAL = frozenset({
    "total", "totais", "total geral", "soma", "somatorio", "geral",
    "subtotal", "sub-total", "acumulado", "grand total",
})


@dataclass
class Layout:
    """O que a detecção concluiu sobre o formato da planilha."""
    linha_cabecalho: int = 0
    linhas_rodape: int = 0
    colunas_vazias_removidas: list[str] = field(default_factory=list)
    avisos: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ajustado(self) -> bool:
        return bool(
            self.linha_cabecalho or self.linhas_rodape or self.colunas_vazias_removidas
        )


def _aviso(tipo: str, mensagem: str, severidade: str = "🟡 MÉDIA") -> dict[str, Any]:
    return {"tipo": tipo, "severidade": severidade, "mensagem": mensagem}


def _fracao_texto(linha: pd.Series) -> float:
    preenchidas = linha.dropna()
    if preenchidas.empty:
        return 0.0
    textos = sum(1 for v in preenchidas if isinstance(v, str) and v.strip())
    return textos / len(preenchidas)


def detectar_linha_cabecalho(df_bruto: pd.DataFrame) -> tuple[int, list[dict[str, Any]]]:
    """Descobre em que linha está o cabeçalho de verdade.

    A ideia: o bloco de dados tem uma largura típica (quantas colunas ficam
    preenchidas). O preâmbulo é estreito — um título ocupa uma célula só. O
    cabeçalho é a primeira linha larga o bastante, feita de texto, com
    rótulos distintos, e seguida por mais linhas largas.
    """
    avisos: list[dict[str, Any]] = []
    if df_bruto.empty:
        return 0, avisos

    larguras = df_bruto.notna().sum(axis=1)
    if larguras.max() == 0:
        return 0, avisos

    # Largura típica do bloco de dados: a moda entre as linhas preenchidas.
    larguras_uteis = larguras[larguras > 0]
    largura_dados = int(larguras_uteis.mode().max())
    minimo = max(2, int(largura_dados * _FRACAO_LARGURA_CABECALHO))

    limite = min(len(df_bruto), _MAX_LINHAS_PREAMBULO)
    for indice in range(limite):
        linha = df_bruto.iloc[indice]
        if int(larguras.iloc[indice]) < minimo:
            continue
        if _fracao_texto(linha) < _FRACAO_TEXTO_CABECALHO:
            continue
        rotulos = [str(v).strip() for v in linha.dropna()]
        if len(set(rotulos)) < len(rotulos):
            continue  # cabeçalho tem rótulos distintos
        # Precisa haver dados abaixo, com a mesma largura.
        abaixo = larguras.iloc[indice + 1: indice + 6]
        if abaixo.empty or (abaixo >= minimo).sum() == 0:
            continue

        if indice > 0:
            preambulo = [
                str(v).strip()
                for v in df_bruto.iloc[:indice].to_numpy().ravel()
                if isinstance(v, str) and str(v).strip()
            ]
            avisos.append(_aviso(
                "Cabeçalho fora da primeira linha",
                f"As {indice} primeiras linhas são preâmbulo "
                f"({', '.join(repr(t) for t in preambulo[:3])}) e o cabeçalho real está na "
                f"linha {indice + 1}. Sem esse ajuste, o título viraria nome de coluna e "
                "toda a tipagem sairia errada.",
                "🔴 ALTA",
            ))
        return indice, avisos

    return 0, avisos


def detectar_linha_de_total(df: pd.DataFrame) -> tuple[int, list[dict[str, Any]]]:
    """Identifica linha de totalização no rodapé.

    Duas evidências independentes: um rótulo textual ("TOTAL", "Soma") na
    linha, ou valores numéricos que batem com a soma da coluna acima. Uma
    linha de total não removida contamina média, máximo, outlier e qualquer
    agregação feita depois.
    """
    avisos: list[dict[str, Any]] = []
    if len(df) < 3:
        return 0, avisos

    ultima = df.iloc[-1]
    corpo = df.iloc[:-1]

    tem_rotulo = any(
        str(v).strip().lower() in _ROTULOS_TOTAL
        for v in ultima.dropna()
        if isinstance(v, str)
    )

    colunas_numericas = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    bate_soma = False
    for coluna in colunas_numericas:
        valor = ultima[coluna]
        if pd.isna(valor):
            continue
        soma = float(corpo[coluna].sum())
        if soma == 0:
            continue
        if abs(float(valor) - soma) <= abs(soma) * _TOLERANCIA_TOTAL:
            bate_soma = True
            break

    if not (tem_rotulo or bate_soma):
        return 0, avisos

    motivo = "rótulo de totalização" if tem_rotulo else "valor igual à soma da coluna"
    if tem_rotulo and bate_soma:
        motivo = "rótulo de totalização e valor igual à soma da coluna"
    avisos.append(_aviso(
        "Linha de total no rodapé",
        f"A última linha é uma totalização ({motivo}) e foi retirada da análise. "
        "Mantida, ela entraria como se fosse um registro e distorceria média, máximo "
        "e contagem de outliers.",
        "🔴 ALTA",
    ))
    return 1, avisos


def detectar_celulas_mescladas(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Sinaliza colunas com cara de célula mesclada.

    No Excel, uma mesclagem de A2:A5 guarda o valor só em A2 — o pandas lê o
    resto como nulo. O resultado é uma coluna cheia de nulos que na verdade
    está totalmente preenchida, e um `%  de nulos` que não quer dizer nada.
    """
    avisos: list[dict[str, Any]] = []
    if df.empty:
        return avisos

    for coluna in df.columns:
        serie = df[coluna]
        nulos = serie.isna()
        if not (0.3 <= nulos.mean() < 1.0):
            continue
        if nulos.iloc[0]:
            continue  # mesclagem sempre guarda o valor na primeira célula do bloco
        preenchida = serie.ffill()
        if preenchida.isna().any():
            continue
        if preenchida.nunique(dropna=True) > _MAX_CARDINALIDADE_MESCLA:
            continue
        # O discriminante é a *não repetição* dos valores preenchidos: numa
        # mesclagem cada valor aparece uma única vez (as repetições são os
        # nulos do bloco). Coluna com nulos espalhados ao acaso repete muito
        # os mesmos valores nas posições preenchidas, e cai fora aqui.
        n_preenchidos = int((~nulos).sum())
        if n_preenchidos == 0:
            continue
        distintos_preenchidos = int(serie.dropna().nunique())
        if distintos_preenchidos / n_preenchidos < 0.8:
            continue
        # E os vazios precisam vir em blocos, não isolados.
        if (nulos.sum() / max(n_preenchidos, 1)) < 1.0:
            continue
        avisos.append(_aviso(
            "Possível célula mesclada",
            f"'{coluna}' tem {nulos.mean():.0%} de nulos, mas cada valor é seguido por uma "
            "sequência de vazios — assinatura de célula mesclada no Excel. Preencher para "
            "baixo (`ffill`) antes de qualquer agrupamento.",
        ))
    return avisos


def detectar_blocos_multiplos(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Detecta mais de uma tabela empilhada na mesma aba.

    Linha totalmente vazia com dados acima *e* abaixo é o separador clássico
    de duas tabelas coladas na mesma planilha. As duas viram uma só na
    leitura, e nenhuma estatística faz sentido depois disso.
    """
    if len(df) < 4:
        return []
    vazias = df.isna().all(axis=1).to_numpy()
    if not vazias.any():
        return []

    separadores = 0
    for i in range(1, len(vazias) - 1):
        if vazias[i] and (~vazias[:i]).any() and (~vazias[i + 1:]).any():
            separadores += 1
    if separadores == 0:
        return []
    return [_aviso(
        "Possível segunda tabela na mesma aba",
        f"Há {separadores} linha(s) totalmente vazia(s) no meio dos dados, com conteúdo "
        "antes e depois — padrão de duas tabelas empilhadas na mesma aba. Se for o caso, "
        "separe antes de perfilar: as duas estão sendo lidas como uma só.",
        "🔴 ALTA",
    )]


def remover_colunas_vazias(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Descarta colunas sem nenhum valor e sem nome de verdade.

    São sobra de formatação da planilha, não colunas do dado — e entrariam no
    relatório como "coluna 100% vazia, remover", ocupando espaço de achado
    real.
    """
    descartaveis = [
        coluna for coluna in df.columns
        if df[coluna].isna().all() and str(coluna).startswith("Unnamed:")
    ]
    if not descartaveis:
        return df, []
    return df.drop(columns=descartaveis), [str(c) for c in descartaveis]


def reinferir_numericas(df: pd.DataFrame) -> pd.DataFrame:
    """Reconverte colunas que só eram texto por causa da linha de total.

    `Matricula` fica `object` enquanto existir um "TOTAL" no rodapé; removida
    a linha, a coluna é numérica e precisa voltar a ser tratada como tal —
    senão a estatística e a semântica seguem degradadas pelo mesmo motivo que
    acabamos de corrigir.

    A conversão só acontece quando ida e volta reproduz o texto original, o
    que preserva código com zero à esquerda (`00123` jamais vira `123`).
    """
    for coluna in df.columns:
        serie = df[coluna]
        # No pandas 3.0 uma coluna de texto tem dtype `str`, não `object` —
        # checar só `object` deixaria de fora justamente o caso comum.
        if not (pd.api.types.is_object_dtype(serie) or pd.api.types.is_string_dtype(serie)):
            continue
        limpa = serie.dropna()
        if limpa.empty:
            continue
        convertida = pd.to_numeric(limpa, errors="coerce")
        if convertida.isna().any():
            continue
        original = limpa.astype(str).str.strip()
        if not (convertida.astype(str).str.replace(r"\.0$", "", regex=True)
                == original.str.replace(r"\.0$", "", regex=True)).all():
            continue
        df[coluna] = pd.to_numeric(serie, errors="coerce")
    return df


def analisar_corpo(df: pd.DataFrame) -> tuple[pd.DataFrame, Layout]:
    """Aplica as detecções que dependem do DataFrame já tipado."""
    layout = Layout()
    layout.avisos.extend(detectar_blocos_multiplos(df))

    linhas_rodape, avisos_total = detectar_linha_de_total(df)
    layout.linhas_rodape = linhas_rodape
    layout.avisos.extend(avisos_total)
    if linhas_rodape:
        df = df.iloc[:-linhas_rodape].copy()
        df = reinferir_numericas(df)

    df, removidas = remover_colunas_vazias(df)
    layout.colunas_vazias_removidas = removidas
    if removidas:
        layout.avisos.append(_aviso(
            "Colunas vazias de formatação",
            f"{len(removidas)} coluna(s) sem nome e sem nenhum valor "
            f"({', '.join(removidas[:4])}) foram descartadas — são sobra de formatação "
            "da planilha, não dado.",
            "🟢 BAIXA",
        ))

    layout.avisos.extend(detectar_celulas_mescladas(df))
    return df, layout

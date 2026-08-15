"""Gráficos em SVG inline para o relatório HTML.

SVG escrito à mão, sem biblioteca e sem JavaScript: o relatório precisa
continuar sendo um arquivo único que abre em qualquer máquina, inclusive numa
corporativa com CDN bloqueada. Um `<img>` apontando para CDN quebraria; um
canvas com JS quebraria; SVG inline sempre desenha.

As cores vêm das variáveis CSS do próprio relatório, então os gráficos
acompanham o tema claro/escuro sem duplicar paleta.
"""
from html import escape
from typing import Any

_LARGURA = 460
_ALTURA = 90
_MARGEM_BASE = 16


def _e(valor: Any) -> str:
    return escape(str(valor), quote=True)


def _num_curto(valor: float) -> str:
    """Rótulo de eixo compacto: 1.2M em vez de 1200000."""
    for limite, sufixo in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(valor) >= limite:
            return f"{valor / limite:.1f}{sufixo}".replace(".0", "")
    if abs(valor) >= 10 or valor == int(valor):
        return f"{valor:,.0f}"
    return f"{valor:.2f}"


def _svg(conteudo: str, altura: int = _ALTURA, titulo: str = "") -> str:
    rotulo = f'<title>{_e(titulo)}</title>' if titulo else ""
    return (
        f'<svg class="grafico" viewBox="0 0 {_LARGURA} {altura}" role="img" '
        f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">{rotulo}{conteudo}</svg>'
    )


def histograma(dados: dict[str, Any] | None) -> str:
    """Distribuição de uma coluna numérica.

    A forma da distribuição responde numa olhada o que assimetria e curtose
    respondem em dois números — e mostra bimodalidade, que nenhuma estatística
    resumo revela.
    """
    if not dados or not dados.get("faixas"):
        return ""
    faixas = dados["faixas"]
    maximo = max(f["qtd"] for f in faixas) or 1
    altura_util = _ALTURA - _MARGEM_BASE
    largura_barra = _LARGURA / len(faixas)

    barras = []
    for i, faixa in enumerate(faixas):
        altura = (faixa["qtd"] / maximo) * altura_util
        x = i * largura_barra
        y = altura_util - altura
        barras.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(largura_barra - 1, 0.5):.1f}" '
            f'height="{altura:.1f}" fill="var(--acento)" opacity="0.75">'
            f'<title>{_num_curto(faixa["de"])} a {_num_curto(faixa["ate"])}: '
            f'{faixa["qtd"]:,} registros</title></rect>'
        )

    eixo = (
        f'<line x1="0" y1="{altura_util}" x2="{_LARGURA}" y2="{altura_util}" '
        f'stroke="var(--borda)" stroke-width="1"/>'
        f'<text x="0" y="{_ALTURA - 3}" font-size="10" fill="var(--texto-fraco)">'
        f'{_e(_num_curto(dados["min"]))}</text>'
        f'<text x="{_LARGURA}" y="{_ALTURA - 3}" font-size="10" fill="var(--texto-fraco)" '
        f'text-anchor="end">{_e(_num_curto(dados["max"]))}</text>'
    )
    return _svg("".join(barras) + eixo, titulo="Distribuição dos valores")


def barras_categoricas(distribuicao: list[dict[str, Any]] | None) -> str:
    """Frequência dos valores mais comuns.

    Mostra concentração: uma barra ocupando tudo diz que a coluna é
    praticamente constante, coisa que a contagem de distintos não revela.
    """
    if not distribuicao:
        return ""
    itens = distribuicao[:5]
    altura_linha = 20
    altura = altura_linha * len(itens) + 4
    largura_rotulo = 130
    largura_util = _LARGURA - largura_rotulo - 46
    maximo = max(i["frequencia_relativa"] for i in itens) or 1

    linhas = []
    for i, item in enumerate(itens):
        y = i * altura_linha
        largura = (item["frequencia_relativa"] / maximo) * largura_util
        rotulo = str(item["valor"])
        if len(rotulo) > 20:
            rotulo = rotulo[:19] + "…"
        linhas.append(
            f'<text x="0" y="{y + 14}" font-size="11" fill="var(--texto-fraco)">'
            f'{_e(rotulo)}</text>'
            f'<rect x="{largura_rotulo}" y="{y + 4}" width="{max(largura, 1):.1f}" height="12" '
            f'rx="2" fill="var(--acento)" opacity="0.75"><title>{_e(item["valor"])}: '
            f'{item["frequencia_pct"]}</title></rect>'
            f'<text x="{largura_rotulo + largura + 6:.1f}" y="{y + 14}" font-size="10" '
            f'fill="var(--texto-fraco)">{_e(item["frequencia_pct"])}</text>'
        )
    return _svg("".join(linhas), altura=altura, titulo="Valores mais frequentes")


def linha_temporal(serie: list[dict[str, Any]] | None) -> str:
    """Volume de registros por mês.

    Buraco no meio da linha é falha de carga; degrau é mudança de sistema.
    Nenhum dos dois aparece em min/max de data.
    """
    if not serie or len(serie) < 2:
        return ""
    valores = [p["qtd"] for p in serie]
    maximo = max(valores) or 1
    altura_util = _ALTURA - _MARGEM_BASE
    passo = _LARGURA / max(len(valores) - 1, 1)

    pontos = " ".join(
        f"{i * passo:.1f},{altura_util - (v / maximo) * altura_util:.1f}"
        for i, v in enumerate(valores)
    )
    area = f"0,{altura_util} {pontos} {_LARGURA},{altura_util}"

    marcadores = "".join(
        f'<circle cx="{i * passo:.1f}" cy="{altura_util - (v / maximo) * altura_util:.1f}" '
        f'r="2" fill="var(--acento)"><title>{_e(serie[i]["mes"])}: {v:,}</title></circle>'
        for i, v in enumerate(valores)
        if len(valores) <= 40
    )
    return _svg(
        f'<polygon points="{area}" fill="var(--acento)" opacity="0.15"/>'
        f'<polyline points="{pontos}" fill="none" stroke="var(--acento)" stroke-width="1.5"/>'
        f"{marcadores}"
        f'<text x="0" y="{_ALTURA - 3}" font-size="10" fill="var(--texto-fraco)">'
        f'{_e(serie[0]["mes"])}</text>'
        f'<text x="{_LARGURA}" y="{_ALTURA - 3}" font-size="10" fill="var(--texto-fraco)" '
        f'text-anchor="end">{_e(serie[-1]["mes"])}</text>',
        titulo="Registros por mês",
    )


def barra_completude(pct_nulos: float, pct_sentinelas: float = 0.0) -> str:
    """Faixa de preenchimento: válido, nulo disfarçado e nulo real.

    Separar sentinela de nulo real na mesma barra é o ponto: uma coluna com
    0% de nulos e 30% de "N/A" parece completa em qualquer contagem.
    """
    altura = 14
    nulo = max(0.0, min(1.0, pct_nulos / 100))
    sentinela = max(0.0, min(1.0 - nulo, pct_sentinelas))
    valido = max(0.0, 1.0 - nulo - sentinela)

    segmentos = []
    x = 0.0
    for fracao, cor, rotulo in (
        (valido, "var(--baixa)", "preenchido"),
        (sentinela, "var(--media)", "nulo disfarçado"),
        (nulo, "var(--alta)", "nulo"),
    ):
        if fracao <= 0:
            continue
        largura = fracao * _LARGURA
        segmentos.append(
            f'<rect x="{x:.1f}" y="0" width="{largura:.1f}" height="{altura}" fill="{cor}" '
            f'opacity="0.8"><title>{fracao:.1%} {rotulo}</title></rect>'
        )
        x += largura
    return _svg("".join(segmentos), altura=altura, titulo="Completude da coluna")


def graficos_da_coluna(coluna: dict[str, Any]) -> str:
    """Escolhe o gráfico adequado ao tipo da coluna.

    Coluna sensível não ganha histograma: a distribuição de uma coluna de CPF
    não tem significado analítico e ainda revela a faixa dos documentos.
    """
    extras = coluna.get("Stats_Extra") or {}
    if coluna.get("Dado_Sensivel_LGPD", "Nenhum") != "Nenhum":
        return ""

    partes = []
    if extras.get("histograma"):
        partes.append(histograma(extras["histograma"]))
    elif extras.get("serie_mensal"):
        partes.append(linha_temporal(extras["serie_mensal"]))
    elif extras.get("distribuicao_top5"):
        partes.append(barras_categoricas(extras["distribuicao_top5"]))

    return "".join(p for p in partes if p)


CSS_GRAFICOS = """
.grafico { width: 100%; height: auto; display: block; margin: .5rem 0 .25rem; }
.grafico rect, .grafico circle, .grafico polyline, .grafico polygon { transition: opacity .15s; }
.coluna:hover .grafico rect { opacity: 0.95; }
.legenda-completude { display: flex; gap: 1rem; font-size: .72rem;
                      color: var(--texto-fraco); margin-top: .2rem; }
.legenda-completude span::before { content: "■ "; }
.leg-ok::before { color: var(--baixa); } .leg-sent::before { color: var(--media); }
.leg-nulo::before { color: var(--alta); }
"""

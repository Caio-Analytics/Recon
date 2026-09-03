"""Contratos estáticos das estruturas que cruzam os módulos do Recon.

O resultado continua sendo um dicionário serializável em JSON. Estes tipos
existem para o mypy apontar nomes de campos errados antes da execução.
"""
from typing import Any, NotRequired, TypedDict


class Aviso(TypedDict):
    tipo: str
    severidade: str
    mensagem: str


class LayoutPayload(TypedDict):
    linha_cabecalho: int
    linhas_rodape_removidas: int
    colunas_vazias_removidas: list[str]
    separador: str | None
    encoding: str | None
    avisos: list[Aviso]


class IncertezaAmostra(TypedDict):
    cobertura_pct: float
    limiar_evento_raro_pct: float | None
    mensagem: str


class PenalidadeScore(TypedDict):
    dimensao: str
    intensidade: float
    pontos_perdidos: float


class ColunaCritica(TypedDict):
    coluna: str
    dano: float
    motivos: list[str]


class ComponenteMetodologiaScore(TypedDict):
    nome: str
    peso_pct: float
    pontos_perdidos: float


class MetodologiaScore(TypedDict):
    versao: str
    descricao: str
    componentes: list[ComponenteMetodologiaScore]


class ScoreQualidade(TypedDict):
    score: float
    nota: str
    metodologia: MetodologiaScore
    colunas_comprometidas: int
    colunas_criticas: list[ColunaCritica]
    penalidades: list[PenalidadeScore]


class MetadadosExecucao(TypedDict):
    tabela: str
    timestamp_utc: str
    versao_profiler: str
    schema_version: str
    linhas_originais: int
    linhas_originais_desconhecidas: bool
    linhas_analisadas: int
    amostragem_aplicada: bool
    motivo_amostragem: str | None
    incerteza_amostra: IncertezaAmostra
    total_colunas: int
    layout: LayoutPayload
    score_qualidade: ScoreQualidade
    risco_lgpd: dict[str, Any]
    duplicatas: dict[str, Any]
    resumo_qualidade: dict[str, Any]
    abas_ignoradas: NotRequired[list[str]]


class PayloadPerfil(TypedDict):
    metadados_execucao: MetadadosExecucao
    colunas: list[dict[str, Any]]
    recomendacoes_etl: list[dict[str, Any]]
    dependencias_funcionais: list[dict[str, Any]]
    colunas_redundantes: list[dict[str, Any]]
    duplicatas_aproximadas: list[dict[str, Any]]
    chaves_compostas: list[dict[str, Any]]
    correlacoes: list[dict[str, Any]]
    hierarquias: list[dict[str, Any]]
    explicacoes_de_medidas: list[dict[str, Any]]
    regras_negocio: list[dict[str, Any]]
    gap_analysis_kpis: list[dict[str, Any]]
    analise_temporal_series: list[dict[str, Any]]
    insights_textuais: list[str]

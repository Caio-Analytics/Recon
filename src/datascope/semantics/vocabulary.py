"""Vocabulários da inferência semântica: abreviaturas e gazetteers de valor.

Só dado, sem lógica. Duas famílias:

- **Abreviaturas** — sistemas corporativos brasileiros abreviam de forma
  sistemática (`cd_dpto_lot`, `nr_seq_mvto`, `vl_tot_liq`). Um dicionário
  curado resolve o caso frequente; o resto cai na reconstrução por
  subsequência (ver `tokens.expandir_abreviatura`).
- **Gazetteers** — conjuntos fechados de valores que identificam a coluna pelo
  *conteúdo*, independentemente de como ela foi batizada. Uma coluna chamada
  `f27` cujos valores são as 27 siglas de UF é uma coluna de localização, e
  nenhuma análise do nome chegaria lá.
"""
from typing import Any

from .. import config

# ── Abreviaturas ────────────────────────────────────────────────────────────
# token abreviado -> lista de expansões possíveis, da mais provável para a
# menos. Múltiplas expansões são o caso interessante: `dep` sozinho é
# ambíguo e só o contexto da tabela desempata.
ABREVIATURAS: dict[str, list[str]] = {
    # papel / estrutura do nome
    "cd": ["codigo"], "cod": ["codigo"], "cdg": ["codigo"],
    "dt": ["data"], "dta": ["data"], "hr": ["hora"],
    "vl": ["valor"], "vlr": ["valor"], "val": ["valor"],
    "qt": ["quantidade"], "qtd": ["quantidade"], "qtde": ["quantidade"],
    "nr": ["numero"], "num": ["numero"], "nro": ["numero"],
    "nm": ["nome"], "ds": ["descricao"], "dsc": ["descricao"], "desc": ["descricao"],
    "tp": ["tipo"], "fl": ["flag"], "flg": ["flag"], "sg": ["sigla"],
    "pc": ["percentual"], "perc": ["percentual"], "pct": ["percentual"],
    "id": ["identificador"], "seq": ["sequencial"], "st": ["status"],
    "ind": ["indicador"], "mt": ["matricula"], "mat": ["matricula"],
    # entidades de RH e estrutura organizacional
    "dep": ["departamento", "dependente", "deposito"],
    "dpto": ["departamento"], "depto": ["departamento"], "dept": ["departamento"],
    "lot": ["lotacao"], "lotac": ["lotacao"],
    "func": ["funcionario"], "fnc": ["funcionario"], "colab": ["colaborador"],
    "emp": ["empresa", "empregado"], "empr": ["empresa"],
    "cargo": ["cargo"], "cgo": ["cargo"], "fun": ["funcao"],
    "adm": ["admissao"], "dem": ["demissao"], "nasc": ["nascimento"],
    "sal": ["salario"], "rem": ["remuneracao"], "benef": ["beneficio"],
    "ferias": ["ferias"], "afast": ["afastamento"], "desl": ["desligamento"],
    "sit": ["situacao"], "escol": ["escolaridade"], "esc": ["escolaridade"],
    # negócio e localização
    "mvto": ["movimento"], "mov": ["movimento"], "movto": ["movimento"],
    "cli": ["cliente"], "clnt": ["cliente"], "forn": ["fornecedor"],
    "prod": ["produto"], "prd": ["produto"], "ped": ["pedido"],
    "nf": ["nota"], "ctr": ["contrato"], "ctt": ["contato"],
    "mun": ["municipio"], "cid": ["cidade"], "est": ["estado"],
    "ender": ["endereco"], "end": ["endereco"], "bai": ["bairro"],
    "reg": ["regiao"], "fil": ["filial"], "uni": ["unidade"],
    # temporais e agregações
    "ini": ["inicio"], "fim": ["fim"], "venc": ["vencimento"],
    "ref": ["referencia"], "comp": ["competencia"], "vig": ["vigencia"],
    "cad": ["cadastro"], "hist": ["historico"], "obs": ["observacao"],
    "resp": ["responsavel"], "tot": ["total"], "liq": ["liquido"],
    "brt": ["bruto"], "med": ["media"], "acum": ["acumulado"],
    "curs": ["curso"], "trein": ["treinamento"], "cap": ["capacitacao"],
    "aval": ["avaliacao"], "res": ["resultado"], "nota": ["nota"],
}

# ── Gazetteers ──────────────────────────────────────────────────────────────
# Cada entrada declara um conjunto fechado de valores. A coluna é atribuída à
# categoria quando a fração dos seus valores distintos contida no conjunto
# supera `cobertura_minima`.

_UFS = {
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms",
    "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc",
    "sp", "se", "to",
}

_CAPITAIS = {
    "rio branco", "maceio", "macapa", "manaus", "salvador", "fortaleza",
    "brasilia", "vitoria", "goiania", "sao luis", "cuiaba", "campo grande",
    "belo horizonte", "belem", "joao pessoa", "curitiba", "recife", "teresina",
    "rio de janeiro", "natal", "porto alegre", "porto velho", "boa vista",
    "florianopolis", "sao paulo", "aracaju", "palmas",
}

_REGIOES = {"norte", "nordeste", "centro-oeste", "centro oeste", "sudeste", "sul"}

_SEXO = {
    "m", "f", "masculino", "feminino", "homem", "mulher", "male", "female",
    "outro", "nao binario", "prefiro nao informar",
}

_BOOLEANOS = {
    "s", "n", "sim", "nao", "true", "false", "verdadeiro", "falso",
    "v", "f", "y", "yes", "no", "0", "1", "t",
}

_STATUS_ATIVIDADE = {
    "ativo", "inativo", "ativa", "inativa", "habilitado", "desabilitado",
    "bloqueado", "desbloqueado", "cancelado", "suspenso", "pendente",
    "aprovado", "reprovado", "em analise", "concluido", "aberto", "fechado",
}

_ESTADO_CIVIL = {
    "solteiro", "solteira", "casado", "casada", "divorciado", "divorciada",
    "viuvo", "viuva", "separado", "separada", "uniao estavel", "amasiado",
}

_ESCOLARIDADE = {
    "fundamental", "fundamental incompleto", "fundamental completo",
    "medio", "medio incompleto", "medio completo", "ensino medio",
    "superior", "superior incompleto", "superior completo", "graduacao",
    "pos-graduacao", "pos graduacao", "especializacao", "mba",
    "mestrado", "doutorado", "pos-doutorado", "analfabeto",
}

_MESES = {
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
    "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out",
    "nov", "dez", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}

_DIAS_SEMANA = {
    "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo",
    "segunda-feira", "terca-feira", "quarta-feira", "quinta-feira", "sexta-feira",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}

_MOEDAS = {"brl", "usd", "eur", "gbp", "ars", "clp", "jpy", "chf", "cad", "r$", "us$"}

_TURNOS = {"manha", "tarde", "noite", "madrugada", "integral", "comercial", "diurno", "noturno"}

_RACA_COR = {"branca", "preta", "parda", "amarela", "indigena", "nao declarada", "nao informada"}

_PORTE_CONTRATO = {
    "clt", "pj", "estagio", "estagiario", "aprendiz", "temporario", "terceirizado",
    "autonomo", "cooperado", "efetivo", "trainee", "socio", "diretor estatutario",
}

# `eixo` diz se o gazetteer identifica o papel da coluna ou o domínio dela.
GAZETTEERS: list[dict[str, Any]] = [
    {"nome": "UF brasileira", "valores": _UFS, "categoria": "Localização Geográfica",
     "eixo": "dominio", "cobertura_minima": 0.85, "peso": 0.95, "max_distintos": 30},
    {"nome": "capital brasileira", "valores": _CAPITAIS, "categoria": "Localização Geográfica",
     "eixo": "dominio", "cobertura_minima": 0.7, "peso": 0.9, "max_distintos": 40},
    {"nome": "região do Brasil", "valores": _REGIOES, "categoria": "Localização Geográfica",
     "eixo": "dominio", "cobertura_minima": 0.9, "peso": 0.9, "max_distintos": 8},
    {"nome": "sexo/gênero", "valores": _SEXO, "categoria": "Perfil do Colaborador",
     "eixo": "dominio", "cobertura_minima": 0.9, "peso": 0.85, "max_distintos": 8},
    {"nome": "raça/cor (IBGE)", "valores": _RACA_COR, "categoria": "Perfil do Colaborador",
     "eixo": "dominio", "cobertura_minima": 0.8, "peso": 0.9, "max_distintos": 10},
    {"nome": "estado civil", "valores": _ESTADO_CIVIL, "categoria": "Perfil do Colaborador",
     "eixo": "dominio", "cobertura_minima": 0.8, "peso": 0.9, "max_distintos": 15},
    {"nome": "escolaridade", "valores": _ESCOLARIDADE, "categoria": "Perfil do Colaborador",
     "eixo": "dominio", "cobertura_minima": 0.7, "peso": 0.9, "max_distintos": 25},
    {"nome": "vínculo/contrato", "valores": _PORTE_CONTRATO, "categoria": "Cargo / Função",
     "eixo": "dominio", "cobertura_minima": 0.8, "peso": 0.85, "max_distintos": 20},
    {"nome": "booleano textual", "valores": _BOOLEANOS,
     "categoria": "Status / Indicador / Flag", "eixo": "papel",
     "cobertura_minima": 1.0, "peso": 0.8, "max_distintos": 4},
    {"nome": "status de atividade", "valores": _STATUS_ATIVIDADE,
     "categoria": "Status / Indicador / Flag", "eixo": "papel",
     "cobertura_minima": 0.8, "peso": 0.85, "max_distintos": 15},
    {"nome": "mês", "valores": _MESES, "categoria": config.SEMANTICA_DATA_CALENDARIO,
     "eixo": "papel", "cobertura_minima": 0.9, "peso": 0.85, "max_distintos": 14},
    {"nome": "dia da semana", "valores": _DIAS_SEMANA,
     "categoria": config.SEMANTICA_DATA_CALENDARIO, "eixo": "papel",
     "cobertura_minima": 0.9, "peso": 0.85, "max_distintos": 10},
    {"nome": "moeda ISO", "valores": _MOEDAS, "categoria": "Valor Financeiro",
     "eixo": "papel", "cobertura_minima": 0.9, "peso": 0.8, "max_distintos": 12},
    {"nome": "turno", "valores": _TURNOS, "categoria": "Cargo / Função",
     "eixo": "dominio", "cobertura_minima": 0.9, "peso": 0.75, "max_distintos": 10},
]


import numpy as np
import pandas as pd
import pytest


def _digitos_verificadores_cpf(base: str) -> str:
    """Calcula os dois DVs de um CPF a partir dos 9 primeiros dígitos."""
    digitos = base
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        digitos += "0" if resto == 10 else str(resto)
    return digitos


def gerar_cpfs(n: int, inicio: int = 111444777) -> list[str]:
    """CPFs sintéticos válidos, formatados. Depois da correção que exige
    dígito verificador, um número qualquer de 11 dígitos não é mais aceito
    como CPF — os testes precisam de documentos que realmente validem."""
    cpfs = []
    valor = inicio
    while len(cpfs) < n:
        base = f"{valor:09d}"
        if len(set(base)) > 1:
            d = _digitos_verificadores_cpf(base)
            cpfs.append(f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}")
        valor += 1
    return cpfs


def gerar_cnpjs(n: int, inicio: int = 111444770001) -> list[str]:
    """CNPJs sintéticos válidos, formatados."""
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6] + pesos_1
    cnpjs = []
    valor = inicio
    while len(cnpjs) < n:
        d = f"{valor:012d}"
        if len(set(d)) > 1:
            for pesos in (pesos_1, pesos_2):
                soma = sum(int(d[i]) * p for i, p in enumerate(pesos))
                resto = soma % 11
                d += "0" if resto < 2 else str(11 - resto)
            cnpjs.append(f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}")
        valor += 1
    return cnpjs


@pytest.fixture
def cpfs_validos() -> list[str]:
    return gerar_cpfs(30)


@pytest.fixture
def df_rh_exemplo() -> pd.DataFrame:
    return pd.DataFrame({
        "id_funcionario": range(1000, 1050),
        "nome_completo": [f"Colaborador_{i}" for i in range(50)],
        "salario_bruto": [3500.50 if i % 3 != 0 else np.nan for i in range(50)],
        "dt_admissao": pd.to_datetime(
            ["2020-01-15", "2021-03-10", "2022-06-20", "2023-09-01"] * 12 + ["2024-01-01"] * 2
        ),
        "cpf_colaborador": gerar_cpfs(1) * 48 + [None, None],
        "email_corporativo": [f"user{i}@empresa.com" for i in range(50)],
        "cod_departamento": (["DEP01"] * 20 + ["DEP02"] * 15 + ["DEP03"] * 15),
        "nome_departamento": (["Operações"] * 20 + ["TI"] * 15 + ["RH"] * 15),
        "status_ativo": (["Ativo"] * 47 + ["Inativo"] * 2 + [None]),
        "score_desempenho": [float(i % 10) for i in range(50)],
        "campo_lixo_vazio": [None] * 50,
    })

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def df_rh_exemplo() -> pd.DataFrame:
    return pd.DataFrame({
        "id_funcionario": range(1000, 1050),
        "nome_completo": [f"Colaborador_{i}" for i in range(50)],
        "salario_bruto": [3500.50 if i % 3 != 0 else np.nan for i in range(50)],
        "dt_admissao": pd.to_datetime(
            ["2020-01-15", "2021-03-10", "2022-06-20", "2023-09-01"] * 12 + ["2024-01-01"] * 2
        ),
        "cpf_colaborador": ["123.456.789-00"] * 48 + [None, None],
        "email_corporativo": [f"user{i}@empresa.com" for i in range(50)],
        "cod_departamento": (["DEP01"] * 20 + ["DEP02"] * 15 + ["DEP03"] * 15),
        "nome_departamento": (["Operações"] * 20 + ["TI"] * 15 + ["RH"] * 15),
        "status_ativo": (["Ativo"] * 47 + ["Inativo"] * 2 + [None]),
        "score_desempenho": [float(i % 10) for i in range(50)],
        "campo_lixo_vazio": [None] * 50,
    })

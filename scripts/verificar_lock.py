"""Confere se o requirements-dev.lock respeita as versões declaradas no pyproject.toml.

O Dependabot atualiza o pyproject.toml, mas a CI instala pelo lock. Sem esta
verificação, uma atualização pode passar na CI sem ter sido testada.

Uso: python scripts/verificar_lock.py
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

RAIZ = Path(__file__).resolve().parent.parent


def _ler_lock(caminho: Path) -> dict[str, str]:
    pinos: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        correspondencia = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s#;]+)", linha)
        if correspondencia:
            pinos[canonicalize_name(correspondencia.group(1))] = correspondencia.group(2)
    return pinos


def main() -> int:
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declaradas = list(projeto.get("dependencies", []))
    for grupo in ("gui", "dev"):
        declaradas += projeto.get("optional-dependencies", {}).get(grupo, [])

    pinos = _ler_lock(RAIZ / "requirements-dev.lock")
    problemas: list[str] = []
    for texto in declaradas:
        requisito = Requirement(texto)
        nome = canonicalize_name(requisito.name)
        if nome not in pinos:
            # PySide6 fica fora do lock de propósito (extra "gui").
            if nome != "pyside6":
                problemas.append(f"{requisito.name}: declarado no pyproject, ausente no lock")
            continue
        if not requisito.specifier.contains(pinos[nome], prereleases=True):
            problemas.append(
                f"{requisito.name}: pyproject pede '{requisito.specifier}', "
                f"o lock fixa {pinos[nome]}"
            )

    if problemas:
        print("O requirements-dev.lock está fora de sincronia com o pyproject.toml:")
        for problema in problemas:
            print(f"  - {problema}")
        print("\nRegenere com: pip-compile --extra=dev --output-file=requirements-dev.lock "
              "--strip-extras pyproject.toml")
        return 1
    print("requirements-dev.lock está em sincronia com o pyproject.toml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

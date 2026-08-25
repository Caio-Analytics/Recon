"""Dois cliques aqui abrem o Recon — sem terminal, sem digitar nada.

A extensão `.pyw` faz o Windows rodar o arquivo pelo `pythonw.exe`, que não
abre janela preta de terminal. Para quem não programa, é a diferença entre
"é um programa" e "é uma coisa de programador".

Se der erro dizendo que o Recon não está instalado, abra o terminal na pasta
do projeto uma única vez e rode:  pip install --user -e .
"""
import sys
from pathlib import Path

# Rodando direto do repositório clonado, sem `pip install`: o pacote está em
# `src/`, que não entra no sys.path sozinho.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from recon.gui import main
except ImportError as erro:  # dependência faltando (pandas, scipy, ...)
    import tkinter.messagebox as caixa
    from tkinter import Tk

    raiz = Tk()
    raiz.withdraw()
    caixa.showerror(
        "Recon",
        "O Recon ainda não está instalado neste computador.\n\n"
        "Abra o terminal na pasta do projeto e rode uma vez:\n\n"
        "    pip install --user -e .\n\n"
        f"Detalhe técnico: {erro}",
    )
    raise SystemExit(1) from None

main()

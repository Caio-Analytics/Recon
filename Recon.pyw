import sys
from pathlib import Path



_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from recon.gui import main
except ImportError as erro:  
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

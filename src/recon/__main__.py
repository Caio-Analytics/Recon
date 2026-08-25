"""Permite `python -m recon`, sem depender do script `recon` estar no PATH.

Numa instalação `--user` (máquina corporativa sem admin), o script vai para a
pasta de scripts do usuário — que nem sempre está no PATH, e a pessoa não tem
como editar variável de ambiente sem ajuda de TI. O Python em si sempre está
no PATH, porque é isso que o instalador oficial garante. `python -m recon`
funciona em qualquer instalação, PATH configurado ou não — o mesmo motivo
pelo qual `python -m pip` é a forma robusta de chamar o pip.
"""
from .cli import app

if __name__ == "__main__":
    app()

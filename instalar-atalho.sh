#!/usr/bin/env bash
# Cria o atalho do Recon no menu de aplicativos (Linux) ou um arquivo
# clicável no Finder (macOS).
#
# No Windows nada disso é necessário: dois cliques no Recon.pyw já abrem a
# janela. No Linux, o gerenciador de arquivos não executa .pyw — quem abre
# programa é um lançador .desktop, que é o que este script escreve.
#
# Uso:   ./instalar-atalho.sh
#        ./instalar-atalho.sh --remover
set -euo pipefail

PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO_LINUX="$HOME/.local/share/applications/recon.desktop"
DESTINO_MAC="$PROJETO/Recon.command"

remover() {
    rm -f "$DESTINO_LINUX" "$DESTINO_MAC"
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    echo "Atalho removido."
    exit 0
}

[[ "${1:-}" == "--remover" ]] && remover

# Qual Python roda o Recon? A venv do projeto tem precedência: é a que o
# desenvolvedor usa. Quem instalou com `pip install --user` cai no python3 do
# sistema, e `python3 -m recon.cli` funciona mesmo sem o `recon` no PATH.
if [[ -x "$PROJETO/.venv/bin/recon" ]]; then
    COMANDO="$PROJETO/.venv/bin/recon janela"
elif command -v recon >/dev/null 2>&1; then
    COMANDO="$(command -v recon) janela"
elif python3 -c "import recon" 2>/dev/null; then
    COMANDO="$(command -v python3) -m recon.cli janela"
else
    echo "O Recon não está instalado neste Python." >&2
    echo "Rode primeiro, dentro de $PROJETO:" >&2
    echo "    pip install --user -e ." >&2
    exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
    cat > "$DESTINO_MAC" <<EOF
#!/usr/bin/env bash
# Dois cliques neste arquivo, no Finder, abrem a janela do Recon.
exec $COMANDO
EOF
    chmod +x "$DESTINO_MAC"
    echo "Pronto. Dois cliques em: $DESTINO_MAC"
    echo "(Se o Finder abrir no editor, botão direito -> Abrir com -> Terminal.)"
    exit 0
fi

mkdir -p "$(dirname "$DESTINO_LINUX")"
cat > "$DESTINO_LINUX" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Recon
GenericName=Perfilador de dados
Comment=Descubra o que tem nos seus arquivos antes de começar a analisar
Exec=$COMANDO
Icon=$PROJETO/assets/recon.svg
Path=$HOME
Terminal=false
Categories=Office;DataVisualization;
Keywords=dados;csv;excel;planilha;análise;perfil;
StartupNotify=true
EOF
chmod +x "$DESTINO_LINUX"

command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Pronto. O Recon está no menu de aplicativos."
echo
echo "  - Aperte a tecla Super e digite 'Recon'."
echo "  - Botão direito no ícone -> 'Adicionar aos favoritos' fixa na barra lateral."
echo
echo "Comando usado pelo atalho: $COMANDO"

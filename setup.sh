#!/usr/bin/env bash
# re-env setup. Phases: pacman (sudo) | system (sudo) | user (no root).
set -Eeuo pipefail
trap 'echo "setup.sh: failed in phase ${PHASE:-?}" >&2' ERR
# shellcheck source=lib/common.sh
source "$(dirname "$(realpath "$0")")/lib/common.sh"
source "$RE_ENV/lib/fetch.sh"
source "$RE_ENV/lib/render.sh"

PACKAGES=(
    ollama ollama-cuda
    ghidra jdk21-openjdk rizin rz-ghidra cutter radare2 binwalk scanmem protontricks
    dotnet-sdk mingw-w64-gcc cmake ninja rustup uv flatpak unzip
)

usage() {
    cat <<USAGE
usage: setup.sh [pacman|system|user|user:<step>]

  pacman   install packages from the Arch repos (sudo)
  system   ollama drop-in, ptrace sysctl, enable the ollama service (sudo)
  user     downloads, tools, the ~/re workspace, models (no root)

With no argument all three phases run in order.
Single steps of the user phase: user:dirs user:tools user:downloads user:workspace user:models
USAGE
}

phase_pacman() {
    PHASE=pacman
    echo "Note: ollama-cuda pulls in the cuda package (5.2 GB)."
    sudo pacman -S --needed --noconfirm "${PACKAGES[@]}"
}

phase_system() {
    PHASE=system
    sudo install -Dm644 "$RE_ENV/system/ollama-re-env.conf" /etc/systemd/system/ollama.service.d/re-env.conf
    sudo install -Dm644 "$RE_ENV/system/10-ptrace.conf" /etc/sysctl.d/10-ptrace.conf
    sudo sysctl --system
    sudo systemctl daemon-reload
    sudo systemctl enable --now ollama
    sudo systemctl restart ollama      # pick up the drop-in on a rerun as well
}

user_dirs() {
    mkdir -p "$RE_HOME"/{tools,targets} "$RE_ENV/downloads"
}

user_tools() {
    if ! command -v claude >/dev/null 2>&1; then
        echo "Installing the Claude Code CLI into $LOCAL_BIN"
        local installer; installer="$(mktemp)"
        curl -fsSL -o "$installer" https://claude.ai/install.sh && bash "$installer"
        rm -f "$installer"
    fi
    uv tool install frida-tools || uv tool upgrade frida-tools
    dotnet tool update -g ilspycmd
    mkdir -p "$LOCAL_BIN"
    ln -sfn "$HOME/.dotnet/tools/ilspycmd" "$LOCAL_BIN/ilspycmd"
    rustup show active-toolchain >/dev/null 2>&1 || rustup default stable
    rustup target add x86_64-pc-windows-gnu
    # user install: a system install would stop for a polkit password
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install --user -y --noninteractive flathub net.werwolv.ImHex
}

user_downloads() {
    # shellcheck source=versions.env
    source "$RE_ENV/versions.env"
    local dl="$RE_ENV/downloads"
    fetch_verified "$GHYDRA_ZIP_URL" "$GHYDRA_ZIP_SHA256" "$dl/$(basename "$GHYDRA_ZIP_URL")"
    fetch_verified "$GHYDRA_BRIDGE_URL" "$GHYDRA_BRIDGE_SHA256" "$dl/$(basename "$GHYDRA_BRIDGE_URL")"
    fetch_verified "$X64DBG_URL" "$X64DBG_SHA256" "$dl/$(basename "$X64DBG_URL")"
    fetch_verified "$IL2CPPDUMPER_URL" "$IL2CPPDUMPER_SHA256" "$dl/$(basename "$IL2CPPDUMPER_URL")"
    fetch_verified "$BEPINEX_URL" "$BEPINEX_SHA256" "$dl/$(basename "$BEPINEX_URL")"

    extract_zip "$dl/$(basename "$X64DBG_URL")" "$RE_HOME/tools/x64dbg"
    extract_zip "$dl/$(basename "$IL2CPPDUMPER_URL")" "$RE_HOME/tools/il2cppdumper"
    extract_zip "$dl/$(basename "$BEPINEX_URL")" "$RE_HOME/tools/bepinex"
    extract_zip "$dl/$(basename "$GHYDRA_ZIP_URL")" "$(ghidra_user_dir)/Extensions"
    mkdir -p "$RE_HOME/tools/ghydra"
    cp "$dl/$(basename "$GHYDRA_BRIDGE_URL")" "$RE_HOME/tools/ghydra/bridge_mcp_hydra.py"
    echo "Ghydra is in $(ghidra_user_dir)/Extensions. Enable it once in Ghidra: File > Configure > Developer."
}

user_workspace() {
    mkdir -p "$RE_HOME" "$LOCAL_BIN"
    render_template "$RE_ENV/mcp/mcp.json.tmpl" "$RE_HOME/.mcp.json"
    ln -sfn "$RE_ENV/claude/CLAUDE.md" "$RE_HOME/CLAUDE.md"
    local f
    for f in "$RE_ENV"/bin/*; do
        ln -sfn "$f" "$LOCAL_BIN/$(basename "$f")"
    done
}

user_models() {
    echo "Pulling three models, about 23 GB."
    ollama pull qwen2.5-coder:14b
    ollama pull deepseek-coder-v2:16b
    ollama pull llama3.1:8b
}

phase_user() {
    PHASE=user
    user_dirs
    user_tools
    user_downloads
    user_workspace
    user_models
}

case "${1:-all}" in
    pacman) phase_pacman ;;
    system) phase_system ;;
    user) phase_user ;;
    user:dirs|user:tools|user:downloads|user:workspace|user:models) PHASE="$1"; "user_${1#user:}" ;;
    user:*) usage >&2; usage_die "unknown step: $1" ;;
    all) phase_pacman; phase_system; phase_user ;;
    -h|--help) usage ;;
    *) usage >&2; usage_die "unknown phase: $1" ;;
esac

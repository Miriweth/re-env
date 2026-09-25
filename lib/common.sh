# Shared definitions for setup.sh and bin/*. Source, do not execute.
# shellcheck shell=bash

RE_ENV="${RE_ENV:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RE_HOME="${RE_HOME:-$HOME/re}"
LOCAL_BIN="${LOCAL_BIN:-$HOME/.local/bin}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
DEFAULT_MODEL="qwen2.5-coder:14b"
export RE_ENV RE_HOME LOCAL_BIN OLLAMA_URL DEFAULT_MODEL

die() { printf 'error: %s\n' "$*" >&2; exit "${DIE_CODE:-1}"; }
usage_die() { DIE_CODE=2 die "$@"; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 not found"; }

# Map short names to Ollama tags; anything else passes through unchanged.
resolve_model() {
    case "$1" in
        qwen) echo "qwen2.5-coder:14b" ;;
        deepseek) echo "deepseek-coder-v2:16b" ;;
        llama) echo "llama3.1:8b" ;;
        *) echo "$1" ;;
    esac
}

ollama_reachable() { curl -sf -m 2 "$OLLAMA_URL/api/version" >/dev/null 2>&1; }

ghidra_version() {
    sed -n 's/^application\.version=//p' "${GHIDRA_ROOT:-/opt/ghidra}/Ghidra/application.properties"
}

ghidra_user_dir() {
    echo "${GHIDRA_USER_DIR:-$HOME/.config/ghidra/ghidra_$(ghidra_version)_PUBLIC}"
}

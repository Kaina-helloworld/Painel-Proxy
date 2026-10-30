#!/usr/bin/env bash
# proxy_panel.sh — shell wrapper
# Usage: source proxy_panel.sh [command]
# Or:    ./proxy_panel.sh --on | --off | --country US | --status | --export

PANEL_DIR="$HOME/.proxy_panel"
PANEL_PY="$(dirname "$(realpath "$0")")/panel.py"
ENV_FILE="$PANEL_DIR/proxy_env.sh"

_pp_run() {
    python3 "$PANEL_PY" "$@"
}

case "$1" in
    --on)
        _pp_run --on
        [ -f "$ENV_FILE" ] && source "$ENV_FILE"
        ;;
    --off)
        _pp_run --off
        [ -f "$ENV_FILE" ] && source "$ENV_FILE"
        ;;
    --country|-c)
        _pp_run --country "$2"
        [ -f "$ENV_FILE" ] && source "$ENV_FILE"
        ;;
    --status|-s)
        _pp_run --status
        ;;
    --export|-e)
        eval "$(_pp_run --export)"
        ;;
    --env)
        [ -f "$ENV_FILE" ] && source "$ENV_FILE" && echo "[+] ENV loaded"
        ;;
    --install)
        # install to PATH
        INSTALL_PATH="/usr/local/bin/pp"
        echo "#!/usr/bin/env bash" > /tmp/pp_install
        echo "source $(realpath "$0") \"\$@\"" >> /tmp/pp_install
        sudo mv /tmp/pp_install "$INSTALL_PATH" 2>/dev/null || mv /tmp/pp_install "$HOME/.local/bin/pp"
        chmod +x "$INSTALL_PATH" 2>/dev/null || chmod +x "$HOME/.local/bin/pp"
        echo "[+] Installed as 'pp'"
        ;;
    "")
        python3 "$PANEL_PY"
        ;;
    *)
        _pp_run "$@"
        ;;
esac
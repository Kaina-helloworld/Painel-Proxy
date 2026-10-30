#!/usr/bin/env bash
# proxy_panel.sh — bash wrapper
# Usage:
#   source proxy_panel.sh --on
#   source proxy_panel.sh --country DE
#   source proxy_panel.sh --export
#   ./proxy_panel.sh             (opens TUI)
#
# Must be SOURCED for env vars to stick in current shell.
# Add alias to ~/.bashrc:
#   alias pp='source /path/to/proxy_panel.sh'

PANEL_DIR="$HOME/.proxy_panel"
ENV_FILE="$PANEL_DIR/proxy_env.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PANEL_PY="$SCRIPT_DIR/panel.py"

_pp_py() { python3 "$PANEL_PY" "$@"; }

# source env file if it exists
_pp_apply_env() {
    if [[ -f "$ENV_FILE" ]]; then
        # shellcheck source=/dev/null
        source "$ENV_FILE"
    fi
}

case "${1:-}" in

    --on|-o)
        _pp_py --on
        _pp_apply_env
        ;;

    --off|-x)
        _pp_py --off
        _pp_apply_env
        ;;

    --country|-c)
        if [[ -z "${2:-}" ]]; then
            echo "[!] usage: pp --country US"
        else
            _pp_py --country "$2"
            _pp_apply_env
        fi
        ;;

    --status|-s)
        _pp_py --status
        echo "ENV  : ${HTTP_PROXY:-not set}"
        ;;

    --export|-e)
        eval "$(_pp_py --export)"
        echo "[+] ENV applied to current shell"
        ;;

    --env)
        _pp_apply_env
        echo "[+] ENV loaded from $ENV_FILE"
        ;;

    --rotate)
        # quick rotate: re-fetch and switch country
        CURRENT_CC="${PROXY_COUNTRY:-}"
        if [[ -z "$CURRENT_CC" ]]; then
            echo "[!] no active country — run: pp --country US"
        else
            _pp_py --country "$CURRENT_CC"
            _pp_apply_env
        fi
        ;;

    --install)
        # install pp alias into ~/.bashrc
        ALIAS_LINE="alias pp='source $(realpath "${BASH_SOURCE[0]}")'"
        if grep -qF "alias pp=" "$HOME/.bashrc" 2>/dev/null; then
            echo "[~] alias already in ~/.bashrc"
        else
            echo "" >> "$HOME/.bashrc"
            echo "# proxy panel" >> "$HOME/.bashrc"
            echo "$ALIAS_LINE" >> "$HOME/.bashrc"
            echo "[+] added to ~/.bashrc — run: source ~/.bashrc"
        fi
        # termux: also add to ~/.profile
        if [[ -n "$PREFIX" && "$PREFIX" == *termux* ]]; then
            if ! grep -qF "alias pp=" "$HOME/.profile" 2>/dev/null; then
                echo "$ALIAS_LINE" >> "$HOME/.profile"
                echo "[+] also added to ~/.profile (termux)"
            fi
        fi
        ;;

    --help|-h)
        echo ""
        echo "  proxy panel — bash wrapper"
        echo ""
        echo "  IMPORTANT: use 'source' so env vars stick:"
        echo "    source proxy_panel.sh --on"
        echo "    source proxy_panel.sh --country BR"
        echo ""
        echo "  Or install the 'pp' alias:"
        echo "    source proxy_panel.sh --install"
        echo "    source ~/.bashrc"
        echo "    pp --on"
        echo ""
        echo "  Commands:"
        echo "    --on          activate saved proxy"
        echo "    --off         deactivate"
        echo "    --country XX  switch country (fetches + tests)"
        echo "    --status      show state"
        echo "    --export      apply env to shell"
        echo "    --env         re-source saved env file"
        echo "    --rotate      re-fetch current country"
        echo "    --install     add 'pp' alias to ~/.bashrc"
        echo "    (no args)     open interactive TUI"
        echo ""
        ;;

    "")
        # no args — open TUI
        python3 "$PANEL_PY"
        _pp_apply_env
        ;;

    *)
        _pp_py "$@"
        ;;
esac
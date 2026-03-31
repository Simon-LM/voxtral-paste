#!/bin/bash
# ─── Shared ANSI colors and UI helpers ───────────────────────────────────────
# Source this file from any VoxRefiner shell script:
#   source "$(dirname "$0")/src/ui.sh"

# ── Colors ───────────────────────────────────────────────────────────────────
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_DIM='\033[2m'
C_ITALIC="\033[3m"
C_UNDERLINE="\033[4m"
C_BLINK="\033[5m"
C_REVERSE="\033[7m"

C_CYAN='\033[36m'
C_GREEN='\033[32m'
C_YELLOW='\033[33m'
C_RED='\033[31m'
C_WHITE='\033[97m'
C_BLUE='\033[34m'
C_BCYAN='\033[1;36m'     # bold cyan
C_BGREEN='\033[1;32m'    # bold green
C_BYELLOW='\033[1;33m'   # bold yellow
C_BBLUE='\033[1;34m'     # bold blue
C_BG_CYAN='\033[46m'
C_BG_BLUE='\033[44m'
C_BG_PURPLE='\033[45m'

# ── UI helpers ────────────────────────────────────────────────────────────────

_header() {
    # Print a section header: _header "TITLE" [emoji]
    local title="$1" emoji="${2:-}"
    local prefix=""
    [ -n "$emoji" ] && prefix="$emoji  "
    echo ""
    printf "${C_DIM}%s${C_RESET}\n" "──────────────────────────────────────────────────────────────────"
    printf "  ${C_BGREEN}%s%s${C_RESET}\n" "$prefix" "$title"
    printf "${C_DIM}%s${C_RESET}\n" "──────────────────────────────────────────────────────────────────"
}

_sep()     { printf "${C_DIM}%s${C_RESET}\n" "──────────────────────────────────────────────────────────────────"; }
_process() { printf "  ${C_BGREEN}⚡${C_RESET} %s\n" "$1"; }
_success() { printf "  ${C_BGREEN}✓${C_RESET} %s\n" "$1"; }
_warn()    { printf "  ${C_BYELLOW}⚠${C_RESET}  %s\n" "$1"; }
_error()   { printf "  ${C_RED}✗${C_RESET} %s\n" "$1"; }
_info()    { printf "  ${C_CYAN}%b${C_RESET}\n" "$1"; }
_crucial() { printf "  ${C_BCYAN}%b${C_RESET}\n" "$1"; }
_stop()    { printf "  ${C_BBLUE}%b${C_RESET}\n" "$1"; }

#!/bin/bash
# VoxRefiner — Launcher
# Opens a terminal window and runs VoxRefiner.
# Bind this file to a keyboard shortcut or use it from the .desktop file.
#
# Launch modes:
#   (no flag)           → interactive menu (vox-refiner-menu.sh)
#   --speak-refine      → record & refine to clipboard (best for keyboard shortcut)
#   --speak-translate   → record & translate to audio  (best for keyboard shortcut)
#   --selection-voice   → read selected/clipboard text aloud (best for keyboard shortcut)
#
# Optional: set VOXREFINER_TERMINAL in your environment to force a specific
# terminal emulator (mate-terminal, gnome-terminal, xfce4-terminal, konsole, xterm).
# ─────────────────────────────────────────────────────────────────────────────

# Auto-detect install directory — works wherever VoxRefiner is installed.
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"

# ─── Display / D-Bus fix ──────────────────────────────────────────────────────
# Keyboard shortcuts run in a minimal environment. mate-terminal and
# gnome-terminal need DBUS_SESSION_BUS_ADDRESS to open a window.
export DISPLAY="${DISPLAY:-:0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

# ─── Mode selection ───────────────────────────────────────────────────────────
case "${1:-}" in
    --speak-refine)
        SCRIPT_PATH="$INSTALL_DIR/record_and_transcribe_local.sh"
        ;;
    --speak-translate)
        SCRIPT_PATH="$INSTALL_DIR/voice_translate.sh"
        ;;
    --selection-voice)
        SCRIPT_PATH="$INSTALL_DIR/selection_to_voice.sh"
        ;;
    *)
        SCRIPT_PATH="$INSTALL_DIR/vox-refiner-menu.sh"
        ;;
esac

# ─── Terminal detection ───────────────────────────────────────────────────────
VOXREFINER_TERMINAL="${VOXREFINER_TERMINAL:-}"

# PID file — close previous VoxRefiner window before opening a new one.
PID_FILE="/tmp/vox-refiner_terminal.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID"
        sleep 0.5
    fi
fi

run_in_terminal() {
    case "$1" in
        mate-terminal|gnome-terminal)
            "$1" -- bash -c "\"$SCRIPT_PATH\"; exec bash" &
            ;;
        xfce4-terminal)
            "$1" -e "bash -c \"\"$SCRIPT_PATH\"; exec bash\"" &
            ;;
        konsole)
            "$1" -e bash -c "\"$SCRIPT_PATH\"; exec bash" &
            ;;
        xterm)
            "$1" -e bash -lc "\"$SCRIPT_PATH\"; exec bash" &
            ;;
        *)
            return 1
            ;;
    esac
    return 0
}

if [ -n "$VOXREFINER_TERMINAL" ] && command -v "$VOXREFINER_TERMINAL" >/dev/null 2>&1; then
    if ! run_in_terminal "$VOXREFINER_TERMINAL"; then
        echo "❌ Unsupported VOXREFINER_TERMINAL: $VOXREFINER_TERMINAL"
        echo "Supported: mate-terminal, gnome-terminal, xfce4-terminal, konsole, xterm"
        exit 1
    fi
elif command -v mate-terminal >/dev/null 2>&1; then
    run_in_terminal mate-terminal
elif command -v gnome-terminal >/dev/null 2>&1; then
    run_in_terminal gnome-terminal
elif command -v xfce4-terminal >/dev/null 2>&1; then
    run_in_terminal xfce4-terminal
elif command -v konsole >/dev/null 2>&1; then
    run_in_terminal konsole
elif command -v xterm >/dev/null 2>&1; then
    run_in_terminal xterm
else
    echo "❌ No supported terminal found."
    echo "Set VOXREFINER_TERMINAL to one of: mate-terminal, gnome-terminal, xfce4-terminal, konsole, xterm"
    exit 1
fi

NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

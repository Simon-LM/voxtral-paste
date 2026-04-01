#!/bin/bash

# ─── VoxRefiner — Launcher example ────────────────────────────────────────
#
# This script opens a new terminal window and runs VoxRefiner.
# Copy it to launch-vox-refiner.sh and customize it for your setup.
#
# Three launch modes:
#   - Interactive menu (vox-refiner-menu.sh):
#       Speech-to-Text, Voice Translate, Settings — best for the app launcher.
#   - Direct recording (record_and_transcribe_local.sh):
#       Speak → clipboard instantly — best for a keyboard shortcut.
#   - Selection to Voice (selection_to_voice.sh):
#       Selected/clipboard text → read aloud instantly — best for a keyboard shortcut.
#
# Recommended setup:
#   1. cp launch-vox-refiner.example.sh launch-vox-refiner.sh
#   2. Edit INSTALL_DIR below to match your installation path
#   3. .desktop file       → launches the interactive menu (no flag)
#   4. Keyboard shortcut 1 → bind to: launch-vox-refiner.sh --direct
#   5. Keyboard shortcut 2 → bind to: launch-vox-refiner.sh --selection
#
# Terminal examples:
#   MATE:    mate-terminal -- bash -c "\"$SCRIPT_PATH\"; exec bash"
#   GNOME:   gnome-terminal -- bash -c "\"$SCRIPT_PATH\"; exec bash"
#   KDE:     konsole -e bash -c "\"$SCRIPT_PATH\"; exec bash"
#   XFCE:    xfce4-terminal -e "bash -c \"\\\"$SCRIPT_PATH\\\"; exec bash\""
# ──────────────────────────────────────────────────────────────────────────────

INSTALL_DIR="$HOME/.local/bin/vox-refiner"

# ─── Display / D-Bus environment fix ─────────────────────────────────────────
# When launched from a DE keyboard shortcut the process runs in a minimal
# environment. mate-terminal and gnome-terminal need DBUS_SESSION_BUS_ADDRESS
# to open a window; without it they exit silently.
export DISPLAY="${DISPLAY:-:0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

case "${1:-}" in
    --direct)
        # Skip the menu, record immediately (ideal for keyboard shortcut)
        SCRIPT_PATH="$INSTALL_DIR/record_and_transcribe_local.sh"
        ;;
    --selection)
        # Read selected/clipboard text aloud (ideal for keyboard shortcut)
        SCRIPT_PATH="$INSTALL_DIR/selection_to_voice.sh"
        ;;
    *)
        SCRIPT_PATH="$INSTALL_DIR/vox-refiner-menu.sh"
        ;;
esac

# Optional terminal override.
# Examples:
#   VOXREFINER_TERMINAL=mate-terminal
#   VOXREFINER_TERMINAL=gnome-terminal
VOXREFINER_TERMINAL="${VOXREFINER_TERMINAL:-}"

# PID file to track the previous terminal (avoids duplicate windows)
PID_FILE="/tmp/vox-refiner_terminal.pid"

# Kill previous terminal if still running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "⚠️  Closing previous VoxRefiner terminal..."
        kill "$OLD_PID"
        sleep 0.5
    fi
fi

# Launch a new terminal and save its PID
# Priority: explicit override -> MATE -> GNOME -> XFCE -> KDE -> xterm.
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
        echo "Supported values: mate-terminal, gnome-terminal, xfce4-terminal, konsole, xterm"
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
    echo "❌ No supported terminal emulator found (mate-terminal, gnome-terminal, xfce4-terminal, konsole, xterm)."
    echo "Set VOXREFINER_TERMINAL to a supported terminal command."
    exit 1
fi

NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"


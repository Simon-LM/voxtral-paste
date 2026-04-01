#!/bin/bash
# VoxRefiner — Selection to Voice
# Read selected (or clipboard) text aloud using the default TTS voice.
# Can be launched standalone (keyboard shortcut) or called from the menu.

cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

# ─── Shared UI ───────────────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$SCRIPT_DIR/src/ui.sh"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "❌ Missing .venv Python interpreter: $VENV_PYTHON"
    echo "Run ./install.sh first."
    exit 1
fi

# Load .env
if [ -f .env ]; then
    # shellcheck disable=SC1091
    set -a; source .env; set +a
fi

# Save stderr so Python progress messages reach the terminal even when stdout
# is captured by $() substitution.
exec 3>&2

# ─── Get selected text ───────────────────────────────────────────────────────

# Try primary selection first (mouse highlight), then clipboard.
selected_text="$(xclip -o -selection primary 2>/dev/null || true)"
_source="primary selection"

if [ -z "$(printf '%s' "$selected_text" | tr -d '[:space:]')" ]; then
    selected_text="$(xclip -o -selection clipboard 2>/dev/null || true)"
    _source="clipboard"
fi

if [ -z "$(printf '%s' "$selected_text" | tr -d '[:space:]')" ]; then
    _header "SELECTION TO VOICE" "⌨→🔊"
    echo ""
    _error "No text found in primary selection or clipboard."
    _info "Select some text with your mouse, then run again."
    echo ""
    exit 1
fi

# ─── Display ─────────────────────────────────────────────────────────────────

_header "SELECTION TO VOICE" "⌨→🔊"
echo ""
_info "Source: $_source  (${#selected_text} chars)"
echo ""
printf "${C_BG_CYAN} %s ${C_RESET}\n" "$selected_text"
echo ""

# ─── TTS ─────────────────────────────────────────────────────────────────────

REC_DIR="$SCRIPT_DIR/recordings/selection-to-voice"
mkdir -p "$REC_DIR"
TTS_OUTPUT="$REC_DIR/output.mp3"
rm -f "$TTS_OUTPUT"

_process "Generating speech..."

# Voice for selection: TTS_SELECTION_VOICE_ID from .env (e.g. fr_male_1 for Luc).
# Derive language from the voice ID prefix (fr_male_1 → fr) for correct pronunciation.
_sel_voice="${TTS_SELECTION_VOICE_ID:-}"
_sel_lang="${_sel_voice%%-*}"  # extract "fr" from "fr-FR-Wavenet-B"
if ! printf '%s' "$selected_text" | \
    TTS_VOICE_ID="$_sel_voice" TTS_LANG="$_sel_lang" "$VENV_PYTHON" -m src.tts "$TTS_OUTPUT" 2>&3; then
    echo ""
    _error "TTS failed — check your MISTRAL_API_KEY and connection."
    exit 1
fi

# ─── Loudness normalization ───────────────────────────────────────────────────

TTS_LOUDNESS="${TTS_LOUDNESS:--16}"
TTS_VOLUME="${TTS_VOLUME:-2.0}"
TTS_NORM_TMP="$REC_DIR/.norm_tmp.mp3"
if ffmpeg -y -i "$TTS_OUTPUT" \
        -af "loudnorm=I=${TTS_LOUDNESS}:TP=-1.5:LRA=11,volume=${TTS_VOLUME}" \
        -codec:a libmp3lame -b:a 128k "$TTS_NORM_TMP" 2>/dev/null; then
    mv "$TTS_NORM_TMP" "$TTS_OUTPUT"
fi
rm -f "$TTS_NORM_TMP"

# ─── Playback ─────────────────────────────────────────────────────────────────

_play_audio() {
    if command -v mpv >/dev/null 2>&1; then
        TTS_PLAYER="${TTS_PLAYER:-mpv --no-video}"
        echo ""
        printf "  ${C_BGREEN}🔊 Playing...${C_RESET}\n"
        $TTS_PLAYER "$TTS_OUTPUT" 2>/dev/null
        echo ""
        _success "Playback complete."
    else
        _warn "mpv is not installed — cannot auto-play."
        _info "Install it: sudo apt install mpv"
        _info "Audio saved at: $TTS_OUTPUT"
    fi
}

_play_audio

# ─── Post-action mini-menu ───────────────────────────────────────────────────

if [ "${VOXREFINER_MENU:-}" != "1" ]; then
    while true; do
        echo ""
        _sep
        printf "  ${C_BOLD}[l]${C_RESET} Listen again  ${C_BOLD}[d]${C_RESET} Save  ${C_DIM}[Enter] Quit${C_RESET}: "
        read -r _action
        case "$_action" in
            l|L)
                _play_audio
                ;;
            d|D)
                # Resolve Downloads folder (handles Téléchargements, Downloads, etc.)
                DOWNLOADS_DIR="$(xdg-user-dir DOWNLOAD 2>/dev/null || echo "$HOME/Downloads")"
                SAVE_DIR="$DOWNLOADS_DIR/VoxRefiner"
                mkdir -p "$SAVE_DIR"
                TIMESTAMP="$(date '+%Y-%m-%d_%Hh%M')"
                DEST="$SAVE_DIR/${TIMESTAMP}_selection-to-voice.mp3"
                if cp "$TTS_OUTPUT" "$DEST"; then
                    echo ""
                    _success "Saved: $DEST"
                else
                    _warn "Could not save file to $DEST"
                fi
                ;;
            *) break ;;
        esac
    done
fi

#!/bin/bash
# VoxRefiner — Shared audio save helper
# Source this file to get _save_audio_to_downloads().
#
# Usage:
#   source "$SCRIPT_DIR/src/save_audio.sh"
#   _save_audio_to_downloads "$audio_file" "$slug_text" "fallback-name"
#
# Arguments:
#   $1  audio_file   — path to the .mp3 to save
#   $2  slug_text    — text fed to src.slug to generate the filename suggestion
#   $3  fallback     — slug used if Mistral is unavailable (default: "audio")

_save_audio_to_downloads() {
    local audio_file="$1"
    local slug_text="$2"
    local fallback="${3:-audio}"

    if [ ! -f "$audio_file" ]; then
        _warn "No audio file to save."
        return 1
    fi

    # Resolve Downloads folder (handles Téléchargements, Downloads, etc.)
    local downloads_dir
    downloads_dir="$(xdg-user-dir DOWNLOAD 2>/dev/null || echo "$HOME/Downloads")"
    local save_dir="$downloads_dir/VoxRefiner"
    mkdir -p "$save_dir"

    local timestamp
    timestamp="$(date '+%Y-%m-%d_%Hh%M')"

    # Generate slug via Mistral
    echo ""
    _info "🏷️  Generating filename..."
    local suggested_slug
    suggested_slug=$(printf '%s' "$slug_text" | \
        "$VENV_PYTHON" -m src.slug --fallback "$fallback" 2>&3)
    suggested_slug="${suggested_slug:-$fallback}"

    # Ask user to confirm or override
    echo ""
    printf "  ${C_BOLD}Suggested name:${C_RESET} ${C_CYAN}%s${C_RESET}\n" "$suggested_slug"
    printf "  Press Enter to confirm, or type a new name: "
    read -r _custom_name

    local final_slug
    if [ -n "$_custom_name" ]; then
        # Sanitise: lowercase, spaces → hyphens, strip unsafe chars
        final_slug=$(printf '%s' "$_custom_name" \
            | tr '[:upper:]' '[:lower:]' \
            | tr ' ' '-' \
            | tr -cd 'a-z0-9-')
        final_slug="${final_slug:-$fallback}"
    else
        final_slug="$suggested_slug"
    fi

    local dest="$save_dir/${timestamp}_${final_slug}.mp3"
    if cp "$audio_file" "$dest"; then
        echo ""
        _success "Saved: $dest"
    else
        _warn "Could not save file to $dest"
    fi
}

#!/bin/bash
# VoxRefiner — Selection to Insight
# Summarise selected text, then offer research (Perplexity) and
# fact-checking (Perplexity + Grok) from the menu.
# Can be launched standalone (keyboard shortcut) or called from the menu.

cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

# ─── Shared UI + helpers ─────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$SCRIPT_DIR/src/ui.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/src/save_audio.sh"

if [ ! -x "$VENV_PYTHON" ]; then
    _error "Missing .venv Python interpreter: $VENV_PYTHON"
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

# ─── API key warnings ─────────────────────────────────────────────────────────

_warn_missing_keys() {
    if [ -z "${PERPLEXITY_API_KEY:-}" ] && [ -z "${XAI_API_KEY:-}" ]; then
        echo ""
        _warn "No search API key configured."
        _info "  Search and Fact-check require at least one of:"
        _info "    PERPLEXITY_API_KEY  → perplexity.ai/settings/api"
        _info "    XAI_API_KEY         → x.ai/api"
        _info "  Add either to your .env file to unlock Search and Fact-check."
        echo ""
        _info "  Tip: Summary works with MISTRAL_API_KEY alone."
        _info "  Either key unlocks Search and Fact-check."
        echo ""
    fi
}

# ─── Get selected text ───────────────────────────────────────────────────────

selected_text="$(xclip -o -selection primary 2>/dev/null || true)"
_source="primary selection"

if [ -z "$(printf '%s' "$selected_text" | tr -d '[:space:]')" ]; then
    selected_text="$(xclip -o -selection clipboard 2>/dev/null || true)"
    _source="clipboard"
fi

if [ -z "$(printf '%s' "$selected_text" | tr -d '[:space:]')" ]; then
    _header "SELECTION TO INSIGHT" "⌨→💡"
    echo ""
    _error "No text found in primary selection or clipboard."
    _info "Select some text with your mouse, then run again."
    echo ""
    exit 1
fi

# ─── Display + key warnings ──────────────────────────────────────────────────

_header "SELECTION TO INSIGHT" "⌨→💡"
echo ""
_info "Source: $_source  (${#selected_text} chars)"
echo ""
printf "${C_BG_CYAN} %s ${C_RESET}\n" "$selected_text"
echo ""
_warn_missing_keys

# ─── Temp files ──────────────────────────────────────────────────────────────

INSIGHT_DIR="$SCRIPT_DIR/recordings/insight"
mkdir -p "$INSIGHT_DIR"

INSIGHT_META_FILE="$INSIGHT_DIR/.meta"
INSIGHT_PERPLEXITY_FILE="$INSIGHT_DIR/.perplexity"
INSIGHT_GROK_FILE="$INSIGHT_DIR/.grok"
export INSIGHT_META_FILE INSIGHT_PERPLEXITY_FILE INSIGHT_GROK_FILE

# Audio files
SUMMARY_AUDIO="$INSIGHT_DIR/summary.mp3"
SEARCH_AUDIO="$INSIGHT_DIR/search.mp3"
FACTCHECK_AUDIO="$INSIGHT_DIR/factcheck.mp3"

TTS_LOUDNESS="${TTS_LOUDNESS:--16}"
TTS_VOLUME="${TTS_VOLUME:-2.0}"

# ─── Audio helpers ────────────────────────────────────────────────────────────

_play_audio() {
    local file="$1"
    if [ ! -f "$file" ]; then return; fi
    if command -v mpv >/dev/null 2>&1; then
        TTS_PLAYER="${TTS_PLAYER:-mpv --no-video}"
        $TTS_PLAYER "$file" 2>/dev/null
    else
        _warn "mpv not installed — cannot auto-play."
        _info "Install: sudo apt install mpv"
    fi
}

_tts_speak() {
    # Generate TTS using the chunked pipeline (sequential: generate all, then play).
    # Supports quote voice switching (TTS_QUOTE_VOICE_ID) identically to
    # Selection to Voice. Skips AI cleaning (text is already clean).
    # Usage: _tts_speak <text> <output_mp3_for_replay>
    local text="$1" out="$2"
    local voice="${TTS_SELECTION_VOICE_ID:-}"
    local lang="${voice%%-*}"

    rm -f "$out"

    local chunks_dir concat_list
    chunks_dir="$(dirname "$out")/chunks_$(basename "${out%.mp3}")"
    concat_list="$(dirname "$out")/.concat_$(basename "${out%.mp3}").txt"
    rm -rf "$chunks_dir"
    mkdir -p "$chunks_dir"
    : > "$concat_list"

    # Generate all chunks synchronously — no FIFO streaming needed for short texts.
    # TTS_SKIP_AI_CLEAN=1: the summary is already clean Mistral output.
    local chunk_output
    chunk_output=$(printf '%s' "$text" | \
        TTS_SKIP_AI_CLEAN=1 \
        TTS_VOICE_ID="$voice" TTS_LANG="$lang" \
        "$VENV_PYTHON" -m src.tts --chunked "$chunks_dir" 2>&3)

    if [ -z "$chunk_output" ]; then
        _warn "TTS failed — text will not be read aloud."
        return 1
    fi

    # Load all chunk paths into an array BEFORE any playback.
    # This prevents mpv (which reads stdin for keyboard input) from consuming
    # bytes from the here-string and corrupting subsequent path strings.
    local tts_ok=1
    local -a chunk_files=()
    while IFS= read -r chunk_file; do
        [ -n "$chunk_file" ] && chunk_files+=("$chunk_file")
    done <<< "$chunk_output"

    for chunk_file in "${chunk_files[@]}"; do
        if [[ "$chunk_file" == CHUNK_FAILED:* ]]; then
            _warn "Un passage TTS a échoué — lecture partielle."
            tts_ok=0
            continue
        fi
        [ ! -s "$chunk_file" ] && { _warn "Chunk vide/absent: $chunk_file"; tts_ok=0; continue; }

        # Normalise loudness
        local norm="${chunk_file%.mp3}_norm.mp3"
        if ffmpeg -y -i "$chunk_file" \
                -af "loudnorm=I=${TTS_LOUDNESS}:TP=-1.5:LRA=11,volume=${TTS_VOLUME}" \
                -codec:a libmp3lame -b:a 128k "$norm" 2>/dev/null; then
            mv "$norm" "$chunk_file"
        fi
        rm -f "$norm"

        printf 'file %s\n' "$(realpath "$chunk_file")" >> "$concat_list"
        _play_audio "$chunk_file"
    done

    # Merge chunks into single file for replay
    if [ -s "$concat_list" ]; then
        ffmpeg -y -f concat -safe 0 -i "$concat_list" \
            -codec:a libmp3lame -b:a 128k "$out" 2>/dev/null || true
    fi
    rm -f "$concat_list"

    [ "$tts_ok" -eq 1 ]
}

# ─── Step 1: Summarise ────────────────────────────────────────────────────────

_header "SUMMARY" "💡"
echo ""
_process "Analysing and summarising..."
echo ""

summary_text=$(printf '%s' "$selected_text" | "$VENV_PYTHON" -m src.insight summarize 2>&3)

if [ -z "$summary_text" ]; then
    _error "Summary failed — check your MISTRAL_API_KEY and connection."
    exit 1
fi

content_type="generic"
if [ -s "$INSIGHT_META_FILE" ]; then
    content_type="$(cat "$INSIGHT_META_FILE")"
fi

_success "Type detected: $content_type"
echo ""
printf "${C_BG_BLUE} %s ${C_RESET}\n" "$summary_text"
echo ""

# ─── Shared: read a result aloud + show it ────────────────────────────────────

_show_and_speak() {
    local header_label="$1" emoji="$2" result_text="$3" audio_file="$4" fallback="${5:-insight}"
    _header "$header_label" "$emoji"
    echo ""
    printf "${C_BG_BLUE} %s ${C_RESET}\n" "$result_text"
    echo ""
    _process "Reading aloud..."
    _tts_speak "$result_text" "$audio_file"
}

# ─── Read summary aloud ───────────────────────────────────────────────────────

_process "Reading summary..."
_tts_speak "$summary_text" "$SUMMARY_AUDIO"

# ─── Search flow ─────────────────────────────────────────────────────────────

_search_flow() {
    if [ -z "${PERPLEXITY_API_KEY:-}" ] && [ -z "${XAI_API_KEY:-}" ]; then
        echo ""
        _error "No search API key set — search unavailable."
        _info "Add PERPLEXITY_API_KEY or XAI_API_KEY to your .env."
        echo ""
        return
    fi

    echo ""
    _header "SEARCH" "🔍"
    echo ""
    _info "Ask your question:"
    printf "  ${C_BOLD}[v]${C_RESET} Voice  ${C_BOLD}[t]${C_RESET} Type  ${C_DIM}[Enter] Cancel${C_RESET}: "
    read -r _input_mode

    case "$_input_mode" in
        v|V)
            echo ""
            VOXREFINER_MENU=1 "$SCRIPT_DIR/record_and_transcribe_local.sh"
            query_text="$(xclip -o -selection clipboard 2>/dev/null || true)"
            if [ -z "$(printf '%s' "$query_text" | tr -d '[:space:]')" ]; then
                _warn "No query recorded — search cancelled."
                return
            fi
            echo ""
            _info "Query: $query_text"
            ;;
        t|T)
            echo ""
            printf "  Type your question: "
            read -r query_text
            if [ -z "$query_text" ]; then
                _warn "Empty query — search cancelled."
                return
            fi
            ;;
        *)
            return
            ;;
    esac

    echo ""
    _process "Searching..."
    echo ""

    # Protocol: first line = query, rest = context summary
    search_result=$(printf '%s\n%s' "$query_text" "$summary_text" | \
        "$VENV_PYTHON" -m src.insight search 2>&3)

    if [ -z "$search_result" ]; then
        _error "Search returned no result — check your API keys and connection."
        return
    fi

    _show_and_speak "SEARCH RESULT" "🔍" "$search_result" "$SEARCH_AUDIO" "insight-search"

    # Post-search menu
    while true; do
        echo ""
        _sep
        printf "  ${C_BOLD}[r]${C_RESET} Replay  ${C_BOLD}[d]${C_RESET} Save  ${C_BOLD}[p]${C_RESET} New search  ${C_BOLD}[f]${C_RESET} Fact-check  ${C_BOLD}[s]${C_RESET} Replay summary  ${C_BOLD}[l]${C_RESET} Read full  ${C_DIM}[Enter] Back${C_RESET}: "
        read -r _post_action
        case "$_post_action" in
            r|R) _play_audio "$SEARCH_AUDIO" ;;
            d|D) _save_audio_to_downloads "$SEARCH_AUDIO" "$search_result" "insight-search" ;;
            p|P) _search_flow; return ;;
            f|F) _factcheck_flow; return ;;
            s|S) _play_audio "$SUMMARY_AUDIO" ;;
            l|L) _read_full_article; return ;;
            *) return ;;
        esac
    done
}

# ─── Fact-check flow ──────────────────────────────────────────────────────────

_factcheck_flow() {
    if [ -z "${PERPLEXITY_API_KEY:-}" ] && [ -z "${XAI_API_KEY:-}" ]; then
        echo ""
        _error "Neither PERPLEXITY_API_KEY nor XAI_API_KEY is set."
        _info "Add at least one to your .env to use fact-checking."
        echo ""
        return
    fi

    echo ""
    _header "FACT-CHECK" "🔬"
    echo ""
    _info "Verify a specific claim, or check the whole article?"
    printf "  ${C_BOLD}[v]${C_RESET} Voice  ${C_BOLD}[t]${C_RESET} Type  ${C_DIM}[Enter] Whole article${C_RESET}: "
    read -r _fc_mode

    export INSIGHT_QUERY=""
    case "$_fc_mode" in
        v|V)
            echo ""
            VOXREFINER_MENU=1 "$SCRIPT_DIR/record_and_transcribe_local.sh"
            fc_query="$(xclip -o -selection clipboard 2>/dev/null || true)"
            if [ -n "$(printf '%s' "$fc_query" | tr -d '[:space:]')" ]; then
                INSIGHT_QUERY="$fc_query"
                export INSIGHT_QUERY
                _info "Verifying: $fc_query"
            fi
            ;;
        t|T)
            echo ""
            printf "  Type the claim to verify: "
            read -r fc_query
            if [ -n "$fc_query" ]; then
                INSIGHT_QUERY="$fc_query"
                export INSIGHT_QUERY
            fi
            ;;
    esac

    echo ""
    _process "Running fact-check (Perplexity + Grok in parallel)..."
    echo ""

    factcheck_result=$(printf '%s' "$summary_text" | \
        "$VENV_PYTHON" -m src.insight factcheck 2>&3)

    if [ -z "$factcheck_result" ]; then
        _error "Fact-check failed — check your API keys and connection."
        return
    fi

    _show_and_speak "FACT-CHECK RESULT" "🔬" "$factcheck_result" "$FACTCHECK_AUDIO" "insight-factcheck"

    # Post-factcheck menu
    while true; do
        echo ""
        _sep
        # Build options dynamically — detail buttons only shown when BOTH sources
        # are present (synthesis mode); single-source result = replay is sufficient.
        _fc_opts="${C_BOLD}[r]${C_RESET} Replay  ${C_BOLD}[d]${C_RESET} Save"
        if [ -s "$INSIGHT_PERPLEXITY_FILE" ] && [ -s "$INSIGHT_GROK_FILE" ]; then
            _fc_opts="$_fc_opts  ${C_BOLD}[w]${C_RESET} Perplexity details  ${C_BOLD}[x]${C_RESET} Grok details"
        fi
        _fc_opts="$_fc_opts  ${C_BOLD}[p]${C_RESET} Search  ${C_BOLD}[f]${C_RESET} New fact-check  ${C_BOLD}[s]${C_RESET} Replay summary  ${C_BOLD}[l]${C_RESET} Read full  ${C_DIM}[Enter] Back${C_RESET}"
        printf "  %b: " "$_fc_opts"
        read -r _fc_action
        case "$_fc_action" in
            r|R)
                _play_audio "$FACTCHECK_AUDIO"
                ;;
            d|D)
                _save_audio_to_downloads "$FACTCHECK_AUDIO" "$factcheck_result" "insight-factcheck"
                ;;
            w|W)
                if [ -s "$INSIGHT_PERPLEXITY_FILE" ]; then
                    _detail="$(cat "$INSIGHT_PERPLEXITY_FILE")"
                    _show_and_speak "WEB DETAILS — PERPLEXITY" "🌐" "$_detail" "$INSIGHT_DIR/perplexity_detail.mp3" "insight-perplexity"
                fi
                ;;
            x|X)
                if [ -s "$INSIGHT_GROK_FILE" ]; then
                    _detail="$(cat "$INSIGHT_GROK_FILE")"
                    _show_and_speak "X DETAILS — GROK" "𝕏" "$_detail" "$INSIGHT_DIR/grok_detail.mp3" "insight-grok"
                fi
                ;;
            p|P) _search_flow; return ;;
            f|F) _factcheck_flow; return ;;
            s|S) _play_audio "$SUMMARY_AUDIO" ;;
            l|L) _read_full_article; return ;;
            *) return ;;
        esac
    done
}

# ─── Read full article ────────────────────────────────────────────────────────

_read_full_article() {
    # Launch Selection to Voice with the original selected text pre-loaded in
    # the primary clipboard so it picks it up immediately.
    printf '%s' "$selected_text" | xclip -selection primary 2>/dev/null || true
    printf '%s' "$selected_text" | xclip -selection clipboard 2>/dev/null || true
    exec "$SCRIPT_DIR/selection_to_voice.sh"
}

# ─── Main menu ────────────────────────────────────────────────────────────────

while true; do
    echo ""
    _sep
    printf "  ${C_BOLD}[l]${C_RESET} Read full  ${C_BOLD}[p]${C_RESET} Search  ${C_BOLD}[f]${C_RESET} Fact-check  ${C_BOLD}[s]${C_RESET} Replay summary  ${C_BOLD}[g]${C_RESET} Re-read summary  ${C_BOLD}[d]${C_RESET} Save summary  ${C_DIM}[Enter] Quit${C_RESET}: "
    read -r _main_action
    case "$_main_action" in
        l|L) _read_full_article ;;
        p|P) _search_flow ;;
        f|F) _factcheck_flow ;;
        s|S) _play_audio "$SUMMARY_AUDIO" ;;
        g|G) _process "Re-generating summary audio..."; _tts_speak "$summary_text" "$SUMMARY_AUDIO" ;;
        d|D) _save_audio_to_downloads "$SUMMARY_AUDIO" "$summary_text" "insight-summary" ;;
        *)   break ;;
    esac
done

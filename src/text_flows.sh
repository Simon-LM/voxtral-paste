#!/bin/bash
# VoxRefiner — Reusable text-processing flow helpers.
# Sourced by any feature or workflow that operates on text:
#   Selection to Insight (F6), Selection to Search (F7),
#   Selection to Fact-check (F8), Screen to Text (F9), future workflows.
#
# Source this file after ui.sh and save_audio.sh.
# Requires globals set by the calling script:
#   SCRIPT_DIR, VENV_PYTHON, TTS_LOUDNESS, TTS_VOLUME
#   INSIGHT_DIR, INSIGHT_META_FILE, INSIGHT_PERPLEXITY_FILE, INSIGHT_GROK_FILE
#   SUMMARY_AUDIO, SEARCH_AUDIO, FACTCHECK_AUDIO, FULL_ARTICLE_AUDIO
#   selected_text, summary_text (initialised to "" in F6/F7)
#   _search_done, _factcheck_done, _article_done, _summary_done, _translate_done
#   _SETTING_SUMMARY_REASONING, _SETTING_SEARCH_ENGINE
#   _SETTING_FACTCHECK_ENGINE, _SETTING_SYNTHESIS_REASONING, _SETTING_TRANSLATE_LANG

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
    fi
}

# ─── Language helper ──────────────────────────────────────────────────────────

_lang_name() {
    # Return the display name for a language code, e.g. "fr" → "French".
    case "$1" in
        en) echo "English" ;;
        fr) echo "French" ;;
        de) echo "German" ;;
        es) echo "Spanish" ;;
        pt) echo "Portuguese" ;;
        it) echo "Italian" ;;
        nl) echo "Dutch" ;;
        hi) echo "Hindi" ;;
        ar) echo "Arabic" ;;
        zh) echo "Chinese" ;;
        ja) echo "Japanese" ;;
        ko) echo "Korean" ;;
        ru) echo "Russian" ;;
        pl) echo "Polish" ;;
        sv) echo "Swedish" ;;
        *)  echo "$1" ;;
    esac
}

# ─── Audio playback ───────────────────────────────────────────────────────────

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

# ─── TTS pipeline ─────────────────────────────────────────────────────────────

_tts_speak() {
    # Generate TTS using the chunked pipeline (sequential: generate all, then play).
    # Skips AI cleaning (text is already clean Mistral output).
    # Usage: _tts_speak <text> <output_mp3_for_replay>
    local _text="$1"
    local _out="$2"

    "$VENV_PYTHON" src/tts.py \
        --loudness "${TTS_LOUDNESS:--16}" \
        --volume   "${TTS_VOLUME:-2.0}"  \
        --output   "$_out"               \
        --no-clean                       \
        <<< "$_text" 2>&3
}

# ─── Show + speak helper ──────────────────────────────────────────────────────

_show_and_speak() {
    local label="$1" icon="$2" result_text="$3" audio_file="$4"
    _header "$label" "$icon"
    _success "Copied to clipboard"
    echo ""
    printf "${C_BG_BLUE} %s ${C_RESET}\n" "$result_text"
    echo ""
    _process "Reading result..."
    _tts_speak "$result_text" "$audio_file"
}

# ─── Summary helpers ──────────────────────────────────────────────────────────

_generate_summary() {
    if [ "$_summary_done" -eq 1 ] && [ -n "$summary_text" ]; then
        _info "Summary already generated."
        return
    fi
    echo ""
    _header "SUMMARY" "💡"
    echo ""
    _process "Analysing and summarising..."
    echo ""

    summary_text=$(printf '%s' "$selected_text" | \
        INSIGHT_SUMMARY_REASONING="$_SETTING_SUMMARY_REASONING" \
        "$VENV_PYTHON" -m src.insight summarize 2>&3)

    if [ -z "$summary_text" ]; then
        _error "Summary failed — check your MISTRAL_API_KEY and connection."
        return
    fi

    content_type="generic"
    if [ -s "$INSIGHT_META_FILE" ]; then
        content_type="$(cat "$INSIGHT_META_FILE")"
    fi

    _success "Type detected: $content_type"
    echo ""
    printf "${C_BG_BLUE} %s ${C_RESET}\n" "$summary_text"
    echo ""
    _process "Reading summary..."
    _tts_speak "$summary_text" "$SUMMARY_AUDIO"
    _summary_done=1
}

_read_full_article() {
    echo ""
    _header "READING FULL ARTICLE" "📖"
    echo ""
    _process "Reading..."
    _tts_speak "$selected_text" "$FULL_ARTICLE_AUDIO"
    _article_done=1
}

# ─── Search flow ──────────────────────────────────────────────────────────────
# Usage: _search_flow <context_text>
# Sets globals: search_result, _search_done=1 on success

_search_flow() {
    local context_text="$1"

    if [ -z "${PERPLEXITY_API_KEY:-}" ] && [ -z "${XAI_API_KEY:-}" ]; then
        echo ""
        _error "Neither PERPLEXITY_API_KEY nor XAI_API_KEY is set."
        _info "Add at least one to your .env to use search."
        echo ""
        return
    fi

    echo ""
    _header "SEARCH" "🔍"
    echo ""
    _info "What do you want to search for?"
    printf "  ${C_BOLD}[v]${C_RESET} Voice  ${C_BOLD}[t]${C_RESET} Type  ${C_BOLD}[m]${C_RESET} Back  ${C_DIM}[Enter] Context summary${C_RESET}: "
    read -r _search_mode

    case "$_search_mode" in
        m|M) return ;;
        v|V)
            echo ""
            _process "Recording query..."
            search_query=$(ENABLE_REFINE=false ENABLE_HISTORY=false \
                "$SCRIPT_DIR/record_and_transcribe_local.sh" 2>&3)
            [ -z "$search_query" ] && { _warn "No query recorded."; return; }
            ;;
        t|T)
            printf "  ${C_DIM}Type your query:${C_RESET} "
            read -r search_query
            [ -z "$search_query" ] && { _warn "Empty query."; return; }
            ;;
        *)
            search_query="$context_text"
            ;;
    esac

    echo ""
    _process "Searching..."
    echo ""

    search_result=$(printf '%s' "$search_query" | \
        INSIGHT_SEARCH_ENGINE="$_SETTING_SEARCH_ENGINE" \
        "$VENV_PYTHON" -m src.insight search 2>&3)

    if [ -z "$search_result" ]; then
        _error "Search returned no result — check your API keys and connection."
        return
    fi

    _show_and_speak "SEARCH RESULT" "🔍" "$search_result" "$SEARCH_AUDIO"
    _search_done=1
}

# ─── Translate flow ───────────────────────────────────────────────────────────
# Usage: _translate_flow <input_text>
# Sets globals: translated_text, _translate_done=1 on success
# Copies translation to both clipboards.
# Target language: _SETTING_TRANSLATE_LANG (session) or TRANSLATE_TARGET_LANG (.env).

_translate_flow() {
    local input_text="$1"
    local _lang_code _lang_display _input

    # Use session setting, fall back to .env, then default to "en"
    _lang_code="${_SETTING_TRANSLATE_LANG:-${TRANSLATE_TARGET_LANG:-en}}"
    _lang_display="$(_lang_name "$_lang_code")"

    echo ""
    _header "TRANSLATE" "🌐"
    echo ""
    printf "  Target language: ${C_BOLD}%s (%s)${C_RESET}\n" "$_lang_display" "$_lang_code"
    printf "  ${C_DIM}[Enter]${C_RESET} Confirm  or type a code ${C_DIM}(fr, en, de, es, it, pt, nl, ru, zh, ja…)${C_RESET}: "
    read -r _input

    if [ -n "$_input" ]; then
        _lang_code="$_input"
        _lang_display="$(_lang_name "$_lang_code")"
        _SETTING_TRANSLATE_LANG="$_lang_code"
        # Persist to .env so the choice survives across sessions.
        local _env_file="$SCRIPT_DIR/.env"
        if [ -f "$_env_file" ]; then
            if grep -q "^TRANSLATE_TARGET_LANG=" "$_env_file"; then
                sed -i "s/^TRANSLATE_TARGET_LANG=.*/TRANSLATE_TARGET_LANG=$_lang_code/" "$_env_file"
            else
                printf '\nTRANSLATE_TARGET_LANG=%s\n' "$_lang_code" >> "$_env_file"
            fi
        fi
        _info "Language set to: $_lang_display ($_lang_code)  (saved to .env)"
    fi

    echo ""
    _process "Translating to $_lang_display..."
    echo ""

    translated_text=$(printf '%s' "$input_text" | \
        TRANSLATE_TARGET_LANG="$_lang_code" \
        "$VENV_PYTHON" -m src.translate 2>&3)

    if [ -z "$translated_text" ]; then
        _error "Translation failed — check your MISTRAL_API_KEY and connection."
        return
    fi

    printf '%s' "$translated_text" | xclip -selection clipboard
    printf '%s' "$translated_text" | xclip -selection primary

    _header "TRANSLATION → $_lang_display — mistral-small-latest" "🌐"
    _success "Copied to clipboard"
    echo ""
    printf "${C_BG_BLUE} %s ${C_RESET}\n" "$translated_text"
    echo ""
    _translate_done=1
}

# ─── Fact-check flow ──────────────────────────────────────────────────────────
# Usage: _factcheck_flow <input_text>
# Sets globals: factcheck_result, _factcheck_done=1 on success

_factcheck_flow() {
    local input_text="$1"

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
    _info "Verify a specific claim, or check the whole text?"
    printf "  ${C_BOLD}[v]${C_RESET} Voice  ${C_BOLD}[t]${C_RESET} Type  ${C_BOLD}[m]${C_RESET} Back  ${C_DIM}[Enter] Whole text${C_RESET}: "
    read -r _fc_mode

    case "$_fc_mode" in
        m|M) return ;;
        v|V)
            echo ""
            _process "Recording claim..."
            factcheck_claim=$(ENABLE_REFINE=false ENABLE_HISTORY=false \
                "$SCRIPT_DIR/record_and_transcribe_local.sh" 2>&3)
            [ -z "$factcheck_claim" ] && { _warn "No claim recorded."; return; }
            ;;
        t|T)
            printf "  ${C_DIM}Type the claim to check:${C_RESET} "
            read -r factcheck_claim
            [ -z "$factcheck_claim" ] && { _warn "Empty claim."; return; }
            ;;
        *)
            factcheck_claim="$input_text"
            ;;
    esac

    echo ""
    _process "Running fact-check..."
    echo ""

    factcheck_result=$(printf '%s' "$factcheck_claim" | \
        INSIGHT_SEARCH_ENGINE="$_SETTING_FACTCHECK_ENGINE" \
        INSIGHT_SYNTHESIS_REASONING="$_SETTING_SYNTHESIS_REASONING" \
        "$VENV_PYTHON" -m src.insight factcheck 2>&3)

    if [ -z "$factcheck_result" ]; then
        _error "Fact-check failed — check your API keys and connection."
        return
    fi

    _show_and_speak "FACT-CHECK RESULT" "🔬" "$factcheck_result" "$FACTCHECK_AUDIO"

    # Show individual source details if available
    if [ -s "${INSIGHT_PERPLEXITY_FILE:-}" ]; then
        _detail="$(cat "$INSIGHT_PERPLEXITY_FILE")"
        echo ""
        _show_and_speak "WEB DETAILS — PERPLEXITY" "🌐" "$_detail" "$INSIGHT_DIR/perplexity_detail.mp3"
        rm -f "$INSIGHT_PERPLEXITY_FILE"
    fi
    if [ -s "${INSIGHT_GROK_FILE:-}" ]; then
        _detail="$(cat "$INSIGHT_GROK_FILE")"
        echo ""
        _show_and_speak "WEB DETAILS — GROK" "🌐" "$_detail" "$INSIGHT_DIR/grok_detail.mp3"
        rm -f "$INSIGHT_GROK_FILE"
    fi

    _factcheck_done=1
}

# ─── Settings sub-menu ────────────────────────────────────────────────────────

_settings_flow() {
    while true; do
        echo ""
        _header "SETTINGS" "⚙"
        echo ""

        if [ -n "${PERPLEXITY_API_KEY:-}" ]; then
            _perplexity_status="${C_BGREEN}✓ key set${C_RESET}"
        else
            _perplexity_status="${C_RED}✗ key missing${C_RESET}"
        fi
        if [ -n "${XAI_API_KEY:-}" ]; then
            _grok_status="${C_BGREEN}✓ key set${C_RESET}"
        else
            _grok_status="${C_RED}✗ key missing${C_RESET}"
        fi
        printf "  Perplexity : %b\n" "$_perplexity_status"
        printf "  Grok       : %b\n" "$_grok_status"
        echo ""

        printf "  ${C_DIM}Summary${C_RESET}\n"
        printf "  ${C_BOLD}[1]${C_RESET} Reasoning (summary)   : ${C_BOLD}%s${C_RESET}  ${C_DIM}(standard · high)${C_RESET}\n" "$_SETTING_SUMMARY_REASONING"
        echo ""
        printf "  ${C_DIM}Search${C_RESET}\n"
        printf "  ${C_BOLD}[2]${C_RESET} Search engine          : ${C_BOLD}%s${C_RESET}  ${C_DIM}(auto · perplexity · grok · both)${C_RESET}\n" "$_SETTING_SEARCH_ENGINE"
        echo ""
        printf "  ${C_DIM}Fact-check${C_RESET}\n"
        printf "  ${C_BOLD}[3]${C_RESET} Fact-check engines     : ${C_BOLD}%s${C_RESET}  ${C_DIM}(both · perplexity · grok)${C_RESET}\n" "$_SETTING_FACTCHECK_ENGINE"
        printf "  ${C_BOLD}[4]${C_RESET} Reasoning (synthesis)  : ${C_BOLD}%s${C_RESET}  ${C_DIM}(standard · high) — only when both engines active${C_RESET}\n" "$_SETTING_SYNTHESIS_REASONING"
        echo ""
        printf "  ${C_DIM}Translate${C_RESET}\n"
        local _tl_code="${_SETTING_TRANSLATE_LANG:-${TRANSLATE_TARGET_LANG:-en}}"
        printf "  ${C_BOLD}[5]${C_RESET} Target language        : ${C_BOLD}%s (%s)${C_RESET}  ${C_DIM}(type a code to change)${C_RESET}\n" \
            "$(_lang_name "$_tl_code")" "$_tl_code"
        echo ""
        printf "  ${C_BOLD}[m]${C_RESET} Back\n"
        printf "  ${C_BGREEN}▸${C_RESET} "
        read -r _set_choice
        case "$_set_choice" in
            1)
                if [ "$_SETTING_SUMMARY_REASONING" = "standard" ]; then
                    _SETTING_SUMMARY_REASONING="high"
                else
                    _SETTING_SUMMARY_REASONING="standard"
                fi
                _success "Summary reasoning → $_SETTING_SUMMARY_REASONING"
                ;;
            2)
                case "$_SETTING_SEARCH_ENGINE" in
                    auto)        _SETTING_SEARCH_ENGINE="perplexity" ;;
                    perplexity)  _SETTING_SEARCH_ENGINE="grok" ;;
                    grok)        _SETTING_SEARCH_ENGINE="both" ;;
                    *)           _SETTING_SEARCH_ENGINE="auto" ;;
                esac
                _success "Search engine → $_SETTING_SEARCH_ENGINE"
                ;;
            3)
                case "$_SETTING_FACTCHECK_ENGINE" in
                    both)        _SETTING_FACTCHECK_ENGINE="perplexity" ;;
                    perplexity)  _SETTING_FACTCHECK_ENGINE="grok" ;;
                    grok)        _SETTING_FACTCHECK_ENGINE="both" ;;
                    *)           _SETTING_FACTCHECK_ENGINE="both" ;;
                esac
                _success "Fact-check engines → $_SETTING_FACTCHECK_ENGINE"
                ;;
            4)
                if [ "$_SETTING_SYNTHESIS_REASONING" = "standard" ]; then
                    _SETTING_SYNTHESIS_REASONING="high"
                else
                    _SETTING_SYNTHESIS_REASONING="standard"
                fi
                _success "Synthesis reasoning → $_SETTING_SYNTHESIS_REASONING"
                ;;
            5)
                printf "  Language code ${C_DIM}(en, fr, de, es, it, pt, nl, ru, zh, ja…)${C_RESET}: "
                read -r _new_lang
                if [ -n "$_new_lang" ]; then
                    _SETTING_TRANSLATE_LANG="$_new_lang"
                    # Persist to .env so the choice survives across sessions.
                    local _env_file="$SCRIPT_DIR/.env"
                    if [ -f "$_env_file" ]; then
                        if grep -q "^TRANSLATE_TARGET_LANG=" "$_env_file"; then
                            sed -i "s/^TRANSLATE_TARGET_LANG=.*/TRANSLATE_TARGET_LANG=$_new_lang/" "$_env_file"
                        else
                            printf '\nTRANSLATE_TARGET_LANG=%s\n' "$_new_lang" >> "$_env_file"
                        fi
                    fi
                    _success "Translate language → $(_lang_name "$_new_lang") ($_new_lang)  (saved to .env)"
                fi
                ;;
            m|M) return ;;
            *) ;;
        esac
    done
}

#!/bin/bash
# VoxRefiner — Web display helper (sourced by flow scripts).
#
# Starts a local HTTP+SSE server (src/web_display.py) and provides shell
# helpers to push events that the parallel browser window mirrors in real time.
#
# Activation: VOX_WEB_DISPLAY=1 in .env. When unset, all helpers are no-ops —
# the calling flow runs unchanged.
#
# Required globals from caller: SCRIPT_DIR, VENV_PYTHON.
#
# Exposed helpers:
#   _web_start <mode>                     — boot server + browser (idempotent)
#   _web_push_init <mode> [full_text]     — broadcast init event
#   _web_send_chunk <idx> <chunks_dir>    — push chunk text from chunks_dir/chunk_NNN.txt
#   _web_push_done                        — broadcast end-of-playback event
#   _web_push_error <message>             — broadcast an error event
#   _web_stop                             — kill server (idempotent)

# ─── State ────────────────────────────────────────────────────────────────────

_WEB_PORT=""
_WEB_PID=""

# ─── Internal: low-level POST ─────────────────────────────────────────────────

_web_push_raw() {
    # Usage: _web_push_raw <json_body>
    [ -z "${_WEB_PORT:-}" ] && return 0
    curl -s --max-time 0.5 -X POST \
        -H "Content-Type: application/json" \
        --data-binary "$1" \
        "http://127.0.0.1:${_WEB_PORT}/push" >/dev/null 2>&1 &
}

# ─── Lifecycle ────────────────────────────────────────────────────────────────

_web_start() {
    # Usage: _web_start <mode>
    [ "${VOX_WEB_DISPLAY:-0}" != "1" ] && return 0
    [ -n "${_WEB_PORT:-}" ] && return 0  # already started

    local mode="${1:-voice}"
    local size="${VOX_WEB_SIZE:-1100x800}"
    local pos="${VOX_WEB_POS:-100x100}"

    local port_file
    port_file="$(mktemp /tmp/vox-web-port-XXXXXX)"

    # Send Python stderr to FD 3 (saved terminal stderr) when available, so
    # browser launch diagnostics are visible. Falls back to /dev/null if FD 3
    # is not open (e.g. sourced from a script that didn't run `exec 3>&2`).
    if { true >&3; } 2>/dev/null; then
        "$VENV_PYTHON" -m src.web_display \
            --mode "$mode" --size "$size" --pos "$pos" \
            --port-file "$port_file" \
            >/dev/null 2>&3 &
    else
        "$VENV_PYTHON" -m src.web_display \
            --mode "$mode" --size "$size" --pos "$pos" \
            --port-file "$port_file" \
            >/dev/null 2>&1 &
    fi
    _WEB_PID=$!

    # Wait up to 2s for the port file
    local _i
    for _i in $(seq 1 20); do
        if [ -s "$port_file" ]; then
            _WEB_PORT="$(cat "$port_file")"
            break
        fi
        sleep 0.1
    done
    rm -f "$port_file"

    if [ -z "${_WEB_PORT:-}" ]; then
        kill "$_WEB_PID" 2>/dev/null
        _WEB_PID=""
        return 1
    fi
    return 0
}

_web_stop() {
    [ -z "${_WEB_PORT:-}" ] && return 0
    _web_push_raw '{"type":"shutdown"}'
    sleep 0.1
    if [ -n "${_WEB_PID:-}" ]; then
        kill -TERM "$_WEB_PID" 2>/dev/null
    fi
    _WEB_PORT=""
    _WEB_PID=""
}

# ─── Event push helpers ───────────────────────────────────────────────────────

_web_push_init() {
    # Usage: _web_push_init <mode> [full_text]
    [ -z "${_WEB_PORT:-}" ] && return 0
    local mode="${1:-voice}"
    local full_text="${2:-}"

    local body
    if [ -n "$full_text" ]; then
        body="$(VOX_INIT_MODE="$mode" VOX_INIT_FULL="$full_text" "$VENV_PYTHON" -c "
import json, os
print(json.dumps({
    'type': 'init',
    'payload': {'mode': os.environ['VOX_INIT_MODE'], 'full_text': os.environ['VOX_INIT_FULL']}
}))
" 2>/dev/null)"
    else
        body="{\"type\":\"init\",\"payload\":{\"mode\":\"$mode\"}}"
    fi

    [ -n "$body" ] && _web_push_raw "$body"
}

_web_send_chunk() {
    # Usage: _web_send_chunk <idx> <chunks_dir>
    [ -z "${_WEB_PORT:-}" ] && return 0
    local idx="$1" dir="$2"
    local text_file
    text_file="$(printf '%s/chunk_%03d.txt' "$dir" "$idx")"
    [ -f "$text_file" ] || return 0

    local body
    body="$(VOX_CHUNK_IDX="$idx" VOX_CHUNK_FILE="$text_file" "$VENV_PYTHON" -c "
import json, os
with open(os.environ['VOX_CHUNK_FILE'], encoding='utf-8') as f:
    text = f.read()
print(json.dumps({
    'type': 'chunk',
    'payload': {'idx': int(os.environ['VOX_CHUNK_IDX']), 'text': text}
}))
" 2>/dev/null)"

    [ -n "$body" ] && _web_push_raw "$body"
}

_web_push_done() {
    [ -z "${_WEB_PORT:-}" ] && return 0
    _web_push_raw '{"type":"done"}'
}

_web_push_error() {
    # Usage: _web_push_error <message>
    [ -z "${_WEB_PORT:-}" ] && return 0
    local msg="${1:-error}"
    local body
    body="$(VOX_ERR="$msg" "$VENV_PYTHON" -c "
import json, os
print(json.dumps({'type':'error','payload':{'message': os.environ['VOX_ERR']}}))
" 2>/dev/null)"
    [ -n "$body" ] && _web_push_raw "$body"
}

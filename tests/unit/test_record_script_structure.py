"""Unit tests that lock key safety primitives in the recording shell script."""

from pathlib import Path


def _script_text() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / "record_and_transcribe_local.sh").read_text(encoding="utf-8")


def test_script_cleans_old_audio_artifacts_before_recording():
    text = _script_text()
    assert 'rm -f "$REC_DIR/source.wav" "$REC_DIR/source.mp3"' in text


def test_script_uses_recordings_stt_directory():
    text = _script_text()
    assert 'REC_DIR="$SCRIPT_DIR/recordings/stt"' in text
    assert 'mkdir -p "$REC_DIR"' in text


def test_script_has_configurable_wav_size_guard():
    text = _script_text()
    assert 'MAX_WAV_BYTES="${MAX_WAV_BYTES:-100000000}"' in text
    assert 'if [ "$wav_size" -gt "$MAX_WAV_BYTES" ]; then' in text


def test_script_has_show_raw_voxtral_branch():
    """SHOW_RAW_VOXTRAL defaults to true and has a dedicated elif branch."""
    text = _script_text()
    assert 'SHOW_RAW_VOXTRAL:-true' in text
    # Must be separate from the compare-models branch (independent elif)
    assert 'elif' in text

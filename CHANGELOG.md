<!-- @format -->

# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.5.0] — 2026-03-08

### Added

- `history.txt`: optional auto-generated context file built from MEDIUM/LONG refinements
  - Enable with `ENABLE_HISTORY=true` in `.env` (opt-in, off by default)
  - Extracts contextual facts (projects, tools, decisions, topics) from refined text
  - Injected into the system prompt for all tiers to improve refinement relevance
  - Configurable: `HISTORY_MAX_BULLETS` (default 60), `HISTORY_EXTRACTION_MODEL` (default `magistral-small-latest`)
  - **Clipboard-first architecture:** extraction runs in the background via `--update-history` CLI flag,
    launched by the shell script **after** the clipboard is populated — never delays the paste operation
  - Added `history.txt` to `.gitignore` (personal file, stays local)
  - Added `history.example.txt` to document the expected format

### Changed

- Default SHORT threshold reduced to **90 words** (was 100) — 100 was too permissive; notes of 90–99 words were routed to MEDIUM unnecessarily
- All 3 system prompts now include an explicit **anti-prompt-injection guard**: the model is instructed to treat `<transcription>` content as raw voice data, never as directives (fixes cases where the AI followed apparent instructions contained in a long transcription)
- Updated `.env.example` and Readme routing table (90 / 240)

---

## [1.4.0] — 2026-03-06

### Added

- `docs/model-selection.md`: rationale and test observations for model and threshold choices per tier (SHORT / MEDIUM / LONG)
- Model comparison testing via OpenWebUI documented for all 3 tiers

### Changed

- Default routing thresholds updated: SHORT < 100 words (was 80), LONG ≥ 240 words (was 200)
- Updated `.env.example` and Readme routing table to reflect new thresholds (100 / 240)

### Decision

- All primary models confirmed after OpenWebUI testing: `devstral-small-latest` (SHORT), `magistral-small-latest` (MEDIUM), `magistral-medium-latest` (LONG)

---

## [1.2.1] — 2026-03-06

### Fixed

- API error body (first 200 chars) now logged to stderr on 429 / 500 / 503, replacing the generic "unavailable, switching..." message — makes rate limiting and server errors easier to diagnose

---

## [1.2.0] — 2026-03-06

### Added

- 3 distinct system prompt templates by tier (SHORT / MEDIUM / LONG)
- XML tags: `<transcription>` wraps user input in the user message; `<context>` wraps domain context in the system prompt
- Prose quality instruction for LONG tier (> 200 words): "well-structured written prose — fluid and precise, while staying true to the speaker's voice and register"
- Deployment section in CONTRIBUTING.md (rsync usage, chmod warning)
- Updating section in README

### Fixed

- Language rule strengthened: `CRITICAL: Never translate. Detect the language of the transcription and reply in that exact same language.`
- Context block moved to end of each prompt (after all instructions) to avoid the "Lost in the Middle" attention drop

### Changed

- Installation guide in README: `git clone` directly to `~/.local/bin/voxtral-paste/`, explicit `chmod +x` step
- `.markdownlint.json` added to suppress MD013 / MD024 false positives in CHANGELOG and CONTRIBUTING

---

## [1.1.0] — 2026-03-06

### Added

- 3-tier model routing based on transcription length:
  - < 80 words → `devstral-small-latest` (fast)
  - 80–200 words → `magistral-small-latest` (balanced)
  - > 200 words → `magistral-medium-latest` (deep reasoning)
- Configurable thresholds and models via `.env` (`REFINE_MODEL_THRESHOLD_SHORT`, `REFINE_MODEL_THRESHOLD_LONG`, etc.)
- Correct fallback message displayed in terminal when primary model is unavailable

### Fixed

- `AttributeError: 'list' object has no attribute 'strip'` — reasoning models (magistral) return `content` as a list of blocks; now handled properly
- Fallback terminal message was never displayed due to a logic bug — now shows `⚠️ primary unavailable — switching to fallback: <model>`

### Changed

- Medium tier fallback set to `mistral-medium-latest` (was `mistral-small-latest`)
- Updated `.env.example` and README routing table to reflect 3-tier structure

---

## [1.0.1] — 2026-03-05

### Added

- MIT License (`LICENSE` file) with copyright notice
- License badge in README
- License section at the bottom of README

### Fixed

- `setsid rec` — isolates the recording process into its own session to prevent double SIGINT on Ctrl+C

---

## [1.0.0] — 2026-03-05

### Added

- Initial release
- Full voice-to-text pipeline: record → speed up → silence removal → MP3 → Voxtral transcription → Mistral refinement → clipboard
- 2-tier model routing (short / long) with fallback chain
- `context.txt` for user domain vocabulary injection into the refinement prompt
- Graceful degradation: returns raw transcription if all models fail
- `.env` configuration with `.env.example` template
- `launch_voxtral.example.sh` for keyboard shortcut setup (multi-terminal documented)
- `.gitignore` excluding `.env`, `launch_voxtral.sh`, audio files

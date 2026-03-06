<!-- @format -->

# Model Selection — Decisions & Rationale

This document records the reasoning behind the model choices and routing thresholds
used in Voxtral Paste. It will be updated as further testing is done.

---

## Routing thresholds

| Parameter                      | Initial value | Current value | Changed in |
| ------------------------------ | ------------- | ------------- | ---------- |
| `REFINE_MODEL_THRESHOLD_SHORT` | 80            | **100**       | v1.4.0     |
| `REFINE_MODEL_THRESHOLD_LONG`  | 200           | **240**       | v1.4.0     |

**Rationale for 100 (was 80):**
80 words felt too short to trigger the MEDIUM tier for notes that were clearly more
than a quick command (e.g. a 85-word bug note would stay in SHORT and receive only
minimal cleanup). 100 words is the minimum useful boundary where a reformulation
pass genuinely adds value over a simple cleanup.

**Rationale for 240 (was 200):**
200 words was considered slightly conservative for the MEDIUM tier. 240 words (~1 min 45 s
of speech) better matches a "developed thought / full paragraph" before switching to
the heavier LONG model. Values above ~300 were judged too high (risk of under-using
LONG on genuine extended monologues).

---

## Tier 1 — SHORT (< 100 words)

| Role     | Model                   |
| -------- | ----------------------- |
| Primary  | `devstral-small-latest` |
| Fallback | `mistral-small-latest`  |

**Why devstral-small:**
Initially questioned because devstral is code-oriented. Testing showed this is
actually an advantage: short notes are frequently technical (endpoint names, variable
names, shell commands, Python syntax). Devstral correctly preserves technical
formatting — for example `/users/{ID}` in FastAPI path notation, where a
general-purpose model substituted `<ID>` (incorrect HTML-style placeholder).

Mistral Nemo (tested as stand-in for mistral-small) produced that substitution error;
devstral-small did not. **devstral-small-latest confirmed as primary.**

> Further testing needed: direct comparison devstral-small vs mistral-small-latest
> on non-technical short notes (personal reminders, shopping lists, etc.).

---

## Tier 2 — MEDIUM (100–240 words)

| Role     | Model                    |
| -------- | ------------------------ |
| Primary  | `magistral-small-latest` |
| Fallback | `mistral-medium-latest`  |

**Why magistral-small over mistral-medium:**
Both models were compared on the same transcription (~130 words, French,
refactoring proposal). Key observations:

- `mistral-medium-2508`: over-formalised the output, shifted first-person suggestions
  ("je pense qu'on devrait") to assertive declarations ("je propose de"). Changed the
  speaker's register and nuance.
- `magistral-small-2509`: cleaned hesitations and repetitions faithfully, kept the
  speaker's voice and uncertainty intact ("je pense qu'on devrait", "ça nous
  permettrait").

The prompt explicitly requires _"staying true to the speaker's voice and register"_.
Magistral Small respected this constraint better. **magistral-small-latest confirmed.**

---

## Tier 3 — LONG (> 240 words)

| Role     | Model                     |
| -------- | ------------------------- |
| Primary  | `magistral-medium-latest` |
| Fallback | `mistral-large-latest`    |

**Why magistral-medium over mistral-large:**
Both models were compared on the same extended transcription (~350 words, French,
architecture review with 3 distinct points). Key observations:

- `mistral-large-2411`: produced fluent, well-structured output but systematically
  shifted the narrator from "je" to "nous" throughout ("nous avons accumulé",
  "nous sommes obligés"). The original used first person singular. This is a
  significant fidelity error — the model reframed a personal note as a collective
  statement.
- `magistral-medium-2509`: preserved the first-person voice, used precise technical
  terms (`try-except` with correct dash, `Pydantic Settings` with correct casing),
  produced clean transitions (Premièrement / Deuxièmement / Enfin), and was more
  concise without losing content.

**magistral-medium-latest confirmed as primary.**

Mistral Large remains the fallback: when magistral-medium is unavailable, its output
quality is still acceptable despite the "nous" drift.

> Further testing needed: mistral-large on English content (the "nous" phenomenon
> may be specific to French); comparison with magistral-large-latest.

---

## Summary table (current defaults)

| Tier   | Words   | Primary                   | Fallback                | Status           |
| ------ | ------- | ------------------------- | ----------------------- | ---------------- |
| SHORT  | < 100   | `devstral-small-latest`   | `mistral-small-latest`  | Partially tested |
| MEDIUM | 100–240 | `magistral-small-latest`  | `mistral-medium-latest` | Confirmed ✅     |
| LONG   | > 240   | `magistral-medium-latest` | `mistral-large-latest`  | Confirmed ✅     |

All values are overridable via `.env` — see `.env.example` for the full list of
configurable parameters.

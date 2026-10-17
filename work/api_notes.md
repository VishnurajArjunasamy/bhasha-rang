# Sarvam API notes (read from docs.sarvam.ai on 2026-10-17)

Sources: `https://docs.sarvam.ai/llms.txt` and the `.md` versions of the pages linked below.
SDK: `sarvamai` **0.1.37** (latest on PyPI; `pip install sarvamai`). Signatures below were checked with
`inspect.signature` against the installed package.

## Auth, base URL, errors

- Base URL `https://api.sarvam.ai`, header `api-subscription-key: <key>`.
- SDK: `SarvamAI(api_subscription_key=...)`.
- Error body: `{"error": {"request_id", "message", "code"}}`. Codes include `rate_limit_exceeded_error` (429),
  `insufficient_quota_error`, `invalid_api_key_error` (403), `internal_server_error` (500), `gateway_timeout_error`.
  Retry 429/5xx with exponential backoff; don't retry 400/403/422.

## Text translation: Mayura (`POST /translate`)

- SDK: `client.text.translate(input, source_language_code, target_language_code, speaker_gender=None,
  mode=None, model=None, output_script=None, numerals_format=None)` → `.translated_text`.
- Models: `mayura:v1` (11 languages: en, hi, bn, gu, kn, ml, mr, od, pa, ta, te; source `auto` allowed) and
  `sarvam-translate:v1` (23 languages, formal mode only).
- `mode`: `formal` (default), `modern-colloquial`, `classic-colloquial`, `code-mixed` (all on Mayura only).
  Tested on real bubbles: `modern-colloquial` leaves many English words ("इसे disappear कर दो? Easy!"),
  `formal` is clean but stiff, and `classic-colloquial` is the most natural ("और तो और … फफोले भी पड़ जाएँगे!").
  **We use `classic-colloquial`**, and retry a bubble in `formal` when English words remain.
- `speaker_gender`: `Male` / `Female`. Used for Hindi verb agreement, so we set it per character.
- Limit: **1000 characters** per request on Mayura (2000 on sarvam-translate).
- **No context / glossary parameter.** Each bubble is translated independently. Character names are fixed up
  afterwards with a per-language glossary in `config.yaml`, and suspect output is flagged in `work/report.md`.
- hi-IN ✅, te-IN ✅.

## Text-to-speech: Bulbul (`POST /text-to-speech`)

- SDK: `client.text_to_speech.convert(text, language_code, speaker=None, pace=None, speech_sample_rate=None,
  model=None, output_audio_codec=None, temperature=None, ...)` → `.audios` (list of base64 strings).
- **Current model: `bulbul:v4-flash`** ("latest, recommended for new integrations"). `bulbul:v3` is still the
  API default when `model` is omitted and remains available on the API. The Bulbul v3 **end of life (10 Nov 2026)
  applies to Voice Agents only**, not to this TTS API. `bulbul:v2` is legacy.
- v4-flash uses persona voice IDs `<name>_<lang>_<style>` (222 voices). v3 short names like `shubh` are **not**
  valid on v4-flash. Default persona is `shubh_enhi_ads`.
  - Telugu has only **4** v4-flash personas: `kavitha_te_conversation`, `kavitha_te_narration`,
    `pooja_te_conversation`, `tarun_te_narration`.
  - Hindi has 116 (for example `ritu_hi_social_lively`, `roopa_hi_narration`, `chhavi_hi_kids`, `anand_hi_documentary`).
- Params on v3/v4-flash: `pace` 0.5–2.0 and `temperature` 0.01–1.0 (default 0.6). **`pitch` and `loudness` are not
  supported** (v2 only). No SSML.
- Limits: 2500 characters per REST request. `speech_sample_rate` can be 8000/16000/22050/24000/32000/44100/48000
  (default 22050). `output_audio_codec` can be wav/mp3/aac/flac/linear16 (opus errors).
- Use native script for Indic text; romanised input degrades quality.
- hi-IN ✅, te-IN ✅.

## Speech-to-text: Saaras (for Phase B)

- **Current model: `saaras:v4`** (default, recommended); `saaras:v3` is still available. Modes are `transcribe`,
  `translate`, `verbatim`, `translit` and `codemix`.
- REST `POST /speech-to-text`: max **30 s** audio, chunk-level timestamps (`with_timestamps`), no diarization.
- **Batch API**: up to 2 h, `with_diarization=True`, **chunk-level timestamps only (no word-level)**. Async job:
  initiate → upload → start → poll (SDK `wait_until_complete()` polls every 5 s) → download.
  → Our 30–60 s excerpt is over the REST limit, so **we use Batch** (diarization plus timestamps).
- `keyterms` (v4 only, up to 50 terms) can bias recognition toward names.

## Chat: Sarvam-105B (optional, for shortening dub lines)

- `sarvam-105b` / `sarvam-105b-conversations` with a 128K context, through `POST /v1/chat/completions` (SDK
  `client.chat.completions`). Same 11-language set as Mayura.

## Document intelligence: Sarvam Vision

- Only needed as a fallback to OCR. **Not needed**: Pepper&Carrot publishes clean per-bubble text in its SVG sources.

## Dubbing API (beta, Phase B compare)

- SDK `client.dubbing.create(source_language_code, target_language_codes=[...], export_options=["video","srt"],
  voice_cloning=True, num_speakers=N)` → `upload(upload_url, path)` → `start(job_id)` → poll `live-status` /
  `export-status` → signed download URLs.
- Inputs MP4/MOV/MKV/WebM/WAV/MP3/M4A. Starter plan: 2 GB / 1 h max. 12 Indian target languages. Beta access may need
  enabling on the key.

## Rate limits (Starter plan; per account, token bucket)

| API | Starter |
|---|---|
| Translate | 60 req/min |
| TTS REST | 60 req/min (**bulbul:v3: 30 req/min**) |
| STT REST | 60 req/min; Batch 20 req/min (poll ≥ 3–5 s) |
| Sarvam-105B | 40 req/min |

## Pricing (₹, used for the end-of-run estimate)

| Service | Price |
|---|---|
| Mayura / Sarvam-Translate | ₹20 per 10K chars |
| Bulbul v3 TTS | ₹30 per 10K chars (v4-flash isn't listed separately, so we assume the same) |
| STT (+translate) | ₹30/h; with diarization ₹45/h |
| Sarvam-105B | ₹15 in / ₹60 out per 1M tokens |
| Dubbing API | ₹40/min of source × target languages (Starter) |
| Document digitization | ₹0.5/page |

New accounts get ₹100 of free credit. The whole comic run (about 30 bubbles × 2 languages) costs well under ₹5.

## Language check

Hindi and Telugu are supported by every model we use: Mayura, Bulbul v3, Bulbul v4-flash, Saaras v4 and Dubbing.

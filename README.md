# Indic Dub & Translate: Sarvam AI workshop demo

Openly licensed English content translated and voiced in **Hindi** and **Telugu** with Sarvam AI:

- **Comic** (done): *Pepper&Carrot* Ep. 12 "Autumn Clearout" (David Revoy, CC BY 4.0). Each speech bubble is
  translated with **Mayura** and voiced with **Bulbul**, then shown over the original artwork.
- **Video** (Phase B, coming): a Blender open-movie excerpt transcribed with **Saaras**, translated and dubbed.

The site in `site/` is static, uses no CDNs, and works offline from pre-generated assets, including from `file://`.

## Setup

```bash
make setup                      # creates .venv and installs requirements (Python 3.10+, ffmpeg on PATH)
cp .env.example .env            # then put your key in it: SARVAM_API_KEY=...
make demo                       # runs all phases; cached results are reused (no credits spent on reruns)
make serve                      # http://localhost:8000/comic.html
make test                       # offline unit tests (API mocked)
```

The key is read from the `SARVAM_API_KEY` environment variable or from a `.env` file in this folder or its parent.
It is only needed when something isn't cached yet.

## Models used (see `work/api_notes.md`)

| Step | Model | Notes |
|---|---|---|
| Translation | `mayura:v1`, mode `classic-colloquial` | Retries in `formal` mode if English words remain. Speaker gender is passed per character. |
| Text-to-speech | **`bulbul:v4-flash`** (current recommended Bulbul) | Persona voices per character and language (`config.yaml`). Bulbul v3's 10 Nov 2026 end of life applies to Voice Agents, not to this API. |
| Speech-to-text | `saaras:v4` (Batch API) | Phase B. |

## How the comic pipeline works

1. `src/comic/fetch.py` downloads the episode's official SVG sources (clean text per bubble, so no OCR), the
   transcript, the artwork-only images, the English renders and the Noto fonts.
2. `src/comic/extract_text.py` writes `work/comic/<page>.json` with `id, panel, bbox, speaker, text_en`, plus the
   exact SVG transform of each text region. Speakers and reading order come from the transcript.
3. `src/comic/translate.py` runs Mayura per bubble, then applies the name glossary (Carrot stays క్యారెట్/कैरट
   rather than becoming "गाजर").
4. `src/comic/voice.py` runs Bulbul per bubble and writes `site/assets/audio/<lang>/<page>/<id>.mp3`.
5. `src/comic/build_page.py` writes `site/comic.html`: inline SVG bubbles with HTML text auto-fitted on top.
6. `work/report.md` lists validation issues: missing audio, empty translations, names that didn't survive translation.

Fix a bad line or speaker without code changes: `config.yaml` → `translation_overrides` / `speaker_overrides`.

## 5-minute demo script

1. **(30 s)** Open `comic.html` and show the English original. "Openly licensed comic, CC BY 4.0."
2. **(60 s)** Switch to **हिन्दी**, then **తెలుగు**. The text is machine-translated per bubble by Mayura and laid into the
   original bubbles.
3. **(60 s)** Click a Cayenne bubble, then a Pepper bubble: two different Bulbul voices. Press **▶ Play page**; the
   highlight follows the dialogue.
4. **(60 s)** Turn on **Side by side** to compare the original and the translation.
5. **(60 s)** Open `work/report.md` and `config.yaml` and show honestly what the machine got wrong and how a human fixes
   it with one config line.
6. **(30 s)** Costs: the whole comic in both languages cost about ₹11 in API credits, and reruns cost ₹0 (cache).

## Troubleshooting

- **`SARVAM_API_KEY is not set`**: export it or add it to `.env`. Cached steps still run without it.
- **429 / rate limit**: the client paces calls (`sarvam.min_interval_s`) and retries with exponential backoff.
  Lower the pace on Starter plans.
- **Indic text looks like boxes**: the fonts in `site/assets/fonts/` are missing. Rerun `make demo` (fetch step).
- **Text overflows a bubble**: check `work/report.md`, then shorten the line with `translation_overrides`.
- **Audio doesn't play from `file://`** in a locked-down browser: use `make serve`.

## License and attribution

See [ATTRIBUTION.md](ATTRIBUTION.md). The translations and voices are machine-generated derivative works made for a
workshop demo.

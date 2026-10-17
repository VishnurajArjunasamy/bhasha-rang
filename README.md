# Bhasha Rang · भाषा रंग

**Colours of language: stories retold in Hindi and Telugu with Sarvam AI.**

🔗 **Live demo:** https://bhasha-rang.vercel.app

Most of the world's stories reach Indian audiences only in English. Bhasha Rang is a workshop showcase that
asks how far today's Indian-language AI can close that gap, and where it still needs a human. It takes
openly licensed English stories and localises them end to end, text and voice, into **Hindi** and **Telugu**
using only [Sarvam AI](https://www.sarvam.ai) models:

| | What happens | Sarvam models |
|---|---|---|
| 📖 **Comic** (*live*) | *Pepper&Carrot* Ep. 12 "Autumn Clearout" by David Revoy (CC BY 4.0). Every speech bubble is translated, placed back into the original artwork, and spoken in a distinct voice per character, with click-to-play bubbles, "Play page" read-along and a side-by-side view of the original. | **Mayura** (translation), **Bulbul v4 Flash** (voices) |
| 🎬 **Film** (*in progress*) | A 30–60 s excerpt of a Blender open movie is transcribed, translated, dubbed with time-fitted voices and subtitled, then compared with Sarvam's own Dubbing API. | **Saaras v4** (speech-to-text), **Mayura**, **Bulbul**, **Dubbing (beta)** |

**What makes it a good demo:**
- **Honest:** the pipeline writes a report of what the machine got wrong (mistranslated names, idioms), and
  any line can be fixed with one line of `config.yaml`. Quality issues stay visible.
- **Reproducible and cheap:** every API response is cached, so one `make demo` rebuilds everything. The whole comic
  in two languages cost about ₹11, and reruns cost ₹0.
- **Works offline:** the static site has no CDNs and bundled Noto fonts, so it runs from `file://` on a projector
  with no Wi-Fi.
- **Respects the source:** only openly licensed content is used, with attribution on every page. The artwork is
  never edited; translations are layered on top.

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

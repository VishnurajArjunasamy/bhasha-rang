"""Translate each spoken bubble with Mayura into every target language -> work/comic/<page>.<lang>.json.

Mayura has no context/glossary parameter, so each bubble is translated on its own (speaker gender is
passed for correct verb agreement) and character names are normalised afterwards with the glossary.
"""
from __future__ import annotations

import re
import unicodedata

from ..common import WORK, load_config, read_json, write_json
from ..sarvam_client import SarvamClient


def latin_words(text: str) -> list[str]:
    """Words of 3+ Latin letters remaining in an Indic translation."""
    return re.findall(r"[A-Za-z]{3,}", text)


def apply_glossary(text_en: str, translated: str, lang: str, glossary: dict) -> tuple[str, list[str]]:
    """Replace literal translations of names with the agreed transliteration; flag names that went missing."""
    flags = []
    nfc = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731  (nukta letters have two encodings)
    translated = nfc(translated)
    for name, per_lang in glossary.items():
        entry = per_lang.get(lang)
        if not entry or not re.search(rf"\b{re.escape(name)}\b", text_en, re.IGNORECASE):
            continue
        for bad in sorted((nfc(a) for a in entry.get("avoid", [])), key=len, reverse=True):
            if bad and bad in translated:
                translated = translated.replace(bad, entry["name"])
        # also catch the name left in Latin script
        translated = re.sub(rf"\b{re.escape(name)}\b", entry["name"], translated, flags=re.IGNORECASE)
        if entry["name"] not in translated:
            flags.append(f"name '{name}' not found as '{entry['name']}' in translation")
    return translated, flags


def translate_page(page: str, lang: str, cfg: dict, client: SarvamClient) -> list[dict]:
    c = cfg["comic"]
    data = read_json(WORK / "comic" / f"{page}.json")
    overrides = c.get("translation_overrides") or {}
    out = []
    for b in data["bubbles"]:
        key = f"{page}.{b['id']}"
        if key in overrides and lang in overrides[key]:
            out.append({"id": b["id"], "text": overrides[key][lang], "source": "override", "flags": []})
            continue
        if not b["spoken"]:  # sound effects / punctuation-only: keep as drawn
            out.append({"id": b["id"], "text": b["text_en"], "source": "original", "flags": []})
            continue
        gender = c["characters"].get(b["speaker"], {}).get("gender")
        glossary = c.get("glossary") or {}
        raw = client.translate(b["text_en"], lang, speaker_gender=gender)
        text, flags = apply_glossary(b["text_en"], raw, lang, glossary)
        mode = cfg["sarvam"]["translate_mode"]
        fallback = cfg["sarvam"].get("translate_fallback_mode")
        if fallback and latin_words(text):  # colloquial modes sometimes keep English words
            raw2 = client.translate(b["text_en"], lang, speaker_gender=gender, mode=fallback)
            text2, flags2 = apply_glossary(b["text_en"], raw2, lang, glossary)
            if len(latin_words(text2)) < len(latin_words(text)):
                raw, text, flags, mode = raw2, text2, flags2, fallback
        if latin_words(text):
            flags.append(f"English words left in translation: {', '.join(latin_words(text))}")
        if not text.strip():
            flags.append("empty translation")
        out.append({"id": b["id"], "text": text, "raw": raw, "source": cfg["sarvam"]["translate_model"],
                    "mode": mode, "flags": flags})
    return out


def main(cfg: dict | None = None, client: SarvamClient | None = None) -> None:
    cfg = cfg or load_config()
    client = client or SarvamClient(cfg)
    for page in cfg["comic"]["pages"]:
        for lang in (l["code"] for l in cfg["languages"]):
            res = translate_page(page, lang, cfg, client)
            write_json(WORK / "comic" / f"{page}.{lang}.json", res)
            nflag = sum(bool(r["flags"]) for r in res)
            print(f"[comic/translate] {page} {lang}: {len(res)} bubbles, {nflag} flagged")


if __name__ == "__main__":
    main()

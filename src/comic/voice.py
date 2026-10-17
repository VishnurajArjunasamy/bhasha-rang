"""Voice every translated spoken bubble with Bulbul -> site/assets/audio/<lang>/<page>/<id>.mp3.

Writes work/comic/<page>.<lang>.audio.json with voice, pace, file and duration per bubble.
"""
from __future__ import annotations

import shutil

from ..common import ASSETS, WORK, audio_duration, load_config, read_json, write_json
from ..sarvam_client import SarvamClient


def voice_page(page: str, lang: str, cfg: dict, client: SarvamClient) -> list[dict]:
    c = cfg["comic"]
    bubbles = {b["id"]: b for b in read_json(WORK / "comic" / f"{page}.json")["bubbles"]}
    translations = read_json(WORK / "comic" / f"{page}.{lang}.json")
    voices = c["voices"][lang]
    out = []
    for t in translations:
        b = bubbles[t["id"]]
        if not b["spoken"] or not t["text"].strip():
            continue
        speaker = voices.get(b["speaker"]) or voices.get("Narrator")
        pace = c["characters"].get(b["speaker"], {}).get("pace")
        cached = client.tts(t["text"], lang, speaker, pace=pace)
        dest = ASSETS / "audio" / lang / page / f"{t['id']}{cached.suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.stat().st_size != cached.stat().st_size:
            shutil.copyfile(cached, dest)
        out.append({"id": t["id"], "voice": speaker, "pace": pace, "model": cfg["sarvam"]["tts_model"],
                    "file": dest.relative_to(ASSETS.parent).as_posix(), "duration_s": audio_duration(dest)})
    return out


def main(cfg: dict | None = None, client: SarvamClient | None = None) -> None:
    cfg = cfg or load_config()
    client = client or SarvamClient(cfg)
    for page in cfg["comic"]["pages"]:
        for lang in (l["code"] for l in cfg["languages"]):
            res = voice_page(page, lang, cfg, client)
            keep = {r["id"] for r in res}
            for stale in (ASSETS / "audio" / lang / page).glob("*.*"):
                if stale.stem not in keep:  # e.g. a bubble later re-marked as a sound effect
                    stale.unlink()
            write_json(WORK / "comic" / f"{page}.{lang}.audio.json", res)
            print(f"[comic/voice] {page} {lang}: {len(res)} clips, {sum(r['duration_s'] for r in res):.1f}s total")


if __name__ == "__main__":
    main()

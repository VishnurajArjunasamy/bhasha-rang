"""Download Pepper&Carrot sources (CC BY 4.0, David Revoy) for the configured episode.

- lang/en/<page>.svg   : per-bubble English text + bubble shapes (from the official webcomics git repo)
- transcript.md        : speaker name + reading order per bubble
- gfx-only/<page>.jpg  : artwork without bubbles/text (we layer bubbles + translated text on top)
- en/<page>.jpg        : the author's original English render (shown in English / side-by-side view)
Also bundles Noto Sans Devanagari / Telugu (SIL OFL) so the site works offline.
"""
from __future__ import annotations

from ..common import ASSETS, WORK, download, load_config

FONTS = {
    "NotoSansDevanagari": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth,wght%5D.ttf",
    "NotoSansTelugu": "https://github.com/google/fonts/raw/main/ofl/notosanstelugu/NotoSansTelugu%5Bwdth,wght%5D.ttf",
    "NotoSans": "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf",
}
FONT_LICENSE = "https://github.com/google/fonts/raw/main/ofl/notosans/OFL.txt"


def episode_number(episode: str) -> str:
    return episode.split("_")[0].replace("ep", "")


def image_name(kind: str, page: str) -> str:
    # kind: "gfx" (artwork only) or a language code like "en"
    return f"{kind}_Pepper-and-Carrot_by-David-Revoy_{page}.jpg"


def main(cfg: dict | None = None) -> None:
    cfg = cfg or load_config()
    c = cfg["comic"]
    ep, res = c["episode"], c["image_res"]
    raw = f"{c['source_repo_raw']}/{ep}"
    srcdir = WORK / "comic" / "src"
    print(f"[comic/fetch] {ep} pages {c['pages']}")
    download(f"{raw}/info.json", srcdir / "info.json")
    download(f"{raw}/lang/en/ep{episode_number(ep)}_en_transcript.md", srcdir / "transcript.en.md")
    for page in c["pages"]:
        download(f"{raw}/lang/en/{page}.svg", srcdir / f"{page}.svg")
        download(f"{c['site_sources']}/{ep}/{res}/gfx-only/{image_name('gfx', page)}",
                 ASSETS / "comic" / f"{page}_art.jpg")
        download(f"{c['site_sources']}/{ep}/{res}/{image_name('en', page)}",
                 ASSETS / "comic" / f"{page}_en.jpg")
    for name, url in FONTS.items():
        download(url, ASSETS / "fonts" / f"{name}.ttf")
    download(FONT_LICENSE, ASSETS / "fonts" / "OFL.txt")


if __name__ == "__main__":
    main()

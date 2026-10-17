"""Build site/comic.html: original page vs. translated overlay, per-bubble audio, "Play page".

Rendering: each page's SVG source is stripped of its text and inlined (artwork + vector speech
bubbles). Translated text is laid on top as HTML boxes using the exact SVG transform of each original
text region, then auto-fit in the browser. Everything is inlined or relative, so it works from file://.
"""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET

from ..common import ASSETS, SITE, WORK, load_config, read_json, write_json

NS = {
    "": "http://www.w3.org/2000/svg",
    "xlink": "http://www.w3.org/1999/xlink",
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
}
for _p, _u in NS.items():
    ET.register_namespace(_p, _u)
SVG = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

# Rough average glyph advance as a fraction of font size, per script (for the build-time fit estimate).
CHAR_WIDTH = {"latin": 0.55, "deva": 0.62, "telu": 0.70}
LINE_HEIGHT = 1.25
MIN_SCALE = 0.45


def script_of(text: str) -> str:
    if re.search(r"[ఀ-౿]", text):
        return "telu"
    if re.search(r"[ऀ-ॿ]", text):
        return "deva"
    return "latin"


def estimate_font_size(text: str, box_w: float, box_h: float, base: float,
                       min_scale: float = MIN_SCALE) -> tuple[float, bool]:
    """Largest font size <= base (stepping down 6%) at which `text` word-wraps into the box.

    Returns (size, fits). Mirrors the browser-side fit loop; used for the build report and tests.
    """
    cw = CHAR_WIDTH[script_of(text)]
    words = text.split() or [""]
    size = base
    while True:
        max_chars = max(1, int(box_w / (cw * size)))
        lines, cur = 1, 0
        too_wide = False
        for w in words:
            n = len(w)
            if n > max_chars:
                too_wide = True
            if cur == 0:
                cur = n
            elif cur + 1 + n <= max_chars:
                cur += 1 + n
            else:
                lines, cur = lines + 1, n
        fits = not too_wide and lines * size * LINE_HEIGHT <= box_h
        if fits or size * 0.94 < base * min_scale:
            return round(size, 1), fits
        size *= 0.94


def textless_svg(page: str, data: dict) -> str:
    """Page SVG with all text removed and the artwork pointing at the local image."""
    root = ET.parse(WORK / "comic" / "src" / f"{page}.svg").getroot()
    parent = {c: p for p in root.iter() for c in p}
    for el in list(root.iter()):
        tag = el.tag.split("}")[-1]
        if tag in ("flowRoot", "text", "metadata", "namedview") and el in parent:
            parent[el].remove(el)
    for img in root.iter(f"{SVG}image"):
        img.set(XLINK_HREF, f"assets/comic/{page}_art.jpg")
    w, h = data["width"], data["height"]
    for k in ("width", "height"):
        root.attrib.pop(k, None)
    root.set("viewBox", f"0 0 {w:g} {h:g}")
    root.set("class", "art")
    svg = ET.tostring(root, encoding="unicode")
    return re.sub(r"\s(sodipodi|inkscape):[\w-]+=\"[^\"]*\"", "", svg)  # editor-only attributes


def page_payload(page: str, cfg: dict, report: list[str]) -> dict:
    data = read_json(WORK / "comic" / f"{page}.json")
    langs = [l["code"] for l in cfg["languages"]]
    tr = {lang: {t["id"]: t for t in read_json(WORK / "comic" / f"{page}.{lang}.json")} for lang in langs}
    au = {lang: {a["id"]: a for a in read_json(WORK / "comic" / f"{page}.{lang}.audio.json")} for lang in langs}
    bubbles = []
    for b in data["bubbles"]:
        base = b["font_size"] or 36.0
        entry = {"id": b["id"], "speaker": b["speaker"], "spoken": b["spoken"], "matrix": b["matrix"],
                 "box": b["box"], "base": base, "color": b.get("color") or "#141414", "en": b["text_en"], "text": {}, "audio": {}, "voice": {}}
        for lang in langs:
            t = tr[lang].get(b["id"])
            entry["text"][lang] = t["text"] if t else b["text_en"]
            a = au[lang].get(b["id"])
            if a:
                entry["audio"][lang] = a["file"]
                entry["voice"][lang] = a["voice"]
            if b["spoken"]:
                size, fits = estimate_font_size(entry["text"][lang], b["box"][0], b["box"][1], base)
                if not fits:
                    report.append(f"- {page}.{b['id']} [{lang}] text may overflow its bubble even at "
                                  f"{int(MIN_SCALE * 100)}% size: {entry['text'][lang]!r}")
        bubbles.append(entry)
    order = [b["id"] for b in sorted(data["bubbles"], key=lambda x: x["position"]) if b["spoken"]]
    return {"page": page, "w": data["width"], "h": data["height"], "svg": textless_svg(page, data),
            "original": f"assets/comic/{page}_en.jpg", "bubbles": bubbles, "order": order}


def render_html(payload: dict, cfg: dict) -> str:
    c = cfg["comic"]
    langs = [{"code": "en", "label": "English"}] + [{"code": l["code"], "label": l["label"]} for l in cfg["languages"]]
    fonts = {l["code"]: l["font"] for l in cfg["languages"]}
    tpl = (SITE.parent / "src" / "site" / "templates" / "comic.html").read_text(encoding="utf-8")
    data_js = json.dumps({"pages": payload, "langs": langs, "fonts": fonts}, ensure_ascii=False)
    data_js = data_js.replace("</", "<\\/")  # keep inline SVG markup from closing the <script>
    return (tpl.replace("{{TITLE}}", html.escape(c["episode_title"]))
               .replace("{{DATA}}", data_js))


def main(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    report: list[str] = []
    payload = [page_payload(p, cfg, report) for p in cfg["comic"]["pages"]]
    out = SITE / "comic.html"
    out.write_text(render_html(payload, cfg), encoding="utf-8")
    write_json(WORK / "comic" / "fit_report.json", report)
    print(f"[comic/build] wrote {out.relative_to(SITE.parent)} ({len(payload)} pages, "
          f"{len(report)} possible text-fit issues)")
    return report


if __name__ == "__main__":
    main()

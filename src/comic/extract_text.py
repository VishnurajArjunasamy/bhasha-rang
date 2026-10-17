"""Extract speech-bubble text per page into work/comic/<page>.json.

Text + bubble geometry come from the official SVG sources (no OCR needed). Speaker names and reading
order come from the episode transcript, matched to SVG text objects by their (whitespace-free) text.
Panels are detected from white gutters in the artwork image.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from ..common import ASSETS, WORK, load_config, write_json

SVG = "{http://www.w3.org/2000/svg}"

# --- transforms ---------------------------------------------------------------------------------
Matrix = tuple  # (a, b, c, d, e, f) as in SVG matrix()

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mat_mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def parse_transform(s: str | None) -> Matrix:
    m = IDENTITY
    if not s:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "matrix":
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:
                t = mat_mul(mat_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        else:
            continue
        m = mat_mul(m, t)
    return m


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def transformed_bbox(m: Matrix, x: float, y: float, w: float, h: float) -> list[float]:
    pts = [apply(m, px, py) for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [round(min(xs), 1), round(min(ys), 1), round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1)]


# --- transcript ---------------------------------------------------------------------------------
def parse_transcript(md: str) -> dict[str, list[dict]]:
    """{page_suffix ('P01'): [{name, position, concat, text}]}"""
    pages: dict[str, list[dict]] = {}
    cur = None
    for line in md.splitlines():
        m = re.match(r"###\s+(P\d+)", line)
        if m:
            cur = m.group(1)
            pages[cur] = []
            continue
        if cur and "|" in line and not line.startswith(("Name|", "----")):
            cols = line.split("|")
            if len(cols) >= 4 and cols[1].strip().isdigit():
                pages[cur].append({"name": cols[0].strip(), "position": int(cols[1]),
                                   "concat": cols[2].strip() == "True", "text": cols[3].strip()})
    return pages


def norm_key(text: str) -> str:
    return re.sub(r"\s+", "", text)


# --- svg ----------------------------------------------------------------------------------------
def _style_font_size(el) -> float | None:
    for node in el.iter():
        m = re.search(r"font-size:\s*([\d.]+)px", node.get("style") or "")
        if m and float(m.group(1)) > 1:
            return float(m.group(1))
    return None


def _style_fill(el) -> str | None:
    """Text colour: the deepest explicit fill inside the text object (paragraph styles win)."""
    fill = None
    for node in el.iter():
        if node.tag.endswith("rect"):
            continue
        m = re.search(r"(?:^|;)\s*fill:\s*(#[0-9a-fA-F]{3,6})", node.get("style") or "")
        if m:
            fill = m.group(1)
    return fill


def svg_text_objects(svg_path: Path) -> tuple[list[dict], float, float]:
    root = ET.parse(svg_path).getroot()
    width, height = float(root.get("width")), float(root.get("height"))
    parent = {c: p for p in root.iter() for c in p}

    def ctm(el) -> Matrix:
        chain = []
        while el is not None:
            chain.append(el)
            el = parent.get(el)
        m = IDENTITY
        for node in reversed(chain):
            m = mat_mul(m, parse_transform(node.get("transform")))
        return m

    objs = []
    for fr in root.iter(f"{SVG}flowRoot"):
        rect = fr.find(f"{SVG}flowRegion/{SVG}rect")
        paras = ["".join(p.itertext()) for p in fr.iter(f"{SVG}flowPara")]
        text = re.sub(r"\s+", " ", "".join(paras)).strip()
        if not text or rect is None:
            continue
        m = ctm(fr)
        x, y, w, h = (float(rect.get(k)) for k in ("x", "y", "width", "height"))
        m_rect = mat_mul(m, parse_transform(rect.get("transform")))
        full = mat_mul(m_rect, (1, 0, 0, 1, x, y))  # maps the w x h text box at the origin onto the page
        objs.append({"svg_id": fr.get("id"), "text": text, "bbox": transformed_bbox(m_rect, x, y, w, h),
                     "matrix": [round(v, 5) for v in full], "box": [round(w, 2), round(h, 2)],
                     "font_size": _style_font_size(fr), "color": _style_fill(fr), "scale": round(math.sqrt(abs(m[0] * m[3] - m[1] * m[2])), 3)})
    return objs, width, height


# --- panels -------------------------------------------------------------------------------------
def _runs(flags: list[bool], min_len: int) -> list[tuple[int, int]]:
    """Runs of False (content) separated by runs of True (gutter) of at least min_len."""
    out, start, gap = [], None, 0
    for i, g in enumerate(flags + [True] * min_len):
        if not g:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_len:
                out.append((start, i - gap + 1))
                start, gap = None, 0
    return out


def detect_panels(image_path: Path, svg_w: float) -> list[list[float]]:
    """Panel boxes [x, y, w, h] in SVG units, in reading order (rows top->bottom, left->right)."""
    from PIL import Image

    img = Image.open(image_path).convert("L")
    small = img.resize((img.width // 4, img.height // 4))
    w, h = small.size
    px = small.load()
    white = lambda v: v > 235  # noqa: E731

    def row_is_gutter(y, x0=0, x1=None):
        x1 = x1 or w
        return sum(white(px[x, y]) for x in range(x0, x1)) > 0.97 * (x1 - x0)

    def col_is_gutter(x, y0, y1):
        return sum(white(px[x, y]) for y in range(y0, y1)) > 0.97 * (y1 - y0)

    k = svg_w / w
    panels = []
    for y0, y1 in _runs([row_is_gutter(y) for y in range(h)], 3):
        if y1 - y0 < 10:
            continue
        for x0, x1 in _runs([col_is_gutter(x, y0, y1) for x in range(w)], 3):
            if x1 - x0 >= 10:
                panels.append([round(x0 * k, 1), round(y0 * k, 1), round((x1 - x0) * k, 1), round((y1 - y0) * k, 1)])
    return panels


def panel_for(bbox: list[float], panels: list[list[float]]) -> int | None:
    cx, cy = bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2
    best, best_d = None, float("inf")
    for i, (x, y, w, h) in enumerate(panels):
        if x <= cx <= x + w and y <= cy <= y + h:
            return i + 1
        d = max(x - cx, 0, cx - x - w) + max(y - cy, 0, cy - y - h)
        if d < best_d:
            best, best_d = i + 1, d
    return best


# --- main ---------------------------------------------------------------------------------------
def extract_page(page: str, cfg: dict, transcript: dict) -> dict:
    c = cfg["comic"]
    objs, width, height = svg_text_objects(WORK / "comic" / "src" / f"{page}.svg")
    lines = transcript.get(page[-3:], [])
    by_key = defaultdict(list)
    for ln in sorted(lines, key=lambda l: l["position"]):
        by_key[norm_key(ln["text"])].append(ln)

    panels = detect_panels(ASSETS / "comic" / f"{page}_art.jpg", width)
    overrides = c.get("speaker_overrides") or {}
    bubbles, unmatched = [], []
    next_pos = max([l["position"] for l in lines], default=0) + 1
    for o in objs:
        cands = by_key.get(norm_key(o["text"]))
        if cands:
            ln = cands.pop(0)
        else:  # not in transcript: keep it, infer speaker, put it last in reading order
            ln = {"name": "Unknown", "position": next_pos, "concat": False, "text": o["text"]}
            next_pos += 1
            unmatched.append(o["text"])
        bid = f"b{ln['position']:02d}"
        speaker = overrides.get(f"{page}.{bid}", ln["name"])
        spoken = speaker not in c["non_spoken_speakers"] and bool(re.search(r"\w", ln["text"]))
        bubbles.append({
            "id": bid, "svg_id": o["svg_id"], "panel": panel_for(o["bbox"], panels), "bbox": o["bbox"],
            "speaker": speaker, "text_en": ln["text"], "position": ln["position"], "concat": ln["concat"],
            "spoken": spoken, "font_size": o["font_size"], "color": o["color"], "matrix": o["matrix"], "box": o["box"],
        })
    bubbles.sort(key=lambda b: b["position"])
    return {"page": page, "width": width, "height": height, "panels": panels,
            "bubbles": bubbles, "unmatched_svg_text": unmatched}


def main(cfg: dict | None = None) -> None:
    cfg = cfg or load_config()
    transcript = parse_transcript((WORK / "comic" / "src" / "transcript.en.md").read_text(encoding="utf-8"))
    for page in cfg["comic"]["pages"]:
        data = extract_page(page, cfg, transcript)
        write_json(WORK / "comic" / f"{page}.json", data)
        n_spoken = sum(b["spoken"] for b in data["bubbles"])
        print(f"[comic/extract] {page}: {len(data['bubbles'])} text objects ({n_spoken} spoken), "
              f"{len(data['panels'])} panels, unmatched={len(data['unmatched_svg_text'])}")


if __name__ == "__main__":
    main()

"""Run every phase idempotently: `python -m src.run_all [--only comic]`.

Cached API results are reused, so reruns are free and work offline once cache/ is populated.
"""
from __future__ import annotations

import argparse

from .common import ASSETS, WORK, load_config, read_json
from .comic import build_page, extract_text, fetch, translate, voice
from .sarvam_client import MissingApiKey, SarvamClient


def validate_comic(cfg: dict) -> list[str]:
    issues = []
    langs = [l["code"] for l in cfg["languages"]]
    for page in cfg["comic"]["pages"]:
        data = read_json(WORK / "comic" / f"{page}.json")
        if data["unmatched_svg_text"]:
            issues.append(f"- {page}: SVG text not found in transcript (speaker inferred): {data['unmatched_svg_text']}")
        for lang in langs:
            tr = {t["id"]: t for t in read_json(WORK / "comic" / f"{page}.{lang}.json")}
            au = {a["id"]: a for a in read_json(WORK / "comic" / f"{page}.{lang}.audio.json")}
            for b in data["bubbles"]:
                t = tr.get(b["id"])
                if not t or not t["text"].strip():
                    issues.append(f"- {page}.{b['id']} [{lang}] empty or missing translation")
                    continue
                for flag in t.get("flags", []):
                    issues.append(f"- {page}.{b['id']} [{lang}] {flag}: {t['text']!r}")
                if b["spoken"]:
                    a = au.get(b["id"])
                    if not a or not (ASSETS.parent / a["file"]).exists():
                        issues.append(f"- {page}.{b['id']} [{lang}] missing audio")
    return issues


def write_report(sections: dict[str, list[str]]) -> None:
    lines = ["# Pipeline report", ""]
    for title, items in sections.items():
        lines += [f"## {title}", ""] + (items or ["- no issues"]) + [""]
    (WORK / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_comic(cfg: dict, client: SarvamClient) -> dict[str, list[str]]:
    fetch.main(cfg)
    extract_text.main(cfg)
    translate.main(cfg, client)
    voice.main(cfg, client)
    fit = build_page.main(cfg)
    return {"Comic: validation": validate_comic(cfg), "Comic: text fit": fit}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["comic"], help="run a single phase")
    args = ap.parse_args()
    cfg = load_config()
    client = SarvamClient(cfg)
    sections: dict[str, list[str]] = {}
    try:
        sections.update(run_comic(cfg, client))
    except MissingApiKey as e:
        print(f"ERROR: {e}")
        raise SystemExit(2)
    finally:
        print(client.stats.summary(cfg["sarvam"]["price_inr"]))
    write_report(sections)
    n = sum(len(v) for v in sections.values())
    print(f"\nReport: work/report.md ({n} items). Open site/comic.html or run `make serve`.")


if __name__ == "__main__":
    main()

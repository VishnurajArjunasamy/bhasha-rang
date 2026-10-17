"""Thin wrapper around the `sarvamai` SDK: disk cache, retries with backoff, pacing, call/cost stats.

Every response is cached under cache/<kind>/<sha256(request)>.* so reruns cost nothing and the demo
works offline. The API key is only needed (and only loaded) on a cache miss.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from .common import CACHE, ROOT, read_json, write_json

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class MissingApiKey(RuntimeError):
    pass


def _parse_env_file(path: Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def load_api_key() -> str:
    """SARVAM_API_KEY from the environment, else from a .env in the repo root or its parent."""
    key = os.environ.get("SARVAM_API_KEY")
    if key:
        return key
    for d in (ROOT, ROOT.parent):
        env_file = d / ".env"
        if env_file.exists():
            env = _parse_env_file(env_file)
            if env.get("SARVAM_API_KEY"):
                return env["SARVAM_API_KEY"]
            if env.get("SARVAM_KEY"):  # tolerated alias; prefer SARVAM_API_KEY
                print(f"  note: using SARVAM_KEY from {env_file}; please rename it to SARVAM_API_KEY")
                return env["SARVAM_KEY"]
    raise MissingApiKey(
        "SARVAM_API_KEY is not set. Export it or put `SARVAM_API_KEY=...` in .env "
        "(see .env.example). Cached results work without a key; this call was not cached."
    )


def cache_key(kind: str, params: dict) -> str:
    blob = json.dumps({"kind": kind, **params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


@dataclass
class Stats:
    calls: dict = field(default_factory=dict)       # kind -> real API calls
    cache_hits: dict = field(default_factory=dict)  # kind -> cache hits
    chars: dict = field(default_factory=dict)       # kind -> billable chars (real calls only)
    retries: int = 0

    def add(self, d: dict, kind: str, n: int = 1):
        d[kind] = d.get(kind, 0) + n

    def summary(self, prices: dict) -> str:
        cost = (self.chars.get("translate", 0) / 10_000 * prices.get("translate_per_10k_chars", 0)
                + self.chars.get("tts", 0) / 10_000 * prices.get("tts_per_10k_chars", 0))
        lines = ["", "=== Sarvam API usage (this run) ==="]
        for kind in sorted(set(self.calls) | set(self.cache_hits)):
            lines.append(f"  {kind:10s} calls={self.calls.get(kind, 0):4d}  cache_hits={self.cache_hits.get(kind, 0):4d}"
                         f"  billable_chars={self.chars.get(kind, 0)}")
        lines.append(f"  retries={self.retries}")
        lines.append(f"  estimated cost this run: ₹{cost:.2f} (docs pricing; estimate only)")
        return "\n".join(lines)


class SarvamClient:
    def __init__(self, cfg: dict, cache_dir: Path = CACHE, sdk_client=None, sleep=time.sleep):
        self.cfg = cfg["sarvam"]
        self.cache_dir = cache_dir
        self._sdk = sdk_client
        self._sleep = sleep
        self._last_call: dict[str, float] = {}
        self.stats = Stats()

    # -- plumbing -----------------------------------------------------------------------------
    @property
    def sdk(self):
        if self._sdk is None:
            from sarvamai import SarvamAI
            self._sdk = SarvamAI(api_subscription_key=load_api_key())
        return self._sdk

    def _pace(self, kind: str):
        gap = self.cfg.get("min_interval_s", {}).get(kind, 0)
        wait = self._last_call.get(kind, 0) + gap - time.monotonic()
        if wait > 0:
            self._sleep(wait)
        self._last_call[kind] = time.monotonic()

    def _call(self, kind: str, fn):
        max_retries = self.cfg.get("max_retries", 5)
        for attempt in range(max_retries + 1):
            self._pace(kind)
            try:
                return fn()
            except Exception as e:  # SDK raises ApiError (status_code) or httpx errors
                status = getattr(e, "status_code", None)
                transient = status in RETRYABLE_STATUS or (status is None and _is_network_error(e))
                if not transient or attempt == max_retries:
                    body = getattr(e, "body", None)
                    raise RuntimeError(f"Sarvam {kind} failed (status={status}): {body or e}") from e
                delay = min(60.0, 2 ** attempt) + random.uniform(0, 0.5)
                retry_after = (getattr(e, "headers", None) or {}).get("retry-after")
                if retry_after and str(retry_after).isdigit():
                    delay = max(delay, float(retry_after))
                self.stats.retries += 1
                print(f"  {kind}: transient error (status={status}); retry {attempt + 1}/{max_retries} in {delay:.1f}s")
                self._sleep(delay)

    # -- APIs ---------------------------------------------------------------------------------
    def translate(self, text: str, target: str, source: str = "en-IN", speaker_gender: str | None = None,
                  mode: str | None = None, model: str | None = None) -> str:
        params = {
            "input": text, "source_language_code": source, "target_language_code": target,
            "model": model or self.cfg["translate_model"], "mode": mode or self.cfg["translate_mode"],
        }
        if speaker_gender:
            params["speaker_gender"] = speaker_gender
        path = self.cache_dir / "translate" / f"{cache_key('translate', params)}.json"
        if path.exists():
            self.stats.add(self.stats.cache_hits, "translate")
            return read_json(path)["translated_text"]
        resp = self._call("translate", lambda: self.sdk.text.translate(**params))
        self.stats.add(self.stats.calls, "translate")
        self.stats.add(self.stats.chars, "translate", len(text))
        write_json(path, {"request": params, "translated_text": resp.translated_text,
                          "request_id": getattr(resp, "request_id", None)})
        return resp.translated_text

    def tts(self, text: str, language: str, speaker: str, pace: float | None = None,
            model: str | None = None) -> Path:
        """Synthesize speech; returns path to the cached audio file."""
        codec = self.cfg.get("tts_codec", "mp3")
        params = {
            "text": text, "language_code": language, "speaker": speaker,
            "model": model or self.cfg["tts_model"], "output_audio_codec": codec,
            "speech_sample_rate": self.cfg.get("tts_sample_rate", 24000),
        }
        if pace:
            params["pace"] = pace
        key = cache_key("tts", params)
        audio_path = self.cache_dir / "tts" / f"{key}.{codec}"
        if audio_path.exists():
            self.stats.add(self.stats.cache_hits, "tts")
            return audio_path
        resp = self._call("tts", lambda: self.sdk.text_to_speech.convert(**params))
        self.stats.add(self.stats.calls, "tts")
        self.stats.add(self.stats.chars, "tts", len(text))
        audio = b"".join(base64.b64decode(a) for a in resp.audios)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(audio)
        write_json(audio_path.with_suffix(".json"), {"request": params, "request_id": getattr(resp, "request_id", None)})
        return audio_path


def _is_network_error(e: Exception) -> bool:
    name = type(e).__name__.lower()
    return any(s in name for s in ("timeout", "connect", "network", "remoteprotocol", "readerror"))

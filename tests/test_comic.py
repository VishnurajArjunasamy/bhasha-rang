"""Offline tests: caching, glossary, text fit, SVG geometry. No real API calls."""
import base64
import types

import pytest

from src.comic.build_page import estimate_font_size
from src.comic.extract_text import mat_mul, parse_transcript, parse_transform, transformed_bbox
from src.comic.translate import apply_glossary, latin_words
from src.sarvam_client import SarvamClient, cache_key

CFG = {"sarvam": {"translate_model": "mayura:v1", "translate_mode": "classic-colloquial", "tts_model": "bulbul:v4-flash",
                  "tts_codec": "mp3", "max_retries": 2, "min_interval_s": {}}}


class FakeSDK:
    def __init__(self, fail_times=0, status=429):
        self.calls, self.fail_times, self.status = 0, fail_times, status
        self.text = types.SimpleNamespace(translate=self._translate)
        self.text_to_speech = types.SimpleNamespace(convert=self._tts)

    def _maybe_fail(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            err = Exception("boom")
            err.status_code = self.status
            raise err

    def _translate(self, **kw):
        self._maybe_fail()
        return types.SimpleNamespace(translated_text=f"T:{kw['input']}", request_id="r1")

    def _tts(self, **kw):
        self._maybe_fail()
        return types.SimpleNamespace(audios=[base64.b64encode(b"ID3fake").decode()], request_id="r2")


def test_translate_is_cached(tmp_path):
    sdk = FakeSDK()
    c = SarvamClient(CFG, cache_dir=tmp_path, sdk_client=sdk, sleep=lambda s: None)
    assert c.translate("hello", "hi-IN") == "T:hello"
    assert c.translate("hello", "hi-IN") == "T:hello"
    assert sdk.calls == 1 and c.stats.cache_hits["translate"] == 1
    # a fresh client (new run) still hits the disk cache, with no SDK at all
    c2 = SarvamClient(CFG, cache_dir=tmp_path, sdk_client=None)
    assert c2.translate("hello", "hi-IN") == "T:hello"


def test_cache_key_depends_on_params():
    assert cache_key("translate", {"input": "a", "mode": "formal"}) != cache_key("translate", {"input": "a", "mode": "x"})
    assert cache_key("translate", {"a": 1, "b": 2}) == cache_key("translate", {"b": 2, "a": 1})


def test_tts_cached_and_retried(tmp_path):
    sdk = FakeSDK(fail_times=2, status=429)
    c = SarvamClient(CFG, cache_dir=tmp_path, sdk_client=sdk, sleep=lambda s: None)
    p = c.tts("नमस्ते", "hi-IN", "ritu_hi_social_lively")
    assert p.read_bytes() == b"ID3fake" and c.stats.retries == 2
    c.tts("नमस्ते", "hi-IN", "ritu_hi_social_lively")
    assert sdk.calls == 3  # 2 failures + 1 success, then cache


def test_non_retryable_error_raises(tmp_path):
    c = SarvamClient(CFG, cache_dir=tmp_path, sdk_client=FakeSDK(fail_times=1, status=400), sleep=lambda s: None)
    with pytest.raises(RuntimeError):
        c.translate("x", "hi-IN")


GLOSSARY = {"Carrot": {"hi-IN": {"name": "कैरट", "avoid": ["गाजर"]}},
            "Chaosah": {"hi-IN": {"name": "केओसा", "avoid": ["चज़ाहा"]}}}


def test_glossary_replaces_literal_and_latin_names():
    assert apply_glossary("CARROT!", "गाजर!", "hi-IN", GLOSSARY) == ("कैरट!", [])
    assert apply_glossary("Carrot!", "Carrot!", "hi-IN", GLOSSARY)[0] == "कैरट!"


def test_glossary_handles_decomposed_nukta():
    decomposed = "चज़ाहा की"  # ज + nukta, as the API may return it
    text, flags = apply_glossary("witch of Chaosah", decomposed, "hi-IN", GLOSSARY)
    assert text == "केओसा की" and not flags


def test_glossary_flags_missing_name():
    _, flags = apply_glossary("witch of Chaosah", "अराजकता की", "hi-IN", GLOSSARY)
    assert flags and "Chaosah" in flags[0]


def test_latin_words():
    assert latin_words("इसे disappear कर दो? OK") == ["disappear"]


def test_text_fit_shrinks_long_text_and_keeps_short_text():
    assert estimate_font_size("हाँ!", 500, 180, 45) == (45, True)
    size, fits = estimate_font_size("बहुत लंबा वाक्य " * 6, 500, 180, 45)
    assert fits and size < 45
    size, fits = estimate_font_size("शब्द " * 200, 300, 60, 45)
    assert not fits and size >= 45 * 0.45 * 0.94


def test_transforms_and_bbox():
    m = mat_mul(parse_transform("translate(10,20)"), parse_transform("scale(2)"))
    assert transformed_bbox(m, 0, 0, 5, 5) == [10, 20, 10, 10]
    r = parse_transform("rotate(90)")
    assert [round(v, 6) for v in r[:4]] == [0, 1, -1, 0]


def test_parse_transcript():
    md = "### P01\n\nName|Position|Concatenate|Text|Whitespace (Optional)\n----|--|--|--|--\nPepper|2|True|Hi!\nSound|1|False|BOOM\n"
    assert parse_transcript(md) == {"P01": [
        {"name": "Pepper", "position": 2, "concat": True, "text": "Hi!"},
        {"name": "Sound", "position": 1, "concat": False, "text": "BOOM"}]}

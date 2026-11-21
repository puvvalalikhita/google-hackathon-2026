import asyncio
import base64
import re
import time
from collections import OrderedDict
from typing import Optional

try:
    import edge_tts
except ImportError:  # pragma: no cover
    edge_tts = None  # type: ignore

_TTS_CACHE: "OrderedDict[tuple[str, str], str]" = OrderedDict()
_TTS_CACHE_MAX = 64
_TTS_COOLDOWN_UNTIL = 0.0

GREETING_TEXT = (
    "Namaste Raju bhai, DeliverEx Live bol raha hoon — bataiye kis shop pe delivery hui?"
)


def _clean_text_for_speech(text: str, language: Optional[str] = None) -> str:
    """Normalizes currency, codes, and strips emojis so neural TTS speaks naturally in each language."""
    lang_low = (language or "").lower()
    if "hindi (hi)" in lang_low:
        rupee_word = "रुपये"
    elif "tamil (ta)" in lang_low:
        rupee_word = "ரூபாய்"
    elif "telugu (te)" in lang_low:
        rupee_word = "రూపాయలు"
    else:
        rupee_word = "rupees"
    cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf]+", " ", text or "")
    cleaned = re.sub(r"₹\s*([\d,]+)", rf"\1 {rupee_word}", cleaned)
    cleaned = re.sub(r"\bRs\.?\s*([\d,]+)\b", rf"\1 {rupee_word}", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bINV-(\d+)\b", r"invoice \1", cleaned)
    cleaned = re.sub(r"\bCUST-(\d+)\b", r"customer \1", cleaned)
    cleaned = re.sub(r"\bSOP-(\d+)\.(\d+)\b", r"S O P \1 point \2", cleaned)
    cleaned = re.sub(r"\s*—\s*", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def pick_neural_voice(text: str, language: Optional[str] = None) -> str:
    """Selects the most natural Indian neural voice for English, Hinglish, Hindi, Tanglish, or Tamil."""
    lang_low = (language or "").lower()
    if "hindi (hi)" in lang_low or sum(1 for ch in text if "\u0900" <= ch <= "\u097f") >= 2:
        return "hi-IN-SwaraNeural"
    if "tamil (ta)" in lang_low or sum(1 for ch in text if "\u0b80" <= ch <= "\u0bff") >= 2:
        return "ta-IN-PallaviNeural"
    if "telugu (te)" in lang_low or sum(1 for ch in text if "\u0c00" <= ch <= "\u0c7f") >= 2:
        return "te-IN-ShrutiNeural"
    if lang_low.startswith("english"):
        return "en-IN-NeerjaExpressiveNeural"
    # Romanized Hinglish / Tanglish read most naturally with the Indian-English neural voice
    return "en-IN-NeerjaNeural"


async def synthesize_speech_b64(
    text: str,
    language: Optional[str] = None,
) -> Optional[str]:
    """
    Synthesizes warm natural Indian neural speech (audio/mpeg base64) via edge-tts.
    Returns None cleanly if edge-tts is unavailable or network fails.
    """
    global _TTS_COOLDOWN_UNTIL
    if not edge_tts or not text or time.monotonic() < _TTS_COOLDOWN_UNTIL:
        return None

    spoken = _clean_text_for_speech(text, language)
    if not spoken:
        return None

    voice = pick_neural_voice(spoken, language)
    cache_key = (voice, spoken)
    if cache_key in _TTS_CACHE:
        _TTS_CACHE.move_to_end(cache_key)
        return _TTS_CACHE[cache_key]

    try:
        async def _synth(selected_voice: str) -> bytes:
            comm = edge_tts.Communicate(spoken, selected_voice, rate="+5%")
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    buf.extend(chunk["data"])
            return bytes(buf)

        audio_bytes = await asyncio.wait_for(_synth(voice), timeout=4.5)
        if not audio_bytes and voice != "en-IN-NeerjaNeural":
            audio_bytes = await asyncio.wait_for(_synth("en-IN-NeerjaNeural"), timeout=4.0)
        if not audio_bytes:
            return None

        b64 = base64.b64encode(audio_bytes).decode("ascii")
        _TTS_CACHE[cache_key] = b64
        while len(_TTS_CACHE) > _TTS_CACHE_MAX:
            _TTS_CACHE.popitem(last=False)
        return b64
    except Exception:
        _TTS_COOLDOWN_UNTIL = time.monotonic() + 45.0
        return None


async def prewarm_common_tts() -> None:
    """Pre-caches the initial live call greeting so clicking Start Live Call speaks immediately."""
    await synthesize_speech_b64(GREETING_TEXT, "Hinglish (HI+EN)")

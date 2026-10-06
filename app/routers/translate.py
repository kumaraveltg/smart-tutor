"""
English -> Tamil translation using free, open-source tools (no API key, no cost).

How it works
- The whole question is translated as one sentence, so the translator sees the
  full context (much better Tamil than translating small pieces).
- Formulas written between $...$ are swapped for markers like [1], [2] before
  translating, then put back exactly as typed. If a marker is lost or changed,
  that attempt is not trusted and the slower piece-by-piece method is used.
- Google Translate (via deep-translator) is tried first; MyMemory is the backup
  if Google refuses (for example when it asks you to slow down).
- Results are cached in Redis for 30 days.

Install once (in the main venv):
  pip install deep-translator
"""
import hashlib
import logging
import re
import time
from typing import Callable, Dict, List, Tuple

from deep_translator import GoogleTranslator, MyMemoryTranslator
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db  # <-- adjust to your project
from app.redis_client import cache_get_json, cache_set_json  # <-- adjust path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/translate", tags=["translate"])

CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

# Add a line here when you add a language: code -> (name, Google code, MyMemory code)
LANGUAGES: Dict[str, Tuple[str, str, str]] = {
    "ta": ("Tamil", "ta", "ta-IN"),
    # "hi": ("Hindi", "hi", "hi-IN"),
    # "te": ("Telugu", "te", "te-IN"),
}

# Anything between two dollar signs is a formula and stays exactly as typed.
_FORMULA = re.compile(r"(\$[^$]+\$)")
# A marker such as [3] (the translator may add spaces or use full-width brackets).
_MARKER = re.compile(r"[\[［]\s*(\d+)\s*[\]］]")


class TranslationError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


# ------------------------------------------------------------ the two translators
# Each "call" takes plain English text and returns the translated text.

def _with_retry(fn: Callable[[], str], tries: int = 3) -> str:
    for attempt in range(tries):
        try:
            return fn()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))  # wait a little, then try again
    return ""


def _google_call(language_code: str) -> Callable[[str], str]:
    translator = GoogleTranslator(source="en", target=LANGUAGES[language_code][1])

    def call(text: str) -> str:
        return _with_retry(lambda: translator.translate(text) or text)

    return call


def _sentence_chunks(text: str, max_len: int = 450) -> List[str]:
    """MyMemory accepts about 500 characters per request, so long text is split by sentence."""
    chunks, cur = [], ""
    for part in re.split(r"(?<=[.?!])\s+", text):
        if cur and len(cur) + 1 + len(part) > max_len:
            chunks.append(cur)
            cur = part
        else:
            cur = f"{cur} {part}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def _mymemory_call(language_code: str) -> Callable[[str], str]:
    translator = MyMemoryTranslator(source="en-US", target=LANGUAGES[language_code][2])

    def call(text: str) -> str:
        out = []
        for chunk in _sentence_chunks(text):
            out.append(_with_retry(lambda c=chunk: translator.translate(c) or c))
            time.sleep(0.3)
        return " ".join(out)

    return call


# ------------------------------------------------------------ formulas in and out

def _mask(text: str) -> Tuple[str, List[str]]:
    """Replace each $formula$ with a numbered marker."""
    formulas: List[str] = []

    def swap(match: re.Match) -> str:
        formulas.append(match.group(0))
        return f" [{len(formulas)}] "

    masked = _FORMULA.sub(swap, text)
    return re.sub(r"[ \t]{2,}", " ", masked).strip(), formulas


def _unmask(translated: str, formulas: List[str]) -> str:
    """Put the formulas back. Raises ValueError if any marker was lost, changed or repeated."""
    found = [int(n) for n in _MARKER.findall(translated)]
    if sorted(found) != list(range(1, len(formulas) + 1)):
        raise ValueError("formula markers were changed by the translator")
    result = _MARKER.sub(lambda m: formulas[int(m.group(1)) - 1], translated)
    result = re.sub(r"\s+([,.;:?!])", r"\1", result)  # no space before punctuation
    return re.sub(r"[ \t]{2,}", " ", result).strip()


def _piece_by_piece(text: str, call: Callable[[str], str]) -> str:
    """Slower fallback: translate only the words between formulas, one piece at a time."""
    parts = _FORMULA.split(text)
    for i, part in enumerate(parts):
        if _FORMULA.fullmatch(part) or not re.search(r"[A-Za-z]", part):
            continue
        lead = part[: len(part) - len(part.lstrip())]
        trail = part[len(part.rstrip()):]
        parts[i] = f"{lead}{call(part.strip()).strip()}{trail}"
        time.sleep(0.3)
    return "".join(parts)


def _translate_with(text: str, call: Callable[[str], str]) -> str:
    masked, formulas = _mask(text)
    if not formulas:
        return call(text).strip()
    # If the question itself contains text like "[1]", markers would be confused.
    if re.search(r"\[\s*\d+\s*\]", _FORMULA.sub("", text)):
        return _piece_by_piece(text, call).strip()
    try:
        return _unmask(call(masked), formulas)
    except ValueError as exc:
        logger.warning("%s; translating piece by piece instead", exc)
        return _piece_by_piece(text, call).strip()


# ------------------------------------------------------------ public function

def translate_text(db: Session, text: str, language_code: str = "ta") -> Tuple[str, bool]:
    """Returns (translation, was_cached). Raises TranslationError on failure."""
    if language_code not in LANGUAGES:
        raise TranslationError(f"Unsupported language: {language_code}", 400)

    text = (text or "").strip()
    if not text:
        raise TranslationError("Text is empty", 400)

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    key = f"translate:v2:{language_code}:{digest}"  # v2: older, lower-quality results are not reused

    cached = cache_get_json(key)
    if cached is not None:
        return cached, True

    translation = ""
    for name, make_call in (("google", _google_call), ("mymemory", _mymemory_call)):
        try:
            translation = _translate_with(text, make_call(language_code))
            if translation:
                break
        except Exception as exc:
            logger.warning("%s translate failed (%s)", name, exc)

    if not translation:
        raise TranslationError("Translation service unavailable")

    cache_set_json(key, translation, CACHE_TTL_SECONDS)
    return translation, False


class TranslateIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    language_code: str = "ta"


class TranslateOut(BaseModel):
    translation: str
    cached: bool


@router.post("", response_model=TranslateOut)
def translate(payload: TranslateIn, db: Session = Depends(get_db)):
    try:
        translation, cached = translate_text(db, payload.text, payload.language_code)
    except TranslationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return TranslateOut(translation=translation, cached=cached)
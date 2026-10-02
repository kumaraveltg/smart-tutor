"""
English -> target language translation using Claude.

- translate_text(db, text, language_code) is the reusable function (used by
  questions.py when a question is created).
- POST /translate exposes it as an endpoint.
- Matching glossary words are sent to the model so maths terms stay consistent.
- Results are cached in Redis. The key includes the glossary version, so editing
  the glossary automatically retires old cached translations.

Env vars:
  ANTHROPIC_API_KEY   required
  ANTHROPIC_MODEL     optional, default claude-sonnet-5-5
"""
import hashlib
import logging
import os
import re
from typing import Dict, Tuple

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db  # <-- adjust to your project
from app.models import GlossaryTerm, GlossaryTermTranslation  # <-- adjust path
from app.redis_client import cache_get_json, cache_set_json, get_version  # <-- adjust path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/translate", tags=["translate"])

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

# Add a line here when you add a language.
LANGUAGE_NAMES: Dict[str, str] = {
    "ta": "Tamil",
    # "hi": "Hindi",
    # "te": "Telugu",
}

_client = None


class TranslationError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _llm() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


def _glossary_matches(db: Session, text: str, language_code: str) -> Dict[str, str]:
    """Single-word glossary terms found in the text, with their translations."""
    words = {w.lower() for w in re.findall(r"[A-Za-z]+", text)}
    if not words:
        return {}
    rows = (
        db.query(GlossaryTerm.english_word, GlossaryTermTranslation.translated_word)
        .join(GlossaryTermTranslation, GlossaryTermTranslation.term_id == GlossaryTerm.id)
        .filter(
            GlossaryTerm.is_active.is_(True),
            GlossaryTermTranslation.language_code == language_code,
            GlossaryTerm.english_word.in_(words),
        )
        .all()
    )
    return {english: translated for english, translated in rows}


def _build_system_prompt(language: str, glossary: Dict[str, str]) -> str:
    prompt = (
        f"You translate school mathematics questions from English into {language}.\n"
        "Rules:\n"
        "- Keep all numbers, variables, symbols, units, and math expressions "
        "(including anything inside $...$ or LaTeX) exactly as written.\n"
        "- Keep the meaning and the question format; do not solve or explain the question.\n"
        "- Use natural wording a school student would understand.\n"
        "- Reply with the translation only, no notes or quotation marks."
    )
    if glossary:
        lines = "\n".join(f"- {en} = {tr}" for en, tr in sorted(glossary.items()))
        prompt += f"\n\nUse exactly these translations for these terms:\n{lines}"
    return prompt


def translate_text(db: Session, text: str, language_code: str = "ta") -> Tuple[str, bool]:
    """Returns (translation, was_cached). Raises TranslationError on failure."""
    language = LANGUAGE_NAMES.get(language_code)
    if language is None:
        raise TranslationError(f"Unsupported language: {language_code}", 400)

    text = (text or "").strip()
    if not text:
        raise TranslationError("Text is empty", 400)

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    key = f"translate:g{get_version('glossary')}:{language_code}:{digest}"

    cached = cache_get_json(key)
    if cached is not None:
        return cached, True

    glossary = _glossary_matches(db, text, language_code)

    try:
        response = _llm().messages.create(
            model=MODEL,
            max_tokens=1500,
            system=_build_system_prompt(language, glossary),
            messages=[{"role": "user", "content": text}],
        )
    except anthropic.APIError as exc:
        logger.error("translation failed: %s", exc)
        raise TranslationError("Translation service unavailable")

    translation = "".join(b.text for b in response.content if b.type == "text").strip()
    if not translation:
        raise TranslationError("Empty translation returned")

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

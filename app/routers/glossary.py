"""
Maths glossary routes (list words, get translations, add/update a word).

The two models GlossaryTerm and GlossaryTermTranslation live in app/models.py.
Put this file in app/routers/ and include it in main.py.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GlossaryTerm, GlossaryTermTranslation
from app.redis_client import bump_version, cache_delete, cache_get_json, cache_set_json

GLOSSARY_TERMS_KEY = "glossary:terms"
GLOSSARY_TTL_SECONDS = 3600


# --------------------------------------------------------------- schemas

class TermOut(BaseModel):
    id: int
    word: str


class TermCreate(BaseModel):
    english_word: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = None
    translations: Dict[str, str] = {}  # {"ta": "முக்கோணம்"}


# ---------------------------------------------------------------- router

router = APIRouter(prefix="/glossary", tags=["glossary"])


@router.get("/terms", response_model=List[TermOut])
def list_terms(db: Session = Depends(get_db)):
    """English words only. The React app loads this once and searches in memory."""
    cached = cache_get_json(GLOSSARY_TERMS_KEY)
    if cached is not None:
        return cached

    rows = (
        db.query(GlossaryTerm.id, GlossaryTerm.english_word)
        .filter(GlossaryTerm.is_active.is_(True))
        .order_by(GlossaryTerm.english_word)
        .all()
    )
    terms = [{"id": r.id, "word": r.english_word} for r in rows]
    cache_set_json(GLOSSARY_TERMS_KEY, terms, GLOSSARY_TTL_SECONDS)
    return terms


@router.get("/terms/{term_id}/translations")
def get_translations(
    term_id: int,
    languages: str = Query("ta", description="comma separated codes, e.g. ta,hi"),
    db: Session = Depends(get_db),
):
    """Translations of one picked word, only for the requested languages."""
    codes = [c.strip() for c in languages.split(",") if c.strip()]
    rows = (
        db.query(GlossaryTermTranslation)
        .filter(
            GlossaryTermTranslation.term_id == term_id,
            GlossaryTermTranslation.language_code.in_(codes),
        )
        .all()
    )
    return {r.language_code: r.translated_word for r in rows}


@router.post("/terms", response_model=TermOut)
def upsert_term(payload: TermCreate, db: Session = Depends(get_db)):
    """
    Create a word (or update it) with its translations.
    Also used to save a corrected auto-translation back into the glossary.
    """
    word = payload.english_word.strip().lower()
    if not word:
        raise HTTPException(status_code=400, detail="english_word is required")

    term = db.query(GlossaryTerm).filter(GlossaryTerm.english_word == word).first()
    if term is None:
        term = GlossaryTerm(english_word=word, category=payload.category)
        db.add(term)
        db.flush()
    elif payload.category:
        term.category = payload.category

    existing = {t.language_code: t for t in term.translations}
    for code, text in payload.translations.items():
        text = text.strip()
        if not text:
            continue
        if code in existing:
            existing[code].translated_word = text
        else:
            db.add(GlossaryTermTranslation(term_id=term.id, language_code=code, translated_word=text))

    db.commit()

    # Glossary changed: drop the cached word list and retire cached translations
    cache_delete(GLOSSARY_TERMS_KEY)
    bump_version("glossary")
    return TermOut(id=term.id, word=term.english_word)
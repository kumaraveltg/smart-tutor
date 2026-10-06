import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from sqlalchemy import inspect as sa_inspect
from app import models, schemas
from app.database import get_db
from app.models import Question, QuestionTranslation
from app.schemas import QuestionTranslationIn, QuestionTranslationOut, QuestionOut, QuestionListOut
from app.routers.translate import translate_text  # <-- adjust path if translate.py lives elsewhere

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/questions", tags=["Questions"])

# Level of a main question. In your tables chapters are level 1 and subchapters
# level 2, so change this to 3 if questions should continue that numbering.
MAIN_QUESTION_LEVEL = 1

# Languages filled in automatically when a question is created. Add more here.
AUTO_TRANSLATE_LANGUAGES = ("ta",)


def _set_level(db: Session, data: dict) -> None:
    """Main questions get MAIN_QUESTION_LEVEL; a sub-question is one level below its parent."""
    if data.get("parent_id"):
        parent = db.get(models.Question, data["parent_id"])
        if not parent:
            raise HTTPException(422, "Parent question not found")
        data["level_no"] = (parent.level_no or MAIN_QUESTION_LEVEL) + 1
    else:
        data["level_no"] = MAIN_QUESTION_LEVEL


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            422, "Chapter, subchapter, class, subject, medium or parent question was not found"
        )


def _clean_exercise(value) -> str | None:
    return (value or "").strip() or None


def _only_columns(data: dict) -> dict:
    """Keep only keys that are real columns on Question, so extra fields cannot crash a save."""
    cols = {a.key for a in sa_inspect(models.Question).mapper.column_attrs}
    return {k: v for k, v in data.items() if k in cols}


def _next_sort_order(db: Session, chapter_id, exercise_no, parent_id) -> int:
    """Next free position among questions with the same chapter, exercise and parent."""
    query = db.query(func.coalesce(func.max(models.Question.sort_order), 0)).filter(
        models.Question.chapter_id == chapter_id
    )
    query = query.filter(
        models.Question.exercise_no.is_(None) if exercise_no is None else models.Question.exercise_no == exercise_no
    )
     
    return (query.scalar() or 0) + 1


# ---------------------------------------------------------------- translations
# (helpers are defined before the routes that use them)

def db_list_question_translations(db: Session, question_id: int):
    return (
        db.query(QuestionTranslation)
        .filter(QuestionTranslation.question_id == question_id)
        .order_by(QuestionTranslation.lang_code)
        .all()
    )


def db_get_question_translation(db: Session, question_id: int, lang_code: str):
    return db.get(QuestionTranslation, (question_id, lang_code))


def db_upsert_question_translation(db, question_id, lang_code, text, user):
    now = datetime.now(timezone.utc)
    row = db_get_question_translation(db, question_id, lang_code)
    if row is None:
        row = QuestionTranslation(
            question_id=question_id,
            lang_code=lang_code,
            created_by=user,
            created_on=now,
        )
        db.add(row)
    row.question_text = text
    row.modified_by = user
    row.modified_on = now
    db.commit()
    db.refresh(row)
    return row


def db_delete_question_translation(db, question_id, lang_code) -> bool:
    row = db_get_question_translation(db, question_id, lang_code)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def _auto_translate(db: Session, question: models.Question) -> None:
    """Fill translations for a new question. Never fails the create."""
    for lang in AUTO_TRANSLATE_LANGUAGES:
        try:
            text, _ = translate_text(db, question.question_text, lang)
            db_upsert_question_translation(db, question.question_id, lang, text, "auto")
        except Exception as exc:
            db.rollback()
            logger.warning("auto-translate to %s failed for question %s: %s", lang, question.question_id, exc)


# ---------------------------------------------------------------- questions

@router.post("/", response_model=schemas.QuestionOut, status_code=201)
def create_question(question: schemas.QuestionCreate, db: Session = Depends(get_db)):
    data = question.model_dump()
    # adminApi.create sends created_by; fall back to modified_by if it is missing
    data["created_by"] = data.get("created_by") or data.get("modified_by")
    _set_level(db, data)
    data["exercise_no"] = _clean_exercise(data.get("exercise_no"))
    if data.get("sort_order") is None:  # left blank: put it last in its exercise
        data["sort_order"] = _next_sort_order(
            db, data.get("chapter_id"), data["exercise_no"], data.get("parent_id")
        )
    db_question = models.Question(**_only_columns(data))
    db.add(db_question)
    _commit(db)
    db.refresh(db_question)

    # English is saved; now fill the Tamil (and other) translations.
    # If translation fails the question is still created and can be edited later.
    _auto_translate(db, db_question)
    return db_question


@router.get("/", response_model=list[schemas.QuestionOut])
def list_questions(
    subchapter_id: int | None = None,
    chapter_id: int | None = None,
    skip: int = 0,
    limit: int = Query(5000, le=10000),
    db: Session = Depends(get_db),
):
    query = db.query(models.Question)
    if subchapter_id is not None:
        query = query.filter(models.Question.subchapter_id == subchapter_id)
    if chapter_id is not None:
        query = query.filter(models.Question.chapter_id == chapter_id)
    return (
        query.order_by(
            models.Question.exercise_no,
            models.Question.sort_order,
            models.Question.question_id,
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


# Question list for one subchapter, with the translated text for `lang`.
# It must stay ABOVE "/{question_id}" so "by-subchapter" is not read as an id.
@router.get("/by-subchapter", response_model=list[QuestionListOut])
def list_questions_by_subchapter(subchapter_id: int, lang: str = "en", db: Session = Depends(get_db)):
    rows = (
        db.query(Question, QuestionTranslation.question_text.label("t_text"))
        .outerjoin(
            QuestionTranslation,
            and_(
                QuestionTranslation.question_id == Question.question_id,
                QuestionTranslation.lang_code == lang,
            ),
        )
        .filter(Question.subchapter_id == subchapter_id)
        .order_by(Question.question_id)
        .all()
    )
    return [
        {
            "question_id": q.question_id,
            "question_text": q.question_text,            # English original
            "display_text": t_text or q.question_text,   # translated text if present
            "has_translation": t_text is not None,
        }
        for q, t_text in rows
    ]


# Trailing slash on purpose: adminApi.create('questions/bulk', ...) calls
# /admin/questions/bulk/ , so this avoids a 307 redirect.
@router.post("/bulk/", response_model=schemas.QuestionImportResult, status_code=201)
def import_questions(payload: schemas.QuestionImportRequest, db: Session = Depends(get_db)):
    """Create many main questions in one chapter (used by the Excel import).

    Each row carries its own exercise number. Rows with a problem are skipped
    and reported back; valid rows are saved.
    """
    who = payload.created_by or payload.modified_by
    created = 0
    errors: list[dict] = []
    next_order: dict = {}  # (chapter, exercise) -> last sort_order used in this import

    for position, row in enumerate(payload.items, start=2):  # Excel row 1 is the header
        text = (row.question_text or "").strip()
        if not text:
            errors.append({"row": row.row or position, "reason": "Question is empty"})
            continue

        exercise = _clean_exercise(row.exercise_no)
        key = (payload.chapter_id, exercise)
        if key in next_order:
            next_order[key] += 1
        else:
            next_order[key] = _next_sort_order(db, payload.chapter_id, exercise, None)

        db.add(
            models.Question(
                **_only_columns(
                    dict( 
                        exercise_no=exercise,
                        sort_order=next_order[key],
                        class_id=payload.class_id,
                        subject_id=payload.subject_id,
                        medium_id=payload.medium_id,
                        chapter_id=payload.chapter_id, 
                        question_text=text,
                        language_translation=(row.language_translation or "").strip() or None,
                        created_by=who,
                        modified_by=payload.modified_by or who,
                    )
                )
            )
        )
        created += 1

    _commit(db)
    return {"created": created, "errors": errors}


@router.get("/{question_id}", response_model=schemas.QuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db)):
    question = db.get(models.Question, question_id)
    if not question:
        raise HTTPException(404, "Question not found")
    return question


@router.put("/{question_id}", response_model=schemas.QuestionOut)
def update_question(question_id: int, question: schemas.QuestionCreate, db: Session = Depends(get_db)):
    db_question = db.get(models.Question, question_id)
    if not db_question:
        raise HTTPException(404, "Question not found")
    data = question.model_dump(exclude={"created_by"})  # never change who created it
    data["exercise_no"] = _clean_exercise(data.get("exercise_no"))
    if data.get("sort_order") is None:
        data.pop("sort_order", None)  # blank: keep the current position
    if data.get("parent_id") == question_id:
        raise HTTPException(422, "A question cannot be its own parent")
    _set_level(db, data)
    for field, value in _only_columns(data).items():
        setattr(db_question, field, value)
    _commit(db)
    db.refresh(db_question)
    return db_question


@router.delete("/{question_id}", status_code=204)
def delete_question(question_id: int, db: Session = Depends(get_db)):
    db_question = db.get(models.Question, question_id)
    if not db_question:
        raise HTTPException(404, "Question not found")
    try:
        # translations belong to the question, so remove them with it
        db.query(QuestionTranslation).filter(QuestionTranslation.question_id == question_id).delete()
        db.delete(db_question)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Delete its sub-questions and answers first")


# ---------------------------------------------------------------- translation routes

@router.get("/{question_id}/translations", response_model=list[QuestionTranslationOut])
def list_question_translations(question_id: int, db: Session = Depends(get_db)):
    return db_list_question_translations(db, question_id)


@router.get("/{question_id}/translations/{lang_code}", response_model=QuestionTranslationOut)
def get_question_translation(question_id: int, lang_code: str, db: Session = Depends(get_db)):
    row = db_get_question_translation(db, question_id, lang_code)
    if row is None:
        raise HTTPException(status_code=404, detail="Translation not found")
    return row


@router.put("/{question_id}/translations/{lang_code}", response_model=QuestionTranslationOut)
def upsert_question_translation(
    question_id: int,
    lang_code: str,
    payload: QuestionTranslationIn,
    db: Session = Depends(get_db),
):
    return db_upsert_question_translation(
        db, question_id, lang_code, payload.question_text, payload.modified_by
    )


@router.delete("/{question_id}/translations/{lang_code}", status_code=204)
def delete_question_translation(question_id: int, lang_code: str, db: Session = Depends(get_db)):
    if not db_delete_question_translation(db, question_id, lang_code):
        raise HTTPException(status_code=404, detail="Translation not found")
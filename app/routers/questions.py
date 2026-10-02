from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app import models, schemas
from app.database import get_db
from app.schemas import QuestionTranslationIn,QuestionTranslationOut,QuestionOut,QuestionListOut

router = APIRouter(prefix="/admin/questions", tags=["Questions"])

# Level of a main question. In your tables chapters are level 1 and subchapters
# level 2, so change this to 3 if questions should continue that numbering.
MAIN_QUESTION_LEVEL = 1


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


@router.post("/", response_model=schemas.QuestionOut, status_code=201)
def create_question(question: schemas.QuestionCreate, db: Session = Depends(get_db)):
    data = question.model_dump()
    # adminApi.create sends created_by; fall back to modified_by if it is missing
    data["created_by"] = data.get("created_by") or data.get("modified_by")
    _set_level(db, data)
    db_question = models.Question(**data)
    db.add(db_question)
    _commit(db)
    db.refresh(db_question)
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
    return query.order_by(models.Question.question_id).offset(skip).limit(limit).all()


# Trailing slash on purpose: adminApi.create('questions/bulk', ...) calls
# /admin/questions/bulk/ , so this avoids a 307 redirect.
@router.post("/bulk/", response_model=schemas.QuestionImportResult, status_code=201)
def import_questions(payload: schemas.QuestionImportRequest, db: Session = Depends(get_db)):
    """Create many main questions in one subchapter (used by the Excel import).

    Rows with a problem are skipped and reported back; valid rows are saved.
    """
    who = payload.created_by or payload.modified_by
    created = 0
    errors: list[dict] = []

    for position, row in enumerate(payload.items, start=2):  # Excel row 1 is the header
        text = (row.question_text or "").strip()
        if not text:
            errors.append({"row": row.row or position, "reason": "Question is empty"})
            continue
        db.add(
            models.Question(
                parent_id=None,
                level_no=MAIN_QUESTION_LEVEL,
                class_id=payload.class_id,
                subject_id=payload.subject_id,
                medium_id=payload.medium_id,
                chapter_id=payload.chapter_id,
                subchapter_id=payload.subchapter_id,
                question_text=text,
                language_translation=(row.language_translation or "").strip() or None,
                created_by=who,
                modified_by=payload.modified_by or who,
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
    if data.get("parent_id") == question_id:
        raise HTTPException(422, "A question cannot be its own parent")
    _set_level(db, data)
    for field, value in data.items():
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
        db.delete(db_question)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Delete its sub-questions and answers first")

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


@router.get("", response_model=list[QuestionListOut])
def list_questions(subchapter_id: int, lang: str = "en", db: Session = Depends(get_db)):
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
        .all()
    )
    return [
        {
            "question_id": q.question_id,
            "question_text": q.question_text,            # English original
            "display_text": t_text or q.question_text,   # Tamil if present
            "has_translation": t_text is not None,
        }
        for q, t_text in rows
    ]

@router.post("", response_model=QuestionOut)
def create_question(payload: QuestionIn, db: Session = Depends(get_db)):
    q = Question(**payload.model_dump(exclude={"modified_by"}))
    db.add(q)
    db.commit()
    db.refresh(q)

    for lang in ("ta",):  # add more languages here
        try:
            text = translate_text(q.question_text, target=lang)
            db_upsert_question_translation(db, q.question_id, lang, text, "auto")
        except Exception:
            pass  # don't fail the create if translation fails; admin can edit later
    return q            
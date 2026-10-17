import os
import uuid
from typing import List, Optional,Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File,BackgroundTasks
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from types import SimpleNamespace 

from app.database import get_db
from app.core.deps import get_current_user
from app.config import settings
from app import models
from app.models import Answer, AnswerStep, AnswerStepTranslation
from app.schemas import AnswerIn, AnswerOut, TranslatePreviewIn,AnswerImportIn,StepImportRow
import random, time
from app.routers.question_images import QuestionImage
from app.routers.translate import translate_text as shared_translate, TranslationError
from app import ai_index


router = APIRouter(prefix="/admin/answers", tags=["Answers"])

# English is the base. Tomorrow add Kannada here:  ["ta", "kn"]
TARGET_LANGUAGES = ["ta"]

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


# ---------- helpers ----------
def _role_name(user) -> str:
    role = getattr(user, "role", None)
    name = getattr(role, "role_name", "") if role is not None else ""
    return str(name).lower().replace("_", "").replace(" ", "")


def _user_id(user) -> int:
    """The logged-in user's id. Your User model may call it id or user_id."""
    uid = getattr(user, "user_id", None)
    if uid is None:
        uid = getattr(user, "id", None)
    if uid is None:
        raise HTTPException(401, "Could not find the logged-in user's id")
    return uid


def require_teacher(user):
    if _role_name(user) not in ("teacher", "superadmin"):
        raise HTTPException(403, "Only teachers can write answers")
    return user

_last_call = 0.0

def translate_text(db: Session, text: Optional[str], lang: str) -> Optional[str]:
    if not text:
        return text
    try:
        out, _ = shared_translate(db, text, lang)
        return out
    except Exception as exc:
        print(f"TRANSLATE FAILED ({lang}): {type(exc).__name__}: {exc}")
        return None

def translate_with_backoff(fn, text, lang, tries=5):
    for attempt in range(tries):
        try:
            return fn(text, lang)
        except Exception as e:
            if "TooManyRequests" not in type(e).__name__ and "429" not in str(e):
                raise
            time.sleep((2 ** attempt) + random.random())
    raise RuntimeError(f"Translation rate-limited after {tries} tries ({lang})")

def _fill_steps(db: Session, answer: Answer, steps_in, auto_translate: bool = True):
    answer.steps.clear()
    db.flush()
    for s in sorted(steps_in, key=lambda x: x.step_no):
        step = AnswerStep(
            step_no=s.step_no,
            step_text=s.step_text,
            images=list(s.images or []),
            graph=s.graph,
        )
        given = {t.language_code: t for t in (s.translations or [])}
        for lang in TARGET_LANGUAGES:
            t = given.get(lang)
            if t and t.step_text:
                ts = t.step_text
            elif auto_translate:
                ts = translate_text(db, s.step_text, lang)
            else:
                ts = None
            step.translations.append(AnswerStepTranslation(language_code=lang, step_text=ts))
        answer.steps.append(step)
    answer.step_count = len(answer.steps)


def _load(db: Session, answer_id: int) -> Answer:
    ans = (db.query(Answer)
             .options(selectinload(Answer.steps).selectinload(AnswerStep.translations))
             .filter(Answer.answer_id == answer_id).first())
    if not ans:
        raise HTTPException(404, "Answer not found")
    return ans


def _answer_image_folder(q, chapter) -> str:
    """c<class_id>/s<subject_id>/ch<chapter_id>/ex_<exercise>/answers"""
    ex = str(q.exercise_no).replace("/", "_").replace("\\", "_").strip()
    return f"c{q.class_id}/s{chapter.subject_lov_id}/ch{q.chapter_id}/ex_{ex}/answers"


# ---------- list ----------
@router.get("/", response_model=List[AnswerOut])
@router.get("", response_model=List[AnswerOut], include_in_schema=False)
def list_all_answers(question_id: Optional[int] = None,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    require_teacher(user)
    q = (db.query(Answer)
           .options(selectinload(Answer.steps).selectinload(AnswerStep.translations)))
    if question_id:
        q = q.filter(Answer.question_id == question_id)
    if _role_name(user) != "superadmin":
        q = q.filter(Answer.teacher_id == _user_id(user))
    return q.order_by(Answer.answer_id).all()


# ---------- lookups for the form (chapter -> exercise -> question) ----------
@router.get("/lookup/exercises/")
@router.get("/lookup/exercises", include_in_schema=False)
def lookup_exercises(chapter_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    require_teacher(user)
    rows = (db.query(models.Question.exercise_no)
              .filter(models.Question.chapter_id == chapter_id)
              .distinct().order_by(models.Question.exercise_no).all())
    return [r[0] for r in rows if r[0] is not None]


@router.get("/lookup/questions/")
@router.get("/lookup/questions", include_in_schema=False)
def lookup_questions(chapter_id: int, exercise_no: str,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    require_teacher(user)
    qs = (db.query(models.Question)
            .filter(models.Question.chapter_id == chapter_id,
                    models.Question.exercise_no == exercise_no)
            .order_by(models.Question.sort_order, models.Question.question_id).all())
    return [{"question_id": q.question_id,
             "sort_order": q.sort_order,
             "question_text": q.question_text} for q in qs]   # your column name


@router.get("/lookup/question/{question_id}")
def lookup_question(question_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    require_teacher(user)
    q = db.get(models.Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")
    imgs = (db.query(QuestionImage)
             .filter(QuestionImage.question_id == question_id).all())
    return {
        "question_id": q.question_id,
        "chapter_id": q.chapter_id,
        "exercise_no": q.exercise_no,
        "sort_order": q.sort_order,
        "question_text": q.question_text,
        "images": [i.image_path for i in imgs],               # your path column name
    }


# ---------- image upload for answer steps ----------
@router.post("/upload-image")
def upload_answer_image(question_id: int,
                        file: UploadFile = File(...),
                        db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)):
    require_teacher(user)
    q = db.get(models.Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, "Only png, jpg, gif or webp images are allowed")

    chapter = db.get(models.Chapter, q.chapter_id)
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    rel_folder = _answer_image_folder(q, chapter)
    abs_folder = os.path.join(settings.image_base_path, *rel_folder.split("/"))
    os.makedirs(abs_folder, exist_ok=True)

    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(abs_folder, name), "wb") as out:
        out.write(file.file.read())

    return {"path": f"{rel_folder}/{name}"}

def _is_rate_limit(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return "toomanyrequests" in s or "429" in s or "too many requests" in s


@router.post("/translate-preview/")
@router.post("/translate-preview", include_in_schema=False)
def translate_preview(data: TranslatePreviewIn,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    require_teacher(user)
    langs = [l for l in (data.languages or TARGET_LANGUAGES) if l in TARGET_LANGUAGES]

    dead_langs: set = set()
    attempted = succeeded = 0
    last_error = ""

    out = []
    for s in data.steps:
        text = (s.step_text or "").strip()
        items = []
        for lang in langs:
            translated, failed = "", False
            if text:
                if lang in dead_langs:
                    failed = True
                else:
                    attempted += 1
                    try:
                        translated, _ = shared_translate(db, text, lang)
                        succeeded += 1
                    except Exception as exc:
                        failed = True
                        dead_langs.add(lang)
                        last_error = str(exc) or type(exc).__name__
            items.append({"language_code": lang, "step_text": translated, "failed": failed})
        out.append({"translations": items})

    if attempted and not succeeded:
        raise HTTPException(502, f"Translation failed: {last_error}")
    return out

# ---------- by question ----------
@router.get("/by-question/{question_id}", response_model=List[AnswerOut])
def list_answers(question_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    require_teacher(user)
    return (db.query(Answer)
              .options(selectinload(Answer.steps).selectinload(AnswerStep.translations))
              .filter(Answer.question_id == question_id)
              .order_by(Answer.answer_id).all())


# ---------- single answer CRUD ----------
@router.get("/{answer_id}", response_model=AnswerOut)
def get_answer(answer_id: int, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    require_teacher(user)
    return _load(db, answer_id)


@router.post("/", response_model=AnswerOut)
@router.post("", response_model=AnswerOut, include_in_schema=False)
def create_answer(data: AnswerIn, background: BackgroundTasks, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_teacher(user)
    if not data.steps:
        raise HTTPException(400, "At least one step is required")
    ans = Answer(question_id=data.question_id, teacher_id=_user_id(user),
                 final_answer=data.final_answer)
    db.add(ans)
    db.flush()
    _fill_steps(db, ans, data.steps)
    db.commit()
    ans = _load(db, ans.answer_id)
    background.add_task(ai_index.index_answer_docs, ans.answer_id, ai_index.answer_to_docs(ans))
    return ans


@router.put("/{answer_id}", response_model=AnswerOut)
def update_answer(answer_id: int, data: AnswerIn,background: BackgroundTasks, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_teacher(user)
    ans = _load(db, answer_id)
    if ans.teacher_id != _user_id(user) and _role_name(user) != "superadmin":
        raise HTTPException(403, "You can edit only your own answers")
    ans.final_answer = data.final_answer
    _fill_steps(db, ans, data.steps)
    db.commit()
    ans = _load(db, answer_id)
    background.add_task(ai_index.index_answer_docs, ans.answer_id, ai_index.answer_to_docs(ans))
    return ans


@router.delete("/{answer_id}")
def delete_answer(answer_id: int,background: BackgroundTasks, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_teacher(user)
    ans = _load(db, answer_id)
    if ans.teacher_id != _user_id(user) and _role_name(user) != "superadmin":
        raise HTTPException(403, "You can delete only your own answers")
    db.delete(ans)
    db.commit()
    background.add_task(ai_index.delete_answer_index, answer_id)
    return {"ok": True}

# Trailing slash on purpose: adminApi.create('answers/bulk', ...) calls /admin/answers/bulk/
@router.post("/bulk/", status_code=201)
@router.post("/bulk", include_in_schema=False)
def import_answers(data: AnswerImportIn, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """Create one answer per question from Excel rows (one row = one step). No final answer needed."""
    require_teacher(user)
    uid = _user_id(user)
    errors: list = []

    # group the rows by question, keeping the order of the file
    groups: dict = {}
    for pos, it in enumerate(data.items, start=2):        # Excel row 1 is the header
        row_no = it.row or pos
        text = (it.step_text or "").strip()
        if not it.question_id:
            errors.append({"row": row_no, "reason": "Question ID is missing"})
        elif not text:
            errors.append({"row": row_no, "reason": "English step is empty"})
        else:
            groups.setdefault(it.question_id, []).append((row_no, it))

    created = 0
    for qid, rows in groups.items():
        first_row = rows[0][0]
        q = db.get(models.Question, qid)
        if not q or q.chapter_id != data.chapter_id:
            errors.append({"row": first_row, "reason": "Question not found in this chapter"})
            continue
        exists = (db.query(Answer.answer_id)
                    .filter(Answer.question_id == qid, Answer.teacher_id == uid).first())
        if exists:
            errors.append({"row": first_row,
                           "reason": "You already have an answer for this question; edit it instead"})
            continue
        try:
            with db.begin_nested():                       # one bad question does not stop the rest
                steps = [
                    SimpleNamespace(
                        step_no=n,
                        step_text=it.step_text.strip(),
                        images=[],
                        graph=None,
                        translations=[
                            SimpleNamespace(language_code=lang, step_text=(txt or "").strip() or None)
                            for lang, txt in (it.translations or {}).items()
                            if lang in TARGET_LANGUAGES
                        ],
                    )
                    for n, (_, it) in enumerate(rows, start=1)
                ]
                ans = Answer(question_id=qid, teacher_id=uid, final_answer="")
                db.add(ans)
                db.flush()
                _fill_steps(db, ans, steps, auto_translate=data.auto_translate)
            created += 1
        except Exception as exc:
            logger.warning("answer import failed for question %s: %s", qid, exc)
            errors.append({"row": first_row, "reason": "Could not save this answer"})

    db.commit()
    return {"created": created, "errors": errors}
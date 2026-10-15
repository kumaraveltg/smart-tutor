from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.core.deps import get_current_user
from app import models
from app.models import Answer, AnswerStep, AnswerStepTranslation
from app.schemas import AnswerIn, AnswerOut, TranslatePreviewIn

router = APIRouter(prefix="/admin/answers", tags=["Answers"])

TARGET_LANGUAGES = ["ta"]  # add more languages later


# ---------- helpers ----------
def _role_name(user) -> str:
    role = getattr(user, "role", None)
    name = getattr(role, "role_name", "") if role is not None else ""
    return str(name).lower().replace("_", "").replace(" ", "")


def require_teacher(user):
    if _role_name(user) not in ("teacher", "superadmin"):
        raise HTTPException(403, "Only teachers can write answers")
    return user


def translate_text(text: Optional[str], lang: str) -> Optional[str]:
    if not text:
        return text
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source="en", target=lang).translate(text)
    except Exception:
        return None


def _fill_steps(db: Session, answer: Answer, steps_in):
    answer.steps.clear()
    db.flush()
    for s in sorted(steps_in, key=lambda x: x.step_no):
        step = AnswerStep(step_no=s.step_no, step_text=s.step_text, hint_text=s.hint_text)
        given = {t.language_code: t for t in (s.translations or [])}
        for lang in TARGET_LANGUAGES:
            t = given.get(lang)
            # use what the teacher typed/edited; otherwise translate automatically
            ts = t.step_text if t and t.step_text else translate_text(s.step_text, lang)
            th = t.hint_text if t and t.hint_text else translate_text(s.hint_text, lang)
            step.translations.append(AnswerStepTranslation(
                language_code=lang, step_text=ts, hint_text=th))
        answer.steps.append(step)
    answer.step_count = len(answer.steps)


def _load(db: Session, answer_id: int) -> Answer:
    ans = (db.query(Answer)
             .options(selectinload(Answer.steps).selectinload(AnswerStep.translations))
             .filter(Answer.answer_id == answer_id).first())
    if not ans:
        raise HTTPException(404, "Answer not found")
    return ans


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
        q = q.filter(Answer.teacher_id == user.user_id)
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
    imgs = (db.query(models.QuestionImage)                    # your image model name
              .filter(models.QuestionImage.question_id == question_id).all())
    return {
        "question_id": q.question_id,
        "chapter_id": q.chapter_id,
        "exercise_no": q.exercise_no,
        "sort_order": q.sort_order,
        "question_text": q.question_text,
        "images": [i.image_path for i in imgs],               # your path column name
    }


# ---------- translation preview ----------
@router.post("/translate-preview/")
@router.post("/translate-preview", include_in_schema=False)
def translate_preview(data: TranslatePreviewIn,
                      user: models.User = Depends(get_current_user)):
    require_teacher(user)
    out = []
    for s in data.steps:
        out.append({
            "translations": [
                {"language_code": lang,
                 "step_text": translate_text(s.step_text, lang),
                 "hint_text": translate_text(s.hint_text, lang)}
                for lang in TARGET_LANGUAGES
            ]
        })
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
def create_answer(data: AnswerIn, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_teacher(user)
    if not data.steps:
        raise HTTPException(400, "At least one step is required")
    ans = Answer(question_id=data.question_id, teacher_id=user.user_id,
                 final_answer=data.final_answer)
    db.add(ans)
    db.flush()
    _fill_steps(db, ans, data.steps)
    db.commit()
    return _load(db, ans.answer_id)


@router.put("/{answer_id}", response_model=AnswerOut)
def update_answer(answer_id: int, data: AnswerIn, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_teacher(user)
    ans = _load(db, answer_id)
    if ans.teacher_id != user.user_id and _role_name(user) != "superadmin":
        raise HTTPException(403, "You can edit only your own answers")
    ans.final_answer = data.final_answer
    _fill_steps(db, ans, data.steps)
    db.commit()
    return _load(db, answer_id)


@router.delete("/{answer_id}")
def delete_answer(answer_id: int, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    require_teacher(user)
    ans = _load(db, answer_id)
    if ans.teacher_id != user.user_id and _role_name(user) != "superadmin":
        raise HTTPException(403, "You can delete only your own answers")
    db.delete(ans)
    db.commit()
    return {"ok": True}
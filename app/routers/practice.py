import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app.core.deps import get_current_user 
from sqlalchemy import func
from app.models import (
     StudentProfile, StudentSubject, Question,LOV,Chapter,QuestionTranslation,Answer,AnswerStep
    
)

# + your get_db, get_current_user and model imports, as in student.py

router = APIRouter(prefix="/practice", tags=["practice"])


# ---------- helpers ----------
def _language(db, s):
    medium = db.get(LOV, s.medium_id)
    return "ta" if "tamil" in ((medium.value if medium else "") or "").lower() else "en"


def _access(db, user, question_id):
    """The student's profile and the question, only if it is in their class and chosen subjects."""
    s = db.query(StudentProfile).filter(StudentProfile.user_id == user.user_id).first()
    if not s:
        raise HTTPException(404, "Not a student")
    q = db.get(Question, question_id)
    ch = db.get(Chapter, q.chapter_id) if q else None
    subject_ids = [
        r.subject_id
        for r in db.query(StudentSubject).filter(StudentSubject.user_id == user.user_id).all()
    ]
    if (
        not ch
        or ch.class_lov_id != s.class_id
        or ch.subject_lov_id not in subject_ids
        or (s.board_id and ch.board_lov_id != s.board_id)
    ):
        raise HTTPException(404, "Question not found")
    return s, q


def _answers(db, question_id, method_id):
    """All teacher answers for the question, or only the locked one (method_id = answer_id)."""
    qry = (
        db.query(Answer)
        .options(selectinload(Answer.steps).selectinload(AnswerStep.translations))
        .filter(Answer.question_id == question_id)
    )
    if method_id and method_id.isdigit():
        qry = qry.filter(Answer.answer_id == int(method_id))
    return qry.order_by(Answer.answer_id).all()


def _norm(t):
    t = (t or "").lower()
    t = t.replace("$", "").replace("\\left", "").replace("\\right", "")
    t = t.replace("\\cdot", "*").replace("\\times", "*").replace("×", "*").replace("·", "*")
    t = t.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    t = re.sub(r"\\[,;:! ]", "", t)          # latex spacing
    t = re.sub(r"\\q?quad", "", t)
    t = re.sub(r"\^\{(\w)\}", r"^\1", t)     # x^{2} == x^2
    t = re.sub(r"_\{(\w)\}", r"_\1", t)
    t = re.sub(r"\s+", "", t)
    return t.rstrip(".,;")


def _matches(student_text, step):
    """THE place to swap in the LLM / Chroma check later."""
    candidates = [step.step_text] + [t.step_text for t in step.translations if t.step_text]
    mine = _norm(student_text)
    return bool(mine) and any(mine == _norm(c) for c in candidates)


def _step(answer, number):
    return next((st for st in answer.steps if st.step_no == number), None)


# ---------- endpoints ----------
@router.get("/questions/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s, q = _access(db, user, question_id)
    lang = _language(db, s)
    body = q.question_text
    if lang != "en":
        t = db.get(QuestionTranslation, (q.question_id, lang))
        if t and t.question_text:
            body = t.question_text
    return {"id": q.question_id, "body": body, "exercise_no": q.exercise_no}


class StepIn(BaseModel):
    step_number: int
    answer: str
    method_id: str | None = None


@router.post("/questions/{question_id}/check-step")
def check_step(question_id: int, body: StepIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _access(db, user, question_id)
    answers = _answers(db, question_id, body.method_id)
    if not answers:
        raise HTTPException(404, "No answer saved for this question yet")

    # First step: try every teacher's method. Later steps: only the locked one.
    for a in answers:
        step = _step(a, body.step_number)
        if step and _matches(body.answer, step):
            last = max(st.step_no for st in a.steps)
            return {
                "correct": True,
                "complete": body.step_number >= last,
                "method_id": str(a.answer_id),
            }
    return {"correct": False, "complete": False, "method_id": body.method_id}


@router.get("/questions/{question_id}/hint")
def get_hint(
    question_id: int,
    step_number: int = 1,
    method_id: str | None = None,   # the page sends method_id= (empty) before a method is locked
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    s, _ = _access(db, user, question_id)
    answers = _answers(db, question_id, method_id)
    step = _step(answers[0], step_number) if answers else None
    if not step:
        raise HTTPException(404, "No hint available")

    text = step.step_text
    lang = _language(db, s)
    if lang != "en":
        tr = next((t for t in step.translations if t.language_code == lang and t.step_text), None)
        if tr:
            text = tr.step_text
    return {"hint": text.replace("$", "")}   # the page offers this text to be typed in as the step
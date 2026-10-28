import logging
import re
import time
from datetime import date, datetime, timedelta 
from fastapi import HTTPException
from sqlalchemy import func

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request,Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

# ADJUST these imports to your project.
from app.database import get_db
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.config import settings
from app.models import (
    User, UserRole, StudentProfile, StudentSubject, Plan, Subscription, Payment, PaymentItem,Question,LOV,Chapter,QuestionTranslation
    
)


router = APIRouter(prefix="/student", tags=["student"])
logger = logging.getLogger("uvicorn.error")  # shows in the uvicorn terminal


def _uid(row) -> int:
    """Primary key value of any model row, whatever the column is called (id, user_id, role_id...)."""
    return sa_inspect(row).identity[0]

TRIAL_DAYS = 30

# Classes, boards, mediums and subjects are rows of smarttutor.st_lov (lov_id, type, value).
CLASS_LOV_TYPE = ("Class", "School")   # your list page filters classes by "School"; both accepted
BOARD_LOV_TYPE = "Board of Category"
MEDIUM_LOV_TYPE = "Medium"
SUBJECT_LOV_TYPE = "Subject"
ALLOWED_CLASSES = {"10", "X", "11", "XI", "12", "XII"}


# ---------------------------------------------------------------- lov helpers
def _normalize_class(value: str) -> str:
    """'Class 10', '10th Std', 'x' -> '10', '10', 'X'"""
    v = str(value or "").upper().strip()
    v = re.sub(r"\b(CLASS|STD|STANDARD)\b", "", v)
    v = re.sub(r"(?<=\d)(TH|ST|ND|RD)\b", "", v)
    return re.sub(r"[\s.\-]", "", v)


def _types(lov_type) -> list[str]:
    return [lov_type] if isinstance(lov_type, str) else list(lov_type)


def _lov_rows(db: Session, lov_type):
    return db.execute(
        text("SELECT lov_id, value FROM smarttutor.st_lov WHERE type = ANY(:ts) ORDER BY lov_id"),
        {"ts": _types(lov_type)},
    ).fetchall()


def _lov_exists(db: Session, lov_id: int, lov_type) -> str | None:
    row = db.execute(
        text("SELECT value FROM smarttutor.st_lov WHERE lov_id = :i AND type = ANY(:ts)"),
        {"i": lov_id, "ts": _types(lov_type)},
    ).first()
    return row[0] if row else None


def _subject_names(db: Session) -> dict[int, str]:
    return {r.lov_id: r.value for r in _lov_rows(db, SUBJECT_LOV_TYPE)}


# ---------------------------------------------------------------- subscription helpers
def razorpay_client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def subject_state(sub: Subscription, ss: StudentSubject) -> dict:
    """Access for ONE subject: free student, paid, still in the free month, or expired."""
    today = date.today()
    if sub.free_override:
        return {"state": "free", "has_access": True, "days_left": None, "paid_until": ss.paid_until}
    if ss.paid_until and today <= ss.paid_until:
        return {"state": "active", "has_access": True,
                "days_left": (ss.paid_until - today).days, "paid_until": ss.paid_until}
    if today <= sub.trial_end:
        return {"state": "trial", "has_access": True,
                "days_left": (sub.trial_end - today).days, "paid_until": ss.paid_until}
    return {"state": "expired", "has_access": False, "days_left": 0, "paid_until": ss.paid_until}


def overall_state(sub: Subscription | None, states: list[dict]) -> dict:
    if sub is None:
        return {"state": "none", "has_access": False, "days_left": 0, "trial_end": None}
    if sub.free_override:
        return {"state": "free", "has_access": True, "days_left": None, "trial_end": sub.trial_end}
    today = date.today()
    if any(s["state"] == "active" for s in states):
        state = "active"
    elif today <= sub.trial_end:
        state = "trial"
    else:
        state = "expired"
    return {
        "state": state,
        "has_access": any(s["has_access"] for s in states),
        "days_left": max([s["days_left"] or 0 for s in states], default=0),
        "trial_end": sub.trial_end,
    }


def _load(db: Session, user_id: int):
    sub = db.query(Subscription).filter_by(user_id=user_id).first()
    subjects = db.query(StudentSubject).filter_by(user_id=user_id).order_by(StudentSubject.subject_id).all()
    return sub, subjects

def _next_period(today: date, prev_end: date, days: int) -> tuple[date, date]:
    """Same rule as activate_payment: counts from the later of today / current end,
    so paying early never loses days."""
    base = max(today, prev_end)
    start = today if today > prev_end else prev_end + timedelta(days=1)
    return start, base + timedelta(days=days)

def require_active_subscription(
    user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """General guard: passes if the student can use at least one subject.
    Admins/teachers have no student profile, so they pass."""
    if db.query(StudentProfile).filter_by(user_id=user.id).first() is None:
        return user
    sub, subjects = _load(db, user.id)
    if sub is None or not any(subject_state(sub, s)["has_access"] for s in subjects):
        raise HTTPException(status_code=402, detail="subscription_expired")
    return user


def ensure_subject_access(db: Session, user, subject_id: int):
    """Call inside a practice endpoint that works on one subject's questions:
        ensure_subject_access(db, user, question.subject_id)
    402 = this subject needs payment, 403 = the student never chose this subject."""
    if db.query(StudentProfile).filter_by(user_id=user.id).first() is None:
        return  # admin / teacher
    sub, subjects = _load(db, user.id)
    ss = next((s for s in subjects if s.subject_id == subject_id), None)
    if sub is None or ss is None:
        raise HTTPException(status_code=403, detail="subject_not_registered")
    if not subject_state(sub, ss)["has_access"]:
        raise HTTPException(status_code=402, detail="subscription_expired")


def activate_payment(db: Session, payment: Payment, razorpay_payment_id: str):
    """Idempotent: verify endpoint and webhook can both call it safely."""
    if payment.status == "paid":
        return
    plan = db.get(Plan, payment.plan_id)
    sub = db.query(Subscription).filter_by(user_id=payment.user_id).first()
    items = db.query(PaymentItem).filter_by(payment_id=payment.payment_id).all()
    today = date.today()

    for item in items:
        ss = db.query(StudentSubject).filter_by(
            user_id=payment.user_id, subject_id=item.subject_id).first()
        if ss is None:  # student added a new subject while paying
            ss = StudentSubject(user_id=payment.user_id, subject_id=item.subject_id)
            db.add(ss)
            db.flush()
        # Paying early never loses free days: count from the later of today / current end.
        base = max(today, sub.trial_end, ss.paid_until or sub.trial_end)
        ss.paid_until = base + timedelta(days=plan.duration_days)

    payment.status = "paid"
    payment.razorpay_payment_id = razorpay_payment_id
    payment.paid_at = datetime.utcnow()
    db.commit()


# ---------------------------------------------------------------- schemas
class RegisterIn(BaseModel):
    username: str
    full_name: str
    email: str
    mobile: str
    password: str
    board_id: int
    class_id: int
    medium_id: int
    subject_ids: list[int]
    school: str | None = None

    @field_validator("mobile")
    @classmethod
    def v_mobile(cls, v):
        digits = re.sub(r"[\s\-]", "", v)
        digits = re.sub(r"^(\+91|91|0)(?=\d{10}$)", "", digits)  # drop +91 / 91 / 0 prefix
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("Enter a valid 10-digit mobile number")
        return digits

    @field_validator("subject_ids")
    @classmethod
    def v_subjects(cls, v):
        v = list(dict.fromkeys(v))  # drop duplicates, keep order
        if not v:
            raise ValueError("Select at least one subject")
        return v

    @field_validator("username")
    @classmethod
    def v_username(cls, v):
        v = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.]{4,30}", v):
            raise ValueError("Username: 4-30 letters, numbers, . or _")
        return v

    @field_validator("email")
    @classmethod
    def v_email(cls, v):
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Enter a valid email")
        return v

    @field_validator("password")
    @classmethod
    def v_password(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class ProfileUpdateIn(BaseModel):
    class_id: int
    medium_id: int


class OrderIn(BaseModel):
    plan_id: int
    subject_ids: list[int]

    @field_validator("subject_ids")
    @classmethod
    def v_subjects(cls, v):
        v = list(dict.fromkeys(v))
        if not v:
            raise ValueError("Select at least one subject")
        return v


class VerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ---------------------------------------------------------------- public
@router.get("/options")
def register_options(db: Session = Depends(get_db)):
    classes = [r for r in _lov_rows(db, CLASS_LOV_TYPE) if _normalize_class(r.value) in ALLOWED_CLASSES]
    return {
        "boards": [{"id": r.lov_id, "name": r.value} for r in _lov_rows(db, BOARD_LOV_TYPE)],
        "classes": [{"id": r.lov_id, "name": r.value} for r in classes],
        "mediums": [{"id": r.lov_id, "name": r.value} for r in _lov_rows(db, MEDIUM_LOV_TYPE)],
        "subjects": [{"id": r.lov_id, "name": r.value} for r in _lov_rows(db, SUBJECT_LOV_TYPE)],
    }


@router.post("/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    username = data.username.strip()
    email = data.email.strip().lower()
    subject_ids = list(dict.fromkeys(data.subject_ids))   # remove duplicates, keep order

    if db.query(User).filter(func.lower(User.username) == username.lower()).first():
        raise HTTPException(400, "Username already taken")
    if db.query(User).filter(func.lower(User.email_id) == email).first():
        raise HTTPException(400, "Email already registered")
    if db.query(StudentProfile).filter_by(mobile=data.mobile).first():
        raise HTTPException(400, "Mobile number already registered")

    class_value = _lov_exists(db, data.class_id, CLASS_LOV_TYPE)
    if class_value is None or _normalize_class(class_value) not in ALLOWED_CLASSES:
        raise HTTPException(400, "Invalid class")
    if _lov_exists(db, data.medium_id, MEDIUM_LOV_TYPE) is None:
        raise HTTPException(400, "Invalid medium")
    if _lov_exists(db, data.board_id, BOARD_LOV_TYPE) is None:
        raise HTTPException(400, "Invalid board")
    if not subject_ids:
        raise HTTPException(400, "Select at least one subject")
    for sid in subject_ids:
        if _lov_exists(db, sid, SUBJECT_LOV_TYPE) is None:
            raise HTTPException(400, "Invalid subject")

    role = db.query(UserRole).filter(func.lower(UserRole.role_name) == "student").first()
    if role is None:
        raise HTTPException(500, "Student role is not set up")

    try:
        user = User(
            username=username,
            full_name=data.full_name.strip(),
            email_id=email,
            password_hash=hash_password(data.password),
            role_id=role.role_id,
        )
        db.add(user)
        db.flush()  # generates user.user_id

        db.add(StudentProfile(
            user_id=user.user_id, mobile=data.mobile, class_id=data.class_id,
            medium_id=data.medium_id, board_id=data.board_id, school=data.school,
        ))
        for sid in subject_ids:
            db.add(StudentSubject(user_id=user.user_id, subject_id=sid))

        today = date.today()
        db.add(Subscription(
            user_id=user.user_id, trial_start=today,
            trial_end=today + timedelta(days=TRIAL_DAYS),
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Student registration failed")
        raise HTTPException(500, f"Could not create account: {type(e).__name__}: {str(e)[:300]}")

    return {"message": "Registered", "trial_days": TRIAL_DAYS}


# ---------------------------------------------------------------- student
@router.get("/me")
def me(user=Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(StudentProfile).filter_by(user_id=user.user_id).first()
    if profile is None:
        raise HTTPException(404, "Not a student")
    sub, subjects = _load(db, user.user_id)
    names = _subject_names(db)

    rows = []
    states = []
    for ss in subjects:
        st = subject_state(sub, ss)
        states.append(st)
        rows.append({"subject_id": ss.subject_id, "name": names.get(ss.subject_id, str(ss.subject_id)), **st})

    return {
        "board_id": profile.board_id,
        "class_id": profile.class_id,
        "medium_id": profile.medium_id,
        "school": profile.school,
        "subscription": overall_state(sub, states),
        "subjects": rows,
    }


def _class_rank(value):
    return {"10": 0, "X": 0, "11": 1, "XI": 1, "12": 2, "XII": 2}.get(_normalize_class(value))


@router.put("/profile")
def update_profile(data: ProfileUpdateIn, user=Depends(get_current_user),
                   db: Session = Depends(get_db)):
    profile = db.query(StudentProfile).filter_by(user_id=user.user_id).first()
    if profile is None:
        raise HTTPException(404, "Not a student")

    new_val = _lov_exists(db, data.class_id, CLASS_LOV_TYPE)
    old_val = _lov_exists(db, profile.class_id, CLASS_LOV_TYPE)
    new_rank = _class_rank(new_val) if new_val else None
    old_rank = _class_rank(old_val) if old_val else None
    if new_rank is None:
        raise HTTPException(400, "Invalid class")
    if old_rank is not None and new_rank not in (old_rank, old_rank + 1):
        raise HTTPException(400, "You can only stay in this class or move up to the next one")
    if _lov_exists(db, data.medium_id, MEDIUM_LOV_TYPE) is None:
        raise HTTPException(400, "Invalid medium")

    profile.class_id = data.class_id
    profile.medium_id = data.medium_id
    db.commit()
    return {"message": "Updated"}


@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    """amount = price per subject for that plan."""
    rows = db.query(Plan).filter_by(is_active=True).order_by(Plan.duration_days).all()
    return [{"plan_id": p.plan_id, "name": p.name, "amount": float(p.amount),
             "duration_days": p.duration_days,
             "months": p.duration_days // 30 if p.duration_days % 30 == 0 else None}
            for p in rows]

@router.post("/payments/order")
def create_order(data: OrderIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(Plan).filter_by(plan_id=data.plan_id, is_active=True).first()
    if plan is None:
        raise HTTPException(404, "Plan not found")
    if db.query(Subscription).filter_by(user_id=user.user_id).first() is None:
        raise HTTPException(404, "Not a student")
    for sid in data.subject_ids:
        if _lov_exists(db, sid, SUBJECT_LOV_TYPE) is None:
            raise HTTPException(400, "Invalid subject")

    total = plan.amount * len(data.subject_ids)  # price per subject x subjects chosen
    order = razorpay_client().order.create({
        "amount": int(total * 100),  # paise
        "currency": "INR",
        "receipt": f"st_{user.id}_{int(time.time())}",
        "notes": {"user_id": str(user.id), "plan_id": str(plan.plan_id),
                  "subjects": ",".join(str(s) for s in data.subject_ids)},
    })
    payment = Payment(user_id=user.id, plan_id=plan.plan_id, amount=total,
                      razorpay_order_id=order["id"])
    db.add(payment)
    db.flush()
    for sid in data.subject_ids:
        db.add(PaymentItem(payment_id=payment.payment_id, subject_id=sid))
    db.commit()
    return {"key_id": settings.razorpay_key_id, "order_id": order["id"],
            "amount": order["amount"], "currency": order["currency"]}


@router.post("/payments/verify")
def verify_payment(data: VerifyIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.query(Payment).filter_by(
        razorpay_order_id=data.razorpay_order_id, user_id=user.id).first()
    if payment is None:
        raise HTTPException(404, "Order not found")
    try:
        razorpay_client().utility.verify_payment_signature(data.model_dump())
    except razorpay.errors.SignatureVerificationError:
        payment.status = "failed"
        db.commit()
        raise HTTPException(400, "Payment verification failed")
    activate_payment(db, payment, data.razorpay_payment_id)
    return {"message": "Payment successful"}

@router.get("/subscriptions")
def my_subscriptions(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """History: the free month, then each paid period per subject, newest first."""
    sub, subjects = _load(db, user.user_id)
    if sub is None:
        raise HTTPException(404, "Not a student")
    names = _subject_names(db)
    today = date.today()

    def status(start, end):
        if start > today:
            return "upcoming"
        return "active" if end >= today else "expired"

    rows = []
    for ss in subjects:
        rows.append({
            "subject_id": ss.subject_id, "subject": names.get(ss.subject_id, str(ss.subject_id)),
            "kind": "trial", "plan": None, "amount": None,
            "start_date": sub.trial_start, "end_date": sub.trial_end,
            "status": status(sub.trial_start, sub.trial_end),
        })

    plans_by_id = {p.plan_id: p for p in db.query(Plan).all()}
    pays = (db.query(Payment).filter_by(user_id=user.user_id, status="paid")
            .order_by(Payment.paid_at, Payment.payment_id).all())
    items_by_pay: dict[int, list] = {}
    if pays:
        for it in db.query(PaymentItem).filter(
                PaymentItem.payment_id.in_([p.payment_id for p in pays])).all():
            items_by_pay.setdefault(it.payment_id, []).append(it)

    prev_end = {ss.subject_id: sub.trial_end for ss in subjects}
    for pay in pays:
        plan = plans_by_id.get(pay.plan_id)
        if plan is None:
            continue
        paid_day = (pay.paid_at or pay.created_at).date()
        for it in items_by_pay.get(pay.payment_id, []):
            start, end = _next_period(paid_day, prev_end.get(it.subject_id, sub.trial_end),
                                      plan.duration_days)
            prev_end[it.subject_id] = end
            rows.append({
                "subject_id": it.subject_id,
                "subject": names.get(it.subject_id, str(it.subject_id)),
                "kind": "paid", "plan": plan.name, "amount": float(plan.amount),
                "start_date": start, "end_date": end, "status": status(start, end),
            })

    rows.sort(key=lambda r: (r["start_date"], r["kind"] == "paid"), reverse=True)
    return rows


@router.get("/payments/preview")
def preview(plan_id: int, subject_ids: list[int] = Query(...),
            user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Shows the start and end dates the student will get before paying."""
    plan = db.query(Plan).filter_by(plan_id=plan_id, is_active=True).first()
    if plan is None:
        raise HTTPException(404, "Plan not found")
    sub, subjects = _load(db, user.user_id)
    if sub is None:
        raise HTTPException(404, "Not a student")
    by_subject = {s.subject_id: s for s in subjects}
    names = _subject_names(db)
    today = date.today()

    items = []
    for sid in dict.fromkeys(subject_ids):
        if _lov_exists(db, sid, SUBJECT_LOV_TYPE) is None:
            raise HTTPException(400, "Invalid subject")
        ss = by_subject.get(sid)
        prev = max(sub.trial_end, (ss.paid_until if ss and ss.paid_until else sub.trial_end))
        start, end = _next_period(today, prev, plan.duration_days)
        items.append({"subject": names.get(sid, str(sid)), "start_date": start, "end_date": end})
    return {"total": float(plan.amount) * len(items), "items": items}

@router.post("/payments/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Backup path: activates the plan even if the student closed the browser after paying.
    Razorpay dashboard -> Webhooks -> URL .../student/payments/webhook, event payment.captured.
    Needs a public URL (use ngrok locally)."""
    raw = (await request.body()).decode()
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
        razorpay_client().utility.verify_webhook_signature(
            raw, signature, settings.razorpay_webhook_secret)
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(400, "Bad signature")

    event = await request.json()
    if event.get("event") == "payment.captured":
        entity = event["payload"]["payment"]["entity"]
        payment = db.query(Payment).filter_by(razorpay_order_id=entity["order_id"]).first()
        if payment:
            activate_payment(db, payment, entity["id"])
    return {"status": "ok"}

def _natural(s):
    # sorts "1.2" before "1.10"
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', str(s or ''))]

def _student(db, user):
    s = db.query(StudentProfile).filter(StudentProfile.user_id == user.user_id).first()
    if not s:
        raise HTTPException(404, "Not a student")
    return s

def _language(db, s):
    medium = db.get(LOV, s.medium_id)
    name = (medium.value if medium else "") or ""
    return "ta" if "tamil" in name.lower() else "en"


@router.get("/practice/chapters")
def practice_chapters(
    subject_id: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    s = _student(db, user)

    subject_ids = [
        r.subject_id
        for r in db.query(StudentSubject)
        .filter(StudentSubject.user_id == user.user_id)
        .order_by(StudentSubject.id)
        .all()
    ]

    wanted = [i for i in [s.class_id, s.board_id, s.medium_id, *subject_ids] if i]
    lov = {r.lov_id: r.value for r in db.query(LOV).filter(LOV.lov_id.in_(wanted)).all()}

    info = {
        "class_name": lov.get(s.class_id),
        "board_name": lov.get(s.board_id),
        "medium_name": lov.get(s.medium_id),
        "language": _language(db, s),
    }
    subjects = [{"subject_id": i, "name": lov.get(i)} for i in subject_ids]
    if not subjects:
        return {"info": info, "subjects": [], "subject_id": None, "chapters": []}

    if subject_id is None:
        subject_id = subjects[0]["subject_id"]
    if subject_id not in subject_ids:
        raise HTTPException(403, "Subject not in your registration")

    cq = db.query(Chapter).filter(
        Chapter.class_lov_id == s.class_id,
        Chapter.subject_lov_id == subject_id,
    )
    if s.board_id:
        cq = cq.filter(Chapter.board_lov_id == s.board_id)
    chs = cq.all()
    chs.sort(key=lambda c: ((c.sort_order or 0), _natural(c.chapter_no)))

    chapter_ids = [c.chapter_id for c in chs]
    counts = (
        dict(
            db.query(Question.chapter_id, func.count())
            .filter(Question.chapter_id.in_(chapter_ids))
            .group_by(Question.chapter_id)
            .all()
        )
        if chapter_ids
        else {}
    )

    return {
        "info": info,
        "subjects": subjects,
        "subject_id": subject_id,
        "chapters": [
            {
                "chapter_id": c.chapter_id,
                "chapter_no": c.chapter_no,
                "title_en": c.title_en,
                "title_ta": c.title_ta,
                "question_count": counts.get(c.chapter_id, 0),
            }
            for c in chs
        ],
    }


@router.get("/practice/chapters/{chapter_id}/questions")
def practice_questions(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    s = _student(db, user)

    subject_ids = [
        r.subject_id
        for r in db.query(StudentSubject).filter(StudentSubject.user_id == user.user_id).all()
    ]
    ch = db.get(Chapter, chapter_id)
    if (
        not ch
        or ch.class_lov_id != s.class_id
        or ch.subject_lov_id not in subject_ids
        or (s.board_id and ch.board_lov_id != s.board_id)
    ):
        raise HTTPException(404, "Chapter not found")

    qs = db.query(Question).filter(Question.chapter_id == chapter_id).all()

    # Translation in the student's medium, from question_translations
    lang = _language(db, s)
    trans = {}
    if lang != "en" and qs:
        trans = {
            t.question_id: t.question_text
            for t in db.query(QuestionTranslation)
            .filter(
                QuestionTranslation.question_id.in_([q.question_id for q in qs]),
                QuestionTranslation.lang_code == lang,
            )
            .all()
        }

    return [
        {
            "question_id": q.question_id,
            "chapter_id": q.chapter_id,
            "parent_id": getattr(q, "parent_id", None),   # not a column on Question
            "exercise_no": q.exercise_no,
            "sort_order": q.sort_order,
            "question_text": q.question_text,
            "language_translation": (trans.get(q.question_id) or q.language_translation) if lang != "en" else None,
        }
        for q in qs
    ]
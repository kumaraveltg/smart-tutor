# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import logging, os, smtplib
from email.message import EmailMessage
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func 

from app.database import get_db
from app import models
from app.core.security import verify_password, create_access_token,hash_password
from app.core.deps import get_current_user 
from app.models import StudentProfile, StudentSubject, Subscription

router = APIRouter(prefix="/auth", tags=["Auth"])

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")   # ADJUST: use the same secret as your JWT settings
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
RESET_MAX_AGE = 30 * 60   # 30 minutes
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="password-reset")


class ForgotIn(BaseModel):
    email: EmailStr

class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


def _send_email(to: str, link: str):
    host = os.getenv("SMTP_HOST")
    if not host:   # dev mode: no SMTP configured, print the link in the terminal
        logger.warning("PASSWORD RESET LINK for %s: %s", to, link)
        return
    msg = EmailMessage()
    msg["Subject"] = "Reset your SmartTutor password"
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER"))
    msg["To"] = to
    msg.set_content(f"Click to reset your password (valid for 30 minutes):\n\n{link}\n\n"
                    "If you did not request this, ignore this email.")
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", 587))) as s:
        s.starttls()
        s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        s.send_message(msg)


def build_user_payload(db: Session, user: models.User) -> dict:
    out = {
        "user_id": user.user_id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email_id,
        "role": user.role.role_name if user.role else None,
        "student": None,
    }

    profile = db.query(StudentProfile).filter_by(user_id=user.user_id).first()
    if profile:
        def lov_text(lov_id):
            row = db.query(models.LOV).filter(models.LOV.lov_id == lov_id).first()  # ADJUST model/PK
            return row.value if row else None                                    # ADJUST text column

        subject_ids = [
            s.subject_id
            for s in db.query(StudentSubject).filter_by(user_id=user.user_id).all()
        ]
        sub = db.query(Subscription).filter_by(user_id=user.user_id).first()

        out["student"] = {
            "mobile": profile.mobile,
            "school": profile.school,
            "class": lov_text(profile.class_id),
            "board": lov_text(profile.board_id),
            "medium": lov_text(profile.medium_id),
            "subjects": [lov_text(i) for i in subject_ids],
            "trial_end": sub.trial_end.isoformat() if sub and sub.trial_end else None,
        }
    return out


@router.get("/me")
def read_current_user(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_user_payload(db, current_user)


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()

    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token = create_access_token(data={"sub": str(user.user_id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": build_user_payload(db, user),
    }


@router.post("/forgot-password")
def forgot_password(data: ForgotIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    user = db.query(models.User).filter(func.lower(models.User.email_id) == email).first()
    if user and user.is_active:
        # the last 10 chars of the current hash make the token single-use
        token = _serializer.dumps({"uid": user.user_id, "fp": user.password_hash[-10:]})
        try:
            _send_email(email, f"{FRONTEND_URL}/reset-password?token={token}")
        except Exception:
            logger.exception("Could not send reset email")
    # same answer whether or not the email exists, so accounts can't be probed
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(data: ResetIn, db: Session = Depends(get_db)):
    try:
        payload = _serializer.loads(data.token, max_age=RESET_MAX_AGE)
    except SignatureExpired:
        raise HTTPException(400, "Reset link has expired. Please request a new one.")
    except BadSignature:
        raise HTTPException(400, "Invalid reset link.")

    user = db.query(models.User).filter(models.User.user_id == payload["uid"]).first()
    if user is None or user.password_hash[-10:] != payload["fp"]:
        raise HTTPException(400, "This reset link has already been used or is invalid.")

    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password updated. You can now log in."}
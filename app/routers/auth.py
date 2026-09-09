# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.core.security import verify_password, create_access_token
from app.core.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.get("/me")
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "role": current_user.role_id,   # same note as before — use the role *name*
                                          # if UserRole is a relationship, not the id
    }

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()

    # NOTE: assumes your User model's password column is named `password_hash`.
    # If yours is named differently, change this one line to match.
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
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role.role_name,   # ← adjust: use whatever actually holds the role name
                                    #   (e.g. user.role.name if UserRole is a relationship,
                                    #   not just the numeric role_id)
        },
    }


    # In your main app:
    # from app.routers.auth import router as auth_router
    # app.include_router(auth_router)
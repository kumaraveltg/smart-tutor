from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.core.security import hash_password,verify_password, create_access_token
from app.core.deps import get_current_user

router = APIRouter(prefix="/admin/users", tags=["Users"], dependencies=[Depends(get_current_user)])

@router.post("/", response_model=schemas.UserOut, status_code=201)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check role_id actually exists before creating the user
    if not db.query(models.UserRole).get(user.role_id):
        raise HTTPException(400, "role_id does not exist")

    # Check username/email aren't already taken
    if db.query(models.User).filter_by(username=user.username).first():
        raise HTTPException(400, "Username already taken")

    # Never store the raw password — hash it first
    data = user.model_dump(exclude={"password"})
    db_user = models.User(**data, password_hash=hash_password(user.password))

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/", response_model=list[schemas.UserOut])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.User).offset(skip).limit(limit).all()


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, user: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).get(user_id)
    if not db_user:
        raise HTTPException(404, "User not found")

    update_data = user.model_dump(exclude_unset=True)

    new_password = update_data.pop("password", None)
    if new_password:
        db_user.password_hash = hash_password(new_password)

    for field, value in update_data.items():
        setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).get(user_id)
    if not db_user:
        raise HTTPException(404, "User not found")
    db.delete(db_user)
    db.commit()
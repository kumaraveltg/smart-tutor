from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.deps import get_current_user
from app.database import get_db
from app.core.security import hash_password,verify_password, create_access_token

router = APIRouter(prefix="/admin/questions", tags=["Questions"])


@router.post("/", response_model=schemas.QuestionOut, status_code=201)
def create_question(question: schemas.QuestionCreate, db: Session = Depends(get_db)):
    db_question = models.Question(**question.model_dump())
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question


@router.get("/", response_model=list[schemas.QuestionOut])
def list_questions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Question).offset(skip).limit(limit).all()


@router.get("/{question_id}", response_model=schemas.QuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db)):
    question = db.query(models.Question).get(question_id)
    if not question:
        raise HTTPException(404, "Question not found")
    return question


@router.put("/{question_id}", response_model=schemas.QuestionOut)
def update_question(question_id: int, question: schemas.QuestionCreate, db: Session = Depends(get_db)):
    db_question = db.query(models.Question).get(question_id)
    if not db_question:
        raise HTTPException(404, "Question not found")
    for field, value in question.model_dump().items():
        setattr(db_question, field, value)
    db.commit()
    db.refresh(db_question)
    return db_question


@router.delete("/{question_id}", status_code=204)
def delete_question(question_id: int, db: Session = Depends(get_db)):
    db_question = db.query(models.Question).get(question_id)
    if not db_question:
        raise HTTPException(404, "Question not found")
    db.delete(db_question)
    db.commit()
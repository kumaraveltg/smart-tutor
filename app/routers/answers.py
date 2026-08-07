from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/admin/answers", tags=["Answers"])


@router.post("/", response_model=schemas.AnswerOut, status_code=201)
def create_answer(answer: schemas.AnswerCreate, db: Session = Depends(get_db)):
    if not db.query(models.Question).get(answer.question_id):
        raise HTTPException(400, "question_id does not exist")
    db_answer = models.Answer(**answer.model_dump())
    db.add(db_answer)
    db.commit()
    db.refresh(db_answer)
    return db_answer


@router.get("/", response_model=list[schemas.AnswerOut])
def list_answers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Answer).offset(skip).limit(limit).all()


@router.get("/{answer_id}", response_model=schemas.AnswerOut)
def get_answer(answer_id: int, db: Session = Depends(get_db)):
    answer = db.query(models.Answer).get(answer_id)
    if not answer:
        raise HTTPException(404, "Answer not found")
    return answer


@router.put("/{answer_id}", response_model=schemas.AnswerOut)
def update_answer(answer_id: int, answer: schemas.AnswerCreate, db: Session = Depends(get_db)):
    db_answer = db.query(models.Answer).get(answer_id)
    if not db_answer:
        raise HTTPException(404, "Answer not found")
    for field, value in answer.model_dump().items():
        setattr(db_answer, field, value)
    db.commit()
    db.refresh(db_answer)
    return db_answer


@router.delete("/{answer_id}", status_code=204)
def delete_answer(answer_id: int, db: Session = Depends(get_db)):
    db_answer = db.query(models.Answer).get(answer_id)
    if not db_answer:
        raise HTTPException(404, "Answer not found")
    db.delete(db_answer)
    db.commit()
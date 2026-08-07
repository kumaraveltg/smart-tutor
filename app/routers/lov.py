from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/admin/lov", tags=["LOV"])


@router.post("/", response_model=schemas.LOVOut, status_code=201)
def create_lov(lov: schemas.LOVCreate, db: Session = Depends(get_db)):
    if lov.question_id and not db.query(models.Question).get(lov.question_id):
        raise HTTPException(400, "question_id does not exist")
    db_lov = models.LOV(**lov.model_dump())
    db.add(db_lov)
    db.commit()
    db.refresh(db_lov)
    return db_lov


@router.get("/", response_model=list[schemas.LOVOut])
def list_lov(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.LOV).offset(skip).limit(limit).all()


@router.get("/{lov_id}", response_model=schemas.LOVOut)
def get_lov(lov_id: int, db: Session = Depends(get_db)):
    lov = db.query(models.LOV).get(lov_id)
    if not lov:
        raise HTTPException(404, "LOV entry not found")
    return lov


@router.put("/{lov_id}", response_model=schemas.LOVOut)
def update_lov(lov_id: int, lov: schemas.LOVCreate, db: Session = Depends(get_db)):
    db_lov = db.query(models.LOV).get(lov_id)
    if not db_lov:
        raise HTTPException(404, "LOV entry not found")
    for field, value in lov.model_dump().items():
        setattr(db_lov, field, value)
    db.commit()
    db.refresh(db_lov)
    return db_lov


@router.delete("/{lov_id}", status_code=204)
def delete_lov(lov_id: int, db: Session = Depends(get_db)):
    db_lov = db.query(models.LOV).get(lov_id)
    if not db_lov:
        raise HTTPException(404, "LOV entry not found")
    db.delete(db_lov)
    db.commit()
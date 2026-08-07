from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/admin/user-roles", tags=["User Roles"])

@router.post("/", response_model=schemas.UserRoleOut, status_code=201)
def create_role(role: schemas.UserRoleCreate, db: Session = Depends(get_db)):
    db_role = models.UserRole(**role.model_dump())
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role

@router.get("/", response_model=list[schemas.UserRoleOut])
def list_roles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.UserRole).offset(skip).limit(limit).all()


@router.get("/{role_id}", response_model=schemas.UserRoleOut)
def get_role(role_id: int, db: Session = Depends(get_db)):
    role = db.query(models.UserRole).get(role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    return role


@router.put("/{role_id}", response_model=schemas.UserRoleOut)
def update_role(role_id: int, role: schemas.UserRoleCreate, db: Session = Depends(get_db)):
    db_role = db.query(models.UserRole).get(role_id)
    if not db_role:
        raise HTTPException(404, "Role not found")
    db_role.role_name = role.role_name
    db.commit()
    db.refresh(db_role)
    return db_role


@router.delete("/{role_id}", status_code=204)
def delete_role(role_id: int, db: Session = Depends(get_db)):
    db_role = db.query(models.UserRole).get(role_id)
    if not db_role:
        raise HTTPException(404, "Role not found")
    db.delete(db_role)
    db.commit()
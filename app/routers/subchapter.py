# app/routers/subchapter.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select,and_
from sqlalchemy.orm import Session
from app import models
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Subchapter,SubchapterTranslation
from app.schemas import SubchapterCreate, SubchapterTranslationIn, SubchapterTranslationOut, SubchapterUpdate, SubchapterOut
from datetime import datetime, timezone
 

router = APIRouter(prefix="/admin/subchapters", tags=["Subchapters"])


# ---------- Subchapter (data access) ----------

def db_get_subchapter(db: Session, subchapter_id: int) -> Optional[Subchapter]:
    return db.get(Subchapter, subchapter_id)


def db_get_subchapters(
    db: Session,
    chapter_id: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> list[Subchapter]:
    """
    Flat listing, matching the admin list page (adminApi.list('subchapters')).
    chapter_id is optional here (unlike the old nested route) so the plain
    "list all" call from the admin UI works; pass chapter_id as a query
    param when you only want one chapter's subchapters.
    """
    query = select(Subchapter)
    if chapter_id is not None:
        query = query.where(Subchapter.chapter_id == chapter_id)
    if is_active is not None:
        query = query.where(Subchapter.is_active == is_active)
    query = query.order_by(Subchapter.chapter_id, Subchapter.sort_order, Subchapter.subchapter_no)
    return db.execute(query).scalars().all()


def db_create_subchapter(db: Session, payload: SubchapterCreate) -> Subchapter:
    subchapter = Subchapter(**payload.model_dump())  # level_no defaults to 2
    db.add(subchapter)
    db.commit()
    db.refresh(subchapter)
    return subchapter


def db_update_subchapter(
    db: Session, subchapter_id: int, payload: SubchapterUpdate
) -> Optional[Subchapter]:
    subchapter = db_get_subchapter(db, subchapter_id)
    if subchapter is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(subchapter, field, value)
    db.commit()
    db.refresh(subchapter)
    return subchapter


def db_delete_subchapter(db: Session, subchapter_id: int) -> bool:
    subchapter = db_get_subchapter(db, subchapter_id)
    if subchapter is None:
        return False
    db.delete(subchapter)
    db.commit()
    return True


# ---------- Subchapter (endpoints) ----------
# Flat routes on purpose: /admin/subchapters/... matches what adminApi.js
# builds (`/admin/${resource}/...`), so the frontend list/get/create/update/
# remove calls work with no special-casing.

@router.get("/", response_model=list[SubchapterOut])
def list_subchapters(
    chapter_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    return db_get_subchapters(db, chapter_id, is_active)


@router.get("/", response_model=list[SubchapterOut])
def list_subchapters(
    chapter_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    subs = db_get_subchapters(db, chapter_id, is_active)
    ta = {
        t.subchapter_id: t.title
        for t in db.query(SubchapterTranslation).filter(SubchapterTranslation.lang_code == "ta").all()
    }
    out = []
    for s in subs:
        item = SubchapterOut.model_validate(s)
        item.title_ta = ta.get(s.subchapter_id) or item.title_ta
        out.append(item)
    return out

@router.post("/", response_model=SubchapterOut, status_code=201)
def create_subchapter(payload: SubchapterCreate, db: Session = Depends(get_db)):
    return db_create_subchapter(db, payload)


@router.put("/{subchapter_id}", response_model=SubchapterOut)
def update_subchapter(subchapter_id: int, payload: SubchapterUpdate, db: Session = Depends(get_db)):
    subchapter = db_update_subchapter(db, subchapter_id, payload)
    if subchapter is None:
        raise HTTPException(status_code=404, detail="Subchapter not found")
    return subchapter


@router.delete("/{subchapter_id}", status_code=204)
def delete_subchapter(subchapter_id: int, db: Session = Depends(get_db)):
    if not db_delete_subchapter(db, subchapter_id):
        raise HTTPException(status_code=404, detail="Subchapter not found")


# ---------- Translation (data access) ----------
 
def db_get_subchapter_translation(db: Session, subchapter_id: int, lang_code: str):
    return db.get(SubchapterTranslation, (subchapter_id, lang_code))
 
 
def db_list_subchapter_translations(db: Session, subchapter_id: int):
    return (
        db.query(SubchapterTranslation)
        .filter(SubchapterTranslation.subchapter_id == subchapter_id)
        .all()
    )
 
 
def db_upsert_subchapter_translation(
    db: Session, subchapter_id: int, lang_code: str, payload: SubchapterTranslationIn
):
    row = db_get_subchapter_translation(db, subchapter_id, lang_code)
    if row is None:
        row = SubchapterTranslation(subchapter_id=subchapter_id, lang_code=lang_code)
        db.add(row)
    row.title = payload.title
    row.modified_by = payload.modified_by
    row.modified_on = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
 
 
def db_delete_subchapter_translation(db: Session, subchapter_id: int, lang_code: str) -> bool:
    row = db_get_subchapter_translation(db, subchapter_id, lang_code)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
 
 
# ---------- Translation (endpoints) ----------
 
@router.get(
    "/{subchapter_id}/translations",
    response_model=list[SubchapterTranslationOut],
)
def list_subchapter_translations(subchapter_id: int, db: Session = Depends(get_db)):
    return db_list_subchapter_translations(db, subchapter_id)
 
 
@router.put(
    "/{subchapter_id}/translations/{lang_code}",
    response_model=SubchapterTranslationOut,
)
def upsert_subchapter_translation(
    subchapter_id: int,
    lang_code: str,
    payload: SubchapterTranslationIn,
    db: Session = Depends(get_db),
):
    if db_get_subchapter(db, subchapter_id) is None:
        raise HTTPException(status_code=404, detail="Subchapter not found")
    return db_upsert_subchapter_translation(db, subchapter_id, lang_code, payload)
 
@router.put(
    "/{subchapter_id}/translations/{lang_code}",
    response_model=SubchapterTranslationOut,
)
def upsert_subchapter_translation(
    subchapter_id: int,
    lang_code: str,
    payload: SubchapterTranslationIn,
    db: Session = Depends(get_db),
):
    if db_get_subchapter(db, subchapter_id) is None:
        raise HTTPException(status_code=404, detail="Subchapter not found")
    return db_upsert_subchapter_translation(db, subchapter_id, lang_code, payload)

@router.delete("/{subchapter_id}/translations/{lang_code}", status_code=204)
def delete_subchapter_translation(subchapter_id: int, lang_code: str, db: Session = Depends(get_db)):
    if not db_delete_subchapter_translation(db, subchapter_id, lang_code):
        raise HTTPException(status_code=404, detail="Translation not found")
 
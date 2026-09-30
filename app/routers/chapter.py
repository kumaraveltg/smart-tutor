# app/routers/chapter.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from app import models, schemas 
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Chapter, Subchapter
from app.schemas import ChapterCreate, ChapterUpdate, ChapterWithSubchapters, SubchapterCreate, SubchapterUpdate, ChapterUpdate, ChapterWithSubchapters, SubchapterCreate, SubchapterUpdate, ChapterOut, SubchapterOut
from app.core.security import hash_password,verify_password, create_access_token
from app.models import ChapterTranslation
from app.schemas import ChapterTranslationIn, ChapterTranslationOut
from datetime import datetime, timezone
 
router = APIRouter(prefix="/admin/chapters", tags=["Chapters"])


# ---------- Chapter (data access) ----------

def db_get_chapter(db: Session, chapter_id: int) -> Optional[models.Chapter]:
    return db.get(Chapter, chapter_id)


def db_get_chapters(
    db: Session,
    board_lov_id: Optional[int] = None,
    class_lov_id: Optional[int] = None,
    subject_lov_id: Optional[int] = None,
    is_active: Optional[bool] = True,
) -> list[Chapter]:
    """
    Used for the student left-menu: pass board/class/subject to get only
    the chapters relevant to that student.
    """
    query = select(Chapter)
    if board_lov_id is not None:
        query = query.where(Chapter.board_lov_id == board_lov_id)
    if class_lov_id is not None:
        query = query.where(Chapter.class_lov_id == class_lov_id)
    if subject_lov_id is not None:
        query = query.where(Chapter.subject_lov_id == subject_lov_id)
    if is_active is not None:
        query = query.where(Chapter.is_active == is_active)
    query = query.order_by(Chapter.sort_order, Chapter.chapter_no)
    return db.execute(query).scalars().all()


def db_get_chapter_with_subchapters(db: Session, chapter_id: int) -> Optional[Chapter]:
    return (
        db.query(Chapter)
        .options(joinedload(Chapter.subchapters))
        .filter(Chapter.chapter_id == chapter_id)
        .first()
    )


def db_create_chapter(db: Session, payload: ChapterCreate) -> Chapter:
    chapter = Chapter(**payload.model_dump())  # level_no defaults to 1
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


def db_update_chapter(db: Session, chapter_id: int, payload: ChapterUpdate) -> Optional[Chapter]:
    chapter = db_get_chapter(db, chapter_id)
    if chapter is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(chapter, field, value)
    db.commit()
    db.refresh(chapter)
    return chapter


def db_delete_chapter(db: Session, chapter_id: int) -> bool:
    chapter = db_get_chapter(db, chapter_id)
    if chapter is None:
        return False
    db.delete(chapter)  # cascades to subchapters (ondelete="CASCADE" + relationship cascade)
    db.commit()
    return True



# ---------- Translation (data access) ----------

def db_get_translation(db: Session, chapter_id: int, lang_code: str):
    return db.get(ChapterTranslation, (chapter_id, lang_code))


def db_list_translations(db: Session, chapter_id: int):
    return (
        db.query(ChapterTranslation)
        .filter(ChapterTranslation.chapter_id == chapter_id)
        .all()
    )


def db_upsert_translation(db: Session, chapter_id: int, lang_code: str, payload: ChapterTranslationIn):
    row = db_get_translation(db, chapter_id, lang_code)
    if row is None:
        row = ChapterTranslation(chapter_id=chapter_id, lang_code=lang_code)
        db.add(row)
    row.title = payload.title
    row.modified_by = payload.modified_by
    row.modified_on = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def db_delete_translation(db: Session, chapter_id: int, lang_code: str) -> bool:
    row = db_get_translation(db, chapter_id, lang_code)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
#
# ---------- Chapter (endpoints) ----------

@router.get("/", response_model=list[ChapterOut])
def list_chapters(
    board_lov_id: Optional[int] = Query(None),
    class_lov_id: Optional[int] = Query(None),
    subject_lov_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Left-menu use case: pass board/class/subject to filter to the student's own list."""
    return db_get_chapters(db, board_lov_id, class_lov_id, subject_lov_id)


@router.get("/{chapter_id}", response_model=ChapterWithSubchapters)
def get_chapter(chapter_id: int, db: Session = Depends(get_db)):
    chapter = db_get_chapter_with_subchapters(db, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.post("/", response_model=ChapterOut, status_code=201)
def create_chapter(payload: ChapterCreate, db: Session = Depends(get_db)):
    return db_create_chapter(db, payload)


@router.put("/{chapter_id}", response_model=ChapterOut)
def update_chapter(chapter_id: int, payload: ChapterUpdate, db: Session = Depends(get_db)):
    chapter = db_update_chapter(db, chapter_id, payload)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.delete("/{chapter_id}", status_code=204)
def delete_chapter(chapter_id: int, db: Session = Depends(get_db)):
    if not db_delete_chapter(db, chapter_id):
        raise HTTPException(status_code=404, detail="Chapter not found")





# ---------- Translation (endpoints) ----------

@router.get("/{chapter_id}/translations", response_model=list[ChapterTranslationOut])
def list_chapter_translations(chapter_id: int, db: Session = Depends(get_db)):
    return db_list_translations(db, chapter_id)


@router.get("/{chapter_id}/translations/{lang_code}", response_model=ChapterTranslationOut)
def get_chapter_translation(chapter_id: int, lang_code: str, db: Session = Depends(get_db)):
    row = db_get_translation(db, chapter_id, lang_code)
    if row is None:
        raise HTTPException(status_code=404, detail="Translation not found")
    return row


@router.put("/{chapter_id}/translations/{lang_code}", response_model=ChapterTranslationOut)
def upsert_chapter_translation(
    chapter_id: int, lang_code: str, payload: ChapterTranslationIn, db: Session = Depends(get_db)
):
    if db_get_chapter(db, chapter_id) is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return db_upsert_translation(db, chapter_id, lang_code, payload)


@router.delete("/{chapter_id}/translations/{lang_code}", status_code=204)
def delete_chapter_translation(chapter_id: int, lang_code: str, db: Session = Depends(get_db)):
    if not db_delete_translation(db, chapter_id, lang_code):
        raise HTTPException(status_code=404, detail="Translation not found")
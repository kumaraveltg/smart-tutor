"""
app/routers/question_images.py  -  table model + API for question images.

Your Question table uses question_id as its primary key and stores class_id,
subject_id and chapter_id (not names), so the folder is built from those ids:
    IMAGE_BASE_PATH / c<class_id> / s<subject_id> / ch<chapter_id> / ex_<exercise> / file
e.g.  c10/s3/ch25/ex_2.1/q5.png
Ids never change when a class/subject/chapter is renamed, so images stay valid.
(To use readable names instead, only edit folder_from_ids() below.)
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import Session

from app.database import Base, get_db           # <-- adjust if Base lives elsewhere
from app.models import Question
from app import image_service as imgs


class QuestionImage(Base):
    __tablename__ = "st_question_images"
    __table_args__ = {"schema": Question.__table__.schema}   # same schema as st_questions

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(
        Integer, ForeignKey(Question.__table__.c.question_id, ondelete="CASCADE"),
        nullable=False, index=True)
    rel_path = Column(String(300), nullable=False)   # c10/s3/ch25/ex_2.1/q5.png
    sort_order = Column(Integer, nullable=False, default=0)


# ---- folder rule ----------------------------------------------------------
def folder_from_ids(class_id, subject_id, chapter_id, exercise_no) -> str:
    return imgs.folder_for(f"c{class_id}", f"s{subject_id}", f"ch{chapter_id}", exercise_no)


def question_folder(q) -> str:
    return folder_from_ids(q.class_id, q.subject_id, q.chapter_id, q.exercise_no)


def image_dict(img: QuestionImage) -> dict:
    return {"id": img.id, "path": img.rel_path,
            "url": f"/images/{img.rel_path}",
            "missing": not imgs.exists(img.rel_path),
            "sort_order": img.sort_order}


router = APIRouter(prefix="/admin", tags=["Question images"])


@router.get("/questions/{question_id}/images")
def list_images(question_id: int, db: Session = Depends(get_db)):
    rows = (db.query(QuestionImage).filter_by(question_id=question_id)
            .order_by(QuestionImage.sort_order, QuestionImage.id).all())
    return [image_dict(r) for r in rows]


@router.post("/questions/{question_id}/images")
async def upload_images(question_id: int, files: list[UploadFile] = File(...),
                        db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")
    folder = question_folder(q)
    count = db.query(QuestionImage).filter_by(question_id=question_id).count()
    saved, saved_paths = [], []
    try:
        for i, f in enumerate(files):
            rel = imgs.save_upload(f.file, f.filename, folder)
            saved_paths.append(rel)
            row = QuestionImage(question_id=question_id, rel_path=rel,
                                sort_order=count + i)
            db.add(row)
            saved.append(row)
        db.commit()
    except imgs.ImageError as e:
        db.rollback()
        for p in saved_paths:
            imgs.delete_file(p)
        raise HTTPException(400, str(e))
    for r in saved:
        db.refresh(r)
    return [image_dict(r) for r in saved]


@router.delete("/question-images/{image_id}", status_code=204)
def delete_image(image_id: int, db: Session = Depends(get_db)):
    row = db.get(QuestionImage, image_id)
    if not row:
        raise HTTPException(404, "Image not found")
    path = row.rel_path
    db.delete(row)
    db.commit()
    imgs.delete_file(path)


@router.put("/questions/{question_id}/images/order")
def reorder_images(question_id: int, ids: list[int],
                   db: Session = Depends(get_db)):
    rows = {r.id: r for r in
            db.query(QuestionImage).filter_by(question_id=question_id).all()}
    for pos, image_id in enumerate(ids):
        if image_id in rows:
            rows[image_id].sort_order = pos
    db.commit()
    return {"ok": True}


# ---- helpers used by questions.py ----------------------------------------
def move_question_images(db: Session, question_id: int, new_folder: str):
    """
    Move a question's image files to new_folder and update the saved paths
    (the DB change is committed by the caller). Returns (old_paths, new_paths)
    so the caller can move the files back if the commit fails.
    Raises HTTPException(409) when a file cannot be moved.
    """
    rows = (db.query(QuestionImage).filter_by(question_id=question_id)
            .order_by(QuestionImage.sort_order).all())
    if not rows:
        return [], []
    old_paths = [r.rel_path for r in rows]
    try:
        new_paths = imgs.move_images(old_paths, new_folder)
    except imgs.ImageError as e:
        raise HTTPException(409, str(e))
    for r, p in zip(rows, new_paths):
        r.rel_path = p
    return old_paths, new_paths


def delete_question_images(db: Session, question_id: int) -> list[str]:
    """Remove the image rows of a question; returns file paths to delete after commit."""
    rows = db.query(QuestionImage).filter_by(question_id=question_id).all()
    paths = [r.rel_path for r in rows]
    for r in rows:
        db.delete(r)
    return paths


def add_imported_images(db: Session, question_id: int, folder: str, cell) -> list[str]:
    """Excel import: store only the image names; returns warnings (missing files)."""
    paths, warnings = imgs.rel_paths_for_import(folder, cell)
    for i, p in enumerate(paths):
        db.add(QuestionImage(question_id=question_id, rel_path=p, sort_order=i))
    return warnings

"""
Question image handling for SmartTutor (backend part).

Folder rule:  IMAGE_BASE_PATH / class / subject / chapter / exercise / file
The DB stores only the RELATIVE path, e.g.  10/maths/ch02/ex_2.1/q5.png
so changing IMAGE_BASE_PATH never breaks the saved data.

Put this file in app/ (next to your routers folder) and import from it.
"""
import os
import re
import shutil
from pathlib import Path, PurePosixPath

from PIL import Image

# ---- settings -------------------------------------------------------------
# Change this one value (or set the environment variable) per machine/server.
from app.config import settings  # <-- adjust the module name if your Settings class lives elsewhere

IMAGE_BASE_PATH = Path(settings.image_base_path)
MAX_WIDTH = 800
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class ImageError(Exception):
    """Raised for problems the user should see (bad file, name clash...)."""


# ---- names and folders ----------------------------------------------------
def slug(value) -> str:
    """lowercase, no spaces, safe characters only: 'Ex 2.1' -> 'ex_2.1'"""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_.\-]", "", text)
    return text.strip("._") or "x"


def safe_filename(name: str) -> str:
    stem, ext = os.path.splitext(os.path.basename(name))
    ext = ext.lower()
    if ext not in ALLOWED_EXT:
        raise ImageError(f"File type {ext or '(none)'} is not allowed")
    return slug(stem) + ext


def folder_for(class_, subject, chapter, exercise) -> str:
    """Relative folder (posix style) for one question's images."""
    if exercise is None or not str(exercise).strip():
        ex = "no_exercise"
    else:
        ex = slug(exercise)
        if not ex.startswith("ex"):
            ex = f"ex_{ex}"
    return str(PurePosixPath(slug(class_), slug(subject), slug(chapter), ex))


def full_path(rel_path: str) -> Path:
    """Relative DB path -> real file path. Blocks '..' tricks."""
    p = (IMAGE_BASE_PATH / rel_path).resolve()
    if IMAGE_BASE_PATH.resolve() not in p.parents:
        raise ImageError("Invalid image path")
    return p


def exists(rel_path: str) -> bool:
    try:
        return full_path(rel_path).is_file()
    except ImageError:
        return False


# ---- save (drag and drop upload) ------------------------------------------
def save_upload(file_obj, original_name: str, folder: str) -> str:
    """
    Save one dropped image, resized to MAX_WIDTH. Returns the relative path.
    If the file name already exists in that folder, a number is added
    (q5.png -> q5_2.png) so nothing is overwritten.
    """
    name = safe_filename(original_name)
    target_dir = full_path(folder)
    target_dir.mkdir(parents=True, exist_ok=True)

    stem, ext = os.path.splitext(name)
    target = target_dir / name
    n = 2
    while target.exists():
        target = target_dir / f"{stem}_{n}{ext}"
        n += 1

    try:
        img = Image.open(file_obj)
        img.load()
    except Exception:
        raise ImageError("This file is not a valid image")

    if img.width > MAX_WIDTH:
        h = round(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, h), Image.LANCZOS)

    if target.suffix.lower() in (".jpg", ".jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(target, optimize=True)
    return str(PurePosixPath(folder, target.name))


# ---- import helper (Excel 'images' column) --------------------------------
def parse_image_names(cell) -> list[str]:
    """'fig1.png, fig2.png' -> ['fig1.png', 'fig2.png']"""
    if cell is None:
        return []
    return [safe_filename(x) for x in str(cell).split(",") if x.strip()]


def rel_paths_for_import(folder: str, cell) -> tuple[list[str], list[str]]:
    """
    Returns (paths_to_save, warnings). Only names are stored: no file is
    copied. Missing files give a warning but the question is still saved.
    """
    paths, warnings = [], []
    try:
        names = parse_image_names(cell)
    except ImageError as e:
        return [], [str(e)]
    for name in names:
        rel = str(PurePosixPath(folder, name))
        paths.append(rel)
        if not exists(rel):
            warnings.append(f"image not found: {rel}")
    return paths, warnings


# ---- move when class/subject/chapter/exercise is edited -------------------
def move_images(old_paths: list[str], new_folder: str) -> list[str]:
    """
    Move files to new_folder. Returns the new relative paths (same order).
    Never overwrites. If anything fails, files already moved are put back
    and ImageError is raised, so the caller must cancel the DB save.
    Missing source files are skipped (the path is still updated).
    """
    new_dir = full_path(new_folder)
    plan = []  # (old_full, new_full, new_rel)
    for rel in old_paths:
        new_rel = str(PurePosixPath(new_folder, PurePosixPath(rel).name))
        if new_rel == rel:
            plan.append((None, None, new_rel))
            continue
        new_full = full_path(new_rel)
        if new_full.exists():
            raise ImageError(f"Cannot move: {new_rel} already exists")
        plan.append((full_path(rel), new_full, new_rel))

    moved = []
    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        for old_full, new_full, _ in plan:
            if old_full is None or not old_full.is_file():
                continue
            shutil.move(str(old_full), str(new_full))
            moved.append((old_full, new_full))
    except Exception as e:
        for old_full, new_full in reversed(moved):  # roll back
            try:
                shutil.move(str(new_full), str(old_full))
            except Exception:
                pass
        raise ImageError(f"Moving images failed: {e}")

    for rel in old_paths:  # tidy empty old folders
        _remove_empty_parents(full_path(rel).parent)
    return [p[2] for p in plan]


def _remove_empty_parents(folder: Path):
    base = IMAGE_BASE_PATH.resolve()
    folder = folder.resolve()
    while folder != base and base in folder.parents:
        try:
            folder.rmdir()  # only works when empty
        except OSError:
            break
        folder = folder.parent


def delete_file(rel_path: str):
    try:
        p = full_path(rel_path)
        if p.is_file():
            p.unlink()
            _remove_empty_parents(p.parent)
    except ImageError:
        pass
